-- Data question: Why do 82 weather-clock hours lack an observed ride aggregate?
SELECT 'observed_source_hour' AS classification, COUNT(*) AS hour_count
FROM fact_system_hourly
UNION ALL
SELECT classification, COUNT(*) AS hour_count
FROM hour_coverage_exception
GROUP BY classification
ORDER BY classification;
