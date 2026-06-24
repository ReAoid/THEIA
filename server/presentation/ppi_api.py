"""
PPI RESTful API Blueprint

数据服务层。职责：
  1. 通过 PPIManager 读取本地缓存数据
  2. 调用 analysis/calculator.py 做各类计算
  3. 返回 JSON 格式给客户端

端点：
  GET  /api/v1/ppi/overview       → 总体概览
  GET  /api/v1/ppi/indicators     → 指标列表
  GET  /api/v1/ppi/data           → 原始数据（带筛选）
  GET  /api/v1/ppi/chart          → 图表友好数据
  GET  /api/v1/ppi/groups         → 分组列表
"""

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from analysis.calculator import (
    analyze_trend,
    prepare_chart_data,
)
from manager.ppi_manager import PPIManager

logger = logging.getLogger(__name__)

# ── Blueprint ─────────────────────────────────────────────

ppi_api_bp = Blueprint("ppi_api", __name__, url_prefix="/api/v1/ppi")

# 全局 Manager 实例（懒初始化）
_manager: PPIManager | None = None


def get_manager() -> PPIManager:
    """获取 PPIManager 单例。"""
    global _manager
    if _manager is None:
        _manager = PPIManager()
    return _manager


# ── 工具函数 ─────────────────────────────────────────────

def _parse_params() -> dict:
    """
    从请求查询参数中解析通用筛选参数。
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
    """统一获取 PPI 数据（带筛选）。"""
    mgr = get_manager()
    return mgr.get_ppi(**kwargs)


def _to_dict_list(data: list[Any]) -> list[dict]:
    return [d.to_dict() for d in data]


def _error(message: str, code: int = 400):
    return jsonify({"error": message, "code": code}), code


# ═══════════════════════════════════════════════════════════
#  端点实现
# ═══════════════════════════════════════════════════════════

@ppi_api_bp.route("/overview", methods=["GET"])
def overview():
    """
    总体概览。

    GET /api/v1/ppi/overview?period=202306-202605
    """
    try:
        params = _parse_params()
        period = params["period"] or "202306-202605"

        data = _get_data(period=period, force_update=params["force_update"])

        if not data:
            return _error("无数据可用", 404)

        trend = analyze_trend(data)

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
        logger.exception("PPI overview 异常")
        return _error(str(e), 500)


@ppi_api_bp.route("/indicators", methods=["GET"])
def indicators():
    """
    指标列表。

    GET /api/v1/ppi/indicators
    """
    try:
        from crawler.sources.ppi_source import PPISource, PPI_GROUPS

        all_indicators = PPISource.list_indicators()

        mgr = get_manager()
        data = mgr.get_ppi(period="202306-202605")
        cached_indicators = set()
        if data:
            cached_indicators = {d.indicator for d in data}

        result = []
        for ind in all_indicators:
            result.append({
                "uuid": ind["uuid"],
                "name": ind["name"],
                "group": ind.get("group", "其他"),
                "has_data": ind["name"] in cached_indicators,
            })

        return jsonify({
            "success": True,
            "data": result,
            "groups": list(PPI_GROUPS.keys()),
        })

    except Exception as e:
        logger.exception("PPI indicators 异常")
        return _error(str(e), 500)


@ppi_api_bp.route("/data", methods=["GET"])
def get_data():
    """
    原始数据。

    GET /api/v1/ppi/data?indicator=工业生产者出厂价格指数&period=202306-202605
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
        logger.exception("PPI data 异常")
        return _error(str(e), 500)


@ppi_api_bp.route("/chart", methods=["GET"])
def chart():
    """
    图表数据（Chart.js 友好格式）。

    GET /api/v1/ppi/chart?indicator=工业生产者出厂价格指数,生产资料&period=202306-202605
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

        chart_data = prepare_chart_data(data)

        return jsonify({
            "success": True,
            "chart_type": "line",
            "data": chart_data,
        })

    except Exception as e:
        logger.exception("PPI chart 异常")
        return _error(str(e), 500)


@ppi_api_bp.route("/groups", methods=["GET"])
def groups():
    """
    分组列表。

    GET /api/v1/ppi/groups

    返回所有可用的 PPI 分组。
    """
    try:
        from crawler.sources.ppi_source import PPI_GROUPS, PPISource

        result = []
        for group_name, uuids in PPI_GROUPS.items():
            indicators = PPISource.list_indicators(group=group_name)
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
        logger.exception("PPI groups 异常")
        return _error(str(e), 500)


@ppi_api_bp.route("/cache", methods=["GET", "DELETE"])
def cache_info():
    """
    缓存管理。

    GET    /api/v1/ppi/cache    → 查看缓存状态
    DELETE /api/v1/ppi/cache    → 清空缓存
    """
    mgr = get_manager()

    if request.method == "DELETE":
        mgr.clear_cache()
        return jsonify({"success": True, "message": "PPI 缓存已清空"})

    info = mgr.get_cache_info()
    return jsonify({
        "success": True,
        "data": info,
    })
