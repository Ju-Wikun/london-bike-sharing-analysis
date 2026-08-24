DROP VIEW IF EXISTS analytics_hourly_quality;
DROP VIEW IF EXISTS analytics_hourly;
DROP TABLE IF EXISTS hour_coverage_exception;
DROP TABLE IF EXISTS known_data_anomaly;
DROP TABLE IF EXISTS source_batch;
DROP TABLE IF EXISTS fact_system_hourly;
DROP TABLE IF EXISTS fact_weather_hourly;
DROP TABLE IF EXISTS dim_holiday;
DROP TABLE IF EXISTS dim_date;

CREATE TABLE fact_system_hourly (
    ts TIMESTAMP PRIMARY KEY,
    ride_count BIGINT NOT NULL CHECK (ride_count >= 0)
);

CREATE TABLE fact_weather_hourly (
    ts TIMESTAMP PRIMARY KEY,
    temperature_c DOUBLE,
    humidity_pct DOUBLE CHECK (humidity_pct BETWEEN 0 AND 100),
    precipitation_mm DOUBLE CHECK (precipitation_mm >= 0),
    wind_speed_kmh DOUBLE CHECK (wind_speed_kmh >= 0),
    weather_code INTEGER
);

CREATE TABLE dim_holiday (
    region VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    holiday_date DATE NOT NULL,
    notes VARCHAR,
    bunting BOOLEAN
);

CREATE TABLE dim_date (
    date_key DATE PRIMARY KEY,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    weekday_num INTEGER NOT NULL,
    weekday_label VARCHAR NOT NULL,
    is_weekend BOOLEAN NOT NULL,
    is_holiday BOOLEAN NOT NULL,
    day_type VARCHAR NOT NULL CHECK (day_type IN ('workday', 'non_workday')),
    quality_status VARCHAR NOT NULL CHECK (quality_status IN ('complete', 'incomplete_source')),
    quality_note VARCHAR
);

CREATE TABLE source_batch (
    source_file VARCHAR PRIMARY KEY,
    file_size_bytes BIGINT NOT NULL,
    format_profile VARCHAR NOT NULL,
    parsed_rows BIGINT NOT NULL,
    valid_start_rows BIGINT NOT NULL,
    invalid_start_rows BIGINT NOT NULL,
    min_start TIMESTAMP,
    max_start TIMESTAMP,
    distinct_dates INTEGER NOT NULL,
    audit_status VARCHAR NOT NULL
);

CREATE TABLE hour_coverage_exception (
    ts TIMESTAMP PRIMARY KEY,
    classification VARCHAR NOT NULL CHECK (
        classification IN (
            'confirmed_zero_trip_hour', 'source_gap', 'nonexistent_local_hour'
        )
    ),
    reason VARCHAR NOT NULL
);

CREATE TABLE known_data_anomaly (
    anomaly_date DATE PRIMARY KEY,
    quality_status VARCHAR NOT NULL,
    observed_trip_records BIGINT NOT NULL,
    observed_hours INTEGER NOT NULL,
    missing_clock_hours INTEGER NOT NULL,
    reason VARCHAR NOT NULL
);
