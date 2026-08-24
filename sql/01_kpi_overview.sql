-- Business question: What is the verified scale and dominant hourly pattern?
WITH daily AS (
    SELECT CAST(ts AS DATE) AS ride_date, SUM(ride_count) AS daily_rides
    FROM analytics_hourly_quality
    GROUP BY CAST(ts AS DATE)
), hourly_profile AS (
    SELECT hour(ts) AS hour_of_day, AVG(ride_count) AS avg_hourly_rides
    FROM analytics_hourly_quality
    GROUP BY hour(ts)
), peak AS (
    SELECT hour_of_day, avg_hourly_rides
    FROM hourly_profile
    ORDER BY avg_hourly_rides DESC, hour_of_day
    LIMIT 1
)
SELECT
    (SELECT SUM(ride_count) FROM fact_system_hourly) AS raw_observed_rides,
    SUM(ride_count) AS analysis_ready_rides,
    COUNT(*) AS analysis_ready_hours,
    COUNT(DISTINCT CAST(ts AS DATE)) AS analysis_ready_days,
    (SELECT COUNT(*) FROM dim_date WHERE quality_status = 'incomplete_source') AS excluded_incomplete_days,
    ROUND((SELECT AVG(daily_rides) FROM daily), 1) AS avg_daily_rides,
    (SELECT hour_of_day FROM peak) AS peak_hour_of_day,
    ROUND((SELECT avg_hourly_rides FROM peak), 1) AS peak_hour_avg_rides
FROM analytics_hourly_quality;
