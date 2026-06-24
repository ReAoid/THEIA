"""
货币供应量 RESTful API Blueprint

数据服务层。职责：
  1. 通过 MoneySupplyManager 读取本地缓存数据
  2. 调用 analysis/calculator.py 做各类计算
  3. 返回 JSON 格式给客户端

端点：
  GET  /api/v1/money-supply/overview       → 总体概览
  GET  /api/v1/money-supply/indicators     → 指标列表
  GET  /api/v1/money-supply/data           → 原始数据（带筛选）
  GET  /api/v1/money-supply/chart          → 图表友好数据
  GET  /api/v1/money-supply/groups         → 分组列表
  GET  /api/v1/money-supply/yoy            → 同比增长数据（画表用）
"""

import logging
from typing import Any

from flask import Blueprint, jsonify, request

from analysis.calculator import (
    analyze_trend,
    prepare_chart_data,
)
from manager.money_supply_manager import MoneySupplyManager

logger = logging.getLogger(__name__)

# ── Blueprint ─────────────────────────────────────────────

# 同时注册两个前缀以便向后兼容
money_supply_api_bp = Blueprint("money_supply_api", __name__,
                                url_prefix="/api/v1/money-supply")

# 全局 Manager 实例（懒初始化）
_manager: MoneySupplyManager | None = None


def get_manager() -> MoneySupplyManager:
    """获取 MoneySupplyManager 单例。"""
    global _manager
    if _manager is None:
        _manager = MoneySupplyManager()
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
    """统一获取货币供应量数据（带筛选）。"""
    mgr = get_manager()
    return mgr.get_money_supply(**kwargs)


def _to_dict_list(data: list[Any]) -> list[dict]:
    return [d.to_dict() for d in data]


def _error(message: str, code: int = 400):
    return jsonify({"error": message, "code": code}), code


# ═══════════════════════════════════════════════════════════
#  端点实现
# ═══════════════════════════════════════════════════════════

@money_supply_api_bp.route("/overview", methods=["GET"])
def overview():
    """
    总体概览。

    返回最新货币供应量值、各指标最新快照、趋势方向。

    GET /api/v1/money-supply/overview?period=200001-202606
    """
    try:
        params = _parse_params()
        period = params["period"] or "200001-202606"

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
        logger.exception("货币供应量 overview 异常")
        return _error(str(e), 500)


@money_supply_api_bp.route("/indicators", methods=["GET"])
def indicators():
    """
    指标列表。

    GET /api/v1/money-supply/indicators
    """
    try:
        from crawler.sources.money_supply_source import MoneySupplySource, MONEY_SUPPLY_GROUPS

        all_indicators = MoneySupplySource.list_indicators()

        mgr = get_manager()
        data = mgr.get_money_supply(period="200001-202606")
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
            "groups": list(MONEY_SUPPLY_GROUPS.keys()),
        })

    except Exception as e:
        logger.exception("货币供应量 indicators 异常")
        return _error(str(e), 500)


@money_supply_api_bp.route("/data", methods=["GET"])
def get_data():
    """
    原始数据。

    GET /api/v1/money-supply/data
        ?indicator=M2&period=200001-202606&group=同比增长
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
        logger.exception("货币供应量 data 异常")
        return _error(str(e), 500)


@money_supply_api_bp.route("/chart", methods=["GET"])
def chart():
    """
    图表数据（Chart.js 友好格式）。

    GET /api/v1/money-supply/chart
        ?indicator=货币和准货币(M2)供应量_同比增长(%)&period=200001-202606
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
        logger.exception("货币供应量 chart 异常")
        return _error(str(e), 500)


@money_supply_api_bp.route("/groups", methods=["GET"])
def groups():
    """
    分组列表。

    GET /api/v1/money-supply/groups

    返回所有可用的货币供应量分组。
    """
    try:
        from crawler.sources.money_supply_source import MONEY_SUPPLY_GROUPS, MoneySupplySource

        result = []
        for group_name, uuids in MONEY_SUPPLY_GROUPS.items():
            indicators = MoneySupplySource.list_indicators(group=group_name)
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
        logger.exception("货币供应量 groups 异常")
        return _error(str(e), 500)


@money_supply_api_bp.route("/yoy", methods=["GET"])
def yoy():
    """
    同比增长数据（专为前端表格设计）。

    返回 M0/M1/M2 三个指标的同比增长率，按时间排序。

    GET /api/v1/money-supply/yoy?period=200001-202606

    Returns:
        {
            "success": true,
            "data": [
                {
                    "date": "2026-03",
                    "M2_同比增长": 8.5,
                    "M1_同比增长": 5.1,
                    "M0_同比增长": 12.5,
                },
                ...
            ]
        }
    """
    try:
        params = _parse_params()
        period = params["period"] or "200001-202606"

        data = _get_data(period=period, group="同比增长",
                         force_update=params["force_update"])

        if not data:
            return _error("无匹配数据", 404)

        # 按日期和指标名组织
        from collections import defaultdict
        by_date: dict[str, dict] = defaultdict(dict)

        for d in data:
            indicator = d.indicator
            date = d.date

            # 归一化指标名为简短键名
            if "M2" in indicator and "同比增长" in indicator:
                key = "M2_同比增长"
            elif "M1" in indicator and "同比增长" in indicator:
                key = "M1_同比增长"
            elif "M0" in indicator and "同比增长" in indicator:
                key = "M0_同比增长"
            else:
                continue

            by_date[date][key] = d.value

        # 转为有序列表
        result = []
        for date in sorted(by_date.keys()):
            entry = {"date": date}
            entry.update(by_date[date])
            result.append(entry)

        return jsonify({
            "success": True,
            "count": len(result),
            "data": result,
        })

    except Exception as e:
        logger.exception("货币供应量 yoy 异常")
        return _error(str(e), 500)


@money_supply_api_bp.route("/cache", methods=["GET", "DELETE"])
def cache_info():
    """
    缓存管理。

    GET    /api/v1/money-supply/cache    → 查看缓存状态
    DELETE /api/v1/money-supply/cache    → 清空缓存
    """
    mgr = get_manager()

    if request.method == "DELETE":
        mgr.clear_cache()
        return jsonify({"success": True, "message": "货币供应量缓存已清空"})

    info = mgr.get_cache_info()
    return jsonify({
        "success": True,
        "data": info,
    })
