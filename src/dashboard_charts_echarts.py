"""伦敦共享单车数据可视化 — ECharts 交互式看板模块。

每个 echarts_*_dashboard 函数返回自包含的 HTML 字符串。
使用 display_echarts_inline() 在 Notebook 中展示。
"""

from __future__ import annotations

from itertools import count
from pathlib import Path

import numpy as np
import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Boxplot, Calendar, HeatMap, Line, Radar, Sankey, Scatter
from pyecharts.commons.utils import JsCode

from .preprocess_london import (
    SEASON_COLORS,
    SEASON_ORDER,
    WEATHER_COLORS,
    WEATHER_ORDER,
    WEEKDAY_ORDER,
    calendar_heatmap_data,
    correlation_features,
    daily_agg,
    day_type_agg,
    hour_month_pivot,
    hourly_agg,
    monthly_agg,
    weather_group_agg,
    weekday_daily,
)

_ECHARTS_CDN = "../vendor/echarts.min.js"
_ECHARTS_FALLBACK = "https://cdn.bootcdn.net/ajax/libs/echarts/5.5.1/echarts.min.js"

_HEADER_BG = "#1A237E"
_PANEL_BG = "#FFFFFF"
_DASH_BG = "#F0F4F8"
_ACCENT = "#3F51B5"
_TEXT_DARK = "#212121"
_TEXT_LIGHT = "#757575"

MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


_CHART_IDS = count(1)


def _cid() -> str:
    return f"ec_{next(_CHART_IDS):04d}"


def _chart_fragment(chart, height: str = "420px") -> str:
    cid = _cid()
    options_js = chart.dump_options()
    return (
        f'<div id="{cid}" class="chart-cell" '
        f'style="width:100%;height:{height};"></div>\n'
        f"<script>\n"
        f"(function(){{\n"
        f"  var dom = document.getElementById('{cid}');\n"
        f"  var c = echarts.init(dom, null, {{renderer:'canvas', locale:'ZH'}});\n"
        f"  c.setOption({options_js});\n"
        f"  (window._ec = window._ec || []).push(c);\n"
        f"  new ResizeObserver(function(){{ c.resize(); }}).observe(dom);\n"
        f"}})();\n"
        f"</script>"
    )


def _kpi_section(kpi_list: list[tuple[str, str, str]]) -> str:
    cards = ""
    for value, label, color in kpi_list:
        cards += (
            f'<div class="kpi-card" style="border-left:4px solid {color};">'
            f'<div class="kpi-value" style="color:{color};">{value}</div>'
            f'<div class="kpi-label">{label}</div>'
            f"</div>\n"
        )
    return f'<div class="kpi-row">{cards}</div>'


def _render_dashboard_html(
    sections: list[str | tuple[str, str]],
    title: str,
    subtitle: str = "",
) -> str:
    body_rows = []
    for item in sections:
        if isinstance(item, tuple):
            left, right = item
            body_rows.append(
                f'<div class="row-2col">'
                f'<div class="col">{left}</div>'
                f'<div class="col">{right}</div>'
                f"</div>"
            )
        else:
            body_rows.append(f'<div class="row-full">{item}</div>')

    body = "\n".join(body_rows)
    sub_html = f'<p class="header-sub">{subtitle}</p>' if subtitle else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<script src="{_ECHARTS_CDN}"></script>
<script>
if (typeof echarts === 'undefined') {{
  document.write('<script src="{_ECHARTS_FALLBACK}"><\\/script>');
}}
</script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:{_DASH_BG};padding:14px}}
.header{{background:{_HEADER_BG};color:#fff;padding:12px 20px;border-radius:6px;margin-bottom:12px}}
.header h1{{font-size:18px;font-weight:700}}
.header-sub{{font-size:11px;color:#B0BEC5;margin-top:3px}}
.kpi-row{{display:flex;gap:12px;margin-bottom:12px}}
.kpi-card{{flex:1;background:#fff;border-radius:6px;padding:14px 18px;
           box-shadow:0 1px 4px rgba(0,0,0,.1)}}
.kpi-value{{font-size:26px;font-weight:700;line-height:1.2}}
.kpi-label{{font-size:11px;color:{_TEXT_LIGHT};margin-top:4px}}
.row-2col{{display:flex;gap:12px;margin-bottom:12px}}
.row-full{{margin-bottom:12px}}
.col{{flex:1;min-width:0}}
.chart-cell{{background:#fff;border-radius:6px;
             box-shadow:0 1px 4px rgba(0,0,0,.1);padding:4px}}
@media(max-width:760px){{
  .row-2col{{flex-direction:column}}
  .kpi-row{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}}
  .kpi-card{{min-width:0;padding:12px}}
  .kpi-value{{font-size:22px;overflow-wrap:anywhere}}
  .header h1{{font-size:16px}}
}}
</style>
</head>
<body>
<div class="header">
  <h1>{title}</h1>
  {sub_html}
</div>
{body}
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard 1 — 总览看板
# ═══════════════════════════════════════════════════════════════════════════════

def _chart_daily_trend(df: pd.DataFrame) -> Line:
    daily = daily_agg(df)
    dates = daily["date"].dt.strftime("%Y-%m-%d").tolist()
    years = sorted(daily["year"].unique())
    _yr_colors = ["#90CAF9", "#1565C0", "#66BB6A", "#E91E63", "#FF9800", "#9C27B0"]
    year_color = {y: _yr_colors[i % len(_yr_colors)] for i, y in enumerate(years)}

    line = Line(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    line.add_xaxis(dates)

    for yr in years:
        sub = daily[daily["year"] == yr]
        y_vals = [None] * len(daily)
        for idx in sub.index:
            pos = daily.index.get_loc(idx)
            y_vals[pos] = round(float(sub.loc[idx, "cnt"]), 1)
        line.add_yaxis(
            str(yr), y_vals, is_smooth=False,
            linestyle_opts=opts.LineStyleOpts(width=1, opacity=0.5, color=year_color[yr]),
            label_opts=opts.LabelOpts(is_show=False),
            symbol_size=0,
            areastyle_opts=opts.AreaStyleOpts(opacity=0.1, color=year_color[yr]),
        )

    line.add_yaxis(
        "30日均线", daily["cnt_ma30"].round(1).tolist(),
        is_smooth=True,
        linestyle_opts=opts.LineStyleOpts(width=2.5, color="#E91E63"),
        label_opts=opts.LabelOpts(is_show=False),
        symbol_size=0, z=10,
    )
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="每日骑行量趋势（含30日移动均线）"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        legend_opts=opts.LegendOpts(pos_top="8%"),
        xaxis_opts=opts.AxisOpts(type_="category",
                                  axislabel_opts=opts.LabelOpts(rotate=30, font_size=9)),
        yaxis_opts=opts.AxisOpts(name="日骑行量"),
        datazoom_opts=[
            opts.DataZoomOpts(type_="inside"),
            opts.DataZoomOpts(type_="slider", range_start=0, range_end=100),
        ],
    )
    return line


def _chart_monthly_bar(df: pd.DataFrame) -> Bar:
    monthly = monthly_agg(df)
    years = sorted(monthly["year"].unique())
    _yr_colors = ["#5C6BC0", "#EF5350", "#66BB6A", "#FF9800", "#9C27B0", "#00BCD4"]

    bar = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bar.add_xaxis(MONTH_ABBR)
    for i, yr in enumerate(years):
        sub = monthly[monthly["year"] == yr].set_index("month").reindex(range(1, 13))
        values = (sub["cnt"].fillna(0) / 1e6).round(3).tolist()
        bar.add_yaxis(
            str(yr), values,
            itemstyle_opts=opts.ItemStyleOpts(color=_yr_colors[i % len(_yr_colors)], opacity=0.85),
            label_opts=opts.LabelOpts(is_show=False),
        )
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="月度骑行总量（按年度分组）"),
        tooltip_opts=opts.TooltipOpts(trigger="axis",
            formatter=JsCode("function(p){return p[0].axisValue+'<br/>'+p.map(function(i){return i.marker+i.seriesName+': '+i.value.toFixed(2)+'M';}).join('<br/>');}")),
        legend_opts=opts.LegendOpts(pos_top="8%"),
        xaxis_opts=opts.AxisOpts(name="月份"),
        yaxis_opts=opts.AxisOpts(name="骑行量 (M)"),
    )
    return bar


def _chart_cumulative(df: pd.DataFrame) -> Line:
    daily = daily_agg(df)
    dates = daily["date"].dt.strftime("%Y-%m-%d").tolist()
    cumsum = (daily["cnt_cumsum"] / 1e6).round(3).tolist()

    line = Line(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    line.add_xaxis(dates)
    line.add_yaxis(
        "累计骑行量", cumsum, is_smooth=True,
        linestyle_opts=opts.LineStyleOpts(width=2, color=_ACCENT),
        label_opts=opts.LabelOpts(is_show=False),
        symbol_size=0,
        areastyle_opts=opts.AreaStyleOpts(opacity=0.2, color=_ACCENT),
    )
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="累计骑行量增长曲线"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(type_="category",
                                  axislabel_opts=opts.LabelOpts(rotate=30, font_size=9)),
        yaxis_opts=opts.AxisOpts(name="累计量 (M)"),
    )
    return line


def echarts_overview_dashboard(df: pd.DataFrame, output_path: str | Path | None = None) -> str:
    daily = daily_agg(df)
    total_rides = df["cnt"].sum()
    avg_daily = daily["cnt"].mean()
    peak_hour = int(df.groupby("hour")["cnt"].mean().idxmax())
    avg_temp = df["temp"].mean()
    date_min = df["ts"].min().strftime("%Y-%m-%d")
    date_max = df["ts"].max().strftime("%Y-%m-%d")

    kpi = _kpi_section([
        (f"{total_rides / 1e6:.1f}M", "总骑行次数", "#3F51B5"),
        (f"{avg_daily:,.0f}", "日均骑行量", "#009688"),
        (f"{peak_hour:02d}:00", "高峰时段", "#FF9800"),
        (f"{avg_temp:.1f}°C", "平均气温", "#E91E63"),
    ])

    sections: list = [
        kpi,
        _chart_fragment(_chart_daily_trend(df), height="380px"),
        (_chart_fragment(_chart_monthly_bar(df), height="360px"),
         _chart_fragment(_chart_cumulative(df), height="360px")),
    ]
    html = _render_dashboard_html(
        sections,
        title="London Santander Cycles — 总览看板",
        subtitle=f"数据时段：{date_min} 至 {date_max}  |  数据源：TfL Open Data + Open-Meteo",
    )
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard 2 — 时间模式看板
# ═══════════════════════════════════════════════════════════════════════════════

def _chart_hourly_profile(df: pd.DataFrame) -> Line:
    hourly = hourly_agg(df)
    type_colors = {"工作日": "#3F51B5", "周末": "#FF9800", "节假日": "#E91E63"}
    type_ls = {"工作日": "solid", "周末": "dashed", "节假日": "dotted"}

    line = Line(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    line.add_xaxis(list(range(24)))

    _peak_markarea = opts.MarkAreaOpts(
        data=[[{"xAxis": 7, "name": "早高峰"}, {"xAxis": 9}],
              [{"xAxis": 17, "name": "晚高峰"}, {"xAxis": 19}]],
        itemstyle_opts=opts.ItemStyleOpts(color="#FFCDD2", opacity=0.3),
        label_opts=opts.LabelOpts(position="insideTop", font_size=10, color="#E91E63"),
    )

    for i, (dtype, grp) in enumerate(hourly.groupby("day_type", observed=True)):
        dtype_str = str(dtype)
        grp = grp.sort_values("hour")
        line.add_yaxis(
            dtype_str, grp["avg_cnt"].round(1).tolist(), is_smooth=True,
            linestyle_opts=opts.LineStyleOpts(width=2.5,
                color=type_colors.get(dtype_str, "#999"),
                type_=type_ls.get(dtype_str, "solid")),
            label_opts=opts.LabelOpts(is_show=False), symbol_size=5,
            areastyle_opts=opts.AreaStyleOpts(opacity=0.08),
            markarea_opts=_peak_markarea if i == 0 else opts.MarkAreaOpts(),
        )

    line.set_global_opts(
        title_opts=opts.TitleOpts(title="24小时骑行量剖面（按日类型）"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        legend_opts=opts.LegendOpts(pos_top="6%", pos_right="5%"),
        xaxis_opts=opts.AxisOpts(name="时段（小时）", min_=0, max_=23),
        yaxis_opts=opts.AxisOpts(name="平均骑行量"),
    )
    return line


def _chart_month_hour_heatmap(df: pd.DataFrame) -> HeatMap:
    pivot = hour_month_pivot(df)
    data = []
    for hour_idx in pivot.index:
        for month_col in pivot.columns:
            data.append([int(hour_idx), int(month_col) - 1, round(float(pivot.loc[hour_idx, month_col]), 1)])
    vmin = min(d[2] for d in data)
    vmax = max(d[2] for d in data)

    hm = HeatMap(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    hm.add_xaxis([str(h) for h in range(24)])
    hm.add_yaxis("平均骑行量", MONTH_ABBR, data, label_opts=opts.LabelOpts(is_show=False))
    hm.set_global_opts(
        title_opts=opts.TitleOpts(title="月份 × 小时 平均骑行量热力图"),
        tooltip_opts=opts.TooltipOpts(
            formatter=JsCode("function(p){return '月份: '+['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][p.value[1]]+'<br/>时段: '+p.value[0]+'h<br/>均量: '+p.value[2];}")),
        visualmap_opts=opts.VisualMapOpts(
            min_=vmin,
            max_=vmax,
            orient="horizontal",
            pos_bottom="1%",
            pos_left="center",
            is_calculable=False,
            range_text=["高", "低"],
            item_width=14,
            item_height=120,
            range_color=["#EDE7F6", "#7986CB", "#1A237E"],
        ),
        xaxis_opts=opts.AxisOpts(type_="category"),
        yaxis_opts=opts.AxisOpts(type_="category"),
    )
    return hm


def _chart_weekday_boxplot(df: pd.DataFrame) -> Boxplot:
    wd = weekday_daily(df)
    labels_short = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    raw_data = [wd[wd["weekday_label"] == day]["cnt"].dropna().tolist() for day in WEEKDAY_ORDER]

    bp = Boxplot(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bp.add_xaxis(labels_short)
    bp.add_yaxis("日均骑行量", bp.prepare_data(raw_data),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode("function(p){return (p.dataIndex>=5)?'#EF5350':'#5C6BC0';}")))
    bp.set_global_opts(
        title_opts=opts.TitleOpts(title="各星期日均骑行量分布"),
        tooltip_opts=opts.TooltipOpts(trigger="item"),
        xaxis_opts=opts.AxisOpts(name="星期"),
        yaxis_opts=opts.AxisOpts(name="日骑行量"),
    )
    return bp


def _chart_daytype_bar(df: pd.DataFrame) -> Bar:
    dt = day_type_agg(df)
    dt_labels = [str(x) for x in dt["day_type"]]
    means = dt["mean"].round(0).tolist()
    stds = dt["std"].round(0).tolist()
    type_colors = {"工作日": "#3F51B5", "周末": "#FF9800", "节假日": "#E91E63"}
    colors = [type_colors.get(l, "#999") for l in dt_labels]

    bar = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bar.add_xaxis(dt_labels)
    bar.add_yaxis("日均骑行量", means,
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(p){{var c={colors!r};return c[p.dataIndex];}}")),
        label_opts=opts.LabelOpts(is_show=True, position="top",
            formatter=JsCode(f"function(p){{var s={stds!r};return p.value.toLocaleString()+' ±'+s[p.dataIndex].toLocaleString();}}")))
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="工作日 / 周末 / 节假日 日均骑行量"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="日类型"),
        yaxis_opts=opts.AxisOpts(name="日均骑行量"),
    )
    return bar


def echarts_time_pattern_dashboard(df: pd.DataFrame, output_path: str | Path | None = None) -> str:
    sections = [
        (_chart_fragment(_chart_hourly_profile(df), height="400px"),
         _chart_fragment(_chart_month_hour_heatmap(df), height="400px")),
        (_chart_fragment(_chart_weekday_boxplot(df), height="380px"),
         _chart_fragment(_chart_daytype_bar(df), height="380px")),
    ]
    html = _render_dashboard_html(sections,
        title="London Santander Cycles — 时间模式看板",
        subtitle="小时、星期、月份、日类型的骑行规律分析")
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard 3 — 环境因素看板
# ═══════════════════════════════════════════════════════════════════════════════

def _chart_temp_scatter(df: pd.DataFrame) -> Scatter:
    scatter = Scatter(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    sample_size = min(3000, len(df))
    sample = df.dropna(subset=["temp", "cnt"]).sample(sample_size, random_state=42)

    all_temps = sample["temp"].round(1).tolist()
    scatter.add_xaxis(all_temps)

    for season in SEASON_ORDER:
        mask = (sample["season"] == season).values
        y_vals = [int(row["cnt"]) if m else None
                  for m, (_, row) in zip(mask, sample.iterrows())]
        scatter.add_yaxis(season, y_vals, symbol_size=4,
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(color=SEASON_COLORS[season], opacity=0.35))

    x_all = df["temp"].dropna().values
    y_all = df.loc[df["temp"].notna(), "cnt"].values
    mask = np.isfinite(x_all) & np.isfinite(y_all)
    z = np.polyfit(x_all[mask], y_all[mask], 2)
    p = np.poly1d(z)
    x_line = np.linspace(x_all[mask].min(), x_all[mask].max(), 60)
    trend_pts = [[round(float(x), 1), round(float(p(x)), 1)] for x in x_line]

    scatter.set_global_opts(
        title_opts=opts.TitleOpts(title="气温 vs 小时骑行量（按季节着色）"),
        tooltip_opts=opts.TooltipOpts(trigger="item"),
        legend_opts=opts.LegendOpts(pos_top="8%"),
        xaxis_opts=opts.AxisOpts(name="气温 (°C)", type_="value"),
        yaxis_opts=opts.AxisOpts(name="小时骑行量"),
    )
    scatter.options["series"].append({
        "type": "line", "name": "拟合趋势", "data": trend_pts,
        "smooth": True, "showSymbol": False,
        "lineStyle": {"color": "#D32F2F", "width": 2.5}, "z": 10,
    })
    return scatter


def _chart_weather_bar(df: pd.DataFrame) -> Bar:
    w_stats = weather_group_agg(df).dropna(subset=["mean"])
    labels = [str(w) for w in w_stats["weather"]]
    means = w_stats["mean"].round(0).tolist()
    colors = [WEATHER_COLORS.get(l, "#999") for l in labels]

    bar = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bar.add_xaxis(labels)
    bar.add_yaxis("日均骑行量", means,
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(p){{var c={colors!r};return c[p.dataIndex];}}")),
        label_opts=opts.LabelOpts(is_show=True, position="right"))
    bar.reversal_axis()
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="天气类别 vs 日均骑行量"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="日均骑行量"),
        yaxis_opts=opts.AxisOpts(name="天气类型", type_="category"),
    )
    return bar


def _chart_rain_boxplot(df: pd.DataFrame) -> Boxplot:
    groups = ["无雨/雪", "雨/雪天"]
    raw = [df[df["is_rainy"] == k]["cnt"].dropna().tolist() for k in [0, 1]]
    bp = Boxplot(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bp.add_xaxis(groups)
    bp.add_yaxis("小时骑行量", bp.prepare_data(raw),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode("function(p){return p.dataIndex===0?'#66BB6A':'#78909C';}")))
    bp.set_global_opts(
        title_opts=opts.TitleOpts(title="降水对骑行量的影响"),
        tooltip_opts=opts.TooltipOpts(trigger="item"),
        xaxis_opts=opts.AxisOpts(name="天气状态"),
        yaxis_opts=opts.AxisOpts(name="小时骑行量"),
    )
    return bp


def _chart_correlation_heatmap(df: pd.DataFrame) -> HeatMap:
    corr_df = correlation_features(df)
    corr_mat = corr_df.corr()
    labels = list(corr_mat.columns)
    data = []
    for i, row_label in enumerate(labels):
        for j, col_label in enumerate(labels):
            data.append([j, i, round(float(corr_mat.loc[row_label, col_label]), 3)])

    hm = HeatMap(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    hm.add_xaxis(labels)
    hm.add_yaxis("Pearson", labels, data,
        label_opts=opts.LabelOpts(is_show=True,
            formatter=JsCode("function(p){return p.value[2].toFixed(2);}"), font_size=9))
    hm.set_global_opts(
        title_opts=opts.TitleOpts(title="环境特征相关性热力图（Pearson）"),
        tooltip_opts=opts.TooltipOpts(
            formatter=JsCode("function(p){return p.value[0]+' × '+p.value[1]+'<br/>r = '+p.value[2];}")),
        visualmap_opts=opts.VisualMapOpts(min_=-1, max_=1, orient="horizontal", pos_bottom="2%",
                                          is_calculable=True, range_color=["#2166AC", "#F7F7F7", "#B2182B"]),
        xaxis_opts=opts.AxisOpts(type_="category", axislabel_opts=opts.LabelOpts(rotate=30, font_size=9)),
        yaxis_opts=opts.AxisOpts(type_="category"),
    )
    return hm


def _chart_humidity_wind_scatter(df: pd.DataFrame) -> Scatter:
    sample = df.dropna(subset=["humidity", "wind_speed", "cnt"]).sample(
        min(2000, len(df)), random_state=42)
    max_cnt = float(sample["cnt"].max())

    sc = Scatter(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    sc.add_xaxis(sample["humidity"].round(1).tolist())
    y_data = [[round(float(r["wind_speed"]), 1), int(r["cnt"])] for _, r in sample.iterrows()]
    sc.add_yaxis("骑行量", y_data,
        symbol_size=JsCode(f"function(v){{return Math.max(4, v[2]/{max_cnt}*25);}}"),
        label_opts=opts.LabelOpts(is_show=False),
        itemstyle_opts=opts.ItemStyleOpts(opacity=0.45, color=_ACCENT))
    sc.set_global_opts(
        title_opts=opts.TitleOpts(title="湿度 vs 风速（气泡大小 = 骑行量）"),
        tooltip_opts=opts.TooltipOpts(
            formatter=JsCode("function(p){return '湿度: '+p.value[0]+'%<br/>风速: '+p.value[1]+' km/h<br/>骑行量: '+p.value[2];}")),
        xaxis_opts=opts.AxisOpts(name="相对湿度 (%)", type_="value"),
        yaxis_opts=opts.AxisOpts(name="风速 (km/h)"),
        visualmap_opts=opts.VisualMapOpts(min_=0, max_=max_cnt, dimension=2,
            orient="horizontal", pos_bottom="2%", is_calculable=True,
            range_color=["#d7ecff", "#2196F3", "#0D47A1"]),
    )
    return sc


def echarts_environmental_dashboard(df: pd.DataFrame, output_path: str | Path | None = None) -> str:
    sections = [
        _chart_fragment(_chart_temp_scatter(df), height="420px"),
        (_chart_fragment(_chart_weather_bar(df), height="360px"),
         _chart_fragment(_chart_rain_boxplot(df), height="360px")),
        (_chart_fragment(_chart_correlation_heatmap(df), height="420px"),
         _chart_fragment(_chart_humidity_wind_scatter(df), height="420px")),
    ]
    html = _render_dashboard_html(sections,
        title="London Santander Cycles — 环境因素看板",
        subtitle="气温、天气、湿度、风速、降水对骑行量的影响分析")
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard 4 — 站点与行程看板（含 Sankey 流向图）
# ═══════════════════════════════════════════════════════════════════════════════

def _chart_top_stations(trip_df: pd.DataFrame) -> Bar:
    top = trip_df["start_station"].value_counts().head(15)[::-1]
    names = [n[:30] + ("…" if len(str(n)) > 30 else "") for n in top.index]
    counts = top.values.tolist()

    bar = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bar.add_xaxis(names)
    bar.add_yaxis("出行次数", counts,
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(p){{var t=p.dataIndex/{max(len(names)-1,1)};"
                         f"return 'rgb('+Math.round(90+t*80)+','+Math.round(130+t*60)+','+Math.round(180+t*40)+')';}}")),
        label_opts=opts.LabelOpts(is_show=True, position="right", font_size=9))
    bar.reversal_axis()
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="最热门出发站点 Top 15"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="出行次数"),
        yaxis_opts=opts.AxisOpts(type_="category",
                                  axislabel_opts=opts.LabelOpts(font_size=8)),
    )
    return bar


def _chart_duration_dist(trip_df: pd.DataFrame) -> Bar:
    dur = trip_df[trip_df["duration_min"] <= 60]["duration_min"].dropna()
    counts, bin_edges = np.histogram(dur, bins=60, range=(0, 60))
    bin_centers = [(bin_edges[i] + bin_edges[i + 1]) / 2 for i in range(len(bin_edges) - 1)]
    x_labels = [f"{b:.0f}" for b in bin_centers]
    median_val = float(dur.median())

    bar = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bar.add_xaxis(x_labels)
    bar.add_yaxis("出行次数", counts.tolist(),
        itemstyle_opts=opts.ItemStyleOpts(color="#5C6BC0", opacity=0.75),
        label_opts=opts.LabelOpts(is_show=False), bar_width="90%",
        markline_opts=opts.MarkLineOpts(
            data=[opts.MarkLineItem(x=f"{median_val:.0f}", name=f"中位数 {median_val:.1f}")],
            linestyle_opts=opts.LineStyleOpts(color="#FF9800", width=2, type_="dashed")))
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="行程时长分布（1–60分钟）", subtitle=f"中位数 {median_val:.1f} min"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="行程时长（分钟）",
                                  axislabel_opts=opts.LabelOpts(interval=9)),
        yaxis_opts=opts.AxisOpts(name="出行次数"),
    )
    return bar


def _chart_hourly_trips(trip_df: pd.DataFrame) -> Line:
    hourly = trip_df.groupby("start_hour").size().reindex(range(24), fill_value=0)

    line = Line(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    line.add_xaxis(list(range(24)))
    line.add_yaxis("出行次数", hourly.tolist(), is_smooth=True,
        linestyle_opts=opts.LineStyleOpts(width=2.5, color=_ACCENT),
        label_opts=opts.LabelOpts(is_show=False), symbol_size=5,
        areastyle_opts=opts.AreaStyleOpts(opacity=0.25, color=_ACCENT),
        markpoint_opts=opts.MarkPointOpts(
            data=[opts.MarkPointItem(type_="max", name="高峰")],
            label_opts=opts.LabelOpts(
                formatter=JsCode("function(p){return p.name+'\\n'+p.value.toLocaleString()+'次';}"),
                font_size=10)))
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="各时段出行次数（小时分布）"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="时段（小时）", min_=0, max_=23),
        yaxis_opts=opts.AxisOpts(name="出行次数"),
    )
    return line


def _chart_top_routes(trip_df: pd.DataFrame) -> Bar:
    routes = (
        trip_df[trip_df["start_station"] != trip_df["end_station"]]
        .groupby(["start_station", "end_station"]).size()
        .nlargest(10).reset_index(name="count")[::-1].reset_index(drop=True)
    )
    labels = [f"{r['start_station'][:20]}→{r['end_station'][:20]}" for _, r in routes.iterrows()]
    counts = routes["count"].tolist()
    n = len(labels)

    bar = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bar.add_xaxis(labels)
    bar.add_yaxis("出行次数", counts,
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(p){{var t=p.dataIndex/{max(n-1,1)};"
                         f"return 'rgb('+Math.round(200+t*30)+','+Math.round(120+t*60)+','+Math.round(30+t*20)+')';}}")),
        label_opts=opts.LabelOpts(is_show=True, position="right", font_size=8))
    bar.reversal_axis()
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="最热门出行路线 Top 10（出发→目的）"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="出行次数"),
        yaxis_opts=opts.AxisOpts(type_="category",
                                  axislabel_opts=opts.LabelOpts(font_size=7)),
    )
    return bar


def _chart_od_sankey(trip_df: pd.DataFrame, top_n: int = 20) -> Sankey:
    """跨站 OD 流向 Sankey 图（样本 Top N 站对）。"""
    valid = trip_df.dropna(subset=["start_station", "end_station"])
    cross_station = valid[valid["start_station"] != valid["end_station"]]
    routes = (
        cross_station
        .groupby(["start_station", "end_station"]).size()
        .nlargest(top_n).reset_index(name="count")
    )
    coverage = routes["count"].sum() / max(len(cross_station), 1)
    nodes_set: set[str] = set()
    for _, r in routes.iterrows():
        s = "O|" + str(r["start_station"])
        e = "D|" + str(r["end_station"])
        nodes_set.add(s)
        nodes_set.add(e)

    nodes = [{"name": n} for n in sorted(nodes_set)]
    links = []
    for _, r in routes.iterrows():
        links.append({
            "source": "O|" + str(r["start_station"]),
            "target": "D|" + str(r["end_station"]),
            "value": int(r["count"]),
        })

    sankey = Sankey(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    sankey.add(
        "OD流向", nodes, links,
        linestyle_opt=opts.LineStyleOpts(opacity=0.3, curve=0.5, color="source"),
        label_opts=opts.LabelOpts(
            font_size=8,
            position="right",
            formatter=JsCode(
                "function(p){var n=p.name.substring(2);"
                "return n.length>28?n.substring(0,28)+'…':n;}"
            ),
        ),
        node_width=20, node_gap=12,
    )
    sankey.set_global_opts(
        title_opts=opts.TitleOpts(
            title=f"跨站 OD 流向（样本 Top {top_n}）",
            subtitle=f"已排除同站归还；覆盖样本跨站行程 {coverage:.2%}",
        ),
        tooltip_opts=opts.TooltipOpts(trigger="item"),
    )
    return sankey


def echarts_station_trip_dashboard(trip_df: pd.DataFrame, output_path: str | Path | None = None) -> str:
    sections = [
        (_chart_fragment(_chart_top_stations(trip_df), height="440px"),
         _chart_fragment(_chart_duration_dist(trip_df), height="440px")),
        (_chart_fragment(_chart_top_routes(trip_df), height="420px"),
         _chart_fragment(_chart_hourly_trips(trip_df), height="420px")),
        _chart_fragment(_chart_od_sankey(trip_df), height="500px"),
    ]
    html = _render_dashboard_html(sections,
        title="London Santander Cycles — 站点与行程分析看板",
        subtitle="基于 TfL Santander Cycles 行程数据（2020-2025）")
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard 5 — 季节与构成看板
# ═══════════════════════════════════════════════════════════════════════════════

def _chart_season_boxplot(df: pd.DataFrame) -> Boxplot:
    raw = [df[df["season"] == s]["cnt"].dropna().tolist() for s in SEASON_ORDER]
    bp = Boxplot(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    bp.add_xaxis(SEASON_ORDER)
    bp.add_yaxis("小时骑行量", bp.prepare_data(raw),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode(f"function(p){{var c={[SEASON_COLORS[s] for s in SEASON_ORDER]!r};return c[p.dataIndex];}}")))
    bp.set_global_opts(
        title_opts=opts.TitleOpts(title="各季节小时骑行量分布"),
        tooltip_opts=opts.TooltipOpts(trigger="item"),
        xaxis_opts=opts.AxisOpts(name="季节"),
        yaxis_opts=opts.AxisOpts(name="小时骑行量"),
    )
    return bp


def _chart_season_radar(df: pd.DataFrame) -> Radar:
    metric_labels = ["骑行量", "气温", "湿度", "风速"]
    season_vals: dict[str, list[float]] = {}
    for s in SEASON_ORDER:
        sub = df[df["season"] == s]
        if sub.empty:
            continue
        season_vals[s] = [
            float(sub["cnt"].mean()),
            float(sub["temp"].mean()) if sub["temp"].notna().any() else 0,
            float(sub["humidity"].mean()) if sub["humidity"].notna().any() else 0,
            float(sub["wind_speed"].mean()) if sub["wind_speed"].notna().any() else 0,
        ]

    if not season_vals:
        return Radar()

    all_v = np.array(list(season_vals.values()))
    vmin = all_v.min(axis=0)
    vmax = all_v.max(axis=0)
    span = np.where(vmax - vmin > 0, vmax - vmin, 1.0)

    radar = Radar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    radar.add_schema(schema=[
        opts.RadarIndicatorItem(name=metric_labels[i], max_=1.1, min_=0)
        for i in range(len(metric_labels))
    ])
    for s, raw in season_vals.items():
        norm = [round(float((v - vmin[i]) / span[i]), 2) for i, v in enumerate(raw)]
        radar.add(s, [norm], color=SEASON_COLORS[s],
                  areastyle_opts=opts.AreaStyleOpts(opacity=0.12),
                  linestyle_opts=opts.LineStyleOpts(width=2),
                  label_opts=opts.LabelOpts(is_show=False))
    radar.set_global_opts(
        title_opts=opts.TitleOpts(title="季节多维指标雷达图（归一化）"),
        legend_opts=opts.LegendOpts(pos_bottom="2%"),
        tooltip_opts=opts.TooltipOpts(
            formatter=JsCode("function(p){var dims=['骑行量','气温','湿度','风速'];"
                             "var s=p.seriesName+'<br/>';"
                             "for(var i=0;i<dims.length;i++){s+=dims[i]+': '+p.value[i].toFixed(2)+'<br/>';}"
                             "return s;}")),
    )
    return radar


def _chart_calendar_heatmap(df: pd.DataFrame) -> list:
    cal_data_raw = calendar_heatmap_data(df)
    cal_data_raw["date"] = pd.to_datetime(cal_data_raw["date"])
    years = sorted(cal_data_raw["date"].dt.year.unique())
    vmax = float(cal_data_raw["cnt"].max())
    vmin = float(cal_data_raw["cnt"].min())

    charts = []
    for yr in years:
        sub = cal_data_raw[cal_data_raw["date"].dt.year == yr]
        pairs = [[d.strftime("%Y-%m-%d"), int(v)] for d, v in zip(sub["date"], sub["cnt"])]
        cal = Calendar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
        cal.add("", pairs,
            calendar_opts=opts.CalendarOpts(range_=str(yr), orient="horizontal",
                pos_top="50", pos_left="40", pos_right="30",
                cell_size=["auto", 18],
                daylabel_opts=opts.CalendarDayLabelOpts(name_map="cn"),
                monthlabel_opts=opts.CalendarMonthLabelOpts(name_map="cn")))
        cal.set_global_opts(
            title_opts=opts.TitleOpts(title=f"日历骑行量热力图 — {yr}"),
            tooltip_opts=opts.TooltipOpts(
                formatter=JsCode("function(p){return p.value[0]+'<br/>骑行量: '+p.value[1].toLocaleString();}")),
            visualmap_opts=opts.VisualMapOpts(min_=vmin, max_=vmax, orient="horizontal",
                pos_bottom="0%", pos_left="center", is_calculable=True,
                range_color=["#EDE7F6", "#7986CB", "#1A237E"]))
        charts.append(cal)
    return charts


def echarts_season_composition_dashboard(df: pd.DataFrame, output_path: str | Path | None = None) -> str:
    cal_charts = _chart_calendar_heatmap(df)
    cal_frags = [_chart_fragment(c, height="280px") for c in cal_charts]
    cal_section = "".join(f'<div class="row-full">{f}</div>' for f in cal_frags)

    sections: list = [
        (_chart_fragment(_chart_season_boxplot(df), height="420px"),
         _chart_fragment(_chart_season_radar(df), height="420px")),
        cal_section,
    ]
    html = _render_dashboard_html(sections,
        title="London Santander Cycles — 季节与时序构成看板",
        subtitle="季节规律、多维季节对比与日历级骑行热力图")
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def render_all_echarts_dashboards(
    df: pd.DataFrame,
    trip_df: pd.DataFrame,
    output_dir: str | Path = "output",
) -> dict[str, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dashboards = {
        "echarts_01_overview": (echarts_overview_dashboard, (df,)),
        "echarts_02_time_pattern": (echarts_time_pattern_dashboard, (df,)),
        "echarts_03_environmental": (echarts_environmental_dashboard, (df,)),
        "echarts_04_station_trip": (echarts_station_trip_dashboard, (trip_df,)),
        "echarts_05_season": (echarts_season_composition_dashboard, (df,)),
    }
    results: dict[str, Path] = {}
    for name, (func, args) in dashboards.items():
        path = out / f"{name}.html"
        func(*args, output_path=path)
        results[name] = path
        print(f"  ✓ {path}")
    return results


def display_echarts_inline(html_str: str, height: str = "580px") -> None:
    """在 Jupyter Notebook 中以 srcdoc 方式内联展示 ECharts 看板。

    使用 iframe srcdoc 属性直接嵌入 HTML，兼容 JupyterLab / Notebook / VS Code
    等环境的 Content Security Policy，避免 data URI 被拦截导致图表空白。
    """
    import html as _html
    from IPython.display import HTML, display
    escaped = _html.escape(html_str)
    iframe = (
        f'<iframe srcdoc="{escaped}" '
        f'width="100%" height="{height}" frameborder="0" '
        f'style="border:none;display:block;"></iframe>'
    )
    display(HTML(iframe))
