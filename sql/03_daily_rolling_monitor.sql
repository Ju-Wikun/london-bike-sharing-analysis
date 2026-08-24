-- Business question: Which days depart most from their recent baseline?
-- The first 30 observations are retained but not flagged because the baseline is immature.
WITH daily AS (
    SELECT CAST(ts AS DATE) AS ride_date, SUM(ride_count) AS daily_rides
    FROM analytics_hourly_quality
    GROUP BY CAST(ts AS DATE)
), baseline AS (
    SELECT
        ride_date,
        daily_rides,
        COUNT(*) OVER window_30d AS baseline_days,
        AVG(daily_rides) OVER window_30d AS moving_avg_30d,
        STDDEV_SAMP(daily_rides) OVER window_30d AS moving_std_30d
    FROM daily
    WINDOW window_30d AS (
        ORDER BY ride_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    )
)
SELECT
    ride_date,
    daily_rides,
    ROUND(moving_avg_30d, 1) AS moving_avg_30d,
    ROUND(moving_std_30d, 1) AS moving_std_30d,
    ROUND((daily_rides - moving_avg_30d) / NULLIF(moving_std_30d, 0), 2) AS rolling_z_score,
    CASE
        WHEN baseline_days = 30
         AND ABS((daily_rides - moving_avg_30d) / NULLIF(moving_std_30d, 0)) >= 2
        THEN TRUE ELSE FALSE
    END AS needs_review
FROM baseline
ORDER BY ride_date;
