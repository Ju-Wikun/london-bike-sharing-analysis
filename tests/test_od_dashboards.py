from __future__ import annotations

from src.od_dashboard_charts import (
    flow_structure_dashboard,
    station_diagnostics_dashboard,
)
from src.render_od_dashboards import load_frames


def test_full_od_dashboard_inputs_and_rendering() -> None:
    frames = load_frames()
    metrics = frames["metrics"]

    assert int(metrics["od_valid_rows"]) == 58311048
    assert int(metrics["cross_od_pairs"]) == 631262
    assert len(frames["station"]) == 888

    flow_html = flow_structure_dashboard(
        metrics, frames["routes"], frames["coverage"]
    )
    station = frames["station"]
    diagnostics_html = station_diagnostics_dashboard(
        frames["balance"],
        frames["station_period"],
        frames["same_behavior"],
        frames["duration"],
        station_count=len(station),
        review_station_count=int(
            (station["mapping_status"] == "review_source_id_reuse").sum()
        ),
    )

    assert "全量流向结构" in flow_html
    assert "Top20 覆盖" in flow_html
    assert "全量站点诊断" in diagnostics_html
    assert "同站归还行为" in diagnostics_html
