from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocess_london import (  # noqa: E402
    _filter_tfl_files_by_year,
    _read_single_tfl_csv,
)


INCOMPLETE_DATES = {
    "2022-09-10": "Official batch contains only 4 trip records for the date.",
    "2022-09-11": "Official batch contains only 7 trip records for the date.",
    "2022-09-12": "Official batch starts at 05:02; hours 00:00-04:59 are absent.",
    "2025-08-05": "Official batch contains only 188 trip records with large intraday gaps.",
}

DST_SPRING_FORWARD_HOURS = {
    f"{year}-{date} 01:00:00"
    for year, date in [
        (2020, "03-29"),
        (2021, "03-28"),
        (2022, "03-27"),
        (2023, "03-26"),
        (2024, "03-31"),
        (2025, "03-30"),
    ]
}


def detect_format_profile(path: Path) -> str:
    try:
        sample = pd.read_csv(path, nrows=200, encoding="utf-8", on_bad_lines="skip")
    except UnicodeDecodeError:
        sample = pd.read_csv(path, nrows=200, encoding="latin-1", on_bad_lines="skip")
    date_column = "Start date" if "Start date" in sample.columns else "Start Date"
    values = sample[date_column].dropna().astype(str)
    has_iso = values.str.match(r"^\d{4}-").any()
    has_day_first = values.str.match(r"^\d{1,2}/\d{1,2}/\d{4}").any()
    if has_iso and has_day_first:
        return "mixed_iso_day_first"
    if has_iso:
        return "iso"
    if has_day_first:
        return "day_first"
    return "unknown"


def audit_batches(raw_dir: Path) -> pd.DataFrame:
    rows = []
    files = _filter_tfl_files_by_year(raw_dir, 2020, 2025)
    for index, path in enumerate(files, start=1):
        frame = _read_single_tfl_csv(path)
        valid = frame["start_dt"].notna()
        valid_dates = frame.loc[valid, "start_dt"]
        rows.append(
            {
                "source_file": path.name,
                "file_size_bytes": path.stat().st_size,
                "format_profile": detect_format_profile(path),
                "parsed_rows": len(frame),
                "valid_start_rows": int(valid.sum()),
                "invalid_start_rows": int((~valid).sum()),
                "min_start": valid_dates.min(),
                "max_start": valid_dates.max(),
                "distinct_dates": valid_dates.dt.date.nunique(),
                "audit_status": "PASS" if valid.all() else "REVIEW",
            }
        )
        if index % 20 == 0:
            print(f"Audited {index}/{len(files)} source files")
    return pd.DataFrame(rows)


def build_coverage_exceptions(project_root: Path) -> pd.DataFrame:
    rides = pd.read_csv(
        project_root / "data" / "processed" / "system_hourly.csv",
        parse_dates=["ts"],
    )
    weather = pd.read_csv(
        project_root / "data" / "reference" / "weather_hourly.csv",
        parse_dates=["timestamp"],
    )
    missing = weather.loc[~weather["timestamp"].isin(rides["ts"]), ["timestamp"]].copy()

    def classify(timestamp: pd.Timestamp) -> tuple[str, str]:
        timestamp_text = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        date_text = timestamp.strftime("%Y-%m-%d")
        if timestamp_text in DST_SPRING_FORWARD_HOURS:
            return (
                "nonexistent_local_hour",
                "Europe/London spring-forward hour does not exist in local trip time.",
            )
        if date_text in INCOMPLETE_DATES:
            return "source_gap", INCOMPLETE_DATES[date_text]
        return (
            "confirmed_zero_trip_hour",
            "No trip rows in an otherwise complete official source batch.",
        )

    classified = missing["timestamp"].apply(classify)
    missing[["classification", "reason"]] = pd.DataFrame(
        classified.tolist(), index=missing.index
    )
    missing = missing.rename(columns={"timestamp": "ts"})
    return missing.sort_values("ts").reset_index(drop=True)


def build_known_anomalies(
    project_root: Path, coverage: pd.DataFrame
) -> pd.DataFrame:
    rides = pd.read_csv(
        project_root / "data" / "processed" / "system_hourly.csv",
        parse_dates=["ts"],
    )
    rides["date"] = rides["ts"].dt.strftime("%Y-%m-%d")
    rows = []
    for date_text, note in INCOMPLETE_DATES.items():
        daily = rides[rides["date"] == date_text]
        missing_hours = coverage[
            (coverage["ts"].dt.strftime("%Y-%m-%d") == date_text)
            & (coverage["classification"] == "source_gap")
        ]
        rows.append(
            {
                "date": date_text,
                "quality_status": "incomplete_source",
                "observed_trip_records": int(daily["cnt"].sum()),
                "observed_hours": len(daily),
                "missing_clock_hours": len(missing_hours),
                "reason": note,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()

    output_dir = args.project_root / "data" / "metadata"
    output_dir.mkdir(parents=True, exist_ok=True)

    batches = audit_batches(args.raw_dir)
    coverage = build_coverage_exceptions(args.project_root)
    anomalies = build_known_anomalies(args.project_root, coverage)

    batches.to_csv(output_dir / "source_batch_audit.csv", index=False, encoding="utf-8-sig")
    coverage.to_csv(
        output_dir / "hour_coverage_exceptions.csv", index=False, encoding="utf-8-sig"
    )
    anomalies.to_csv(
        output_dir / "known_data_anomalies.csv", index=False, encoding="utf-8-sig"
    )

    print(f"Source files: {len(batches)}")
    print(f"Valid trip rows: {batches['valid_start_rows'].sum():,}")
    print(f"Invalid start rows: {batches['invalid_start_rows'].sum():,}")
    print("Coverage classifications:")
    print(coverage["classification"].value_counts().to_string())


if __name__ == "__main__":
    main()
