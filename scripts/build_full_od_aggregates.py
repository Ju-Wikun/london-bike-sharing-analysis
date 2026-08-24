from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re
import sys
import unicodedata

import duckdb
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocess_london import (  # noqa: E402
    _filter_tfl_files_by_year,
    _load_bank_holidays,
    _read_single_tfl_csv,
)


def normalize_station_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def station_key(normalized_name: str) -> str:
    return hashlib.sha1(normalized_name.encode("utf-8")).hexdigest()[:16]


def normalize_station_id(values: pd.Series) -> pd.Series:
    return (
        values.astype("string")
        .fillna("")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def update_numeric_accumulator(
    accumulator: dict[tuple, np.ndarray], grouped: pd.DataFrame, key_columns: list[str]
) -> None:
    value_columns = [column for column in grouped.columns if column not in key_columns]
    for row in grouped.itertuples(index=False, name=None):
        key = tuple(row[: len(key_columns)])
        values = np.asarray(row[len(key_columns) :], dtype=np.float64)
        if key in accumulator:
            accumulator[key] += values
        else:
            accumulator[key] = values


def accumulator_frame(
    accumulator: dict[tuple, np.ndarray], key_columns: list[str], value_columns: list[str]
) -> pd.DataFrame:
    rows = [(*key, *values.tolist()) for key, values in accumulator.items()]
    return pd.DataFrame(rows, columns=[*key_columns, *value_columns])


def write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect()
    try:
        connection.register("frame_to_write", frame)
        safe_path = str(path.resolve()).replace("\\", "/").replace("'", "''")
        connection.execute(
            f"COPY frame_to_write TO '{safe_path}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD)"
        )
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    incomplete = pd.read_csv(
        args.project_root / "data" / "metadata" / "known_data_anomalies.csv",
        parse_dates=["date"],
    )
    incomplete_dates = set(incomplete["date"].dt.date)
    holidays = _load_bank_holidays(
        args.project_root / "data" / "reference" / "bank_holidays.csv"
    )

    route_acc: dict[tuple, np.ndarray] = {}
    station_period_acc: dict[tuple, np.ndarray] = {}
    same_station_acc: dict[tuple, np.ndarray] = {}
    alias_acc: dict[tuple, list] = {}
    display_names: dict[str, Counter] = defaultdict(Counter)
    normalized_by_key: dict[str, str] = {}

    audit = {
        "source_rows": 0,
        "valid_duration_rows": 0,
        "excluded_incomplete_date_rows": 0,
        "od_valid_rows": 0,
    }

    files = _filter_tfl_files_by_year(args.raw_dir, 2020, 2025)
    for index, path in enumerate(files, start=1):
        frame = _read_single_tfl_csv(path)
        audit["source_rows"] += len(frame)

        if "start_station" not in frame.columns or "end_station" not in frame.columns:
            print(f"Skipped station aggregation for missing name columns: {path.name}")
            continue
        if "start_station_id" not in frame.columns:
            frame["start_station_id"] = ""
        if "end_station_id" not in frame.columns:
            frame["end_station_id"] = ""

        frame["duration_sec"] = pd.to_numeric(frame["duration_sec"], errors="coerce")
        frame = frame.dropna(subset=["start_dt", "duration_sec"])
        frame = frame[
            (frame["duration_sec"] >= 60) & (frame["duration_sec"] <= 10800)
        ].copy()
        audit["valid_duration_rows"] += len(frame)

        is_incomplete = frame["start_dt"].dt.date.isin(incomplete_dates)
        audit["excluded_incomplete_date_rows"] += int(is_incomplete.sum())
        frame = frame[~is_incomplete]
        frame = frame.dropna(subset=["start_station", "end_station"]).copy()
        audit["od_valid_rows"] += len(frame)

        names = pd.unique(
            pd.concat([frame["start_station"], frame["end_station"]], ignore_index=True)
        )
        name_lookup = {str(name): normalize_station_name(name) for name in names}
        key_lookup = {name: station_key(normalized) for name, normalized in name_lookup.items()}

        frame["start_name_raw"] = frame["start_station"].astype(str)
        frame["end_name_raw"] = frame["end_station"].astype(str)
        frame["start_normalized"] = frame["start_name_raw"].map(name_lookup)
        frame["end_normalized"] = frame["end_name_raw"].map(name_lookup)
        frame["start_key"] = frame["start_name_raw"].map(key_lookup)
        frame["end_key"] = frame["end_name_raw"].map(key_lookup)
        frame["start_source_id"] = normalize_station_id(frame["start_station_id"])
        frame["end_source_id"] = normalize_station_id(frame["end_station_id"])
        frame["duration_min"] = frame["duration_sec"] / 60.0
        frame["same_station"] = frame["start_key"] == frame["end_key"]
        frame["duration_le_3m"] = frame["duration_min"] <= 3
        frame["duration_3_15m"] = (
            (frame["duration_min"] > 3) & (frame["duration_min"] <= 15)
        )
        frame["duration_gt_15m"] = frame["duration_min"] > 15
        frame["hour_of_day"] = frame["start_dt"].dt.hour
        frame["day_type"] = np.where(
            frame["start_dt"].dt.weekday.isin([5, 6])
            | frame["start_dt"].dt.date.isin(holidays),
            "non_workday",
            "workday",
        )

        route_grouped = (
            frame.groupby(["start_key", "end_key", "same_station"], as_index=False)
            .agg(
                trip_count=("start_dt", "size"),
                duration_sum_min=("duration_min", "sum"),
                duration_le_3m_count=("duration_le_3m", "sum"),
                duration_3_15m_count=("duration_3_15m", "sum"),
                duration_gt_15m_count=("duration_gt_15m", "sum"),
            )
        )
        update_numeric_accumulator(
            route_acc,
            route_grouped,
            ["start_key", "end_key", "same_station"],
        )

        departures = (
            frame.groupby(["start_key", "day_type", "hour_of_day"], as_index=False)
            .size()
            .rename(columns={"start_key": "station_key", "size": "outflow"})
        )
        departures["inflow"] = 0
        arrivals = (
            frame.groupby(["end_key", "day_type", "hour_of_day"], as_index=False)
            .size()
            .rename(columns={"end_key": "station_key", "size": "inflow"})
        )
        arrivals["outflow"] = 0
        station_grouped = (
            pd.concat([departures, arrivals], ignore_index=True)
            .groupby(["station_key", "day_type", "hour_of_day"], as_index=False)
            .agg(outflow=("outflow", "sum"), inflow=("inflow", "sum"))
        )
        update_numeric_accumulator(
            station_period_acc,
            station_grouped,
            ["station_key", "day_type", "hour_of_day"],
        )

        same = frame[frame["same_station"]]
        if not same.empty:
            same_grouped = (
                same.groupby(["start_key", "day_type", "hour_of_day"], as_index=False)
                .agg(
                    trip_count=("start_dt", "size"),
                    duration_sum_min=("duration_min", "sum"),
                    duration_le_3m_count=("duration_le_3m", "sum"),
                    duration_3_15m_count=("duration_3_15m", "sum"),
                    duration_gt_15m_count=("duration_gt_15m", "sum"),
                )
                .rename(columns={"start_key": "station_key"})
            )
            update_numeric_accumulator(
                same_station_acc,
                same_grouped,
                ["station_key", "day_type", "hour_of_day"],
            )

        endpoint_frames = [
            frame[["start_key", "start_normalized", "start_source_id", "start_name_raw", "start_dt"]]
            .rename(
                columns={
                    "start_key": "station_key",
                    "start_normalized": "normalized_name",
                    "start_source_id": "source_station_id",
                    "start_name_raw": "original_name",
                    "start_dt": "observed_at",
                }
            ),
            frame[["end_key", "end_normalized", "end_source_id", "end_name_raw", "start_dt"]]
            .rename(
                columns={
                    "end_key": "station_key",
                    "end_normalized": "normalized_name",
                    "end_source_id": "source_station_id",
                    "end_name_raw": "original_name",
                    "start_dt": "observed_at",
                }
            ),
        ]
        endpoints = pd.concat(endpoint_frames, ignore_index=True)
        alias_grouped = (
            endpoints.groupby(
                ["station_key", "normalized_name", "source_station_id", "original_name"],
                as_index=False,
            )
            .agg(
                endpoint_mentions=("observed_at", "size"),
                first_seen=("observed_at", "min"),
                last_seen=("observed_at", "max"),
            )
        )
        for row in alias_grouped.itertuples(index=False):
            key = (
                row.station_key,
                row.normalized_name,
                row.source_station_id,
                row.original_name,
            )
            if key in alias_acc:
                current = alias_acc[key]
                current[0] += int(row.endpoint_mentions)
                current[1] = min(current[1], row.first_seen)
                current[2] = max(current[2], row.last_seen)
            else:
                alias_acc[key] = [
                    int(row.endpoint_mentions),
                    row.first_seen,
                    row.last_seen,
                ]
            display_names[row.station_key][row.original_name] += int(row.endpoint_mentions)
            normalized_by_key[row.station_key] = row.normalized_name

        if index % 20 == 0:
            print(f"Aggregated {index}/{len(files)} source files")

    route = accumulator_frame(
        route_acc,
        ["start_key", "end_key", "same_station"],
        [
            "trip_count",
            "duration_sum_min",
            "duration_le_3m_count",
            "duration_3_15m_count",
            "duration_gt_15m_count",
        ],
    )
    count_columns = [
        "trip_count",
        "duration_le_3m_count",
        "duration_3_15m_count",
        "duration_gt_15m_count",
    ]
    route[count_columns] = route[count_columns].astype("int64")
    route["avg_duration_min"] = route["duration_sum_min"] / route["trip_count"]

    station_period = accumulator_frame(
        station_period_acc,
        ["station_key", "day_type", "hour_of_day"],
        ["outflow", "inflow"],
    )
    station_period[["outflow", "inflow"]] = station_period[
        ["outflow", "inflow"]
    ].astype("int64")
    station_period["net_inflow"] = station_period["inflow"] - station_period["outflow"]

    same_station = accumulator_frame(
        same_station_acc,
        ["station_key", "day_type", "hour_of_day"],
        [
            "trip_count",
            "duration_sum_min",
            "duration_le_3m_count",
            "duration_3_15m_count",
            "duration_gt_15m_count",
        ],
    )
    same_station[count_columns] = same_station[count_columns].astype("int64")
    same_station["avg_duration_min"] = (
        same_station["duration_sum_min"] / same_station["trip_count"]
    )

    alias_rows = [
        (*key, values[0], values[1], values[2])
        for key, values in alias_acc.items()
    ]
    alias = pd.DataFrame(
        alias_rows,
        columns=[
            "station_key",
            "normalized_name",
            "source_station_id",
            "original_name",
            "endpoint_mentions",
            "first_seen",
            "last_seen",
        ],
    )
    source_id_key_count = (
        alias[alias["source_station_id"] != ""]
        .groupby("source_station_id")["station_key"]
        .nunique()
    )
    alias["source_id_key_count"] = (
        alias["source_station_id"].map(source_id_key_count).fillna(0).astype(int)
    )
    alias["requires_review"] = alias["source_id_key_count"] > 1

    station_rows = []
    for key, name_counter in display_names.items():
        subset = alias[alias["station_key"] == key]
        source_id_count = subset.loc[
            subset["source_station_id"] != "", "source_station_id"
        ].nunique()
        alias_count = subset["original_name"].nunique()
        station_rows.append(
            {
                "station_key": key,
                "canonical_name": name_counter.most_common(1)[0][0],
                "normalized_name": normalized_by_key[key],
                "source_id_count": source_id_count,
                "alias_count": alias_count,
                "first_seen": subset["first_seen"].min(),
                "last_seen": subset["last_seen"].max(),
                "endpoint_mentions": int(subset["endpoint_mentions"].sum()),
                "mapping_status": (
                    "review_source_id_reuse"
                    if subset["requires_review"].any()
                    else "normalized_name_candidate"
                ),
            }
        )
    station = pd.DataFrame(station_rows)

    processed_dir = args.project_root / "data" / "processed" / "od"
    metadata_dir = args.project_root / "data" / "metadata"
    output_dir = args.project_root / "output" / "od_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    write_parquet(route, processed_dir / "fact_od_flow.parquet")
    write_parquet(station_period, processed_dir / "fact_station_period.parquet")
    write_parquet(same_station, processed_dir / "fact_same_station.parquet")
    write_parquet(station, processed_dir / "dim_station.parquet")
    alias.to_csv(metadata_dir / "station_alias_audit.csv", index=False, encoding="utf-8-sig")

    total_trips = int(route["trip_count"].sum())
    same_trips = int(route.loc[route["same_station"], "trip_count"].sum())
    cross = route[~route["same_station"]].sort_values("trip_count", ascending=False)
    cross_trips = int(cross["trip_count"].sum())
    summary = pd.DataFrame(
        [
            ["source_rows", audit["source_rows"]],
            ["valid_duration_rows", audit["valid_duration_rows"]],
            ["excluded_incomplete_date_rows", audit["excluded_incomplete_date_rows"]],
            ["od_valid_rows", audit["od_valid_rows"]],
            ["candidate_stations", len(station)],
            ["od_pairs", len(route)],
            ["cross_od_pairs", len(cross)],
            ["same_station_trips", same_trips],
            ["cross_station_trips", cross_trips],
            ["same_station_rate", same_trips / total_trips],
            ["cross_station_rate", cross_trips / total_trips],
        ],
        columns=["metric", "value"],
    )
    summary.to_csv(output_dir / "summary_metrics.csv", index=False, encoding="utf-8-sig")

    coverage_rows = []
    for n in [10, 20, 50, 100, 500, 1000, 5000]:
        selected = cross.head(n)
        coverage_rows.append(
            {
                "top_n": min(n, len(cross)),
                "trip_count": int(selected["trip_count"].sum()),
                "coverage_rate": selected["trip_count"].sum() / cross_trips,
            }
        )
    pd.DataFrame(coverage_rows).to_csv(
        output_dir / "cross_od_topn_coverage.csv", index=False, encoding="utf-8-sig"
    )

    station_names = station.set_index("station_key")["canonical_name"]
    top_cross = cross.head(100).copy()
    top_cross["start_station"] = top_cross["start_key"].map(station_names)
    top_cross["end_station"] = top_cross["end_key"].map(station_names)
    top_cross.to_csv(output_dir / "top_cross_routes.csv", index=False, encoding="utf-8-sig")

    departures = route.groupby("start_key")["trip_count"].sum()
    self_routes = route[route["same_station"]].copy()
    self_routes["station_name"] = self_routes["start_key"].map(station_names)
    self_routes["departure_count"] = self_routes["start_key"].map(departures)
    self_routes["same_station_rate"] = self_routes["trip_count"] / self_routes["departure_count"]
    self_routes.sort_values("trip_count", ascending=False).head(100).to_csv(
        output_dir / "top_same_station_by_count.csv", index=False, encoding="utf-8-sig"
    )
    self_routes[self_routes["departure_count"] >= 200].sort_values(
        "same_station_rate", ascending=False
    ).head(100).to_csv(
        output_dir / "top_same_station_by_rate.csv", index=False, encoding="utf-8-sig"
    )

    print(summary.to_string(index=False))
    print(f"Wrote OD aggregates to: {processed_dir}")


if __name__ == "__main__":
    main()
