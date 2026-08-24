-- Business question: How does demand change month to month?
-- LAG is used for MoM; a three-month moving average reduces short-term noise.
WITH monthly AS (
    SELECT
        date_trunc('month', ts)::DATE AS month_start,
        SUM(ride_count) AS monthly_rides
    FROM analytics_hourly_quality
    GROUP BY date_trunc('month', ts)
), compared AS (
    SELECT
        month_start,
        monthly_rides,
        LAG(monthly_rides) OVER (ORDER BY month_start) AS previous_month_rides,
        AVG(monthly_rides) OVER (
            ORDER BY month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ) AS moving_avg_3m
    FROM monthly
), incomplete_dates AS (
    SELECT
        date_trunc('month', date_key)::DATE AS month_start,
        COUNT(*) AS excluded_incomplete_days
    FROM dim_date
    WHERE quality_status = 'incomplete_source'
    GROUP BY 1
)
SELECT
    month_start,
    monthly_rides,
    previous_month_rides,
    ROUND(100.0 * (monthly_rides - previous_month_rides) / previous_month_rides, 1) AS mom_pct,
    ROUND(moving_avg_3m, 1) AS moving_avg_3m,
    COALESCE(i.excluded_incomplete_days, 0) AS excluded_incomplete_days,
    COALESCE(i.excluded_incomplete_days, 0) = 0 AS is_complete_month
FROM compared
LEFT JOIN incomplete_dates AS i USING (month_start)
ORDER BY month_start;
