"""
数据源：国家统计局 HTML 页面

爬不带 API 的静态页面，从 <table> 里解析数据。
"""

import re
import logging

import requests
from bs4 import BeautifulSoup

from crawler.base import DataSource, DataPoint
from crawler.middleware import rate_limit, retry, log_request

logger = logging.getLogger(__name__)


# ── 工具函数 ──────────────────────────────────────────

def _safe_float(v: str | None) -> float | None:
    if v is None:
        return None
    v = v.strip().replace(",", "").replace("，", "")
    if not v:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _normalize_date(s: str) -> str:
    """统一日期格式为 YYYY-MM。"""
    s = s.strip()
    m = re.match(r'(\d{4})\s*年\s*(\d{1,2})\s*月?', s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r'(\d{4})[-/](\d{1,2})', s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.match(r'(\d{4})(\d{2})', s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


# ── 数据源 ────────────────────────────────────────────

class HTMLTableSource(DataSource):
    """
    从 HTML <table> 里解析数据。

    用法：
        source = HTMLTableSource(url="https://...", indicator="CPI")
        data = source.flow()
    """

    name = "stats_html"

    def __init__(self, url: str, indicator: str = "general"):
        super().__init__(url=url, indicator=indicator)
        self.url = url

    # ── 请求 ──────────────────────────────────────────

    @rate_limit(interval=2.0)
    @retry(max_times=3, delay=1.0)
    @log_request
    def fetch(self) -> str:
        """GET 请求，返回 HTML 文本。"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        resp = requests.get(self.url, headers=headers, timeout=15)
        resp.encoding = "utf-8"
        resp.raise_for_status()
        return resp.text

    # ── 解析 ──────────────────────────────────────────

    def parse(self, html: str) -> list[DataPoint]:
        """从 HTML 表格里提取数据。"""
        soup = BeautifulSoup(html, "lxml")

        # 策略 1：<table>
        data = self._parse_table(soup)
        if data:
            return data

        # 策略 2：列表 <ul><li>
        data = self._parse_list(soup)
        if data:
            return data

        logger.warning("HTML 中没有找到表格或列表数据")
        return []

    def _parse_table(self, soup: BeautifulSoup) -> list[DataPoint]:
        tables = soup.find_all("table")
        if not tables:
            return []

        results = []
        for table in tables:
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # 表头
            headers = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]

            # 找日期列、数值列、地区列
            date_idx = next((i for i, h in enumerate(headers)
                             if any(k in h for k in ["日期", "时间", "年月", "date", "time"])), 0)
            val_idx = next((i for i, h in enumerate(headers)
                            if any(k in h for k in ["数值", "数据", "指标值", "value", "index"])), 1 if len(headers) > 1 else 0)
            reg_idx = next((i for i, h in enumerate(headers)
                            if any(k in h for k in ["地区", "区域", "region", "area"])), None)

            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) <= max(date_idx, val_idx):
                    continue

                d = cells[date_idx].get_text(strip=True)
                v = _safe_float(cells[val_idx].get_text(strip=True))
                r = cells[reg_idx].get_text(strip=True) if reg_idx is not None and reg_idx < len(cells) else "全国"

                if d and v is not None:
                    results.append(DataPoint(
                        date=_normalize_date(d),
                        value=v,
                        region=r,
                        source=self.name,
                    ))

        return results

    def _parse_list(self, soup: BeautifulSoup) -> list[DataPoint]:
        for ul in soup.find_all("ul"):
            items = ul.find_all("li")
            if len(items) < 2:
                continue

            results = []
            for li in items:
                text = li.get_text(strip=True)
                m = re.match(r'([\d\-年\.月/]+)\s*[:：]?\s*([\d\.\,\-]+)', text)
                if m:
                    d = _normalize_date(m.group(1))
                    v = _safe_float(m.group(2))
                    if d and v is not None:
                        results.append(DataPoint(
                            date=d,
                            value=v,
                            region="全国",
                            source=self.name,
                        ))

            if results:
                return results

        return []
