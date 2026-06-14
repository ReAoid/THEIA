"""
数据源：CPI 专项（居民消费价格指数）

基于 StatsAPISource 的通用能力，封装 CPI 特有的指标注册表、
分组查询、同比/环比计算等逻辑。

用法：
    # 配合 Engine 使用
    engine = Engine()
    data = engine.run(CPISource(zbcode="A010101", period="2022"), save=True)

    # 直接使用
    source = CPISource(zbcode="A010101", period="202201")
    points = source.flow()
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from crawler.base import DataSource, DataPoint
from crawler.middleware import rate_limit, retry, log_request

logger = logging.getLogger(__name__)

# ── API 基础配置（与 stats_api.py 一致）─────────────────

BASE_URL = "https://data.stats.gov.cn/easyquery.htm"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded",
}

# ── CPI 指标注册表 ────────────────────────────────────────
#
# 代码来源：refer/cnstats-main/README.md + refer/national_data_spider/getcode.py
# 分组说明：
#   上年同月=100 — 最常用，反映月度同比价格变动
#   上年同期=100 — 反映累计同比价格变动
#   上月=100     — 反映月度环比价格变动

CPI_INDICATORS = {
    # ── 上年同月=100 ──────────────────────────────
    "A010101": "全国居民消费价格指数(上年同月=100)",
    "A01010101": "全国居民消费价格指数(上年同月=100)(2016-)",
    "A01010102": "全国居民消费价格指数(上年同月=100)(-2015)",
    "A010102": "全国食品类居民消费价格指数(上年同月=100)",
    "A010103": "城市居民消费价格指数(上年同月=100)",
    "A01010301": "城市居民消费价格指数(上年同月=100)(2016-)",
    "A01010302": "城市居民消费价格指数(上年同月=100)(-2015)",
    "A010104": "城市食品类居民消费价格指数(上年同月=100)",
    "A010105": "农村居民消费价格指数(上年同月=100)",
    "A01010501": "农村居民消费价格指数(上年同月=100)(2016-)",
    "A01010502": "农村居民消费价格指数(上年同月=100)(-2015)",
    "A010106": "农村食品类居民消费价格指数(上年同月=100)",
    # ── 上年同期=100 ──────────────────────────────
    "A010201": "全国居民消费价格指数(上年同期=100)(2016-)",
    "A010202": "全国居民消费价格指数(上年同期=100)(-2015)",
    "A010203": "全国食品类居民消费价格指数(上年同期=100)",
    "A010204": "城市居民消费价格指数(上年同期=100)(2016-)",
    "A010205": "城市居民消费价格指数(上年同期=100)(-2015)",
    "A010206": "城市食品类居民消费价格指数(上年同期=100)",
    "A010207": "农村居民消费价格指数(上年同期=100)(2016-)",
    "A010208": "农村居民消费价格指数(上年同期=100)(-2015)",
    "A010209": "农村食品类居民消费价格指数(上年同期=100)",
    # ── 上月=100 ────────────────────────────────
    "A010301": "全国居民消费价格指数(上月=100)(2016-)",
    "A010302": "全国居民消费价格指数(上月=100)(-2015)",
    "A010303": "食品类居民消费价格指数(上月=100)",
    "A010304": "城市居民消费价格指数(上月=100)(2016-)",
    "A010305": "城市居民消费价格指数(上月=100)(-2015)",
    "A010306": "城市食品类居民消费价格指数(上月=100)",
    "A010307": "农村居民消费价格指数(上月=100)(2016-)",
    "A010308": "农村居民消费价格指数(上月=100)(-2015)",
    "A010309": "农村食品类居民消费价格指数(上月=100)",
    # ── 分省 CPI (2016-) ─────────────────────────
    "A01010B01": "居民消费价格指数(上年同月=100), 分省",
    "A01010B02": "食品烟酒类居民消费价格指数(上年同月=100), 分省",
}

CPI_GROUPS = {
    "全国(上年同月)": ["A010101", "A010102", "A010103", "A010105"],
    "全国(上年同期)": ["A010201", "A010203", "A010204", "A010207"],
    "全国(上月)":     ["A010301", "A010303", "A010304", "A010307"],
    "分省CPI":        ["A01010B01", "A01010B02"],
}


# ── 工具函数 ──────────────────────────────────────────────

def _safe_float(v: str) -> float | None:
    if not v or not v.strip():
        return None
    try:
        return float(v.strip().replace(",", "").replace("，", ""))
    except (ValueError, TypeError):
        return None


def _normalize_date(code: str) -> str:
    """时间代码转可读格式：202201 → 2022-01"""
    code = code.strip()
    if len(code) == 6 and code.isdigit():
        return f"{code[:4]}-{code[4:]}"
    return code


# ═══════════════════════════════════════════════════════════
#  CPISource — CPI 数据源
# ═══════════════════════════════════════════════════════════

class CPISource(DataSource):
    """
    CPI 数据源。

    专为国家统计局 CPI 指标设计的数据源，在 StatsAPISource 的基础上：
      - 内置 CPI 指标注册表（代码 + 名称 + 分组）
      - 支持分组查询（同时查多个 CPI 指标）
      - 提供同比/环比分析辅助
      - 支持分省 CPI 查询
      - 支持双后端：requests（轻量） 或 Playwright（防 403）

    数据读取方式参考：
      - crawler/sources/stats_api.py  — 通用 API 调用 + DataPoint 封装
      - refer/cnstats-main/common.py  — EasyQuery 请求参数构造
      - refer/cnstats-main/stats.py   — JSON 响应解析逻辑
      - server/crawler/playwright_crawler.py  — Playwright 浏览器内 fetch
    """

    name = "cpi"

    def __init__(self, zbcode: str, period: str = "1949-",
                 regcode: str = None, dbcode: str = "hgyd",
                 backend: str = "requests"):
        """
        Args:
            zbcode: 指标代码（见 CPI_INDICATORS）
            period: 时间段
                "202201"       → 单月
                "2022"         → 全年
                "202201,202112" → 多个月
                "1949-"        → 全部历史（默认）
            regcode: 地区代码（分省查询用，如 "110000"）
            dbcode: 数据库代码
                hgyd = 宏观月度（默认）
                fsyd = 分省月度（配合 regcode）
                csyd = 城市月度（配合 regcode）
            backend: 请求后端
                "requests"   — 用 requests 库（轻量，需要先拿 Cookie）
                "playwright" — 用 Playwright 浏览器（真浏览器，自动防 403）
        """
        super().__init__(zbcode=zbcode, period=period,
                         regcode=regcode, dbcode=dbcode)
        self.zbcode = zbcode
        self.period = period
        self.regcode = regcode
        self.dbcode = dbcode
        self.backend = backend

        # requests 后端：持久化 Session（参考 cnstats-main/common.py）
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.headers.update(HEADERS)
        self._initialized = False

        # playwright 后端：缓存的 browser / page 对象
        self._playwright = None
        self._browser = None
        self._page = None

    # ── 后端选择 ──────────────────────────────────────

    def fetch(self) -> dict:
        """调 EasyQuery API 拿原始 JSON。"""
        if self.backend == "playwright":
            return self._fetch_via_playwright()
        return self._fetch_via_requests()

    # ── 后端 A：requests（参考 cnstats-main/common.py）───

    def _ensure_session(self):
        """
        先访问首页拿 Cookie，避免 403。

        参考：
          refer/areacode-master/spiders.py  — Cookie 依赖
          refer/cnstats-main/common.py      — session.trust_env = False
        """
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
    @retry(max_times=3, delay=1.0)
    @log_request
    def _fetch_via_requests(self) -> dict:
        """用 requests 发起 POST 请求。"""
        self._ensure_session()

        wds = []
        dfwds = [
            {"wdcode": "zb", "valuecode": self.zbcode},
            {"wdcode": "sj", "valuecode": self.period},
        ]
        if self.regcode:
            wds.append({"wdcode": "reg", "valuecode": self.regcode})

        payload = {
            "m": "QueryData",
            "dbcode": self.dbcode,
            "rowcode": "zb",
            "colcode": "sj",
            "wds": json.dumps(wds),
            "dfwds": json.dumps(dfwds),
            "k1": str(int(time.time() * 1000)),
        }

        resp = self._session.post(BASE_URL, data=payload,
                                  timeout=15, verify=False)
        resp.raise_for_status()
        return resp.json()

    # ── 后端 B：Playwright（参考 playwright_crawler.py）───

    @log_request
    def _fetch_via_playwright(self) -> dict:
        """
        用 Playwright 调 EasyQuery API。

        使用 Playwright 的 APIRequestContext（浏览器内的 HTTP 客户端），
        自动携带浏览器 Cookie，绝不会 403。

        参考：
          server/crawler/playwright_crawler.py  — StatsAPIClient.query_via_browser()
        """
        import asyncio

        async def _run():
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                b = await p.chromium.launch(headless=True)
                context = await b.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                )

                # 先访问首页，让浏览器拿到 Cookie
                page = await context.new_page()
                await page.goto("https://data.stats.gov.cn",
                                wait_until="domcontentloaded", timeout=30000)

                # 用浏览器内的 HTTP 客户端发请求（自动带 Cookie）
                api = await context.new_context()
                # 实际上用 context.request 就行了，它已包含浏览器 Cookie
                # 但为了独立 API 请求，用 request 的 post

                wds = []
                dfwds = [
                    {"wdcode": "zb", "valuecode": self.zbcode},
                    {"wdcode": "sj", "valuecode": self.period},
                ]
                if self.regcode:
                    wds.append({"wdcode": "reg", "valuecode": self.regcode})

                params = {
                    "m": "QueryData",
                    "dbcode": self.dbcode,
                    "rowcode": "zb",
                    "colcode": "sj",
                    "wds": json.dumps(wds),
                    "dfwds": json.dumps(dfwds),
                    "k1": str(int(time.time() * 1000)),
                }

                resp = await context.request.post(
                    BASE_URL,
                    form=params,
                    headers={
                        "Referer": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                return await resp.json()

        return asyncio.run(_run())

    def parse(self, raw: dict) -> list[DataPoint]:
        """
        从 API 返回的 JSON 中解析出 DataPoint 列表。

        参考：
          refer/cnstats-main/stats.py       → 维度映射 + 数据节点遍历
          crawler/sources/stats_api.py      → _parse_response() 的实现
          refer/national_data_spider/...    → datanodes 遍历模式

        API 返回结构：
        {
          "returncode": 200,
          "returndata": {
            "wdnodes": [
              {"wdcode":"zb", "nodes":[{"code":"A010101","cname":"...","unit":"%"}]},
              {"wdcode":"sj", "nodes":[{"code":"202201","cname":"2022年1月"}]}
            ],
            "datanodes": [
              {"wds":[{"wdcode":"zb","valuecode":"A010101"}, ...],
               "data":{"strdata":"100.5","hasdata":true}}
            ]
          }
        }
        """
        if raw.get("returncode") != 200:
            logger.warning(f"API 异常: returncode={raw.get('returncode')}")
            return []

        returndata = raw.get("returndata", {})
        wdnodes = returndata.get("wdnodes", [])
        datanodes = returndata.get("datanodes", [])

        if not wdnodes or not datanodes:
            logger.warning("API 返回空数据")
            return []

        # 1) 维度映射 code → name/unit
        wd_map = {}
        dim_info = {}
        for idx, node in enumerate(wdnodes):
            wdcode = node["wdcode"]
            wd_map[wdcode] = idx
            dim_info[wdcode] = {
                n["code"]: {
                    "name": n.get("cname", n.get("name", "")),
                    "unit": n.get("unit", ""),
                }
                for n in node.get("nodes", [])
            }

        has_reg = "reg" in wd_map

        # 2) 遍历数据节点
        results = []
        for node in datanodes:
            if not node.get("data", {}).get("hasdata"):
                continue
            strdata = node.get("data", {}).get("strdata", "")
            if not strdata:
                continue

            val = _safe_float(strdata)
            if val is None:
                continue

            zb_code = node["wds"][wd_map["zb"]]["valuecode"]
            sj_code = node["wds"][wd_map["sj"]]["valuecode"]

            zb_name = dim_info["zb"].get(zb_code, {}).get("name",
                      CPI_INDICATORS.get(zb_code, zb_code))
            unit = dim_info["zb"].get(zb_code, {}).get("unit", "")

            extra = {"indicator_code": zb_code}

            if has_reg:
                reg_code = node["wds"][wd_map["reg"]]["valuecode"]
                reg_name = dim_info["reg"].get(reg_code, {}).get("name", reg_code)
                extra["region_code"] = reg_code
            else:
                reg_name = "全国"
                extra["region_code"] = ""

            results.append(DataPoint(
                date=_normalize_date(sj_code),
                value=val,
                indicator=zb_name,
                region=reg_name,
                unit=unit,
                source=self.name,
                extra=extra,
            ))

        return results

    # ── CPI 特有的辅助方法 ────────────────────────────

    @classmethod
    def list_indicators(cls, group: str = None) -> list[dict]:
        """
        列出 CPI 指标。
        Args:
            group: 分组名，None 表示全部
        Returns:
            [{"code": ..., "name": ..., "group": ...}]
        """
        code_to_group = {}
        for g, codes in CPI_GROUPS.items():
            for c in codes:
                code_to_group[c] = g

        results = []
        for code, name in CPI_INDICATORS.items():
            g = code_to_group.get(code, "其他")
            if group and g != group:
                continue
            results.append({"code": code, "name": name, "group": g})
        return results

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

        sorted_data = sorted(data, key=lambda d: d.date)
        results = []

        for i, d in enumerate(sorted_data):
            entry = d.to_dict()
            entry["yoy"] = None

            if len(d.date) == 7:  # YYYY-MM
                prev_date = f"{int(d.date[:4]) - 1}{d.date[4:]}"
                for prev in sorted_data:
                    if prev.date == prev_date and prev.value:
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

        sorted_data = sorted(data, key=lambda d: d.date)
        results = []

        for i, d in enumerate(sorted_data):
            entry = d.to_dict()
            entry["mom"] = None
            if i > 0 and sorted_data[i - 1].value:
                entry["mom"] = round(
                    (d.value / sorted_data[i - 1].value - 1) * 100, 2
                )
            results.append(entry)

        return results

    @staticmethod
    def summary(data: list[DataPoint]) -> dict:
        """生成 CPI 摘要统计。"""
        if not data:
            return {"count": 0}

        sorted_data = sorted(data, key=lambda d: d.date)
        values = [d.value for d in sorted_data if d.value is not None]

        if not values:
            return {"count": len(data)}

        min_d = min(sorted_data, key=lambda d: d.value or float("inf"))
        max_d = max(sorted_data, key=lambda d: d.value or float("-inf"))
        latest = sorted_data[-1]
        mean_val = sum(values) / len(values)

        result = {
            "indicator": sorted_data[0].indicator,
            "period": f"{sorted_data[0].date} ~ {latest.date}",
            "count": len(sorted_data),
            "min": {"date": min_d.date, "value": min_d.value},
            "max": {"date": max_d.date, "value": max_d.value},
            "mean": round(mean_val, 2),
            "latest": {"date": latest.date, "value": latest.value},
        }

        if len(sorted_data) >= 13:
            prev = sorted_data[-13]
            if prev.value:
                result["latest_yoy"] = round(
                    (latest.value / prev.value - 1) * 100, 2
                )

        return result

    @staticmethod
    def describe_code(code: str) -> str:
        """返回指标代码的中文说明。"""
        return CPI_INDICATORS.get(code, f"未知指标代码: {code}")
