"""
数据源：CPI 专项（居民消费价格指数）

基于国家统计局新版 esData API，封装 CPI 特有的指标注册表、
分组查询、同比/环比计算等逻辑。

新版 API（2024+）：
    POST https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData
    请求体：JSON { cid, daCatalogId, das, dts, indicatorIds, rootId, showType }
    响应体：{ "data": [...], "success": true, "state": 20000, "message": "成功" }

用法：
    # 配合 Engine 使用
    engine = Engine()
    data = engine.run(CPISource(period="202605"), save=True)

    # 指定特定指标（默认查全部 13 个 CPI 分类）
    source = CPISource(indicator_ids=["53180dfb9c14411ba4b762307c85920c"], period="202601")
    points = source.flow()
"""

import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from crawler.base import DataSource, DataPoint
from crawler.middleware import rate_limit, log_request

logger = logging.getLogger(__name__)

# ── API 基础配置 ─────────────────────────────────────

BASE_URL = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/json",
}

# ── esData API 固定参数（CPI 专项页面）────────────────

CID = "5c7452825c7c4dcba391db5ca7f335c5"
ROOT_ID = "fc982599aa684be7969d7b90b1bd0e84"
DEFAULT_DA = [{"text": "全国", "value": "000000000000"}]

# ── CPI 指标 UUID 注册表 ──────────────────────────────
#
# 从新版 esData API 返回结果中提取的 UUID → 中文名映射。
# 以"上年同月=100"的 CPI 细分指标为主（共 13 个二级分类）。

# ── 运行时校验缓存 ────────────────────────────────
# 记录 parse() 时发现的 UUID ↔ 名称不匹配，避免重复警告
_uuid_warnings_emitted: set[str] = set()


CPI_UUID_INDICATORS = {
    "53180dfb9c14411ba4b762307c85920c": "居民消费价格指数 (上年同月=100)",
    "42c2d9b5d1b749c4b68c2cbd2e3d4a42": "食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)",
    "23db96d6f25c4acbb8801616fc2e509d": "衣着类居民消费价格指数 (上年同月=100)",
    "4fb7ea343fc7403bb412cf48fb2f3f0e": "居住类居民消费价格指数 (上年同月=100)",
    "e4a6cd580cfe43c3a92140d2edb5e7df": "生活用品及服务类居民消费价格指数 (上年同月=100)",
    "e6e42078f30e483b899b2701a766909a": "交通通信类居民消费价格指数 (上年同月=100)",
    "e2636c6c7549458ca90057f9b7eff442": "教育文化娱乐类居民消费价格指数 (上年同月=100)",
    "27cc82bede504fbc896c02a412bc7671": "医疗保健类居民消费价格指数 (上年同月=100)",
    "2cf481203dd0404c8b778d435d401c7a": "其他用品及服务类居民消费价格指数 (上年同月=100)",
    "f91a869a255949ccba0cd73cfa871340": "非食品居民消费价格指数 (上年同月=100)",
    "61a170ad7fa44fa4b2ff60fd708e516e": "消费品居民消费价格指数 (上年同月=100)",
    "c87191b714554e9eba8c2c062abfabb4": "服务居民消费价格指数 (上年同月=100)",
    "71be3d43d2fb44188199840272463ae0": "不包括食品和能源居民消费价格指数 (上年同月=100)",
}

CPI_GROUPS = {
    "全部CPI(13项)": [
        "53180dfb9c14411ba4b762307c85920c",
        "42c2d9b5d1b749c4b68c2cbd2e3d4a42",
        "23db96d6f25c4acbb8801616fc2e509d",
        "4fb7ea343fc7403bb412cf48fb2f3f0e",
        "e4a6cd580cfe43c3a92140d2edb5e7df",
        "e6e42078f30e483b899b2701a766909a",
        "e2636c6c7549458ca90057f9b7eff442",
        "27cc82bede504fbc896c02a412bc7671",
        "2cf481203dd0404c8b778d435d401c7a",
        "f91a869a255949ccba0cd73cfa871340",
        "61a170ad7fa44fa4b2ff60fd708e516e",
        "c87191b714554e9eba8c2c062abfabb4",
        "71be3d43d2fb44188199840272463ae0",
    ],
    "核心CPI(8项)": [
        "53180dfb9c14411ba4b762307c85920c",
        "42c2d9b5d1b749c4b68c2cbd2e3d4a42",
        "23db96d6f25c4acbb8801616fc2e509d",
        "4fb7ea343fc7403bb412cf48fb2f3f0e",
        "e4a6cd580cfe43c3a92140d2edb5e7df",
        "e6e42078f30e483b899b2701a766909a",
        "e2636c6c7549458ca90057f9b7eff442",
        "27cc82bede504fbc896c02a412bc7671",
    ],
}


# ── 工具函数 ──────────────────────────────────────────────

def _safe_float(v: str) -> float | None:
    if not v or not v.strip():
        return None
    try:
        return float(v.strip().replace(",", "").replace("，", ""))
    except (ValueError, TypeError):
        return None


def _normalize_name(name: str) -> str:
    """归一化指标名称，用于比较（去空格、全角转半角、去括号内空格）。"""
    if not name:
        return ""
    result = name.strip()
    # 全角转半角
    result = result.replace("（", "(").replace("）", ")")
    result = result.replace("　", " ")
    # 括号内去空格
    result = result.replace("( ", "(").replace(" )", ")")
    # 连续空格合并
    while "  " in result:
        result = result.replace("  ", " ")
    return result.strip()


def _normalize_date(code: str) -> str:
    """时间代码转可读格式：202605MM → 2026-05"""
    code = code.strip().upper()
    if code.endswith("MM") and len(code) == 8:
        return f"{code[:4]}-{code[4:6]}"
    return code


def _period_to_dts(period: str) -> list[str]:
    """
    将用户输入的 period 转换为 dts 数组。

    输入格式：
        "202605"        → 单月：["202605MM"]
        "202406-202605" → 范围：["202406MM-202605MM"]
        "2026"          → 全年：["202601MM-202612MM"]
        "1949-"         → 全部历史（实际用最近 5 年）：["202106MM-202605MM"]
        "202406MM"      → 已有 MM 后缀则直接使用

    返回：dts 数组
    """
    period = period.strip()

    # 已有 MM 后缀
    if period.upper().endswith("MM"):
        return [period.upper()]

    # 范围格式：YYYY-YYYY 或 YYYYMM-YYYYMM
    if "-" in period and period != "-":
        parts = period.split("-", 1)
        start = parts[0].strip()
        end = parts[1].strip()

        # YYYY 格式 → YYYY01MM
        if len(start) == 4 and start.isdigit():
            start = start + "01"
        if len(end) == 4 and end.isdigit():
            end = end + "12"

        # 补 MM 后缀
        if len(start) == 6 and start.isdigit():
            start = start + "MM"
        if len(end) == 6 and end.isdigit():
            end = end + "MM"

        if start.endswith("MM") and end.endswith("MM"):
            return [f"{start}-{end}"]

    # 开放范围如 "1949-"
    if period.endswith("-") and len(period) > 1:
        # 最近 5 年
        now = datetime.now()
        end_ym = f"{now.year}{now.month:02d}MM"
        start_ym = f"{now.year - 5}{now.month:02d}MM"
        return [f"{start_ym}-{end_ym}"]

    # 单月格式：YYYYMM
    if len(period) == 6 and period.isdigit():
        return [period + "MM"]

    # 单年格式：YYYY
    if len(period) == 4 and period.isdigit():
        return [period + "01MM-" + period + "12MM"]

    # 兜底：返回最近 12 个月
    now = datetime.now()
    end_ym = f"{now.year}{now.month:02d}MM"
    start_dt = now - timedelta(days=365)
    start_ym = f"{start_dt.year}{start_dt.month:02d}MM"
    return [f"{start_ym}-{end_ym}"]


# ═══════════════════════════════════════════════════════════
#  CPISource — CPI 数据源（新版 esData API）
# ═══════════════════════════════════════════════════════════

class CPISource(DataSource):
    """
    CPI 数据源（新版 esData API）。

    基于国家统计局新版 esData 接口，使用 JSON POST + UUID 指标 ID 查询 CPI 数据。

    主要变化（vs 旧版 EasyQuery API）：
      - 请求体为 JSON，不再是 form-encoded
      - 使用 UUID 指标 ID（如 "53180dfb9c14411ba4b762307c85920c"）
      - 时间格式为 "YYYYMMMM"（如 "202605MM"）
      - 支持一次查询多个指标
    """

    name = "cpi"

    def __init__(self, indicator_ids: list[str] | None = None,
                 period: str = "202406-202605",
                 das: list[dict] | None = None,
                 da_catalog_id: str = ""):
        """
        Args:
            indicator_ids: CPI 指标 UUID 列表。
                默认为全部 13 个 CPI 细分指标（上年同月=100）。
            period: 时间段。
                "202605"        → 单月
                "202406-202605" → 范围（默认，最近 12 个月）
                "2026"          → 全年
                "1949-"         → 全部历史（实际映射为最近 5 年）
            das: 地区选择。默认为全国。
                [{"text": "全国", "value": "000000000000"}]
            da_catalog_id: 地区目录 ID，通常为空字符串。
        """
        if indicator_ids is None:
            indicator_ids = list(CPI_UUID_INDICATORS.keys())
        if das is None:
            das = DEFAULT_DA

        self.indicator_ids = indicator_ids
        self.period = period
        self.das = das
        self.da_catalog_id = da_catalog_id

        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._initialized = False

    # ── 核心流程 ──────────────────────────────────────

    def fetch(self) -> dict:
        """调 esData API 拿原始 JSON。"""
        self._ensure_session()
        return self._do_request()

    def _ensure_session(self):
        if self._initialized:
            return
        logger.info("初始化 requests Session：访问统计局首页获取 Cookie")
        try:
            self._session.get("https://data.stats.gov.cn",
                              timeout=15, verify=False)
            self._initialized = True
        except Exception as e:
            logger.warning(f"Session 初始化失败: {e}")
            self._initialized = True

    @rate_limit(interval=2.0)
    @log_request
    def _do_request(self) -> dict:
        """用 JSON POST 发起 esData 请求。"""
        dts = _period_to_dts(self.period)

        payload = {
            "cid": CID,
            "daCatalogId": self.da_catalog_id,
            "das": self.das,
            "dts": dts,
            "indicatorIds": self.indicator_ids,
            "rootId": ROOT_ID,
            "showType": "1",
        }

        logger.debug(f"esData 请求: {json.dumps(payload, ensure_ascii=False)}")

        resp = self._session.post(
            BASE_URL,
            json=payload,
            timeout=30,
            verify=False,
        )
        resp.raise_for_status()
        return resp.json()

    @classmethod
    def _check_cid(cls, raw: dict):
        """检查 API 返回的 catalogid 是否与预设 CID 一致。"""
        data_list = raw.get("data", [])
        if not data_list:
            return
        for period in data_list:
            for val in period.get("values", []):
                api_cid = val.get("catalogid", "")
                if api_cid and api_cid != CID:
                    logger.warning(
                        f"CID 不匹配！预设: {CID}, API 返回: {api_cid}. "
                        f"CPI 注册表可能需要更新。"
                    )
                    return

    def parse(self, raw: dict) -> list[DataPoint]:
        """
        从 esData API 返回的 JSON 中解析出 DataPoint 列表。

        esData 响应结构：
        {
          "success": true,
          "state": 20000,
          "message": "成功",
          "data": [
            {
              "code": "202605MM",
              "name": "2026年5月",
              "values": [
                {
                  "_id": "53180dfb9c14411ba4b762307c85920c",
                  "i_showname": "居民消费价格指数 (上年同月=100)",
                  "value": "101.2",
                  "du_name": "%",
                  "da_name": "全国",
                  "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                  ...
                },
                ...
              ]
            },
            ...
          ]
        }
        """
        if not raw.get("success"):
            logger.warning(f"API 异常: state={raw.get('state')}, message={raw.get('message')}")
            return []

        # ── 运行时校验：CID 是否匹配 ────────────────
        self._check_cid(raw)

        data_list = raw.get("data", [])
        if not data_list:
            logger.warning("API 返回空数据")
            return []

        results = []
        for period_entry in data_list:
            sj_code = period_entry.get("code", "")      # "202605MM"
            date_str = _normalize_date(sj_code)          # "2026-05"
            period_name = period_entry.get("name", "")

            values = period_entry.get("values", [])
            if not values:
                # 该月份无数据（可能尚未发布）
                continue

            for val_entry in values:
                uuid = val_entry.get("_id", "")
                raw_value = val_entry.get("value", "")

                val = _safe_float(raw_value)
                if val is None:
                    continue

                # ── 指标名称：优先用 API 返回的名称，同时校验注册表 ──
                api_name = val_entry.get("i_showname", "").strip()
                registry_name = CPI_UUID_INDICATORS.get(uuid, "")

                if api_name:
                    indicator_name = api_name
                    # 校验：注册表中的名称是否与 API 一致
                    if (registry_name
                            and uuid not in _uuid_warnings_emitted
                            and _normalize_name(api_name) != _normalize_name(registry_name)):
                        logger.warning(
                            f"UUID {uuid} 的名称不匹配！\n"
                            f"  注册表: {registry_name}\n"
                            f"  API返回: {api_name}\n"
                            f"  → 将使用 API 返回的名称，CPI_UUID_INDICATORS 可能需要更新"
                        )
                        _uuid_warnings_emitted.add(uuid)
                elif registry_name:
                    indicator_name = registry_name
                else:
                    # 两边都没有 → 用 UUID 本身
                    indicator_name = uuid
                    if uuid not in _uuid_warnings_emitted:
                        logger.warning(f"未知 UUID: {uuid}，CPI_UUID_INDICATORS 可能需要更新")
                        _uuid_warnings_emitted.add(uuid)

                unit = val_entry.get("du_name", "")
                region = val_entry.get("da_name", "全国")

                results.append(DataPoint(
                    date=date_str,
                    value=val,
                    indicator=indicator_name,
                    region=region,
                    unit=unit,
                    source=self.name,
                    extra={
                        "indicator_uuid": uuid,
                        "period_code": sj_code,
                        "period_name": period_name,
                    },
                ))

        return results

    # ── 辅助方法 ──────────────────────────────────────

    @classmethod
    def list_indicators(cls, group: str = None) -> list[dict]:
        """
        列出 CPI 指标（UUID 版）。
        Args:
            group: 分组名，None 表示全部
        Returns:
            [{"uuid": ..., "name": ..., "group": ...}]
        """
        uuid_to_group = {}
        for g, uuids in CPI_GROUPS.items():
            for u in uuids:
                uuid_to_group[u] = g

        results = []
        for uuid, name in CPI_UUID_INDICATORS.items():
            g = uuid_to_group.get(uuid, "其他")
            if group and g != group:
                continue
            results.append({"uuid": uuid, "name": name, "group": g})
        return results

    @classmethod
    def validate_registry(cls, period: str = "202605") -> dict:
        """
        全量校验注册表：拉取最新数据，检查每个 UUID 对应的名称是否匹配。

        用法：
            result = CPISource.validate_registry()
            if result["mismatches"]:
                print("注册表需要更新！")

        Args:
            period: 用于校验的时间段，默认最近一个月。

        Returns:
            {
                "checked": 13,          # 检查的指标数
                "ok": 13,               # 匹配的指标数
                "mismatches": [],       # 不匹配的 [(uuid, 注册表名称, API名称)]
                "unknown": [],          # 注册表中没有的 UUID
                "cid_match": True,      # CID 是否匹配
            }
        """
        source = cls(indicator_ids=list(CPI_UUID_INDICATORS.keys()),
                     period=period)
        raw = source.fetch()

        result = {
            "checked": 0,
            "ok": 0,
            "mismatches": [],
            "unknown": [],
            "cid_match": True,
        }

        if not raw.get("success"):
            logger.error(f"API 返回异常: {raw.get('message')}")
            return result

        # 检查 CID
        for period_entry in raw.get("data", []):
            for val in period_entry.get("values", []):
                api_cid = val.get("catalogid", "")
                if api_cid and api_cid != CID:
                    result["cid_match"] = False
                    break

        # 检查每个 UUID 的名称
        seen_uuids: set[str] = set()
        for period_entry in raw.get("data", []):
            for val in period_entry.get("values", []):
                uuid = val.get("_id", "")
                if not uuid or uuid in seen_uuids:
                    continue
                seen_uuids.add(uuid)
                result["checked"] += 1

                api_name = val.get("i_showname", "").strip()
                registry_name = CPI_UUID_INDICATORS.get(uuid, "")

                if not registry_name:
                    result["unknown"].append({
                        "uuid": uuid,
                        "api_name": api_name,
                    })
                    continue

                if _normalize_name(api_name) == _normalize_name(registry_name):
                    result["ok"] += 1
                else:
                    result["mismatches"].append({
                        "uuid": uuid,
                        "registry_name": registry_name,
                        "api_name": api_name,
                    })

        if result["mismatches"]:
            logger.warning(f"发现 {len(result['mismatches'])} 个 UUID 名称不匹配！")
        if result["unknown"]:
            logger.warning(f"发现 {len(result['unknown'])} 个未知 UUID！")
        if not result["cid_match"]:
            logger.warning(f"CID 不匹配！预设: {CID}")

        return result

    @staticmethod
    def calc_yoy(data: list[DataPoint]) -> list[dict]:
        """
        计算同比增长率。

        YoY = (当期值 / 上年同期值 - 1) * 100

        注意：CPI(上年同月=100) 本身就是同比指数，
        这里展示的是"同比的同比"变化，通常用于分析 CPI 走势加速度。
        """
        if not data:
            return []

        sorted_data = sorted(data, key=lambda d: (d.indicator, d.date))
        results = []

        for d in sorted_data:
            entry = d.to_dict()
            entry["yoy"] = None

            if len(d.date) == 7:  # YYYY-MM
                prev_date = f"{int(d.date[:4]) - 1}{d.date[4:]}"
                for prev in sorted_data:
                    if (prev.date == prev_date
                            and prev.indicator == d.indicator
                            and prev.value):
                        entry["yoy"] = round(
                            (d.value / prev.value - 1) * 100, 2
                        )
                        break

            results.append(entry)

        return results

    @staticmethod
    def calc_mom(data: list[DataPoint]) -> list[dict]:
        """计算环比增长率。"""
        if not data:
            return []

        sorted_data = sorted(data, key=lambda d: (d.indicator, d.date))
        results = []

        for i, d in enumerate(sorted_data):
            entry = d.to_dict()
            entry["mom"] = None
            if i > 0 and sorted_data[i - 1].indicator == d.indicator:
                prev = sorted_data[i - 1]
                if prev.value:
                    entry["mom"] = round(
                        (d.value / prev.value - 1) * 100, 2
                    )
            results.append(entry)

        return results

    @staticmethod
    def summary(data: list[DataPoint]) -> dict:
        """生成 CPI 摘要统计（按指标分组）。"""
        if not data:
            return {"count": 0}

        by_indicator: dict[str, list[DataPoint]] = {}
        for d in data:
            by_indicator.setdefault(d.indicator, []).append(d)

        summaries = {}
        for indicator, points in by_indicator.items():
            sorted_points = sorted(points, key=lambda p: p.date)
            values = [p.value for p in sorted_points if p.value is not None]

            if not values:
                summaries[indicator] = {"count": len(points), "data": []}
                continue

            min_p = min(sorted_points, key=lambda p: p.value or float("inf"))
            max_p = max(sorted_points, key=lambda p: p.value or float("-inf"))
            latest = sorted_points[-1]
            mean_val = sum(values) / len(values)

            s = {
                "period": f"{sorted_points[0].date} ~ {latest.date}",
                "count": len(sorted_points),
                "min": {"date": min_p.date, "value": min_p.value},
                "max": {"date": max_p.date, "value": max_p.value},
                "mean": round(mean_val, 2),
                "latest": {"date": latest.date, "value": latest.value},
            }

            if len(sorted_points) >= 13:
                prev = sorted_points[-13]
                if prev.value:
                    s["latest_yoy"] = round(
                        (latest.value / prev.value - 1) * 100, 2
                    )

            summaries[indicator] = s

        return {
            "count": len(data),
            "indicators": len(by_indicator),
            "details": summaries,
        }
