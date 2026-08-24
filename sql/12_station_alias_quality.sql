-- Candidate station keys remain auditable because source IDs can change over time.
SELECT
    mapping_status,
    COUNT(*) AS station_count,
    SUM(source_id_count) AS source_id_references,
    MAX(source_id_count) AS max_source_ids_for_one_station
FROM dim_station
GROUP BY mapping_status
ORDER BY mapping_status;
