from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .od_dashboard_charts import (
    flow_structure_dashboard,
    station_diagnostics_dashboard,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OD_DIR = PROJECT_ROOT / "data" / "processed" / "od"
DASHBOARD_DIR = PROJECT_ROOT / "dashboards" / "echarts"


def parquet_path(name: str) -> str:
    return str((OD_DIR / name).resolve()).replace("\\", "/").replace("'", "''")


def load_frames() -> dict[str, object]:
    connection = duckdb.connect()
    try:
        routes = connection.execute(
            f"""
            SELECT
                f.*,
                origin.canonical_name AS start_station,
                destination.canonical_name AS end_station
            FROM read_parquet('{parquet_path('fact_od_flow.parquet')}') AS f
            JOIN read_parquet('{parquet_path('dim_station.parquet')}') AS origin
                ON origin.station_key = f.start_key
            JOIN read_parquet('{parquet_path('dim_station.parquet')}') AS destination
                ON destination.station_key = f.end_key
            """
        ).fetchdf()
        station = connection.execute(
            f"SELECT * FROM read_parquet('{parquet_path('dim_station.parquet')}')"
        ).fetchdf()
        station_period = connection.execute(
            f"SELECT * FROM read_parquet('{parquet_path('fact_station_period.parquet')}')"
        ).fetchdf()
        balance = connection.execute(
            f"""
            SELECT
                s.station_key,
                s.canonical_name,
                SUM(f.outflow) AS outflow,
                SUM(f.inflow) AS inflow,
                SUM(f.net_inflow) AS net_inflow,
                SUM(f.outflow + f.inflow) AS throughput
            FROM read_parquet('{parquet_path('fact_station_period.parquet')}') AS f
            JOIN read_parquet('{parquet_path('dim_station.parquet')}') AS s USING (station_key)
            GROUP BY s.station_key, s.canonical_name
            """
        ).fetchdf()
        same_behavior = connection.execute(
            f"""
            WITH departures AS (
                SELECT start_key AS station_key, SUM(trip_count) AS departure_count
                FROM read_parquet('{parquet_path('fact_od_flow.parquet')}')
                GROUP BY start_key
            )
            SELECT
                s.station_key,
                s.canonical_name,
                f.trip_count AS same_station_trips,
                d.departure_count,
                100.0 * f.trip_count / d.departure_count AS same_station_rate_pct,
                f.avg_duration_min
            FROM read_parquet('{parquet_path('fact_od_flow.parquet')}') AS f
            JOIN departures AS d ON d.station_key = f.start_key
            JOIN read_parquet('{parquet_path('dim_station.parquet')}') AS s
                ON s.station_key = f.start_key
            WHERE f.same_station
            """
        ).fetchdf()
        duration = connection.execute(
            f"""
            SELECT
                same_station,
                100.0 * SUM(duration_le_3m_count) / SUM(trip_count) AS duration_le_3m_pct,
                100.0 * SUM(duration_3_15m_count) / SUM(trip_count) AS duration_3_15m_pct,
                100.0 * SUM(duration_gt_15m_count) / SUM(trip_count) AS duration_gt_15m_pct
            FROM read_parquet('{parquet_path('fact_od_flow.parquet')}')
            GROUP BY same_station
            ORDER BY same_station
            """
        ).fetchdf()
    finally:
        connection.close()

    summary = pd.read_csv(PROJECT_ROOT / "output" / "od_analysis" / "summary_metrics.csv")
    metrics = dict(zip(summary["metric"], summary["value"]))
    coverage = pd.read_csv(
        PROJECT_ROOT / "output" / "od_analysis" / "cross_od_topn_coverage.csv"
    )
    return {
        "routes": routes,
        "station": station,
        "station_period": station_period,
        "balance": balance,
        "same_behavior": same_behavior,
        "duration": duration,
        "metrics": metrics,
        "coverage": coverage,
    }


def main() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    frames = load_frames()
    flow_path = DASHBOARD_DIR / "echarts_04_flow_structure.html"
    diagnostics_path = DASHBOARD_DIR / "echarts_05_station_diagnostics.html"

    flow_structure_dashboard(
        frames["metrics"], frames["routes"], frames["coverage"], flow_path
    )
    station = frames["station"]
    station_diagnostics_dashboard(
        frames["balance"],
        frames["station_period"],
        frames["same_behavior"],
        frames["duration"],
        station_count=len(station),
        review_station_count=int(
            (station["mapping_status"] == "review_source_id_reuse").sum()
        ),
        output_path=diagnostics_path,
    )
    print(f"Rendered: {flow_path}")
    print(f"Rendered: {diagnostics_path}")


if __name__ == "__main__":
    main()
