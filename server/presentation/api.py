"""
CPI RESTful API Blueprint

前端数据服务层。职责：
  1. 通过 CPIManager 读取本地缓存数据
  2. 调用 analysis/calculator.py 做各类计算
  3. 返回 JSON 格式给客户端

端点：
  GET  /api/v1/cpi/overview       → 总体概览
  GET  /api/v1/cpi/indicators     → 指标列表
  GET  /api/v1/cpi/data           → 原始数据（带筛选）
  GET  /api/v1/cpi/growth         → 增长率数据
  GET  /api/v1/cpi/summary        → 统计摘要
  GET  /api/v1/cpi/chart          → 图表友好数据
  GET  /api/v1/cpi/groups         → 分组列表
"""

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from analysis.calculator import (
    calculate_growth,
    analyze_trend,
    prepare_chart_data,
    prepare_growth_chart_data,
)
from manager.cpi_manager import CPIManager

logger = logging.getLogger(__name__)

# ── Blueprint ─────────────────────────────────────────────

api_bp = Blueprint("cpi_api", __name__, url_prefix="/api/v1/cpi")

# 全局 Manager 实例（懒初始化）
_manager: CPIManager | None = None


def get_manager() -> CPIManager:
    """获取 CPIManager 单例。"""
    global _manager
    if _manager is None:
        _manager = CPIManager()
    return _manager


# ── 工具函数 ─────────────────────────────────────────────

def _parse_params() -> dict:
    """
    从请求查询参数中解析通用筛选参数。

    Returns:
        {
            "indicators": list[str] | None,
            "period": str | None,
            "group": str | None,
            "force_update": bool,
        }
    """
    indicators = request.args.get("indicator")
    period = request.args.get("period")
    group = request.args.get("group")
    force_update = request.args.get("force_update", "").lower() in ("1", "true", "yes")

    return {
        "indicators": indicators.split(",") if indicators else None,
        "period": period or None,
        "group": group or None,
        "force_update": force_update,
    }


def _get_data(**kwargs) -> list[Any]:
    """
    统一获取 CPI 数据（带筛选）。

    Args:
        **kwargs: 透传给 CPIManager.get_cpi() 的参数

    Returns:
        DataPoint 列表（Python 对象，不是 dict）
    """
    mgr = get_manager()
    return mgr.get_cpi(**kwargs)


def _to_dict_list(data: list[Any]) -> list[dict]:
    """将 DataPoint 列表转为 dict 列表。"""
    return [d.to_dict() for d in data]


def _error(message: str, code: int = 400):
    """返回 JSON 错误响应。"""
    return jsonify({"error": message, "code": code}), code


# ═══════════════════════════════════════════════════════════
#  端点实现
# ═══════════════════════════════════════════════════════════

@api_bp.route("/overview", methods=["GET"])
def overview():
    """
    总体概览。

    返回最新 CPI 值、各指标最新快照、趋势方向。

    GET /api/v1/cpi/overview?period=202601-202605
    """
    try:
        params = _parse_params()
        period = params["period"] or "202406-202605"

        data = _get_data(period=period, force_update=params["force_update"])

        if not data:
            return _error("无数据可用", 404)

        # 趋势分析
        trend = analyze_trend(data)

        # 最新各指标快照
        latest_by_indicator = {}
        for d in data:
            ind = d.indicator
            if ind not in latest_by_indicator or d.date > latest_by_indicator[ind]["date"]:
                details = trend.get("details", {}).get(ind, {})
                latest_by_indicator[ind] = {
                    "indicator": ind,
                    "date": d.date,
                    "value": d.value,
                    "unit": d.unit,
                    "region": d.region,
                    "trend": details.get("trend", "stable"),
                    "latest_change": details.get("latest_change"),
                    "mean": details.get("mean"),
                }

        return jsonify({
            "success": True,
            "data": {
                "total_count": trend["count"],
                "indicator_count": trend["indicators"],
                "date_range": trend["date_range"],
                "latest": list(latest_by_indicator.values()),
                "summary": {
                    k: v for k, v in trend.items() if k != "details"
                },
            },
        })

    except Exception as e:
        logger.exception("overview 异常")
        return _error(str(e), 500)


@api_bp.route("/indicators", methods=["GET"])
def indicators():
    """
    指标列表。

    GET /api/v1/cpi/indicators
    """
    try:
        from crawler.sources.cpi_source import CPISource, CPI_GROUPS

        # 获取所有指标
        all_indicators = CPISource.list_indicators()

        # 获取缓存中的数据统计
        mgr = get_manager()
        data = mgr.get_cpi(period="202406-202605")
        cached_indicators = set()
        if data:
            cached_indicators = {d.indicator for d in data}

        # 为每个指标添加 has_data 标记
        result = []
        for ind in all_indicators:
            result.append({
                "uuid": ind["uuid"],
                "name": ind["name"],
                "group": ind.get("group", "其他"),
                "period": ind.get("period", "未知"),
                "has_data": ind["name"] in cached_indicators,
            })

        return jsonify({
            "success": True,
            "data": result,
            "groups": list(CPI_GROUPS.keys()),
        })

    except Exception as e:
        logger.exception("indicators 异常")
        return _error(str(e), 500)


@api_bp.route("/data", methods=["GET"])
def get_data():
    """
    原始数据。

    GET /api/v1/cpi/data?indicator=居民消费价格指数&period=202601-202605&group=全部CPI(13项)
    """
    try:
        params = _parse_params()
        data = _get_data(
            indicators=params["indicators"],
            period=params["period"],
            group=params["group"],
            force_update=params["force_update"],
        )

        if not data:
            return _error("无匹配数据", 404)

        return jsonify({
            "success": True,
            "count": len(data),
            "data": _to_dict_list(data),
        })

    except Exception as e:
        logger.exception("data 异常")
        return _error(str(e), 500)


@api_bp.route("/growth", methods=["GET"])
def growth():
    """
    增长率数据。

    GET /api/v1/cpi/growth?indicator=居民消费价格指数&period=year
         &period=202601-202605

    Query:
        period: "year"（同比, 默认）或 "month"（环比）
    """
    try:
        params = _parse_params()
        growth_period = request.args.get("growth_period", "year")

        data = _get_data(
            indicators=params["indicators"],
            period=params.get("period"),
            group=params["group"],
            force_update=params["force_update"],
        )

        if not data:
            return _error("无匹配数据", 404)

        growth_data = calculate_growth(data, period=growth_period)

        return jsonify({
            "success": True,
            "count": len(growth_data),
            "growth_period": growth_period,
            "data": growth_data,
        })

    except Exception as e:
        logger.exception("growth 异常")
        return _error(str(e), 500)


@api_bp.route("/summary", methods=["GET"])
def summary():
    """
    统计摘要。

    GET /api/v1/cpi/summary?indicator=居民消费价格指数&period=202601-202605
    """
    try:
        params = _parse_params()
        data = _get_data(
            indicators=params["indicators"],
            period=params["period"],
            group=params["group"],
            force_update=params["force_update"],
        )

        if not data:
            return _error("无匹配数据", 404)

        trend = analyze_trend(data)

        return jsonify({
            "success": True,
            "data": trend,
        })

    except Exception as e:
        logger.exception("summary 异常")
        return _error(str(e), 500)


@api_bp.route("/chart", methods=["GET"])
def chart():
    """
    图表数据（Chart.js 友好格式）。

    GET /api/v1/cpi/chart?indicator=居民消费价格指数,食品烟酒及在外餐饮类居民消费价格指数
         &period=202601-202605

    Query:
        type: "line"（折线图, 默认）或 "growth"（增长率图）
    """
    try:
        params = _parse_params()
        chart_type = request.args.get("type", "line")
        growth_period = request.args.get("growth_period", "year")

        data = _get_data(
            indicators=params["indicators"],
            period=params["period"],
            group=params["group"],
            force_update=params["force_update"],
        )

        if not data:
            return _error("无匹配数据", 404)

        if chart_type == "growth":
            growth_data = calculate_growth(data, period=growth_period)
            chart_data = prepare_growth_chart_data(growth_data, params["indicators"])
        else:
            chart_data = prepare_chart_data(data, params["indicators"])

        return jsonify({
            "success": True,
            "chart_type": chart_type,
            "data": chart_data,
        })

    except Exception as e:
        logger.exception("chart 异常")
        return _error(str(e), 500)


@api_bp.route("/groups", methods=["GET"])
def groups():
    """
    分组列表。

    GET /api/v1/cpi/groups

    返回所有可用的 CPI 分组。
    """
    try:
        from crawler.sources.cpi_source import CPI_GROUPS, CPISource

        result = []
        for group_name, uuids in CPI_GROUPS.items():
            indicators = CPISource.list_indicators(group=group_name)
            result.append({
                "name": group_name,
                "indicator_count": len(indicators),
                "indicators": [
                    {"uuid": i["uuid"], "name": i["name"]}
                    for i in indicators
                ],
            })

        return jsonify({
            "success": True,
            "data": result,
        })

    except Exception as e:
        logger.exception("groups 异常")
        return _error(str(e), 500)


@api_bp.route("/cache", methods=["GET", "DELETE"])
def cache_info():
    """
    缓存管理。

    GET  /api/v1/cpi/cache         → 查看缓存状态
    DELETE /api/v1/cpi/cache        → 清空缓存
    """
    mgr = get_manager()

    if request.method == "DELETE":
        mgr.clear_cache()
        return jsonify({"success": True, "message": "缓存已清空"})

    # GET
    info = mgr.get_cache_info()
    return jsonify({
        "success": True,
        "data": info,
    })
