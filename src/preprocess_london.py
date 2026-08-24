"""伦敦共享单车数据集加载与预处理模块。

数据来源：
  1. data/raw/tfl_cycling/usage-stats/ — 可选的 TfL 原始行程目录，不随仓库发布。
  2. data/reference/weather_hourly.csv — Open-Meteo 小时天气。
  3. data/reference/bank_holidays.csv  — GOV.UK 公共假期。
  4. data/processed/system_hourly.csv  — 可复现的小时骑行聚合。
"""

from __future__ import annotations

import glob
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# ─── 常量 ─────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[1]

LONDON_MERGED_PATH = PROJECT_ROOT / "data" / "legacy" / "london_merged.csv"
WEATHER_HOURLY_PATH = PROJECT_ROOT / "data" / "reference" / "weather_hourly.csv"
WEATHER_DAILY_PATH = PROJECT_ROOT / "data" / "reference" / "weather_daily.csv"
TFL_USAGE_DIR = PROJECT_ROOT / "data" / "raw" / "tfl_cycling" / "usage-stats"
BANK_HOLIDAYS_PATH = PROJECT_ROOT / "data" / "reference" / "bank_holidays.csv"

SEASON_MAP_LM = {0: "Spring", 1: "Summer", 2: "Fall", 3: "Winter"}
SEASON_ORDER = ["Spring", "Summer", "Fall", "Winter"]
SEASON_COLORS = {
    "Spring": "#4CAF50",
    "Summer": "#FF9800",
    "Fall": "#9C27B0",
    "Winter": "#2196F3",
}

WEATHER_MAP_LM = {
    1: "晴朗",
    2: "多云/薄雾",
    3: "小雨/小雪",
    4: "大雨/暴雪",
    7: "小雨/小雪",
    10: "多云/薄雾",
    26: "小雨/小雪",
}
WEATHER_ORDER = ["晴朗", "多云/薄雾", "小雨/小雪", "大雨/暴雪"]
WEATHER_COLORS = {
    "晴朗": "#FDD835",
    "多云/薄雾": "#90CAF9",
    "小雨/小雪": "#78909C",
    "大雨/暴雪": "#37474F",
}

# Open-Meteo WMO 天气代码 → 简化分类
_WMO_WEATHER_MAP: dict[int, str] = {}
for _c in (0, 1):
    _WMO_WEATHER_MAP[_c] = "晴朗"
for _c in (2, 3, 45, 48):
    _WMO_WEATHER_MAP[_c] = "多云/薄雾"
for _c in (51, 53, 56, 61, 63, 71, 73, 77, 80, 85):
    _WMO_WEATHER_MAP[_c] = "小雨/小雪"
for _c in (55, 57, 65, 66, 67, 75, 81, 82, 86, 95, 96, 99):
    _WMO_WEATHER_MAP[_c] = "大雨/暴雪"

WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_MAP = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
               4: "Friday", 5: "Saturday", 6: "Sunday"}

MONTH_ABBR_MAP = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                  7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}


def _month_to_season_num(month: int) -> int:
    """月份 → 季节编号 (0=Spring 1=Summer 2=Fall 3=Winter)。"""
    if month in (3, 4, 5):
        return 0
    if month in (6, 7, 8):
        return 1
    if month in (9, 10, 11):
        return 2
    return 3


def _assign_time_period(hr: int) -> str:
    if 0 <= hr <= 5:
        return "凌晨"
    if 6 <= hr <= 9:
        return "早高峰"
    if 10 <= hr <= 15:
        return "日间"
    if 16 <= hr <= 20:
        return "晚高峰"
    return "夜间"


# ─── TfL 行程数据读取（支持新旧两种 CSV 格式）───────────────────────────────

def _parse_tfl_datetime(values: pd.Series) -> pd.Series:
    """Parse TfL's mixed ISO and day-first timestamps without swapping dates."""
    raw = values.astype("string").str.strip()
    is_iso = raw.str.match(r"^\d{4}-", na=False)
    parsed = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    parsed.loc[is_iso] = pd.to_datetime(
        raw.loc[is_iso], format="mixed", errors="coerce"
    )
    parsed.loc[~is_iso] = pd.to_datetime(
        raw.loc[~is_iso], format="mixed", dayfirst=True, errors="coerce"
    )
    return parsed

def _read_single_tfl_csv(fp: Path, max_rows: int | None = None) -> pd.DataFrame:
    """读取单个 TfL 行程 CSV，统一输出列名。

    旧格式 (2015-2021)：Start Date 格式 DD/MM/YYYY HH:MM，Duration 为秒数。
    新格式 (2022+)：Start date 可能是 YYYY-MM-DD 或 DD/MM/YYYY，
    Total duration (ms) 为毫秒。TfL 在 2024 年部分批次切换过日期格式。
    """
    try:
        peek = pd.read_csv(fp, nrows=0, encoding="utf-8", on_bad_lines="skip")
    except Exception:
        peek = pd.read_csv(fp, nrows=0, encoding="latin-1", on_bad_lines="skip")
    cols = [c.strip().strip('"') for c in peek.columns]

    is_new_format = "Start date" in cols or "Number" in cols

    if is_new_format:
        use_cols_map = {
            "Total duration (ms)": "duration_ms",
            "Start date": "start_dt",
            "End date": "end_dt",
            "Start station": "start_station",
            "End station": "end_station",
            "Start station number": "start_station_id",
            "End station number": "end_station_id",
            "Bike model": "bike_model",
        }
        available = [c for c in use_cols_map if c in cols]
        try:
            df = pd.read_csv(fp, usecols=available, nrows=max_rows,
                             on_bad_lines="skip", encoding="utf-8", low_memory=False)
        except Exception:
            df = pd.read_csv(fp, usecols=available, nrows=max_rows,
                             on_bad_lines="skip", encoding="latin-1", low_memory=False)
        df = df.rename(columns=use_cols_map)
        if "duration_ms" in df.columns:
            df["duration_sec"] = pd.to_numeric(df["duration_ms"], errors="coerce") / 1000.0
            df.drop(columns=["duration_ms"], inplace=True, errors="ignore")
        else:
            df["duration_sec"] = np.nan
        # Parse by notation: pandas applies dayfirst to ISO dates too, which would
        # silently turn 2024-01-08 into 2024-08-01.
        df["start_dt"] = _parse_tfl_datetime(df["start_dt"])
        df["end_dt"] = _parse_tfl_datetime(df["end_dt"])
    else:
        use_cols = ["Duration", "Start Date", "End Date",
                    "StartStation Name", "EndStation Name",
                    "StartStation Id", "EndStation Id"]
        available = [c for c in use_cols if c in cols]
        try:
            df = pd.read_csv(fp, usecols=available, nrows=max_rows,
                             on_bad_lines="skip", encoding="utf-8", low_memory=False)
        except Exception:
            df = pd.read_csv(fp, usecols=available, nrows=max_rows,
                             on_bad_lines="skip", encoding="latin-1", low_memory=False)
        df = df.rename(columns={
            "Duration": "duration_sec",
            "Start Date": "start_dt",
            "End Date": "end_dt",
            "StartStation Name": "start_station",
            "EndStation Name": "end_station",
            "StartStation Id": "start_station_id",
            "EndStation Id": "end_station_id",
        })
        df["duration_sec"] = pd.to_numeric(df.get("duration_sec"), errors="coerce")
        df["start_dt"] = pd.to_datetime(df.get("start_dt"),
                                        format="%d/%m/%Y %H:%M", errors="coerce")
        df["end_dt"] = pd.to_datetime(df.get("end_dt"),
                                      format="%d/%m/%Y %H:%M", errors="coerce")
        if "bike_model" not in df.columns:
            df["bike_model"] = "CLASSIC"

    return df


def _filter_tfl_files_by_year(usage_dir: Path,
                              start_year: int = 2020,
                              end_year: int = 2025) -> list[Path]:
    """筛选文件名中包含指定年份范围的 TfL CSV 文件。"""
    all_csv = sorted(usage_dir.glob("*.csv"))
    year_pat = re.compile(r"(20\d{2})")
    selected = []
    for fp in all_csv:
        years_in_name = [int(y) for y in year_pat.findall(fp.stem)]
        if not years_in_name:
            continue
        if any(start_year <= y <= end_year for y in years_in_name):
            selected.append(fp)
    return selected


# ─── 核心: 从 TfL 行程构建小时级骑行量 ────────────────────────────────────────

def build_hourly_from_tfl(
    usage_dir: str | Path = TFL_USAGE_DIR,
    start_year: int = 2020,
    end_year: int = 2025,
    cache_path: str | Path | None = None,
) -> pd.DataFrame:
    """从 TfL 行程 CSV 聚合为小时级骑行量 DataFrame。

    返回 columns = [ts, cnt]，ts 为整点时间戳。
    若 cache_path 已存在则直接读取缓存。
    """
    if cache_path:
        cache_path = Path(cache_path)
        if cache_path.exists():
            df = pd.read_csv(cache_path, parse_dates=["ts"])
            print(f"  从缓存加载小时级骑行量: {len(df)} 条 ({cache_path.name})")
            return df

    usage_dir = Path(usage_dir)
    files = _filter_tfl_files_by_year(usage_dir, start_year, end_year)
    if not files:
        raise FileNotFoundError(f"在 {usage_dir} 中未找到 {start_year}-{end_year} 的 CSV 文件")

    print(f"  正在聚合 {len(files)} 个 TfL 行程文件 ({start_year}-{end_year})...")
    hourly_counts: dict[pd.Timestamp, int] = {}
    total_trips = 0

    for i, fp in enumerate(files):
        try:
            chunk = _read_single_tfl_csv(fp)
            valid = chunk.dropna(subset=["start_dt"])
            ts_hours = valid["start_dt"].dt.floor("h")
            counts = ts_hours.value_counts()
            for ts, cnt in counts.items():
                hourly_counts[ts] = hourly_counts.get(ts, 0) + int(cnt)
            total_trips += len(valid)
        except Exception as exc:
            warnings.warn(f"跳过 {fp.name}: {exc}")
        if (i + 1) % 20 == 0:
            print(f"    已处理 {i+1}/{len(files)} 文件, 累计行程 {total_trips:,}")

    print(f"  聚合完成: {len(files)} 文件, {total_trips:,} 条行程, {len(hourly_counts)} 个小时时间点")

    result = pd.DataFrame([
        {"ts": ts, "cnt": cnt} for ts, cnt in sorted(hourly_counts.items())
    ])
    result["ts"] = pd.to_datetime(result["ts"])

    start_dt = pd.Timestamp(f"{start_year}-01-01")
    end_dt = pd.Timestamp(f"{end_year}-12-31 23:00:00")
    result = result[(result["ts"] >= start_dt) & (result["ts"] <= end_dt)]
    result = result.sort_values("ts").reset_index(drop=True)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(cache_path, index=False, encoding="utf-8-sig")
        print(f"  已缓存至 {cache_path}")

    return result


# ─── 加载英国公共假期 ──────────────────────────────────────────────────────────

def _load_bank_holidays(path: str | Path = BANK_HOLIDAYS_PATH) -> set:
    """返回英格兰和威尔士公共假期日期集合。"""
    path = Path(path)
    if not path.exists():
        warnings.warn(f"未找到假期文件 {path}，is_holiday 将全部为 0")
        return set()
    df = pd.read_csv(path, parse_dates=["date"])
    ew = df[df["region"] == "england-and-wales"]
    return set(ew["date"].dt.date)


# ─── 合并数据集: TfL 骑行量 + 天气 + 假期 ─────────────────────────────────────

def load_merged_2020_2025(
    usage_dir: str | Path = TFL_USAGE_DIR,
    weather_hourly_path: str | Path = WEATHER_HOURLY_PATH,
    holidays_path: str | Path = BANK_HOLIDAYS_PATH,
    start_year: int = 2020,
    end_year: int = 2025,
) -> pd.DataFrame:
    """构建 2020-2025 合并数据集，字段结构与旧 london_merged 兼容。"""
    cache_name = (
        "system_hourly.csv"
        if (start_year, end_year) == (2020, 2025)
        else f"system_hourly_{start_year}_{end_year}.csv"
    )
    cache = PROJECT_ROOT / "data" / "processed" / cache_name
    hourly = build_hourly_from_tfl(usage_dir, start_year, end_year, cache_path=cache)

    weather_path = Path(weather_hourly_path)
    if weather_path.exists():
        w = pd.read_csv(weather_path, parse_dates=["timestamp"])
        w = w.rename(columns={
            "timestamp": "ts",
            "temperature_2m": "temp",
            "relative_humidity_2m": "humidity",
            "wind_speed_10m": "wind_speed",
            "weather_code": "weather_code_wmo",
            "precipitation": "precipitation",
        })
        w["ts"] = w["ts"].dt.floor("h")
        w = w.drop_duplicates(subset=["ts"], keep="first")

        hourly = hourly.merge(w[["ts", "temp", "humidity", "wind_speed",
                                  "weather_code_wmo", "precipitation"]],
                              on="ts", how="left")
    else:
        warnings.warn(f"天气数据 {weather_path} 不存在，天气相关列将填充 NaN")
        hourly["temp"] = np.nan
        hourly["humidity"] = np.nan
        hourly["wind_speed"] = np.nan
        hourly["weather_code_wmo"] = np.nan
        hourly["precipitation"] = np.nan

    hourly["atemp"] = hourly["temp"]

    if "weather_code_wmo" in hourly.columns:
        hourly["weather_code"] = hourly["weather_code_wmo"].fillna(-1).astype(int)
        hourly["weather"] = hourly["weather_code"].map(
            lambda c: _WMO_WEATHER_MAP.get(c, "多云/薄雾")
        )
    else:
        hourly["weather_code"] = 0
        hourly["weather"] = "晴朗"
    hourly["weather"] = pd.Categorical(hourly["weather"], categories=WEATHER_ORDER, ordered=True)

    holidays = _load_bank_holidays(holidays_path)
    hourly["date"] = hourly["ts"].dt.date
    hourly["is_holiday"] = hourly["date"].apply(lambda d: 1 if d in holidays else 0)
    hourly["is_weekend"] = hourly["ts"].dt.weekday.isin([5, 6]).astype(int)

    hourly["year"] = hourly["ts"].dt.year
    hourly["month"] = hourly["ts"].dt.month
    hourly["day"] = hourly["ts"].dt.day
    hourly["hour"] = hourly["ts"].dt.hour
    hourly["weekday"] = hourly["ts"].dt.weekday
    hourly["weekday_label"] = hourly["weekday"].map(WEEKDAY_MAP)
    hourly["weekday_label"] = pd.Categorical(
        hourly["weekday_label"], categories=WEEKDAY_ORDER, ordered=True
    )

    hourly["season_num"] = hourly["month"].apply(_month_to_season_num)
    hourly["season"] = hourly["season_num"].map(SEASON_MAP_LM)
    hourly["season"] = pd.Categorical(hourly["season"], categories=SEASON_ORDER, ordered=True)

    hourly["day_type"] = np.where(
        hourly["is_holiday"] == 1, "节假日",
        np.where(hourly["is_weekend"] == 1, "周末", "工作日")
    )
    hourly["day_type"] = pd.Categorical(
        hourly["day_type"], categories=["工作日", "周末", "节假日"], ordered=True
    )

    hourly["time_period"] = hourly["hour"].map(_assign_time_period)
    hourly["time_period"] = pd.Categorical(
        hourly["time_period"],
        categories=["凌晨", "早高峰", "日间", "晚高峰", "夜间"],
        ordered=True,
    )

    hourly["month_label"] = hourly["month"].map(MONTH_ABBR_MAP)
    hourly["is_rainy"] = hourly["weather"].isin(["小雨/小雪", "大雨/暴雪"]).astype(int)

    hourly.drop(columns=["weather_code_wmo"], inplace=True, errors="ignore")

    return hourly.sort_values("ts").reset_index(drop=True)


# ─── 兼容: 旧 london_merged.csv 加载 ──────────────────────────────────────────

def load_london_merged(path: str | Path = LONDON_MERGED_PATH) -> pd.DataFrame:
    """加载 london_merged.csv 并进行特征工程，返回小时级 DataFrame。"""
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.rename(columns={
        "timestamp": "ts",
        "cnt": "cnt",
        "t1": "temp",
        "t2": "atemp",
        "hum": "humidity",
        "wind_speed": "wind_speed",
        "weather_code": "weather_code",
        "is_holiday": "is_holiday",
        "is_weekend": "is_weekend",
        "season": "season_num",
    })

    df["date"] = df["ts"].dt.date
    df["year"] = df["ts"].dt.year
    df["month"] = df["ts"].dt.month
    df["day"] = df["ts"].dt.day
    df["hour"] = df["ts"].dt.hour
    df["weekday"] = df["ts"].dt.weekday
    df["weekday_label"] = df["weekday"].map(WEEKDAY_MAP)
    df["weekday_label"] = pd.Categorical(df["weekday_label"], categories=WEEKDAY_ORDER, ordered=True)

    df["season_num"] = df["season_num"].astype(int)
    df["season"] = df["season_num"].map(SEASON_MAP_LM)
    df["season"] = pd.Categorical(df["season"], categories=SEASON_ORDER, ordered=True)

    df["weather_code"] = df["weather_code"].astype(int)
    df["weather"] = df["weather_code"].map(WEATHER_MAP_LM)
    df["weather"] = pd.Categorical(df["weather"], categories=WEATHER_ORDER, ordered=True)

    df["is_holiday"] = df["is_holiday"].astype(int)
    df["is_weekend"] = df["is_weekend"].astype(int)
    df["day_type"] = np.where(
        df["is_holiday"] == 1, "节假日",
        np.where(df["is_weekend"] == 1, "周末", "工作日")
    )
    df["day_type"] = pd.Categorical(
        df["day_type"], categories=["工作日", "周末", "节假日"], ordered=True
    )

    df["time_period"] = df["hour"].map(_assign_time_period)
    df["time_period"] = pd.Categorical(
        df["time_period"],
        categories=["凌晨", "早高峰", "日间", "晚高峰", "夜间"],
        ordered=True,
    )
    df["month_label"] = df["month"].map(MONTH_ABBR_MAP)
    df["is_rainy"] = df["weather"].isin(["小雨/小雪", "大雨/暴雪"]).astype(int)

    return df.sort_values("ts").reset_index(drop=True)


# ─── 天气数据 ──────────────────────────────────────────────────────────────────

def load_weather_hourly(path: str | Path = WEATHER_HOURLY_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.rename(columns={
        "temperature_2m": "temperature",
        "relative_humidity_2m": "humidity_om",
        "precipitation": "precipitation",
        "wind_speed_10m": "wind_speed_om",
        "weather_code": "weather_code_om",
    })
    return df.sort_values("timestamp").reset_index(drop=True)


def load_weather_daily(path: str | Path = WEATHER_DAILY_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    return df.sort_values("date").reset_index(drop=True)


def merge_with_weather(lm_df: pd.DataFrame) -> pd.DataFrame:
    """将 df 与 Open-Meteo 小时天气合并（追加 precipitation 列）。"""
    w_path = Path(WEATHER_HOURLY_PATH)
    if not w_path.exists():
        if "precipitation" not in lm_df.columns:
            lm_df = lm_df.copy()
            lm_df["precipitation"] = 0.0
        return lm_df
    w = load_weather_hourly()
    w = w.rename(columns={"timestamp": "ts"})
    merged = lm_df.merge(
        w[["ts", "precipitation", "temperature"]],
        on="ts",
        how="left",
    )
    return merged


# ─── TfL 行程数据（用于站点/路线分析）─────────────────────────────────────────

def load_tfl_trips(
    usage_dir: str | Path = TFL_USAGE_DIR,
    start_year: int = 2020,
    end_year: int = 2025,
    sample_n_files: int | None = None,
    max_rows_per_file: int | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """加载 TfL 单次行程数据并清洗，支持新旧两种格式。

    若 sample_n_files 不为 None，则随机抽样指定数量的文件。
    若 max_rows_per_file 不为 None，则每个文件最多读取指定行数。
    """
    usage_dir = Path(usage_dir)
    all_files = _filter_tfl_files_by_year(usage_dir, start_year, end_year)
    if not all_files:
        raise FileNotFoundError(f"在 {usage_dir} 中未找到 {start_year}-{end_year} 的 CSV 文件")

    if sample_n_files is not None and sample_n_files < len(all_files):
        rng = np.random.default_rng(seed)
        chosen = rng.choice(all_files, size=sample_n_files, replace=False)
        chosen = sorted(chosen, key=lambda p: p.name)
    else:
        chosen = all_files

    print(f"  正在加载 {len(chosen)} 个行程文件...")
    frames: list[pd.DataFrame] = []
    for i, fp in enumerate(chosen):
        try:
            chunk = _read_single_tfl_csv(fp, max_rows=max_rows_per_file)
            frames.append(chunk)
        except Exception as exc:
            warnings.warn(f"跳过 {fp.name}: {exc}")
        if (i + 1) % 20 == 0:
            print(f"    已加载 {i+1}/{len(chosen)}")

    if not frames:
        raise RuntimeError("无法加载任何 TfL 行程文件")

    df = pd.concat(frames, ignore_index=True)

    df["duration_sec"] = pd.to_numeric(df.get("duration_sec"), errors="coerce")
    df = df.dropna(subset=["duration_sec", "start_dt"])
    df = df[(df["duration_sec"] >= 60) & (df["duration_sec"] <= 10800)]
    df["duration_min"] = df["duration_sec"] / 60.0
    df["start_hour"] = df["start_dt"].dt.hour
    df["start_weekday"] = df["start_dt"].dt.weekday
    df["start_weekday_label"] = df["start_weekday"].map(WEEKDAY_MAP)
    df["start_date"] = df["start_dt"].dt.date
    df["start_month"] = df["start_dt"].dt.month
    df["start_year"] = df["start_dt"].dt.year

    start_dt = pd.Timestamp(f"{start_year}-01-01")
    end_dt = pd.Timestamp(f"{end_year}-12-31 23:59:59")
    df = df[(df["start_dt"] >= start_dt) & (df["start_dt"] <= end_dt)]

    print(f"  加载完成: {len(df):,} 条有效行程记录")
    return df.reset_index(drop=True)


# ─── 聚合工具 ──────────────────────────────────────────────────────────────────

def daily_agg(df: pd.DataFrame) -> pd.DataFrame:
    daily = (
        df.groupby("date", as_index=False)
        .agg(
            cnt=("cnt", "sum"),
            temp_mean=("temp", "mean"),
            humidity_mean=("humidity", "mean"),
            wind_mean=("wind_speed", "mean"),
        )
    )
    daily["date"] = pd.to_datetime(daily["date"])
    daily = daily.sort_values("date").reset_index(drop=True)
    daily["cnt_ma30"] = daily["cnt"].rolling(30, min_periods=1).mean()
    daily["cnt_cumsum"] = daily["cnt"].cumsum()
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month
    return daily


def monthly_agg(df: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        df.groupby(["year", "month"], as_index=False)
        .agg(cnt=("cnt", "sum"))
    )
    monthly["month_label"] = monthly["month"].map(MONTH_ABBR_MAP)
    return monthly.sort_values(["year", "month"]).reset_index(drop=True)


def hourly_agg(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["hour", "day_type"], observed=True, as_index=False)
        .agg(avg_cnt=("cnt", "mean"))
    )


def hour_month_pivot(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["hour", "month"])["cnt"]
        .mean()
        .unstack(level="month")
        .fillna(0)
    )


def weekday_daily(df: pd.DataFrame) -> pd.DataFrame:
    d = df.groupby(["date", "weekday_label"], as_index=False, observed=True).agg(cnt=("cnt", "sum"))
    return d


def season_hourly_pivot(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["season", "hour"], observed=True)["cnt"]
        .mean()
        .unstack(level="hour")
        .reindex(SEASON_ORDER)
    )


def weather_group_agg(df: pd.DataFrame) -> pd.DataFrame:
    d = df.groupby(["date", "weather"], as_index=False, observed=True).agg(cnt=("cnt", "sum"))
    return d.groupby("weather", observed=True)["cnt"].agg(["mean", "std", "count"]).reindex(WEATHER_ORDER).reset_index()


def day_type_agg(df: pd.DataFrame) -> pd.DataFrame:
    d = df.groupby(["date", "day_type"], as_index=False, observed=True).agg(cnt=("cnt", "sum"))
    return d.groupby("day_type", observed=True)["cnt"].agg(["mean", "std"]).reset_index()


def correlation_features(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["cnt", "temp", "atemp", "humidity", "wind_speed"]
    labels = ["骑行量", "气温(°C)", "体感温度(°C)", "湿度(%)", "风速(km/h)"]
    available = [c for c in cols if c in df.columns]
    sub = df[available].dropna().copy()
    sub.columns = labels[:len(available)]
    return sub


def calendar_heatmap_data(df: pd.DataFrame) -> pd.DataFrame:
    daily = df.groupby("date")["cnt"].sum().reset_index()
    daily["date"] = pd.to_datetime(daily["date"])
    return daily
