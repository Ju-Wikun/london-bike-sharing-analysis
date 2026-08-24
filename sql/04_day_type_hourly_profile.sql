-- Business question: How do workday and non-workday demand curves differ?
SELECT
    day_type,
    hour(ts) AS hour_of_day,
    COUNT(*) AS observed_hours,
    ROUND(AVG(ride_count), 1) AS avg_rides,
    ROUND(median(ride_count), 1) AS median_rides,
    MAX(ride_count) AS peak_observation
FROM analytics_hourly_quality
GROUP BY day_type, hour(ts)
ORDER BY day_type, hour_of_day;
