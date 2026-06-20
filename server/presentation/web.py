"""
Web 展示模块（向后兼容）

Flask 网页服务，提供数据图表展示。
新功能请使用 api.py REST API + client/ 前端。
"""

import io
import logging
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # 非交互后端
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# 让 matplotlib 支持中文
plt.rcParams["font.sans-serif"] = ["SimHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC",
                                   "Source Han Sans CN", "Microsoft YaHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

from flask import Flask, render_template_string, request

logger = logging.getLogger(__name__)

# ── HTML 模板 ─────────────────────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans SC", sans-serif;
            background: #f5f7fa; color: #333; padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; color: #1a1a2e; margin-bottom: 24px; font-weight: 600; }
        .summary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border-radius: 12px; padding: 20px 28px;
            margin-bottom: 24px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }
        .summary h2 { font-size: 18px; margin-bottom: 12px; opacity: 0.9; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
        .summary-item { background: rgba(255,255,255,0.15); border-radius: 8px; padding: 12px 16px; }
        .summary-item .label { font-size: 12px; opacity: 0.8; }
        .summary-item .value { font-size: 24px; font-weight: 700; }
        .chart-container {
            background: white; border-radius: 12px; padding: 20px;
            margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }
        .chart-container h2 { font-size: 16px; color: #555; margin-bottom: 16px; }
        img { width: 100%; height: auto; border-radius: 8px; }
        .data-table {
            background: white; border-radius: 12px; padding: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06); overflow-x: auto;
        }
        .data-table h2 { font-size: 16px; color: #555; margin-bottom: 12px; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th { background: #f0f2f5; padding: 10px 12px; text-align: left; font-weight: 600; }
        td { padding: 8px 12px; border-bottom: 1px solid #eee; }
        tr:hover { background: #f8f9ff; }
        .trend-up { color: #e74c3c; }
        .trend-down { color: #27ae60; }
        .growth-cell { font-weight: 600; }
        .positive { color: #e74c3c; }
        .negative { color: #27ae60; }
        .zero { color: #999; }
        .footer { text-align: center; color: #999; font-size: 12px; margin-top: 20px; padding: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 {{ title }}</h1>

        <div class="summary">
            <h2>📊 数据总览</h2>
            <div class="summary-grid">
                <div class="summary-item">
                    <div class="label">数据条数</div>
                    <div class="value">{{ summary.count }}</div>
                </div>
                <div class="summary-item">
                    <div class="label">指标数</div>
                    <div class="value">{{ summary.indicators }}</div>
                </div>
                {% if summary.date_range %}
                <div class="summary-item">
                    <div class="label">时间范围</div>
                    <div class="value" style="font-size:16px;">{{ summary.date_range }}</div>
                </div>
                {% endif %}
                {% if summary.details and summary.details.values()|first is mapping %}
                {% set first = summary.details.values()|first %}
                <div class="summary-item">
                    <div class="label">最新值</div>
                    <div class="value">{{ first.latest.value }}</div>
                    <div style="font-size:12px;">{{ first.latest.date }}</div>
                </div>
                <div class="summary-item">
                    <div class="label">均值</div>
                    <div class="value">{{ first.mean }}</div>
                </div>
                {% endif %}
            </div>
        </div>

        {% if chart %}
        <div class="chart-container">
            <h2>📈 趋势图</h2>
            <img src="data:image/png;base64,{{ chart }}" alt="CPI 趋势图">
        </div>
        {% endif %}

        {% if growth_chart %}
        <div class="chart-container">
            <h2>📊 同比增长率</h2>
            <img src="data:image/png;base64,{{ growth_chart }}" alt="同比增长率">
        </div>
        {% endif %}

        <div class="data-table">
            <h2>📋 数据明细</h2>
            <table>
                <thead>
                    <tr>
                        <th>日期</th>
                        <th>指标</th>
                        <th>值</th>
                        <th>单位</th>
                        <th>同比增长(%)</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in data[:100] %}
                    <tr>
                        <td>{{ row.date }}</td>
                        <td>{{ row.indicator }}</td>
                        <td class="{% if row.growth is defined and row.growth and row.growth > 0 %}trend-up{% elif row.growth is defined and row.growth and row.growth < 0 %}trend-down{% endif %}">
                            {{ row.value }}
                        </td>
                        <td>{{ row.unit }}</td>
                        <td class="growth-cell">
                            {% if row.growth is defined and row.growth is not none %}
                            <span class="{% if row.growth > 0 %}positive{% elif row.growth < 0 %}negative{% else %}zero{% endif %}">
                                {{ row.growth }}%
                            </span>
                            {% else %}
                            -
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% if data|length > 100 %}
            <p style="text-align:center;color:#999;margin-top:12px;">仅显示前 100 条，共 {{ data|length }} 条</p>
            {% endif %}
        </div>

        <div class="footer">
            数据来源：国家统计局 | THEIA CPI 数据展示系统
        </div>
    </div>
</body>
</html>
"""


# ── 工具函数 ─────────────────────────────────────────────

def _generate_chart(data: list[dict], title: str = "CPI 走势") -> str | None:
    """
    生成折线图并返回 base64 编码的 PNG。

    Args:
        data: 数据列表，每条含 date, value, indicator 字段
        title: 图表标题

    Returns:
        base64 图片字符串，失败时返回 None
    """
    try:
        fig, ax = plt.subplots(figsize=(12, 5))

        # 按指标分组绘图
        by_indicator: dict[str, dict] = {}
        for d in data:
            ind = d.get("indicator", "未知")
            if ind not in by_indicator:
                by_indicator[ind] = {"dates": [], "values": []}
            by_indicator[ind]["dates"].append(d.get("date", ""))
            by_indicator[ind]["values"].append(d.get("value"))

        colors = ["#667eea", "#e74c3c", "#27ae60", "#f39c12", "#9b59b6"]
        for i, (ind, pts) in enumerate(by_indicator.items()):
            color = colors[i % len(colors)]
            ax.plot(pts["dates"], pts["values"], marker="o", label=ind,
                    color=color, linewidth=2, markersize=4)

        ax.set_title(title, fontsize=14, fontweight="bold", pad=16)
        ax.set_ylabel("CPI (上年同月=100)")
        ax.legend(loc="best", fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="x", rotation=45)

        # 只显示部分 x 轴标签避免重叠
        if len(data) > 20:
            step = max(1, len(data) // 15)
            for label in ax.get_xticklabels():
                label.set_visible(False)
            for i, label in enumerate(ax.get_xticklabels()):
                if i % step == 0:
                    label.set_visible(True)

        fig.tight_layout()

        # 输出为 base64
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120)
        plt.close(fig)
        buf.seek(0)

        import base64
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as e:
        logger.warning(f"图表生成失败: {e}")
        return None


# ── Flask 应用 ──────────────────────────────────────────

def create_app(data: list[dict], title: str = "国家统计局数据",
               summary: dict | None = None) -> Flask:
    """
    创建 Flask 应用实例。

    Args:
        data: 展示数据列表
        title: 页面标题
        summary: 趋势摘要字典

    Returns:
        Flask 应用
    """
    app = Flask(__name__)

    @app.route("/")
    def index():
        nonlocal summary
        if summary is None:
            summary = {"count": len(data), "indicators": 0, "date_range": None, "details": {}}

        chart = _generate_chart(data, f"{title} - 趋势图")

        # 如果有增长率字段，生成增长率图表
        growth_data = [d for d in data if d.get("growth") is not None]
        growth_chart = _generate_chart(growth_data, f"{title} - 同比增长率") if growth_data else None

        return render_template_string(
            HTML_TEMPLATE,
            title=title,
            data=data,
            summary=summary,
            chart=chart,
            growth_chart=growth_chart,
        )

    return app


def render_web(
    data: list[dict],
    title: str = "国家统计局数据",
    host: str = "127.0.0.1",
    port: int = 5000,
    summary: dict | None = None,
) -> None:
    """
    启动 Flask Web 服务展示数据。

    Args:
        data: 展示数据列表
        title: 页面标题
        host: 监听地址
        port: 监听端口
        summary: 趋势摘要
    """
    app = create_app(data, title, summary)
    print(f"\n🌐 Web 服务启动: http://{host}:{port}")
    print("   按 Ctrl+C 停止服务\n")
    app.run(host=host, port=port, debug=False)
