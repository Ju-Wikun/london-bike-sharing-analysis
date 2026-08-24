-- Full-data spatial structure after duration, station and source-quality filters.
SELECT
    SUM(trip_count) AS od_analysis_ready_trips,
    SUM(trip_count) FILTER (WHERE same_station) AS same_station_trips,
    SUM(trip_count) FILTER (WHERE NOT same_station) AS cross_station_trips,
    ROUND(
        100.0 * SUM(trip_count) FILTER (WHERE same_station) / SUM(trip_count), 2
    ) AS same_station_pct,
    ROUND(
        100.0 * SUM(trip_count) FILTER (WHERE NOT same_station) / SUM(trip_count), 2
    ) AS cross_station_pct,
    COUNT(*) AS od_pairs,
    COUNT(*) FILTER (WHERE NOT same_station) AS cross_od_pairs
FROM fact_od_flow;
