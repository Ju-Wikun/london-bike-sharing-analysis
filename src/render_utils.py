"""在 Jupyter / VS Code 中可靠显示 Pyecharts 图表。

显示策略（默认 inline=True）
-----------------------------
render_notebook() 的传统方案把图表存到 output/nb_charts/，再用
  <iframe src="http://localhost:8888/files/...">
渲染。PDF 导出时 Jupyter 把 src 改写为 file:/// 绝对路径，浏览器安全
策略拒绝加载，导致 PDF 中图表空白。

修复方案：inline=True（默认）将完整 HTML 编码为 base64 data URI，
直接嵌入 iframe src，彻底绕开文件路径依赖。
设置 inline=False 可恢复旧有 /files/ 路径方案（需要 Jupyter 服务器运行）。
"""

from __future__ import annotations

import base64
import re
import uuid
from pathlib import Path

from IPython.display import HTML, IFrame, display

PROJECT_ROOT = Path(__file__).resolve().parent
CHART_DIR = PROJECT_ROOT / "output" / "nb_charts"

ECHARTS_CDN = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"
ECHARTS_CDN_FALLBACK = "https://cdn.bootcdn.net/ajax/libs/echarts/5.4.3/echarts.min.js"


def _patch_html(html_path: Path) -> None:
    """替换 ECharts CDN 链接并注入备用 CDN。"""
    text = html_path.read_text(encoding="utf-8")
    text = re.sub(
        r'https?://[^"\']+/echarts\.min\.js',
        ECHARTS_CDN,
        text,
        count=1,
    )
    fallback = (
        f'<script>if(typeof echarts==="undefined"){{'
        f'document.write(\'<script src="{ECHARTS_CDN_FALLBACK}"><\\/script>\');}}</script>'
    )
    text = text.replace("</head>", f"{fallback}\n</head>", 1)
    html_path.write_text(text, encoding="utf-8")


def _save_chart_html(chart) -> Path:
    """将 pyecharts 图表保存到 output/nb_charts/ 目录。"""
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    html_path = CHART_DIR / f"chart_{uuid.uuid4().hex[:8]}.html"
    chart.render(str(html_path))
    _patch_html(html_path)
    return html_path


def _show_inline(html_path: Path, height: str) -> None:
    """以 base64 data URI 内联显示（PDF 友好，无路径依赖）。"""
    b64 = base64.b64encode(html_path.read_bytes()).decode()
    iframe_html = (
        f'<iframe src="data:text/html;base64,{b64}" '
        f'width="100%" height="{height}" frameborder="0" '
        f'style="border:none;display:block;border-radius:4px;'
        f'box-shadow:0 1px 4px rgba(0,0,0,.12);"></iframe>'
    )
    display(HTML(iframe_html))


def _show_files_iframe(html_path: Path, height: str) -> None:
    """以 /files/ 路径 iframe 显示（旧方案，需 Jupyter 服务器）。"""
    try:
        rel = html_path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        rel = html_path.relative_to(PROJECT_ROOT).as_posix()
    files_url = f"/files/{rel}"

    display(
        IFrame(
            src=files_url,
            width="100%",
            height=height,
            style="border:1px solid #ccc;background:#fff;",
        )
    )
    display(
        HTML(
            f'<p style="margin:4px 0;font-size:12px;color:#666;">若上图空白，请 '
            f'<a href="{files_url}" target="_blank" rel="noopener">点此在新标签页打开图表</a>'
            f'（或本地打开：<code>{html_path}</code>）</p>'
        )
    )


def show_chart(chart, height: str = "580px", inline: bool = True) -> Path:
    """在 Notebook 中显示单个 Pyecharts 图表，返回 HTML 文件路径。

    Parameters
    ----------
    chart  : pyecharts 图表对象（Bar / Line / HeatMap / Tab / Page …）
    height : iframe 高度，默认 "580px"
    inline : True（默认）—— base64 data URI 内联，无路径依赖，PDF 导出更稳定；
             False —— /files/ 路径 iframe，需要 Jupyter 服务器运行。
    """
    html_path = _save_chart_html(chart)
    if inline:
        _show_inline(html_path, height)
    else:
        _show_files_iframe(html_path, height)
    return html_path


def show_tab(tab, height: str = "640px", inline: bool = True) -> Path:
    """显示 Tab 多图仪表板（封装 show_chart）。"""
    return show_chart(tab, height=height, inline=inline)


def show_page(page, height: str = "640px", inline: bool = True) -> Path:
    """显示 Page 多图看板（封装 show_chart）。"""
    return show_chart(page, height=height, inline=inline)
