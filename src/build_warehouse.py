from __future__ import annotations

import csv
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SCHEMA_PATH = PROJECT_ROOT / "warehouse" / "schema.sql"
SQL_DIR = PROJECT_ROOT / "sql"
DEFAULT_DB_PATH = PROJECT_ROOT / "output" / "london_bike.duckdb"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "output" / "query_results"


def sql_path(path: Path) -> str:
    """Return a DuckDB-safe string literal for a local path."""
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def load_sources(conn: duckdb.DuckDBPyConnection) -> None:
    rides = sql_path(DATA_DIR / "processed" / "system_hourly.csv")
    weather = sql_path(DATA_DIR / "reference" / "weather_hourly.csv")
    holidays = sql_path(DATA_DIR / "reference" / "bank_holidays.csv")
    batches = sql_path(DATA_DIR / "metadata" / "source_batch_audit.csv")
    coverage = sql_path(DATA_DIR / "metadata" / "hour_coverage_exceptions.csv")
    anomalies = sql_path(DATA_DIR / "metadata" / "known_data_anomalies.csv")

    conn.execute(
        f"""
        INSERT INTO fact_system_hourly
        SELECT CAST(ts AS TIMESTAMP), CAST(cnt AS BIGINT)
        FROM read_csv_auto('{rides}', header = true)
        WHERE CAST(ts AS DATE) BETWEEN DATE '2020-01-01' AND DATE '2025-12-31'
        """
    )
    conn.execute(
        f"""
        INSERT INTO source_batch
        SELECT
            source_file,
            CAST(file_size_bytes AS BIGINT),
            format_profile,
            CAST(parsed_rows AS BIGINT),
            CAST(valid_start_rows AS BIGINT),
            CAST(invalid_start_rows AS BIGINT),
            CAST(min_start AS TIMESTAMP),
            CAST(max_start AS TIMESTAMP),
            CAST(distinct_dates AS INTEGER),
            audit_status
        FROM read_csv_auto('{batches}', header = true)
        """
    )
    conn.execute(
        f"""
        INSERT INTO hour_coverage_exception
        SELECT CAST(ts AS TIMESTAMP), classification, reason
        FROM read_csv_auto('{coverage}', header = true)
        """
    )
    conn.execute(
        f"""
        INSERT INTO known_data_anomaly
        SELECT
            CAST(date AS DATE),
            quality_status,
            CAST(observed_trip_records AS BIGINT),
            CAST(observed_hours AS INTEGER),
            CAST(missing_clock_hours AS INTEGER),
            reason
        FROM read_csv_auto('{anomalies}', header = true)
        """
    )
    conn.execute(
        f"""
        INSERT INTO fact_weather_hourly
        SELECT
            CAST(timestamp AS TIMESTAMP),
            CAST(temperature_2m AS DOUBLE),
            CAST(relative_humidity_2m AS DOUBLE),
            CAST(precipitation AS DOUBLE),
            CAST(wind_speed_10m AS DOUBLE),
            CAST(weather_code AS INTEGER)
        FROM read_csv_auto('{weather}', header = true)
        WHERE CAST(timestamp AS DATE) BETWEEN DATE '2020-01-01' AND DATE '2025-12-31'
        """
    )
    conn.execute(
        f"""
        INSERT INTO dim_holiday
        SELECT
            region,
            title,
            CAST(date AS DATE),
            notes,
            CAST(bunting AS BOOLEAN)
        FROM read_csv_auto('{holidays}', header = true)
        """
    )
    conn.execute(
        """
        INSERT INTO dim_date
        WITH calendar AS (
            SELECT CAST(day AS DATE) AS date_key
            FROM generate_series(
                DATE '2020-01-01', DATE '2025-12-31', INTERVAL 1 DAY
            ) AS dates(day)
        ), england_wales_holidays AS (
            SELECT DISTINCT holiday_date
            FROM dim_holiday
            WHERE region = 'england-and-wales'
        )
        SELECT
            c.date_key,
            year(c.date_key),
            month(c.date_key),
            day(c.date_key),
            isodow(c.date_key) - 1,
            dayname(c.date_key),
            isodow(c.date_key) >= 6,
            h.holiday_date IS NOT NULL,
            CASE
                WHEN isodow(c.date_key) >= 6 OR h.holiday_date IS NOT NULL
                THEN 'non_workday'
                ELSE 'workday'
            END,
            COALESCE(a.quality_status, 'complete'),
            a.reason
        FROM calendar AS c
        LEFT JOIN england_wales_holidays AS h
            ON h.holiday_date = c.date_key
        LEFT JOIN known_data_anomaly AS a
            ON a.anomaly_date = c.date_key
        ORDER BY c.date_key
        """
    )
    conn.execute(
        """
        CREATE VIEW analytics_hourly AS
        SELECT
            r.ts,
            r.ride_count,
            d.date_key,
            d.year,
            d.month,
            d.weekday_label,
            d.day_type,
            d.is_weekend,
            d.is_holiday,
            d.quality_status,
            d.quality_note,
            'observed_source_hour' AS record_status,
            w.temperature_c,
            w.humidity_pct,
            w.precipitation_mm,
            w.wind_speed_kmh,
            w.weather_code
        FROM fact_system_hourly AS r
        JOIN dim_date AS d
            ON d.date_key = CAST(r.ts AS DATE)
        LEFT JOIN fact_weather_hourly AS w
            ON w.ts = r.ts
        """
    )
    conn.execute(
        """
        CREATE VIEW analytics_hourly_quality AS
        WITH analysis_clock AS (
            SELECT ts, ride_count, 'observed_source_hour' AS record_status
            FROM fact_system_hourly
            UNION ALL
            SELECT ts, 0 AS ride_count, 'confirmed_zero_trip_hour' AS record_status
            FROM hour_coverage_exception
            WHERE classification = 'confirmed_zero_trip_hour'
        )
        SELECT
            r.ts,
            r.ride_count,
            r.record_status,
            d.date_key,
            d.year,
            d.month,
            d.weekday_label,
            d.day_type,
            d.is_weekend,
            d.is_holiday,
            d.quality_status,
            w.temperature_c,
            w.humidity_pct,
            w.precipitation_mm,
            w.wind_speed_kmh,
            w.weather_code
        FROM analysis_clock AS r
        JOIN dim_date AS d
            ON d.date_key = CAST(r.ts AS DATE)
        LEFT JOIN fact_weather_hourly AS w
            ON w.ts = r.ts
        WHERE d.quality_status = 'complete'
        """
    )


def validation_rows(conn: duckdb.DuckDBPyConnection) -> list[tuple[str, object, object, str]]:
    checks = [
        ("ride_hours_with_source_records", "SELECT COUNT(*) FROM fact_system_hourly", 52526),
        ("weather_hours", "SELECT COUNT(*) FROM fact_weather_hourly", 52608),
        ("calendar_days", "SELECT COUNT(*) FROM dim_date", 2192),
        ("total_rides", "SELECT SUM(ride_count) FROM fact_system_hourly", 58865471),
        ("source_batches", "SELECT COUNT(*) FROM source_batch", 242),
        (
            "source_batch_valid_rows",
            "SELECT SUM(valid_start_rows) FROM source_batch",
            58865471,
        ),
        (
            "source_batch_invalid_start_rows",
            "SELECT SUM(invalid_start_rows) FROM source_batch",
            0,
        ),
        (
            "duplicate_ride_timestamps",
            "SELECT COUNT(*) - COUNT(DISTINCT ts) FROM fact_system_hourly",
            0,
        ),
        (
            "invalid_ride_counts",
            "SELECT COUNT(*) FROM fact_system_hourly WHERE ride_count < 0 OR ride_count IS NULL",
            0,
        ),
        (
            "matched_weather_hours",
            "SELECT COUNT(*) FROM analytics_hourly WHERE temperature_c IS NOT NULL",
            52526,
        ),
        (
            "coverage_exceptions",
            "SELECT COUNT(*) FROM hour_coverage_exception",
            82,
        ),
        (
            "confirmed_zero_trip_hours",
            "SELECT COUNT(*) FROM hour_coverage_exception WHERE classification = 'confirmed_zero_trip_hour'",
            21,
        ),
        (
            "source_gap_hours",
            "SELECT COUNT(*) FROM hour_coverage_exception WHERE classification = 'source_gap'",
            55,
        ),
        (
            "nonexistent_local_hours",
            "SELECT COUNT(*) FROM hour_coverage_exception WHERE classification = 'nonexistent_local_hour'",
            6,
        ),
        (
            "incomplete_source_dates",
            "SELECT COUNT(*) FROM dim_date WHERE quality_status = 'incomplete_source'",
            4,
        ),
        (
            "analysis_ready_hours",
            "SELECT COUNT(*) FROM analytics_hourly_quality",
            52506,
        ),
        (
            "analysis_ready_trips",
            "SELECT SUM(ride_count) FROM analytics_hourly_quality",
            58842971,
        ),
        (
            "clock_hours_without_ride_record",
            """
            SELECT COUNT(*)
            FROM fact_weather_hourly AS w
            LEFT JOIN fact_system_hourly AS r ON r.ts = w.ts
            WHERE r.ts IS NULL
            """,
            82,
        ),
    ]
    rows: list[tuple[str, object, object, str]] = []
    for name, query, expected in checks:
        actual = conn.execute(query).fetchone()[0]
        status = "PASS" if actual == expected else "FAIL"
        rows.append((name, expected, actual, status))
    return rows


def export_validation(
    rows: list[tuple[str, object, object, str]], export_dir: Path
) -> None:
    path = export_dir / "validation_summary.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["check_name", "expected", "actual", "status"])
        writer.writerows(rows)


def export_queries(conn: duckdb.DuckDBPyConnection, export_dir: Path) -> None:
    for path in sorted(SQL_DIR.glob("[0-9][0-9]_*.sql")):
        frame = conn.execute(path.read_text(encoding="utf-8")).fetchdf()
        frame.to_csv(export_dir / f"{path.stem}.csv", index=False, encoding="utf-8-sig")


def build_database(
    db_path: Path = DEFAULT_DB_PATH,
    export_dir: Path = DEFAULT_EXPORT_DIR,
) -> list[tuple[str, object, object, str]]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        load_sources(conn)
        rows = validation_rows(conn)
        export_validation(rows, export_dir)
        failed = [row for row in rows if row[-1] == "FAIL"]
        if failed:
            raise AssertionError(f"Data validation failed: {failed}")
        export_queries(conn, export_dir)
        return rows
    finally:
        conn.close()


def main() -> None:
    rows = build_database()
    print(f"Built warehouse: {DEFAULT_DB_PATH}")
    print(f"Exported results: {DEFAULT_EXPORT_DIR}")
    print(f"Validation: {sum(row[-1] == 'PASS' for row in rows)}/{len(rows)} PASS")


if __name__ == "__main__":
    main()
