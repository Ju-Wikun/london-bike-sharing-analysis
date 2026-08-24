-- Count and within-station rate are shown together to avoid denominator bias.
WITH departures AS (
    SELECT start_key AS station_key, SUM(trip_count) AS departure_count
    FROM fact_od_flow
    GROUP BY start_key
), self_routes AS (
    SELECT
        start_key AS station_key,
        trip_count,
        avg_duration_min,
        duration_le_3m_count,
        duration_3_15m_count,
        duration_gt_15m_count
    FROM fact_od_flow
    WHERE same_station
)
SELECT
    s.station_key,
    s.canonical_name,
    r.trip_count AS same_station_trips,
    d.departure_count,
    ROUND(100.0 * r.trip_count / d.departure_count, 2) AS same_station_rate_pct,
    ROUND(r.avg_duration_min, 1) AS avg_duration_min,
    ROUND(100.0 * r.duration_le_3m_count / r.trip_count, 1) AS duration_le_3m_pct,
    ROUND(100.0 * r.duration_gt_15m_count / r.trip_count, 1) AS duration_gt_15m_pct
FROM self_routes AS r
JOIN departures AS d USING (station_key)
JOIN dim_station AS s USING (station_key)
ORDER BY r.trip_count DESC, s.canonical_name;
