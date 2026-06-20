"""
通用数据计算器

对统一数据格式 list[DataPoint] 做各类计算：
  1. 同比/环比增长率
  2. 移动平均
  3. 趋势分析（最高/最低/均值/波动）
  4. 统计摘要

所有函数都是纯函数，不依赖任何外部状态。
入参出参都是 list[DataPoint] 或基本 Python 类型。
"""

import logging
from collections import defaultdict
from typing import Any

from crawler.base import DataPoint

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  增长率计算
# ═══════════════════════════════════════════════════════════

def calculate_growth(
    data: list[DataPoint],
    period: str = "year",
) -> list[dict]:
    """
    计算增长率。

    Args:
        data: DataPoint 列表
        period: "year" → 同比增长（YoY），"month" → 环比增长（MoM）

    Returns:
        [ {date, value, indicator, region, unit, growth, growth_label}, ... ]
        growth=None 表示无法计算（数据不足）
    """
    if not data:
        return []

    sorted_data = sorted(data, key=lambda d: (d.indicator, d.date))
    results: list[dict] = []

    if period == "year":
        # 同比增长：与上年同月比较
        for d in sorted_data:
            entry = d.to_dict()
            entry["growth"] = None
            entry["growth_label"] = "同比"

            if len(d.date) == 7:  # YYYY-MM
                prev_date = f"{int(d.date[:4]) - 1}{d.date[4:]}"
                for prev in sorted_data:
                    if (prev.date == prev_date
                            and prev.indicator == d.indicator
                            and prev.value is not None
                            and d.value is not None
                            and prev.value != 0):
                        entry["growth"] = round(
                            (d.value / prev.value - 1) * 100, 2
                        )
                        break

            results.append(entry)

    elif period == "month":
        # 环比增长：与上个月比较
        for i, d in enumerate(sorted_data):
            entry = d.to_dict()
            entry["growth"] = None
            entry["growth_label"] = "环比"

            if i > 0:
                prev = sorted_data[i - 1]
                if (prev.indicator == d.indicator
                        and prev.value is not None
                        and d.value is not None
                        and prev.value != 0):
                    entry["growth"] = round(
                        (d.value / prev.value - 1) * 100, 2
                    )

            results.append(entry)

    else:
        raise ValueError(f"不支持的 period 参数: {period!r}，可选: 'year', 'month'")

    return results


# ═══════════════════════════════════════════════════════════
#  移动平均
# ═══════════════════════════════════════════════════════════

def calculate_mean(
    data: list[DataPoint],
    window: int = 12,
) -> list[dict]:
    """
    计算移动平均。

    Args:
        data: DataPoint 列表
        window: 移动窗口大小，默认 12（12 个月移动平均）

    Returns:
        [ {date, value, indicator, region, unit, moving_avg}, ... ]
        moving_avg=None 表示窗口内数据不足
    """
    if not data:
        return []

    # 按指标分组，每个指标独立计算移动平均
    by_indicator: dict[str, list[DataPoint]] = defaultdict(list)
    for d in data:
        by_indicator[d.indicator].append(d)

    results: list[dict] = []

    for indicator, points in by_indicator.items():
        sorted_points = sorted(points, key=lambda p: p.date)

        for i, d in enumerate(sorted_points):
            entry = d.to_dict()
            entry["moving_avg"] = None
            entry["moving_window"] = window

            # 取窗口内的有效值
            window_start = max(0, i - window + 1)
            window_values = [
                p.value for p in sorted_points[window_start:i + 1]
                if p.value is not None
            ]

            if len(window_values) >= 2:  # 至少 2 个值才有意义
                entry["moving_avg"] = round(
                    sum(window_values) / len(window_values), 2
                )

            results.append(entry)

    return results


# ═══════════════════════════════════════════════════════════
#  趋势分析
# ═══════════════════════════════════════════════════════════

def analyze_trend(data: list[DataPoint]) -> dict[str, Any]:
    """
    分析数据趋势。

    按指标分组，计算每组的：
      - count: 数据条数
      - date_range: 时间范围
      - latest: 最新值（日期+数值）
      - max: 最大值（日期+数值）
      - min: 最小值（日期+数值）
      - mean: 均值
      - std: 标准差
      - volatility: 波动幅度 (max - min)
      - trend: 趋势方向 ("up" / "down" / "stable")
      - latest_change: 最近变化值

    Args:
        data: DataPoint 列表

    Returns:
        {
            "count": 总条数,
            "indicators": 指标数量,
            "date_range": "YYYY-MM ~ YYYY-MM" | None,
            "details": { 指标名: { ... 上述字段 ... } }
        }
    """
    if not data:
        return {"count": 0, "indicators": 0, "date_range": None, "details": {}}

    by_indicator: dict[str, list[DataPoint]] = defaultdict(list)
    for d in data:
        by_indicator[d.indicator].append(d)

    all_dates = sorted({d.date for d in data if d.date})
    details: dict[str, dict] = {}

    for indicator, points in by_indicator.items():
        sorted_points = sorted(points, key=lambda p: p.date)
        values = [p.value for p in sorted_points if p.value is not None]

        if not values:
            details[indicator] = {"count": len(points), "data": []}
            continue

        min_p = min(sorted_points, key=lambda p: p.value or float("inf"))
        max_p = max(sorted_points, key=lambda p: p.value or float("-inf"))
        latest = sorted_points[-1]

        mean_val = sum(values) / len(values)
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        std_val = variance ** 0.5
        volatility = (max_p.value or 0) - (min_p.value or 0)

        # 趋势方向判断：比较最近 3 个值的线性变化
        trend = "stable"
        if len(values) >= 3:
            recent = values[-3:]
            if recent[-1] > recent[0]:
                trend = "up"
            elif recent[-1] < recent[0]:
                trend = "down"

        # 最新变化量
        latest_change = None
        if len(values) >= 2:
            latest_change = round(values[-1] - values[-2], 2)

        details[indicator] = {
            "count": len(sorted_points),
            "date_range": f"{sorted_points[0].date} ~ {latest.date}",
            "latest": {"date": latest.date, "value": latest.value},
            "max": {"date": max_p.date, "value": max_p.value},
            "min": {"date": min_p.date, "value": min_p.value},
            "mean": round(mean_val, 2),
            "std": round(std_val, 2),
            "volatility": round(volatility, 2),
            "trend": trend,
            "latest_change": latest_change,
        }

    return {
        "count": len(data),
        "indicators": len(by_indicator),
        "date_range": (
            f"{all_dates[0]} ~ {all_dates[-1]}"
            if len(all_dates) >= 2
            else (all_dates[0] if all_dates else None)
        ),
        "details": details,
    }


# ═══════════════════════════════════════════════════════════
#  图表数据准备
# ═══════════════════════════════════════════════════════════

def prepare_chart_data(
    data: list[DataPoint],
    indicators: list[str] | None = None,
) -> dict:
    """
    将原始数据转换为 Chart.js 友好的格式。

    Args:
        data: DataPoint 列表
        indicators: 要包含的指标名列表，None 表示全部

    Returns:
        {
            "labels": ["2026-01", "2026-02", ...],
            "datasets": [
                {
                    "label": "居民消费价格指数",
                    "data": [100.5, 101.2, ...],
                    "borderColor": "#...",
                    ...
                },
                ...
            ]
        }
    """
    if not data:
        return {"labels": [], "datasets": []}

    # 按指标分组
    by_indicator: dict[str, dict] = defaultdict(lambda: {"label": "", "data_map": {}})

    for d in data:
        if indicators and d.indicator not in indicators:
            continue
        by_indicator[d.indicator]["label"] = d.indicator
        by_indicator[d.indicator]["data_map"][d.date] = d.value

    # 收集所有日期标签（去重排序）
    all_dates = sorted({
        d.date for d in data
        if (not indicators or d.indicator in indicators) and d.date
    })

    # Chart.js 调色板
    colors = [
        "#FF6384", "#36A2EB", "#FFCE56", "#4BC0C0", "#9966FF",
        "#FF9F40", "#C9CBCF", "#7BC8A4", "#E7E9ED", "#F7464A",
        "#46BFBD", "#FDB45C", "#949FB1",
    ]

    datasets = []
    for i, (_, info) in enumerate(by_indicator.items()):
        datasets.append({
            "label": info["label"],
            "data": [info["data_map"].get(date) for date in all_dates],
            "borderColor": colors[i % len(colors)],
            "backgroundColor": colors[i % len(colors)] + "33",
            "tension": 0.3,
            "fill": False,
        })

    return {
        "labels": all_dates,
        "datasets": datasets,
    }


# ═══════════════════════════════════════════════════════════
#  增长率图表数据
# ═══════════════════════════════════════════════════════════

def prepare_growth_chart_data(
    growth_data: list[dict],
    indicators: list[str] | None = None,
) -> dict:
    """
    将增长率数据转换为 Chart.js 柱状图格式。

    Args:
        growth_data: calculate_growth() 的输出
        indicators: 要包含的指标名列表

    Returns:
        { "labels": [...], "datasets": [...] }
    """
    if not growth_data:
        return {"labels": [], "datasets": []}

    # 过滤
    if indicators:
        growth_data = [g for g in growth_data if g.get("indicator") in indicators]

    # 按指标分组
    by_indicator: dict[str, dict] = defaultdict(lambda: {"label": "", "data_map": {}})

    for g in growth_data:
        ind = g.get("indicator", "")
        if indicators and ind not in indicators:
            continue
        by_indicator[ind]["label"] = ind
        by_indicator[ind]["data_map"][g["date"]] = g.get("growth")

    # 日期标签
    all_dates = sorted({g["date"] for g in growth_data
                       if not indicators or g.get("indicator") in indicators})

    colors = ["#FF6384", "#36A2EB", "#FFCE56"]

    datasets = []
    for i, (_, info) in enumerate(by_indicator.items()):
        datasets.append({
            "label": info["label"],
            "data": [info["data_map"].get(date) for date in all_dates],
            "borderColor": colors[i % len(colors)],
            "backgroundColor": colors[i % len(colors)] + "66",
            "type": "line" if i > 0 else "bar",
            "tension": 0.3,
        })

    return {
        "labels": all_dates,
        "datasets": datasets,
    }
