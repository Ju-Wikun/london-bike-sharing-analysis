from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, HeatMap, Line, Sankey
from pyecharts.commons.utils import JsCode

from .dashboard_charts_echarts import (
    _PANEL_BG,
    _chart_fragment,
    _kpi_section,
    _render_dashboard_html,
)


def _short(value: object, limit: int = 30) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _structure_bar(metrics: dict[str, float]) -> Bar:
    cross_pct = float(metrics["cross_station_rate"]) * 100
    same_pct = float(metrics["same_station_rate"]) * 100
    chart = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis(["OD分析就绪行程"])
    chart.add_yaxis(
        "跨站骑行",
        [round(cross_pct, 2)],
        stack="share",
        itemstyle_opts=opts.ItemStyleOpts(color="#3F51B5"),
        label_opts=opts.LabelOpts(formatter="{c}%", position="inside"),
    )
    chart.add_yaxis(
        "同站归还",
        [round(same_pct, 2)],
        stack="share",
        itemstyle_opts=opts.ItemStyleOpts(color="#F9A825"),
        label_opts=opts.LabelOpts(formatter="{c}%", position="inside"),
    )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title="总体空间行为结构"),
        legend_opts=opts.LegendOpts(pos_top=34),
        tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="shadow"),
        yaxis_opts=opts.AxisOpts(name="占比（%）", max_=100),
    )
    return chart


def _coverage_bar(coverage: pd.DataFrame) -> Bar:
    chart = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis([f"Top {int(value):,}" for value in coverage["top_n"]])
    chart.add_yaxis(
        "跨站流量覆盖率",
        (coverage["coverage_rate"] * 100).round(3).tolist(),
        itemstyle_opts=opts.ItemStyleOpts(color="#00897B"),
        label_opts=opts.LabelOpts(is_show=True, formatter="{c}%", font_size=9),
    )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title="Top-N 代表性"),
        legend_opts=opts.LegendOpts(pos_top=34),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=25)),
        yaxis_opts=opts.AxisOpts(name="覆盖率（%）"),
    )
    return chart


def _pareto_curve(routes: pd.DataFrame) -> Line:
    cross = routes.loc[~routes["same_station"]].sort_values(
        "trip_count", ascending=False
    )
    cumulative = cross["trip_count"].cumsum() / cross["trip_count"].sum() * 100
    count = len(cross)
    indices = np.unique(
        np.concatenate(
            [
                np.arange(min(200, count)),
                np.geomspace(1, count, num=min(500, count), dtype=int) - 1,
                np.array([count - 1]),
            ]
        )
    )
    ranks = (indices + 1).tolist()
    values = cumulative.iloc[indices].round(3).tolist()

    chart = Line(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis(ranks)
    chart.add_yaxis(
        "累计跨站流量",
        values,
        is_symbol_show=False,
        linestyle_opts=opts.LineStyleOpts(width=2.5, color="#3F51B5"),
        areastyle_opts=opts.AreaStyleOpts(opacity=0.12, color="#3F51B5"),
        label_opts=opts.LabelOpts(is_show=False),
    )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(
            title="跨站 OD 长尾累计曲线",
            subtitle="横轴为按行程次数排序的 OD 对排名（对数尺度）",
        ),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(type_="log", name="OD对排名", min_=1),
        yaxis_opts=opts.AxisOpts(name="累计覆盖率（%）", min_=0, max_=100),
    )
    chart.options["grid"] = {
        "left": "8%",
        "right": "7%",
        "top": "23%",
        "bottom": "13%",
    }
    return chart


def _cross_sankey(routes: pd.DataFrame, top_n: int = 20) -> Sankey:
    cross = routes.loc[~routes["same_station"]].nlargest(top_n, "trip_count")
    denominator = routes.loc[~routes["same_station"], "trip_count"].sum()
    coverage = cross["trip_count"].sum() / denominator * 100
    nodes_set: set[str] = set()
    links = []
    for row in cross.itertuples():
        source = "O|" + str(row.start_station)
        target = "D|" + str(row.end_station)
        nodes_set.update([source, target])
        links.append({"source": source, "target": target, "value": int(row.trip_count)})

    chart = Sankey(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add(
        "跨站OD",
        [{"name": name} for name in sorted(nodes_set)],
        links,
        linestyle_opt=opts.LineStyleOpts(opacity=0.35, curve=0.5, color="source"),
        label_opts=opts.LabelOpts(
            font_size=8,
            formatter=JsCode(
                "function(p){var n=p.name.substring(2);"
                "return n.length>30?n.substring(0,30)+'…':n;}"
            ),
        ),
        node_width=18,
        node_gap=10,
    )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(
            title=f"全量跨站 OD Top {top_n}",
            subtitle=f"覆盖全部跨站行程 {coverage:.3f}%；只展示最强连接，不代表总体",
        ),
        tooltip_opts=opts.TooltipOpts(trigger="item"),
    )
    return chart


def flow_structure_dashboard(
    metrics: dict[str, float],
    routes: pd.DataFrame,
    coverage: pd.DataFrame,
    output_path: str | Path | None = None,
) -> str:
    top20 = coverage.loc[coverage["top_n"] == 20, "coverage_rate"].iloc[0]
    kpis = [
        ("跨站骑行", f"{metrics['cross_station_rate']:.2%}", "#3F51B5"),
        ("同站归还", f"{metrics['same_station_rate']:.2%}", "#F9A825"),
        ("跨站 OD 组合", f"{int(metrics['cross_od_pairs']):,}", "#00897B"),
        ("Top20 覆盖", f"{top20:.3%}", "#D81B60"),
    ]
    sections = [
        _kpi_section([(value, label, color) for label, value, color in kpis]),
        (
            _chart_fragment(_structure_bar(metrics), height="350px"),
            _chart_fragment(_coverage_bar(coverage), height="350px"),
        ),
        _chart_fragment(_pareto_curve(routes), height="440px"),
        _chart_fragment(_cross_sankey(routes), height="610px"),
    ]
    html = _render_dashboard_html(
        sections,
        title="London Santander Cycles — 全量流向结构",
        subtitle="总体结构、长尾覆盖率与跨站头部连接（58,311,048 条质量过滤行程）",
    )
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html


def _station_balance_bar(balance: pd.DataFrame) -> Bar:
    selected = pd.concat(
        [balance.nlargest(10, "net_inflow"), balance.nsmallest(10, "net_inflow")]
    ).drop_duplicates("station_key")
    selected = selected.sort_values("net_inflow")
    chart = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis([_short(value, 27) for value in selected["canonical_name"]])
    chart.add_yaxis(
        "净流入",
        selected["net_inflow"].astype(int).tolist(),
        itemstyle_opts=opts.ItemStyleOpts(
            color=JsCode("function(p){return p.value>=0?'#00897B':'#E53935';}")
        ),
        label_opts=opts.LabelOpts(is_show=False),
    )
    chart.reversal_axis()
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title="站点累计净流入 / 净流出"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="净流入（流入-流出）"),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=8)),
    )
    chart.options["grid"] = {
        "left": "35%",
        "right": "8%",
        "top": "14%",
        "bottom": "9%",
    }
    return chart


def _throughput_bar(balance: pd.DataFrame) -> Bar:
    selected = balance.nlargest(15, "throughput").sort_values("throughput")
    chart = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis([_short(value, 27) for value in selected["canonical_name"]])
    chart.add_yaxis(
        "吞吐量",
        selected["throughput"].astype(int).tolist(),
        itemstyle_opts=opts.ItemStyleOpts(color="#5C6BC0"),
        label_opts=opts.LabelOpts(is_show=False),
    )
    chart.reversal_axis()
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title="站点总吞吐量 Top 15"),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        xaxis_opts=opts.AxisOpts(name="流入+流出"),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=8)),
    )
    chart.options["grid"] = {
        "left": "35%",
        "right": "8%",
        "top": "14%",
        "bottom": "9%",
    }
    return chart


def _net_heatmap(
    station_period: pd.DataFrame, balance: pd.DataFrame, day_type: str
) -> HeatMap:
    keys = balance.assign(abs_net=balance["net_inflow"].abs()).nlargest(
        15, "abs_net"
    )["station_key"]
    subset = station_period[
        (station_period["station_key"].isin(keys))
        & (station_period["day_type"] == day_type)
    ].copy()
    names = balance.set_index("station_key")["canonical_name"]
    ordered_keys = list(keys)
    data = []
    for y_index, key in enumerate(ordered_keys):
        hourly = (
            subset[subset["station_key"] == key]
            .set_index("hour_of_day")["net_inflow"]
            .reindex(range(24), fill_value=0)
        )
        data.extend([[hour, y_index, int(value)] for hour, value in hourly.items()])
    limit = max(abs(value[2]) for value in data) if data else 1
    chart = HeatMap(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis([str(hour) for hour in range(24)])
    chart.add_yaxis(
        "净流入",
        [_short(names.get(key, key), 24) for key in ordered_keys],
        data,
        label_opts=opts.LabelOpts(is_show=False),
    )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(
            title="工作日小时失衡" if day_type == "workday" else "非工作日小时失衡"
        ),
        tooltip_opts=opts.TooltipOpts(
            formatter=JsCode(
                "function(p){return p.name+'<br/>时段: '+p.value[0]+':00'"
                "+'<br/>净流入: '+p.value[2].toLocaleString();}"
            )
        ),
        visualmap_opts=opts.VisualMapOpts(
            min_=-limit,
            max_=limit,
            orient="horizontal",
            pos_bottom="1%",
            pos_left="center",
            range_color=["#D73027", "#F7F7F7", "#00897B"],
            is_calculable=False,
        ),
    )
    chart.options["grid"] = {
        "left": "34%",
        "right": "5%",
        "top": "16%",
        "bottom": "15%",
    }
    return chart


def _same_station_bar(same_behavior: pd.DataFrame, by_rate: bool) -> Bar:
    frame = same_behavior.copy()
    if by_rate:
        frame = frame[frame["departure_count"] >= 200].nlargest(
            12, "same_station_rate_pct"
        )
        value_column = "same_station_rate_pct"
        title = "同站归还率 Top 12（出发≥200）"
        series = "同站率（%）"
        color = "#F9A825"
    else:
        frame = frame.nlargest(12, "same_station_trips")
        value_column = "same_station_trips"
        title = "同站归还次数 Top 12"
        series = "同站次数"
        color = "#7E57C2"
    frame = frame.sort_values(value_column)
    chart = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis([_short(value, 28) for value in frame["canonical_name"]])
    chart.add_yaxis(
        series,
        frame[value_column].round(2).tolist(),
        itemstyle_opts=opts.ItemStyleOpts(color=color),
        label_opts=opts.LabelOpts(is_show=False),
    )
    chart.reversal_axis()
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title=title),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=8)),
    )
    chart.options["grid"] = {
        "left": "36%",
        "right": "8%",
        "top": "15%",
        "bottom": "8%",
    }
    return chart


def _duration_band_bar(duration: pd.DataFrame) -> Bar:
    chart = Bar(init_opts=opts.InitOpts(bg_color=_PANEL_BG))
    chart.add_xaxis(["跨站骑行", "同站归还"])
    colors = ["#E53935", "#F9A825", "#00897B"]
    for index, column in enumerate(
        ["duration_le_3m_pct", "duration_3_15m_pct", "duration_gt_15m_pct"]
    ):
        label = ["1-3分钟", "3-15分钟", "15分钟以上"][index]
        chart.add_yaxis(
            label,
            duration[column].round(1).tolist(),
            stack="duration",
            itemstyle_opts=opts.ItemStyleOpts(color=colors[index]),
            label_opts=opts.LabelOpts(formatter="{c}%", position="inside"),
        )
    chart.set_global_opts(
        title_opts=opts.TitleOpts(title="同站与跨站骑行时长结构"),
        tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="shadow"),
        yaxis_opts=opts.AxisOpts(name="占比（%）", max_=100),
    )
    return chart


def station_diagnostics_dashboard(
    balance: pd.DataFrame,
    station_period: pd.DataFrame,
    same_behavior: pd.DataFrame,
    duration: pd.DataFrame,
    station_count: int,
    review_station_count: int,
    output_path: str | Path | None = None,
) -> str:
    largest_in = balance.nlargest(1, "net_inflow").iloc[0]
    largest_out = balance.nsmallest(1, "net_inflow").iloc[0]
    kpis = [
        ("候选规范站点", f"{station_count:,}", "#3F51B5"),
        ("映射待复核", f"{review_station_count:,}", "#F9A825"),
        ("最大净流入", _short(largest_in["canonical_name"], 22), "#00897B"),
        ("最大净流出", _short(largest_out["canonical_name"], 22), "#E53935"),
    ]
    sections = [
        _kpi_section([(value, label, color) for label, value, color in kpis]),
        (
            _chart_fragment(_station_balance_bar(balance), height="560px"),
            _chart_fragment(_throughput_bar(balance), height="560px"),
        ),
        (
            _chart_fragment(_net_heatmap(station_period, balance, "workday"), height="520px"),
            _chart_fragment(
                _net_heatmap(station_period, balance, "non_workday"), height="520px"
            ),
        ),
        (
            _chart_fragment(_same_station_bar(same_behavior, False), height="480px"),
            _chart_fragment(_same_station_bar(same_behavior, True), height="480px"),
        ),
        _chart_fragment(_duration_band_bar(duration), height="400px"),
    ]
    html = _render_dashboard_html(
        sections,
        title="London Santander Cycles — 全量站点诊断",
        subtitle="站点平衡、小时失衡与同站归还行为（候选站点映射需结合审计状态解释）",
    )
    if output_path:
        Path(output_path).write_text(html, encoding="utf-8")
    return html
