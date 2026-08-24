-- Overall station balance; time-sliced diagnosis uses the underlying period table.
SELECT
    s.station_key,
    s.canonical_name,
    SUM(f.outflow) AS outflow,
    SUM(f.inflow) AS inflow,
    SUM(f.inflow) - SUM(f.outflow) AS net_inflow,
    SUM(f.inflow) + SUM(f.outflow) AS throughput
FROM fact_station_period AS f
JOIN dim_station AS s USING (station_key)
GROUP BY s.station_key, s.canonical_name
ORDER BY ABS(SUM(f.inflow) - SUM(f.outflow)) DESC, throughput DESC;
