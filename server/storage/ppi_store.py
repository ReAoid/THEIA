"""
PPI 数据专用存储 —— PPIStore

继承 BaseStore，提供 DataPoint ↔ dict 的序列化，
以及 PPI 特有的查询方法（按指标名、UUID、分组筛选）。

用法：
    from storage.ppi_store import PPIStore
    from crawler.sources.ppi_source import PPISource

    source = PPISource(period="202306-202605")
    data = source.flow()

    store = PPIStore()
    store.save(data)

    cached = store.load()

    info = store.get_cache_info()
"""

import logging
from pathlib import Path
from typing import Any

from crawler.base import DataPoint
from storage.base import BaseStore

logger = logging.getLogger(__name__)


class PPIStore(BaseStore[DataPoint]):
    """
    PPI 数据专用存储。

    数据唯一键：(date, indicator, region) — 与 PPIManager 保持一致。
    序列化/反序列化直接复用 DataPoint.to_dict() 和构造方法。
    """

    store_name = "ppi"

    def __init__(self, cache_dir: str | Path | None = None,
                 cache_file: str | Path | None = None,
                 max_age_hours: int | None = None):
        super().__init__(cache_dir=cache_dir, cache_file=cache_file,
                         max_age_hours=max_age_hours)

    # ── BaseStore 抽象方法实现 ────────────────────────

    def _point_key(self, item: DataPoint) -> tuple:
        """PPI 数据的唯一键：(date, indicator, region)。"""
        return (item.date, item.indicator, item.region)

    def _serialize(self, item: DataPoint) -> dict:
        """DataPoint → dict。"""
        return item.to_dict()

    def _deserialize(self, data: dict) -> DataPoint:
        """dict → DataPoint。"""
        return DataPoint(
            date=data.get("date", ""),
            value=data.get("value"),
            indicator=data.get("indicator", ""),
            region=data.get("region", "国家"),
            unit=data.get("unit", ""),
            source=data.get("source", "ppi"),
            extra={k: v for k, v in data.items()
                   if k not in ("date", "value", "indicator",
                                "region", "unit", "source")},
        )

    # ── PPI 特有查询方法 ──────────────────────────────

    def get_by_indicator(self, indicator: str | list[str]) -> list[DataPoint]:
        """
        按指标名称/UUID/关键词筛选。

        Args:
            indicator: 指标名称/UUID/关键词，或它们的列表

        Returns:
            符合条件的 DataPoint 列表
        """
        data = self.load()
        if not data:
            return []

        if isinstance(indicator, str):
            indicators = [indicator]
        else:
            indicators = indicator

        conditions = []
        for ind in indicators:
            ind = ind.strip()
            if not ind:
                continue
            cleaned = ind.replace("-", "")
            if len(cleaned) == 32 and all(c in "0123456789abcdefABCDEF" for c in cleaned):
                conditions.append(("uuid", ind))
            else:
                conditions.append(("name", ind.lower()))

        result = []
        for d in data:
            for cond_type, cond_val in conditions:
                if cond_type == "uuid":
                    if d.extra.get("indicator_uuid", "").lower() == cond_val.lower():
                        result.append(d)
                        break
                    if d.extra.get("_id", "").lower() == cond_val.lower():
                        result.append(d)
                        break
                elif cond_type == "name":
                    d_name = d.indicator.lower()
                    if d_name == cond_val or cond_val in d_name:
                        result.append(d)
                        break

        return result

    def get_by_group(self, group_name: str) -> list[DataPoint]:
        """
        按 PPI 分组筛选。

        可用分组：
          - "总PPI"
          - "两大分项"

        Args:
            group_name: 分组名称

        Returns:
            该分组下的全部 DataPoint
        """
        from crawler.sources.ppi_source import PPI_GROUPS

        uuids = PPI_GROUPS.get(group_name)
        if not uuids:
            logger.warning(f"未知 PPI 分组: {group_name}")
            return []

        return self.get_by_indicator(list(uuids))

    def get_period(self, start: str, end: str | None = None) -> list[DataPoint]:
        """
        按时间段筛选。

        Args:
            start: 起始日期 "YYYY-MM" 或 "YYYYMM"
            end: 结束日期，默认与 start 相同

        Returns:
            时间段内的 DataPoint
        """
        data = self.load()
        if not data:
            return []

        start_key = int(start.replace("-", "").replace("MM", ""))
        end_key = int(end.replace("-", "").replace("MM", "")) if end else start_key

        result = []
        for d in data:
            date_key = int(d.date.replace("-", ""))
            if start_key <= date_key <= end_key:
                result.append(d)

        return result

    def get_summary(self) -> dict:
        """
        生成 PPI 数据摘要。

        Returns:
            {
                "count": 总条数,
                "indicators": 指标种类数,
                "date_range": "YYYY-MM ~ YYYY-MM",
                "details": { 指标名: { count, min, max, mean, latest } }
            }
        """
        data = self.load()
        if not data:
            return {"count": 0, "indicators": 0, "date_range": None, "details": {}}

        from collections import defaultdict

        by_indicator: dict[str, list[DataPoint]] = defaultdict(list)
        for d in data:
            by_indicator[d.indicator].append(d)

        dates = sorted({d.date for d in data if d.date})
        details = {}

        for indicator, points in by_indicator.items():
            sorted_points = sorted(points, key=lambda p: p.date)
            values = [p.value for p in sorted_points if p.value is not None]

            if not values:
                details[indicator] = {"count": len(points)}
                continue

            min_p = min(sorted_points, key=lambda p: p.value or float("inf"))
            max_p = max(sorted_points, key=lambda p: p.value or float("-inf"))
            latest = sorted_points[-1]
            mean_val = sum(values) / len(values)

            s = {
                "count": len(sorted_points),
                "min": {"date": min_p.date, "value": min_p.value},
                "max": {"date": max_p.date, "value": max_p.value},
                "mean": round(mean_val, 2),
                "latest": {"date": latest.date, "value": latest.value},
            }
            details[indicator] = s

        return {
            "count": len(data),
            "indicators": len(by_indicator),
            "date_range": f"{dates[0]} ~ {dates[-1]}" if len(dates) >= 2 else (dates[0] if dates else None),
            "details": details,
        }
