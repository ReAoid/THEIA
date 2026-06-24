"""
货币供应量数据管理者

职责：
  1. 封装 MoneySupplySource，提供更友好的查询接口
  2. 缓存管理 — 委托给 MoneySupplyStore，先读缓存，没有再请求 API
  3. 灵活筛选 — 支持按指标名称、UUID、分组名查询

用法：
    mgr = MoneySupplyManager()

    # 拿全部货币供应量（6 项），默认 2000 年至今
    data = mgr.get_money_supply()

    # 只看同比增长
    data = mgr.get_money_supply(group="同比增长")

    # 只看期末值
    data = mgr.get_money_supply(group="期末值")

    # 强制刷新
    data = mgr.get_money_supply(force_update=True)

    # 按年份
    data = mgr.get_money_supply(period="2026")
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from crawler.base import DataPoint
from crawler.sources.money_supply_source import (
    MoneySupplySource,
    MONEY_SUPPLY_GROUPS,
    CID_PERIODS,
    MONEY_SUPPLY_UUID_INDICATORS,
)
from storage.money_supply_store import MoneySupplyStore

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).parent.parent / "cache"


class MoneySupplyManager:
    """
    货币供应量数据管理者。

    在 MoneySupplySource 之上增加：
      - 本地缓存读写（委托给 MoneySupplyStore）
      - 按名称/分组灵活筛选指标
      - 强制全量更新
    """

    def __init__(self, cache_dir: str | Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._store = MoneySupplyStore(cache_dir=self.cache_dir)
        self._all_data: list[DataPoint] = []
        self._cache_loaded = False

    # ── 公开查询接口 ──────────────────────────────────

    def get_money_supply(
        self,
        indicators: str | list[str] | None = None,
        group: str | None = None,
        period: str | None = None,
        force_update: bool = False,
    ) -> list[DataPoint]:
        """
        获取货币供应量数据。

        Args:
            indicators: 要筛选的指标。
                - None / "all" → 全部 6 项
                - "M2"         → 按名称模糊匹配
                - UUID 字符串  → 精确匹配 indicator_uuid
            group: 分组名，如 "期末值"、"同比增长"、"全指标"。
                与 indicators 互斥，同时传时 group 优先。
            period: 时间段（同 MoneySupplySource 的 period 参数）。
                - None         → 使用缓存中的全部时间段（默认 2000 年至今）
                - "202605"     → 单月
                - "200001-202606" → 范围
                - "2026"       → 全年
            force_update: 是否强制从 API 拉取（忽略缓存）。

        Returns:
            符合条件的 DataPoint 列表
        """
        self._load_cache()

        need_fetch = force_update
        if not need_fetch and not self._all_data:
            need_fetch = True
            period = period or "200001-202606"
        if not need_fetch and period is not None:
            need_fetch = not self._cache_covers_period(period)

        if need_fetch:
            self._fetch_from_api(period=period)

        data = self._all_data
        if group:
            data = self._filter_by_group(data, group)
        elif indicators is not None and indicators != "all":
            data = self._filter_by_indicators(data, indicators)

        if period is not None:
            data = self._filter_by_period(data, period)

        return data

    # ── 便捷方法 ──────────────────────────────────────

    def get_yoy_growth(self, period: str | None = None,
                       force_update: bool = False) -> list[DataPoint]:
        """快捷获取 M0/M1/M2 同比增长数据。"""
        return self.get_money_supply(
            group="同比增长",
            period=period,
            force_update=force_update,
        )

    def get_absolute_values(self, period: str | None = None,
                            force_update: bool = False) -> list[DataPoint]:
        """快捷获取 M0/M1/M2 期末绝对值数据。"""
        return self.get_money_supply(
            group="期末值",
            period=period,
            force_update=force_update,
        )

    def get_by_group(self, group_name: str, period: str | None = None,
                     force_update: bool = False) -> list[DataPoint]:
        """按分组获取货币供应量数据。"""
        return self.get_money_supply(
            group=group_name,
            period=period,
            force_update=force_update,
        )

    # ── 缓存管理 ──────────────────────────────────────

    def clear_cache(self):
        self._all_data = []
        self._cache_loaded = False
        self._store.clear()

    def get_cache_info(self) -> dict:
        self._load_cache()
        info = self._store.get_cache_info()
        info["cached"] = info.get("valid", False)
        info["cache_file"] = str(self._store.cache_file)
        if self._all_data:
            indicators = sorted({d.indicator for d in self._all_data})
            info["indicators"] = indicators
        return info

    def _load_cache(self):
        if self._cache_loaded:
            return
        self._all_data = self._store.load()
        if self._all_data:
            logger.info(f"从缓存加载了 {len(self._all_data)} 条货币供应量数据")
        else:
            logger.info("本地无货币供应量缓存")
        self._cache_loaded = True

    def _save_cache(self, data: list[DataPoint]):
        count = self._store.save(data)
        self._all_data = self._store.load(force=True)
        logger.info(f"货币供应量缓存已更新: {count} 条")

    def _fetch_from_api(self, period: str | None = None):
        """从 API 拉取货币供应量数据。"""
        from crawler.sources.money_supply_source import (
            _period_to_dts,
            get_period_config_for_range,
            MoneySupplySource,
        )

        effective_period = period or "200001-202606"

        dts = _period_to_dts(effective_period)
        if not dts:
            source = MoneySupplySource(period=effective_period)
            raw_data = source.flow()
            if raw_data:
                self._save_cache(raw_data)
            return

        dt_range = dts[0]
        if "-" in dt_range:
            parts = dt_range.split("-")
            start_code = parts[0].replace("MM", "")
            end_code = parts[1].replace("MM", "")
        else:
            start_code = dt_range.replace("MM", "")
            end_code = start_code

        start_year = int(start_code[:4]) if start_code.isdigit() else None
        end_year = int(end_code[:4]) if end_code.isdigit() else None
        if start_year is None or end_year is None:
            source = MoneySupplySource(period=effective_period)
            raw_data = source.flow()
            if raw_data:
                self._save_cache(raw_data)
            return

        period_configs = get_period_config_for_range(start_year, end_year)
        if not period_configs:
            source = MoneySupplySource(period=effective_period)
            raw_data = source.flow()
            if raw_data:
                self._save_cache(raw_data)
            return

        all_data: list[DataPoint] = []
        for cfg in period_configs:
            logger.info(f"拉取货币供应量 {cfg['label']} 周期数据")
            try:
                source = MoneySupplySource(
                    period=effective_period,
                    indicator_ids=list(cfg["indicator_ids"]),
                    cid=cfg["cid"],
                    root_id=cfg.get("root_id"),
                )
                raw_data = source.flow()
                if raw_data:
                    all_data.extend(raw_data)
                    logger.info(f"  → {len(raw_data)} 条")
            except Exception as e:
                logger.error(f"拉取货币供应量 {cfg['label']} 失败: {e}")

        if all_data:
            self._save_cache(all_data)
        else:
            logger.warning("货币供应量 API 未返回任何数据")

    # ── 内部：筛选 ────────────────────────────────────

    @staticmethod
    def _point_key(d: DataPoint) -> tuple:
        return (d.date, d.indicator, d.region)

    def _filter_by_indicators(self, data: list[DataPoint],
                               indicators: str | list[str]) -> list[DataPoint]:
        """
        按指标名称 / UUID / 关键词筛选。
        """
        if isinstance(indicators, str):
            indicators = [indicators]

        def _norm(name: str) -> str:
            return name.replace(" ", "").replace("(", "").replace(")", "").lower()

        uuid_entries: list[tuple[str, str]] = [
            (name, uuid) for uuid, name in MONEY_SUPPLY_UUID_INDICATORS.items()
        ]

        target_uuids: set[str] = set()

        for ind in indicators:
            ind = ind.strip()
            if not ind:
                continue

            cleaned = ind.replace("-", "")
            is_uuid = len(cleaned) == 32 and all(c in "0123456789abcdefABCDEF" for c in cleaned)

            if is_uuid:
                target_uuids.add(ind.lower())
            else:
                norm_input = _norm(ind)
                for raw_name, uuid in uuid_entries:
                    if _norm(raw_name) == norm_input:
                        target_uuids.add(uuid.lower())
                if len(ind) <= 10:
                    for raw_name, uuid in uuid_entries:
                        if norm_input in _norm(raw_name):
                            target_uuids.add(uuid.lower())

        result = []
        for d in data:
            d_uuid = d.extra.get("indicator_uuid", "").lower()
            d_id = d.extra.get("_id", "").lower()

            if d_uuid in target_uuids or d_id in target_uuids:
                result.append(d)
                continue

            if not target_uuids:
                d_name = d.indicator.lower()
                for ind in indicators:
                    ind = ind.strip()
                    if not ind:
                        continue
                    if d_name == ind.lower():
                        result.append(d)
                        break
                    if len(ind) <= 10 and ind.lower() in d_name:
                        result.append(d)
                        break
                    if _norm(d_name) == _norm(ind):
                        result.append(d)
                        break
                    norm_input = _norm(ind)
                    norm_dname = _norm(d_name)
                    if len(norm_input) <= 10 and norm_input in norm_dname:
                        result.append(d)
                        break

        return result

    def _filter_by_group(self, data: list[DataPoint],
                          group_name: str) -> list[DataPoint]:
        """按分组筛选。"""
        uuids = MONEY_SUPPLY_GROUPS.get(group_name)
        if not uuids:
            logger.warning(f"未知分组: {group_name}，可用分组: {list(MONEY_SUPPLY_GROUPS.keys())}")
            return []
        return self._filter_by_indicators(data, uuids)

    def _filter_by_period(self, data: list[DataPoint],
                           period: str) -> list[DataPoint]:
        """按时间段过滤已缓存的数据。"""
        from crawler.sources.money_supply_source import _period_to_dts

        dts = _period_to_dts(period)
        if not dts:
            return data

        dt_range = dts[0]
        if "-" in dt_range:
            parts = dt_range.split("-")
            start_code = parts[0].replace("MM", "")
            end_code = parts[1].replace("MM", "")
        else:
            start_code = dt_range.replace("MM", "")
            end_code = start_code

        def _to_sort_key(code: str) -> int:
            return int(code) if code.isdigit() else 0

        start_key = _to_sort_key(start_code)
        end_key = _to_sort_key(end_code)

        result = []
        for d in data:
            date_key = int(d.date.replace("-", ""))
            if start_key <= date_key <= end_key:
                result.append(d)

        return result

    def _cache_covers_period(self, period: str) -> bool:
        """检查缓存是否已覆盖请求的时间段。"""
        from crawler.sources.money_supply_source import _period_to_dts

        if not self._all_data:
            return False

        dts = _period_to_dts(period)
        if not dts:
            return True

        dt_range = dts[0]
        if "-" in dt_range:
            parts = dt_range.split("-")
            start_code = parts[0].replace("MM", "")
            end_code = parts[1].replace("MM", "")
        else:
            start_code = dt_range.replace("MM", "")
            end_code = start_code

        def _to_sort_key(code: str) -> int:
            return int(code) if code.isdigit() else 0

        start_key = _to_sort_key(start_code)
        end_key = _to_sort_key(end_code)

        cached_dates = {int(d.date.replace("-", "")) for d in self._all_data}
        if not cached_dates:
            return False

        return start_key in cached_dates and end_key in cached_dates
