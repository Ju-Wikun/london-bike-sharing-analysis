-- Top-N is reported with its denominator; it is not treated as the whole network.
WITH ranked AS (
    SELECT
        trip_count,
        ROW_NUMBER() OVER (ORDER BY trip_count DESC) AS route_rank,
        SUM(trip_count) OVER () AS total_cross_trips
    FROM fact_od_flow
    WHERE NOT same_station
), thresholds(top_n) AS (VALUES (10), (20), (50), (100), (500), (1000), (5000))
SELECT
    top_n,
    SUM(trip_count) FILTER (WHERE route_rank <= top_n) AS top_n_trips,
    ROUND(
        100.0 * SUM(trip_count) FILTER (WHERE route_rank <= top_n)
        / MAX(total_cross_trips),
        3
    ) AS coverage_pct
FROM thresholds
CROSS JOIN ranked
GROUP BY top_n
ORDER BY top_n;
