-- Business question: Which three dates contributed the most rides in each month?
WITH daily AS (
    SELECT
        CAST(ts AS DATE) AS ride_date,
        date_trunc('month', ts)::DATE AS month_start,
        SUM(ride_count) AS daily_rides
    FROM analytics_hourly_quality
    GROUP BY CAST(ts AS DATE), date_trunc('month', ts)
), ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY month_start ORDER BY daily_rides DESC, ride_date
        ) AS demand_rank
    FROM daily
)
SELECT month_start, ride_date, daily_rides, demand_rank
FROM ranked
WHERE demand_rank <= 3
ORDER BY month_start, demand_rank;
