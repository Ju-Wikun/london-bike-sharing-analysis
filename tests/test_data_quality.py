from __future__ import annotations

import sys
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.build_warehouse import build_database  # noqa: E402
from src.preprocess_london import _read_single_tfl_csv  # noqa: E402


def test_build_and_core_quality(tmp_path: Path) -> None:
    db_path = tmp_path / "test.duckdb"
    export_dir = tmp_path / "results"
    rows = build_database(db_path, export_dir)

    assert all(row[-1] == "PASS" for row in rows)
    assert (export_dir / "01_kpi_overview.csv").exists()
    assert (export_dir / "validation_summary.csv").exists()

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        assert conn.execute("SELECT COUNT(*) FROM fact_system_hourly").fetchone()[0] == 52526
        assert conn.execute("SELECT SUM(ride_count) FROM fact_system_hourly").fetchone()[0] == 58865471
        assert conn.execute("SELECT COUNT(*) FROM analytics_hourly WHERE temperature_c IS NULL").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM source_batch").fetchone()[0] == 242
        assert conn.execute("SELECT SUM(invalid_start_rows) FROM source_batch").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM analytics_hourly_quality").fetchone()[0] == 52506
        assert conn.execute("SELECT SUM(ride_count) FROM analytics_hourly_quality").fetchone()[0] == 58842971
        assert conn.execute("SELECT MIN(ride_count) FROM fact_system_hourly").fetchone()[0] >= 0
        missing_clock_hours = conn.execute(
            """
            SELECT COUNT(*)
            FROM fact_weather_hourly w
            LEFT JOIN fact_system_hourly r ON r.ts = w.ts
            WHERE r.ts IS NULL
            """
        ).fetchone()[0]
        assert missing_clock_hours == 82
        coverage_counts = dict(
            conn.execute(
                """
                SELECT classification, COUNT(*)
                FROM hour_coverage_exception
                GROUP BY classification
                """
            ).fetchall()
        )
        assert coverage_counts == {
            "confirmed_zero_trip_hour": 21,
            "source_gap": 55,
            "nonexistent_local_hour": 6,
        }
        assert conn.execute("SELECT COUNT(*) FROM dim_station").fetchone()[0] == 888
        assert conn.execute("SELECT COUNT(*) FROM fact_od_flow").fetchone()[0] == 632144
        assert conn.execute("SELECT SUM(trip_count) FROM fact_od_flow").fetchone()[0] == 58311048
        assert conn.execute(
            "SELECT SUM(trip_count) FROM fact_od_flow WHERE same_station"
        ).fetchone()[0] == 2392658
        assert conn.execute(
            "SELECT SUM(trip_count) FROM fact_od_flow WHERE NOT same_station"
        ).fetchone()[0] == 55918390
        assert conn.execute("SELECT SUM(outflow) FROM fact_station_period").fetchone()[0] == 58311048
        assert conn.execute("SELECT SUM(inflow) FROM fact_station_period").fetchone()[0] == 58311048
        assert conn.execute(
            "SELECT COUNT(*) FROM station_alias WHERE requires_review"
        ).fetchone()[0] == 97
    finally:
        conn.close()


def test_mixed_tfl_dates_keep_day_month_order(tmp_path: Path) -> None:
    source = tmp_path / "mixed_dates.csv"
    source.write_text(
        "Number,Start date,End date,Total duration (ms)\n"
        "1,2024-01-31 23:59,2024-02-01 00:04,300000\n"
        "2,14/08/2024 23:59,15/08/2024 00:04,300000\n"
        "3,01/08/2024 08:00,01/08/2024 08:05,300000\n",
        encoding="utf-8",
    )

    parsed = _read_single_tfl_csv(source)

    assert parsed["start_dt"].dt.strftime("%Y-%m-%d %H:%M").tolist() == [
        "2024-01-31 23:59",
        "2024-08-14 23:59",
        "2024-08-01 08:00",
    ]
