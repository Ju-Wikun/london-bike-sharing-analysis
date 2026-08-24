-- Business question: Is lower demand during rainy hours still visible after matching hour of day?
-- This is descriptive, not causal: season, weekday and other conditions remain uncontrolled.
SELECT
    hour(ts) AS hour_of_day,
    CASE WHEN precipitation_mm > 0 THEN 'rainy' ELSE 'dry' END AS rain_label,
    COUNT(*) AS observed_hours,
    ROUND(AVG(ride_count), 1) AS avg_rides,
    ROUND(median(ride_count), 1) AS median_rides
FROM analytics_hourly_quality
WHERE precipitation_mm IS NOT NULL
GROUP BY hour(ts), CASE WHEN precipitation_mm > 0 THEN 'rainy' ELSE 'dry' END
ORDER BY hour_of_day, rain_label;
