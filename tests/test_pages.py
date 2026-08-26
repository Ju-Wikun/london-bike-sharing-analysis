from pathlib import Path

from scripts.build_pages import package_pages

ROOT = Path(__file__).resolve().parents[1]


def test_pages_bundle_is_restricted_to_active_views(tmp_path):
    files = package_pages(ROOT / "dashboards", tmp_path / "site")
    assert len(files) == 9
    assert "echarts/echarts_04_station_trip.html" not in files
    assert not any(name.startswith(("data/", "src/", "output/")) for name in files)
    for name in files:
        assert (tmp_path / "site" / name).is_file()
    for name in files:
        if name.startswith("echarts/"):
            assert '../vendor/echarts.min.js' in (tmp_path / "site" / name).read_text(encoding="utf-8")
