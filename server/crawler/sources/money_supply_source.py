"""
数据源：Money Supply（货币供应量）

基于国家统计局新版 esData API，封装货币供应量特有的指标注册表、
分组查询等逻辑。

新版 API（2024+）：
    POST https://data.stats.gov.cn/dg/website/publicrelease/web/external/stream/esData
    请求体：JSON { cid, daCatalogId, das, dts, indicatorIds, rootId, showType }
    响应体：{ "data": [...], "success": true, "state": 20000, "message": "成功" }

指标说明（共 6 项）：
  - M2 期末值 (亿元)       → 货币和准货币供应量绝对规模
  - M2 同比增长 (%)        → 货币和准货币供应量同比增速
  - M1 期末值 (亿元)       → 货币供应量绝对规模
  - M1 同比增长 (%)        → 货币供应量同比增速
  - M0 期末值 (亿元)       → 流通中现金绝对规模
  - M0 同比增长 (%)        → 流通中现金同比增速

用法：
    engine = Engine()
    data = engine.run(MoneySupplySource(period="200001-202606"), save=True)

    source = MoneySupplySource(period="200001-202606")
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

# ── esData API 固定参数（货币供应量页面）──────────────

DEFAULT_DA = [{"text": "全国", "value": "000000000000"}]

# ── CID 周期注册表 ────────────────────────────────────────
#
# 货币供应量只有一套 CID，适用于全部历史年份（2000-至今）。
# 若未来统计局切换 CID，可在此追加新的周期配置。

CID_PERIODS = [
    {
        "label": "全部历史",
        "years": (2000, 2099),
        "cid": "82130c6621a745cda3d64b090e733383",
        "root_id": "fc982599aa684be7969d7b90b1bd0e84",
        "indicator_ids": [
            "f3c0ae453a54424489af41de315ec592",  # 货币和准货币 (M2) 供应量_期末值 (亿元)
            "e03f2232631f41cd9d754a7d7feb4a81",  # 货币和准货币 (M2) 供应量_同比增长 (%)
            "add08d4a1ca049158166f126e169edde",  # 货币 (M1) 供应量_期末值 (亿元)
            "640401d3351b4b868dea28f89f410a54",  # 货币 (M1) 供应量_同比增长 (%)
            "bd67997414b147a08d4aa03d146f4486",  # 流通中现金 (M0) 供应量_期末值 (亿元)
            "db7891fb8f3c4eb2a4d71a9955eba8c7",  # 流通中现金 (M0) 供应量_同比增长 (%)
        ],
    },
]

# ── 当前默认配置 ──────────────────────────────────
_DEFAULT_PERIOD_CONFIG = CID_PERIODS[0]
CID = _DEFAULT_PERIOD_CONFIG["cid"]
ROOT_ID = _DEFAULT_PERIOD_CONFIG["root_id"]


# ── 工具：根据年份查找对应周期配置 ──────────────────

def get_period_config(year: int) -> dict:
    """根据年份查找对应的 CID 周期配置。货币供应量始终返回唯一周期。"""
    for period in CID_PERIODS:
        start, end = period["years"]
        if start <= year <= end:
            return period
    raise ValueError(f"找不到年份 {year} 对应的 CID 周期配置")


def get_period_config_for_range(year_start: int, year_end: int) -> list[dict]:
    """获取覆盖 [year_start, year_end] 的所有周期配置。"""
    result = []
    for period in CID_PERIODS:
        p_start, p_end = period["years"]
        if p_start <= year_end and p_end >= year_start:
            result.append(period)
    return result


# ── 货币供应量指标 UUID 注册表 ───────────────────────

MONEY_SUPPLY_UUID_INDICATORS = {
    "f3c0ae453a54424489af41de315ec592": "货币和准货币 (M2) 供应量_期末值 (亿元)",
    "e03f2232631f41cd9d754a7d7feb4a81": "货币和准货币 (M2) 供应量_同比增长 (%)",
    "add08d4a1ca049158166f126e169edde": "货币 (M1) 供应量_期末值 (亿元)",
    "640401d3351b4b868dea28f89f410a54": "货币 (M1) 供应量_同比增长 (%)",
    "bd67997414b147a08d4aa03d146f4486": "流通中现金 (M0) 供应量_期末值 (亿元)",
    "db7891fb8f3c4eb2a4d71a9955eba8c7": "流通中现金 (M0) 供应量_同比增长 (%)",
}

# ── 货币供应量分组结构 ──────────────────────────────
#
# 1. 期末值 —— M0、M1、M2 的绝对规模（亿元）
# 2. 同比增长 —— M0、M1、M2 的同比增速（%）
# 3. 全指标 —— 全部 6 项

MONEY_SUPPLY_GROUPS = {
    "期末值": [
        "f3c0ae453a54424489af41de315ec592",  # M2 期末值
        "add08d4a1ca049158166f126e169edde",  # M1 期末值
        "bd67997414b147a08d4aa03d146f4486",  # M0 期末值
    ],
    "同比增长": [
        "e03f2232631f41cd9d754a7d7feb4a81",  # M2 同比增长
        "640401d3351b4b868dea28f89f410a54",  # M1 同比增长
        "db7891fb8f3c4eb2a4d71a9955eba8c7",  # M0 同比增长
    ],
    "全指标": [
        "f3c0ae453a54424489af41de315ec592",
        "e03f2232631f41cd9d754a7d7feb4a81",
        "add08d4a1ca049158166f126e169edde",
        "640401d3351b4b868dea28f89f410a54",
        "bd67997414b147a08d4aa03d146f4486",
        "db7891fb8f3c4eb2a4d71a9955eba8c7",
    ],
}


# ── 运行时校验缓存 ────────────────────────────────
_uuid_warnings_emitted: set[str] = set()


# ── 工具函数 ──────────────────────────────────────────────

def _extract_year_from_period(period: str) -> int | None:
    """
    从 period 字符串中提取年份，用于自动选择 CID 周期。

    例如：
      "202605"        → 2026
      "202406-202605" → 2026（取结束年份）
      "200001-200012" → 2000
      "2026"          → 2026
      "1949-"         → 2026（动态取当前年份）
    """
    period = period.strip()
    if not period:
        return None

    if "-" in period and period != "-":
        parts = period.split("-", 1)
        end_part = parts[1].strip()
        if end_part:
            if not end_part:
                return datetime.now().year
            digits = "".join(c for c in end_part if c.isdigit())
            if len(digits) >= 4:
                return int(digits[:4])

    digits = "".join(c for c in period if c.isdigit())
    if len(digits) >= 4:
        return int(digits[:4])

    return None


def _safe_float(v: str) -> float | None:
    if not v or not v.strip():
        return None
    try:
        return float(v.strip().replace(",", "").replace("，", ""))
    except (ValueError, TypeError):
        return None


def _normalize_name(name: str) -> str:
    """归一化指标名称，用于比较。"""
    if not name:
        return ""
    result = name.strip()
    result = result.replace("（", "(").replace("）", ")")
    result = result.replace("　", " ")
    result = result.replace("( ", "(").replace(" )", ")")
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
        "1949-"         → 全部历史：["194901MM-202605MM"]
        "202406MM"      → 已有 MM 后缀则直接使用

    返回：dts 数组
    """
    period = period.strip()

    if period.upper().endswith("MM"):
        return [period.upper()]

    if "-" in period and period != "-":
        parts = period.split("-", 1)
        start = parts[0].strip()
        end = parts[1].strip()

        if len(start) == 4 and start.isdigit():
            start = start + "01"
        if len(end) == 4 and end.isdigit():
            end = end + "12"

        if len(start) == 6 and start.isdigit():
            start = start + "MM"
        if len(end) == 6 and end.isdigit():
            end = end + "MM"

        if start.endswith("MM") and end.endswith("MM"):
            return [f"{start}-{end}"]

    if period.endswith("-") and len(period) > 1:
        now = datetime.now()
        end_ym = f"{now.year}{now.month:02d}MM"
        start_ym = f"{period[:4]}01MM"
        return [f"{start_ym}-{end_ym}"]

    if len(period) == 6 and period.isdigit():
        return [period + "MM"]

    if len(period) == 4 and period.isdigit():
        return [period + "01MM-" + period + "12MM"]

    now = datetime.now()
    end_ym = f"{now.year}{now.month:02d}MM"
    start_dt = now - timedelta(days=365)
    start_ym = f"{start_dt.year}{start_dt.month:02d}MM"
    return [f"{start_ym}-{end_ym}"]


# ═══════════════════════════════════════════════════════════
#  MoneySupplySource — 货币供应量数据源（新版 esData API）
# ═══════════════════════════════════════════════════════════

class MoneySupplySource(DataSource):
    """
    货币供应量数据源（新版 esData API）。

    基于国家统计局新版 esData 接口，使用 JSON POST + UUID 指标 ID
    查询 M0/M1/M2 货币供应量数据（期末值和同比增长）。
    """

    name = "money_supply"

    def __init__(self, indicator_ids: list[str] | None = None,
                 period: str = "200001-202606",
                 das: list[dict] | None = None,
                 da_catalog_id: str = "",
                 cid: str | None = None,
                 root_id: str | None = None):
        """
        Args:
            indicator_ids: 货币供应量指标 UUID 列表。默认为全部 6 个指标。
            period: 时间段。
                "200001-202606" → 范围（默认，2000年1月至最新）
                "202605"        → 单月
                "2026"          → 全年
                "1949-"         → 全部历史
            das: 地区选择。默认为全国级别。
            da_catalog_id: 地区目录 ID，通常为空字符串。
            cid: 手动指定 CID，默认根据 period 自动选择。
            root_id: 手动指定 rootId，默认自动选择。
        """
        if das is None:
            das = DEFAULT_DA

        self._period_config = None
        if cid is None:
            year = _extract_year_from_period(period)
            if year is not None:
                try:
                    self._period_config = get_period_config(year)
                    cid = self._period_config["cid"]
                    root_id = self._period_config["root_id"]
                    if indicator_ids is None:
                        indicator_ids = list(self._period_config["indicator_ids"])
                except ValueError:
                    pass

        if cid is None:
            cid = _DEFAULT_PERIOD_CONFIG["cid"]
        if root_id is None:
            root_id = _DEFAULT_PERIOD_CONFIG["root_id"]
        if indicator_ids is None:
            indicator_ids = list(_DEFAULT_PERIOD_CONFIG["indicator_ids"])

        self.cid = cid
        self.root_id = root_id
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
            "cid": self.cid,
            "daCatalogId": self.da_catalog_id,
            "das": self.das,
            "dts": dts,
            "indicatorIds": self.indicator_ids,
            "rootId": self.root_id,
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

    def parse(self, raw: dict) -> list[DataPoint]:
        """
        从 esData API 返回的 JSON 中解析出 DataPoint 列表。

        esData 响应结构：
        {
          "success": true,
          "state": 20000,
          "data": [
            {
              "code": "202603MM",
              "name": "2026年3月",
              "values": [
                {
                  "_id": "f3c0ae453a54424489af41de315ec592",
                  "i_showname": "货币和准货币 (M2) 供应量_期末值 (亿元) ",
                  "value": "3538636.53",
                  "du_name": "亿元",
                  "da_name": "国家",
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

        data_list = raw.get("data", [])
        if not data_list:
            logger.warning("API 返回空数据")
            return []

        results = []
        for period_entry in data_list:
            sj_code = period_entry.get("code", "")
            date_str = _normalize_date(sj_code)
            period_name = period_entry.get("name", "")

            values = period_entry.get("values", [])
            if not values:
                continue

            for val_entry in values:
                uuid = val_entry.get("_id", "")
                raw_value = val_entry.get("value", "")

                val = _safe_float(raw_value)
                if val is None:
                    continue

                # 指标名称
                api_name = val_entry.get("i_showname", "").strip()
                registry_name = MONEY_SUPPLY_UUID_INDICATORS.get(uuid, "")

                if api_name:
                    indicator_name = api_name
                    if (registry_name
                            and uuid not in _uuid_warnings_emitted
                            and _normalize_name(api_name) != _normalize_name(registry_name)):
                        logger.warning(
                            f"UUID {uuid} 的名称不匹配！\n"
                            f"  注册表: {registry_name}\n"
                            f"  API返回: {api_name}\n"
                            f"  → 将使用 API 返回的名称，MONEY_SUPPLY_UUID_INDICATORS 可能需要更新"
                        )
                        _uuid_warnings_emitted.add(uuid)
                elif registry_name:
                    indicator_name = registry_name
                else:
                    indicator_name = uuid
                    if uuid not in _uuid_warnings_emitted:
                        logger.warning(f"未知 UUID: {uuid}，MONEY_SUPPLY_UUID_INDICATORS 可能需要更新")
                        _uuid_warnings_emitted.add(uuid)

                unit = val_entry.get("du_name", "")
                # 货币供应量 API 返回 da_name 为 "国家"
                region = val_entry.get("da_name", "国家")

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
                        "cid": self.cid,
                        "period_label": self._period_config["label"] if self._period_config else None,
                    },
                ))

        return results

    # ── 辅助方法 ──────────────────────────────────────

    @classmethod
    def list_indicators(cls, group: str = None) -> list[dict]:
        """
        列出货币供应量指标。

        Args:
            group: 分组名，None 表示全部
                - "期末值" → M0/M1/M2 绝对规模
                - "同比增长" → M0/M1/M2 同比增速
                - "全指标" → 全部 6 项

        Returns:
            [{"uuid": ..., "name": ..., "group": ...}]
        """
        uuid_to_group = {}
        for g, uuids in MONEY_SUPPLY_GROUPS.items():
            for u in uuids:
                uuid_to_group[u] = g

        results = []
        for uuid, name in MONEY_SUPPLY_UUID_INDICATORS.items():
            g = uuid_to_group.get(uuid, "其他")
            if group and g != group:
                continue
            results.append({"uuid": uuid, "name": name, "group": g})
        return results

    @classmethod
    def validate_registry(cls, period: str = "202603") -> dict:
        """
        全量校验注册表：拉取最新数据，检查每个 UUID 对应的名称是否匹配。

        用法：
            result = MoneySupplySource.validate_registry()
            if result["mismatches"]:
                print("注册表需要更新！")

        Args:
            period: 用于校验的时间段，默认最近一个月。

        Returns:
            {
                "checked": 6,
                "ok": 6,
                "mismatches": [],
                "unknown": [],
                "cid_match": True,
            }
        """
        source = cls(period=period)
        raw = source.fetch()

        result = {
            "checked": 0,
            "ok": 0,
            "mismatches": [],
            "unknown": [],
            "cid_match": True,
            "cid": source.cid,
            "period_label": source._period_config["label"] if source._period_config else None,
        }

        if not raw.get("success"):
            logger.error(f"API 返回异常: {raw.get('message')}")
            return result

        seen_uuids: set[str] = set()
        for period_entry in raw.get("data", []):
            for val in period_entry.get("values", []):
                uuid = val.get("_id", "")
                if not uuid or uuid in seen_uuids:
                    continue
                seen_uuids.add(uuid)
                result["checked"] += 1

                api_name = val.get("i_showname", "").strip()
                registry_name = MONEY_SUPPLY_UUID_INDICATORS.get(uuid, "")

                if not registry_name:
                    result["unknown"].append({"uuid": uuid, "api_name": api_name})
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

        return result

    @staticmethod
    def summary(data: list[DataPoint]) -> dict:
        """生成货币供应量摘要统计（按指标分组）。"""
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

            summaries[indicator] = s

        return {
            "count": len(data),
            "indicators": len(by_indicator),
            "details": summaries,
        }
