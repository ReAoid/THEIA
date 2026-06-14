"""
数据源：国家统计局 EasyQuery API

调 API 拿 JSON 数据，最轻量稳定的方式。
"""

import json
import time
import logging

import requests

from crawler.base import DataSource, DataPoint
from crawler.middleware import rate_limit, retry, log_request

logger = logging.getLogger(__name__)

# ── API 参数 ──────────────────────────────────────────

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


class StatsAPISource(DataSource):
    """
    国家统计局 API 数据源。

    用法：
        source = StatsAPISource(zbcode="A010101", period="202201")
        data = source.flow()
    """

    name = "stats_api"

    def __init__(self, zbcode: str, period: str, dbcode: str = "hgyd"):
        super().__init__(zbcode=zbcode, period=period, dbcode=dbcode)
        self.zbcode = zbcode
        self.period = period
        self.dbcode = dbcode

        # 持久化 Session（参考 cnstats-main/common.py）
        # 复用 Session 保留 Cookie，避免 403
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._session.trust_env = False
        self._initialized = False

    def _ensure_session(self):
        """先访问首页拿 Cookie，避免 403。"""
        if self._initialized:
            return
        logger.info("初始化 Session：访问统计局首页获取 Cookie")
        try:
            self._session.get("https://data.stats.gov.cn", timeout=15, verify=False)
            self._initialized = True
        except Exception as e:
            logger.warning(f"Session 初始化失败: {e}")
            self._initialized = True

    # ── 请求 ──────────────────────────────────────────

    @rate_limit(interval=2.0)
    @retry(max_times=3, delay=1.0)
    @log_request
    def fetch(self) -> dict:
        """发 POST 请求，返回 JSON 字典。"""
        self._ensure_session()

        payload = {
            "m": "QueryData",
            "dbcode": self.dbcode,
            "rowcode": "zb",
            "colcode": "sj",
            "wds": json.dumps([]),
            "dfwds": json.dumps([
                {"wdcode": "zb", "valuecode": self.zbcode},
                {"wdcode": "sj", "valuecode": self.period},
            ]),
            "k1": str(int(time.time() * 1000)),
        }

        resp = self._session.post(BASE_URL, data=payload, timeout=15, verify=False)
        resp.raise_for_status()
        return resp.json()

    # ── 解析 ──────────────────────────────────────────

    def parse(self, raw: dict) -> list[DataPoint]:
        """从 API 返回的 JSON 里提取数据。"""
        if raw.get("returncode") != 200:
            logger.warning(f"API 异常: returncode={raw.get('returncode')}")
            return []

        returndata = raw.get("returndata", {})
        wdnodes = returndata.get("wdnodes", [])
        datanodes = returndata.get("datanodes", [])

        if not wdnodes or not datanodes:
            logger.warning("API 返回空数据")
            return []

        # 构建维度映射
        wd_map = {}
        for idx, node in enumerate(wdnodes):
            wd_map[node["wdcode"]] = idx

        # 维度值 → 名称
        dim_info = {}
        for wdcode, idx in wd_map.items():
            dim_info[wdcode] = {}
            for n in wdnodes[idx].get("nodes", []):
                dim_info[wdcode][n["code"]] = n.get("cname", n.get("name", ""))

        has_reg = "reg" in wd_map
        results = []

        for node in datanodes:
            if not node.get("data", {}).get("hasdata"):
                continue

            strdata = node.get("data", {}).get("strdata", "")
            if not strdata:
                continue

            zb = node["wds"][wd_map["zb"]]["valuecode"]
            sj = node["wds"][wd_map["sj"]]["valuecode"]
            region = node["wds"][wd_map["reg"]]["valuecode"] if has_reg else ""

            results.append(DataPoint(
                date=sj,
                value=float(strdata.replace(",", "").replace("，", "")),
                indicator=dim_info["zb"].get(zb, zb),
                region=dim_info["reg"].get(region, "全国") if region else "全国",
                unit=next((n.get("unit", "") for n in wdnodes[wd_map["zb"]].get("nodes", []) if n["code"] == zb), ""),
                source=self.name,
                extra={"indicator_code": zb, "region_code": region},
            ))

        return results
