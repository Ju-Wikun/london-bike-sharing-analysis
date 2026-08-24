DROP VIEW IF EXISTS analytics_hourly_quality;
DROP VIEW IF EXISTS analytics_hourly;
DROP TABLE IF EXISTS hour_coverage_exception;
DROP TABLE IF EXISTS known_data_anomaly;
DROP TABLE IF EXISTS source_batch;
DROP TABLE IF EXISTS od_build_metric;
DROP TABLE IF EXISTS fact_same_station;
DROP TABLE IF EXISTS fact_station_period;
DROP TABLE IF EXISTS fact_od_flow;
DROP TABLE IF EXISTS station_alias;
DROP TABLE IF EXISTS dim_station;
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

CREATE TABLE dim_station (
    station_key VARCHAR PRIMARY KEY,
    canonical_name VARCHAR NOT NULL,
    normalized_name VARCHAR NOT NULL,
    source_id_count INTEGER NOT NULL,
    alias_count INTEGER NOT NULL,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    endpoint_mentions BIGINT NOT NULL,
    mapping_status VARCHAR NOT NULL
);

CREATE TABLE station_alias (
    station_key VARCHAR NOT NULL,
    normalized_name VARCHAR NOT NULL,
    source_station_id VARCHAR,
    original_name VARCHAR NOT NULL,
    endpoint_mentions BIGINT NOT NULL,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    source_id_key_count INTEGER NOT NULL,
    requires_review BOOLEAN NOT NULL
);

CREATE TABLE fact_od_flow (
    start_key VARCHAR NOT NULL,
    end_key VARCHAR NOT NULL,
    same_station BOOLEAN NOT NULL,
    trip_count BIGINT NOT NULL,
    duration_sum_min DOUBLE NOT NULL,
    duration_le_3m_count BIGINT NOT NULL,
    duration_3_15m_count BIGINT NOT NULL,
    duration_gt_15m_count BIGINT NOT NULL,
    avg_duration_min DOUBLE NOT NULL
);

CREATE TABLE fact_station_period (
    station_key VARCHAR NOT NULL,
    day_type VARCHAR NOT NULL,
    hour_of_day INTEGER NOT NULL,
    outflow BIGINT NOT NULL,
    inflow BIGINT NOT NULL,
    net_inflow BIGINT NOT NULL
);

CREATE TABLE fact_same_station (
    station_key VARCHAR NOT NULL,
    day_type VARCHAR NOT NULL,
    hour_of_day INTEGER NOT NULL,
    trip_count BIGINT NOT NULL,
    duration_sum_min DOUBLE NOT NULL,
    duration_le_3m_count BIGINT NOT NULL,
    duration_3_15m_count BIGINT NOT NULL,
    duration_gt_15m_count BIGINT NOT NULL,
    avg_duration_min DOUBLE NOT NULL
);

CREATE TABLE od_build_metric (
    metric VARCHAR PRIMARY KEY,
    value DOUBLE NOT NULL
);
