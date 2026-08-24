from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .dashboard_charts_echarts import (
    echarts_environmental_dashboard,
    echarts_overview_dashboard,
    echarts_season_composition_dashboard,
    echarts_time_pattern_dashboard,
)
from .preprocess_london import (
    MONTH_ABBR_MAP,
    SEASON_MAP_LM,
    SEASON_ORDER,
    WEATHER_ORDER,
    WEEKDAY_MAP,
    WEEKDAY_ORDER,
    _WMO_WEATHER_MAP,
    _assign_time_period,
    _load_bank_holidays,
    _month_to_season_num,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DASHBOARD_DIR = PROJECT_ROOT / "dashboards" / "echarts"


def load_dashboard_frame() -> pd.DataFrame:
    hourly = pd.read_csv(
        DATA_DIR / "processed" / "system_hourly.csv", parse_dates=["ts"]
    )
    exceptions = pd.read_csv(
        DATA_DIR / "metadata" / "hour_coverage_exceptions.csv", parse_dates=["ts"]
    )
    confirmed_zero = exceptions[
        exceptions["classification"] == "confirmed_zero_trip_hour"
    ][["ts"]].copy()
    confirmed_zero["cnt"] = 0
    hourly = pd.concat([hourly, confirmed_zero], ignore_index=True)

    anomalies = pd.read_csv(
        DATA_DIR / "metadata" / "known_data_anomalies.csv", parse_dates=["date"]
    )
    incomplete_dates = set(anomalies["date"].dt.date)
    hourly = hourly[~hourly["ts"].dt.date.isin(incomplete_dates)].copy()
    weather = pd.read_csv(
        DATA_DIR / "reference" / "weather_hourly.csv", parse_dates=["timestamp"]
    ).rename(
        columns={
            "timestamp": "ts",
            "temperature_2m": "temp",
            "relative_humidity_2m": "humidity",
            "wind_speed_10m": "wind_speed",
            "weather_code": "weather_code_wmo",
        }
    )
    weather["ts"] = weather["ts"].dt.floor("h")
    frame = hourly.merge(weather, on="ts", how="left", validate="one_to_one")
    frame["atemp"] = frame["temp"]
    frame["weather_code"] = frame["weather_code_wmo"].fillna(-1).astype(int)
    frame["weather"] = frame["weather_code"].map(
        lambda code: _WMO_WEATHER_MAP.get(code, "多云/薄雾")
    )
    frame["weather"] = pd.Categorical(
        frame["weather"], categories=WEATHER_ORDER, ordered=True
    )

    holidays = _load_bank_holidays(DATA_DIR / "reference" / "bank_holidays.csv")
    frame["date"] = frame["ts"].dt.date
    frame["is_holiday"] = frame["date"].isin(holidays).astype(int)
    frame["is_weekend"] = frame["ts"].dt.weekday.isin([5, 6]).astype(int)
    frame["year"] = frame["ts"].dt.year
    frame["month"] = frame["ts"].dt.month
    frame["day"] = frame["ts"].dt.day
    frame["hour"] = frame["ts"].dt.hour
    frame["weekday"] = frame["ts"].dt.weekday
    frame["weekday_label"] = pd.Categorical(
        frame["weekday"].map(WEEKDAY_MAP), categories=WEEKDAY_ORDER, ordered=True
    )
    frame["season_num"] = frame["month"].apply(_month_to_season_num)
    frame["season"] = pd.Categorical(
        frame["season_num"].map(SEASON_MAP_LM),
        categories=SEASON_ORDER,
        ordered=True,
    )
    frame["day_type"] = np.where(
        frame["is_holiday"] == 1,
        "节假日",
        np.where(frame["is_weekend"] == 1, "周末", "工作日"),
    )
    frame["day_type"] = pd.Categorical(
        frame["day_type"], categories=["工作日", "周末", "节假日"], ordered=True
    )
    frame["time_period"] = pd.Categorical(
        frame["hour"].map(_assign_time_period),
        categories=["凌晨", "早高峰", "日间", "晚高峰", "夜间"],
        ordered=True,
    )
    frame["month_label"] = frame["month"].map(MONTH_ABBR_MAP)
    frame["is_rainy"] = frame["weather"].isin(["小雨/小雪", "大雨/暴雪"]).astype(int)
    return frame.sort_values("ts").reset_index(drop=True)


def main() -> None:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    frame = load_dashboard_frame()
    if len(frame) != 52506 or frame["temp"].isna().any():
        raise AssertionError("Dashboard input must contain 52,506 analysis-ready hours")

    outputs = {
        "echarts_01_overview.html": echarts_overview_dashboard,
        "echarts_02_time_pattern.html": echarts_time_pattern_dashboard,
        "echarts_03_environmental.html": echarts_environmental_dashboard,
        "echarts_05_season.html": echarts_season_composition_dashboard,
    }
    for filename, renderer in outputs.items():
        renderer(frame, output_path=DASHBOARD_DIR / filename)
        print(f"Rendered: {DASHBOARD_DIR / filename}")


if __name__ == "__main__":
    main()
