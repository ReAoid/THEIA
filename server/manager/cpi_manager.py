"""
CPI 数据管理者

职责：
  1. 封装 CPISource，提供更友好的查询接口
  2. 缓存管理 — 委托给 CPIStore，先读缓存，没有再请求 API
  3. 灵活筛选 — 支持按指标名称、UUID、分组名查询

用法：
    mgr = CPIManager()

    # 拿全部 CPI（13 项），默认最近 12 个月
    data = mgr.get_cpi()

    # 只要总体 CPI
    data = mgr.get_cpi(indicators="总体CPI")

    # 只要居住类 + 教育类
    data = mgr.get_cpi(indicators=["居住", "教育"])

    # 按分组
    data = mgr.get_cpi(group="核心CPI(8项)")

    # 强制刷新（忽略本地缓存）
    data = mgr.get_cpi(force_update=True)

    # 按年份
    data = mgr.get_cpi(period="2026")
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from crawler.base import DataPoint
from crawler.sources.cpi_source import (
    CPISource,
    CPI_GROUPS,
)
from storage.cpi_store import CPIStore

logger = logging.getLogger(__name__)

# ── 默认缓存目录 ──────────────────────────────────────

DEFAULT_CACHE_DIR = Path(__file__).parent.parent / "cache"


# ═══════════════════════════════════════════════════════════
#  CPIManager
# ═══════════════════════════════════════════════════════════

class CPIManager:
    """
    CPI 数据管理者。

    在 CPISource 之上增加：
      - 本地缓存读写（委托给 CPIStore）
      - 按名称/分组灵活筛选指标
      - 部分更新（只拉缺失的时间段）
      - 强制全量更新
    """

    def __init__(self, cache_dir: str | Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 使用 CPIStore 管理持久化
        self._store = CPIStore(cache_dir=self.cache_dir)
        self._all_data: list[DataPoint] = []  # 当前生命周期内的全量内存缓存
        self._cache_loaded = False

    # ── 向后兼容属性 ──────────────────────────────

    @property
    def _cache_file(self) -> Path:
        """获取缓存文件路径（向后兼容）。"""
        return self._store.cache_file

    # ── 公开查询接口 ──────────────────────────────────

    def get_cpi(
        self,
        indicators: str | list[str] | None = None,
        group: str | None = None,
        period: str | None = None,
        force_update: bool = False,
    ) -> list[DataPoint]:
        """
        获取 CPI 数据。

        Args:
            indicators: 要筛选的指标。
                - None / "all" → 全部 13 项
                - "总体CPI"    → 只返回总体居民消费价格指数
                - "居住"       → 按名称模糊匹配（含"居住"的指标）
                - ["居住","教育"] → 多个模糊匹配（取并集）
                - UUID 字符串   → 精确匹配 indicator_uuid
            group: 分组名，如 "全部CPI(13项)"、"核心CPI(8项)"。
                与 indicators 互斥，同时传时 group 优先。
            period: 时间段（同 CPISource 的 period 参数）。
                - None         → 使用缓存中的全部时间段（默认最近 12 个月）
                - "202605"     → 单月
                - "202406-202605" → 范围
                - "2026"       → 全年
            force_update: 是否强制从 API 拉取（忽略缓存）。

        Returns:
            符合条件的 DataPoint 列表
        """
        # 1. 缓存加载（懒加载）
        self._load_cache()

        # 2. 判断是否需要拉取
        need_fetch = force_update or not self._all_data
        if not need_fetch and period is not None:
            # 检查缓存是否覆盖了请求的时间段
            need_fetch = not self._cache_covers_period(period)

        # 3. 拉取
        if need_fetch:
            self._fetch_from_api(period=period, force_update=force_update)

        # 4. 筛选指标
        data = self._all_data
        if group:
            data = self._filter_by_group(data, group)
        elif indicators is not None and indicators != "all":
            data = self._filter_by_indicators(data, indicators)

        # 5. 按时间段再过滤（如果缓存比请求范围大）
        if period is not None and not need_fetch:
            data = self._filter_by_period(data, period)

        return data

    # ── 便捷方法 ──────────────────────────────────────

    def get_overall_cpi(self, period: str | None = None,
                        force_update: bool = False) -> list[DataPoint]:
        """快捷获取总体 CPI（居民消费价格指数）"""
        return self.get_cpi(
            indicators="居民消费价格指数",
            period=period,
            force_update=force_update,
        )

    def get_by_group(self, group_name: str, period: str | None = None,
                     force_update: bool = False) -> list[DataPoint]:
        """按分组获取 CPI 数据"""
        return self.get_cpi(
            group=group_name,
            period=period,
            force_update=force_update,
        )

    def get_core_cpi(self, period: str | None = None,
                     force_update: bool = False) -> list[DataPoint]:
        """快捷获取核心 CPI（8 项）"""
        return self.get_by_group("核心CPI(8项)", period=period,
                                 force_update=force_update)

    # ── 缓存管理（委托给 CPIStore）────────────────────

    def clear_cache(self):
        """清空本地缓存文件和内存数据。"""
        self._all_data = []
        self._cache_loaded = False
        self._store.clear()

    def get_cache_info(self) -> dict:
        """查看缓存状态（含指标和时间范围）。"""
        self._load_cache()
        info = self._store.get_cache_info()
        # 向后兼容键
        info["cached"] = info.get("valid", False)
        info["cache_file"] = str(self._store.cache_file)
        if self._all_data:
            indicators = sorted({d.indicator for d in self._all_data})
            info["indicators"] = indicators
        return info

    # ── 内部：缓存读写（委托给 CPIStore）───────────────

    def _load_cache(self):
        """通过 CPIStore 从本地 JSON 文件加载缓存。"""
        if self._cache_loaded:
            return

        self._all_data = self._store.load()
        if self._all_data:
            logger.info(f"从缓存加载了 {len(self._all_data)} 条 CPI 数据")
        else:
            logger.info("本地无缓存")

        self._cache_loaded = True

    def _save_cache(self, data: list[DataPoint]):
        """通过 CPIStore 写入本地缓存（增量合并）。"""
        count = self._store.save(data)
        self._all_data = self._store.load(force=True)
        logger.info(f"缓存已更新: {count} 条")

    # ── 内部：API 拉取 ────────────────────────────────

    def _fetch_from_api(self, period: str | None = None,
                        force_update: bool = False):
        """
        从 API 拉取数据。

        - force_update=True：全量拉取（默认 5 年）
        - 否则：只拉指定时间段
        """
        effective_period = period or "202406-202605"  # 默认最近 12 个月

        if force_update:
            # 强制更新：拉 5 年全覆盖
            now = datetime.now()
            end = f"{now.year}{now.month:02d}"
            start = f"{now.year - 5}{now.month:02d}"
            effective_period = f"{start}-{end}"
            logger.info(f"强制更新: 拉取 {effective_period}")

        # 用 CPISource 拉取全部 13 个指标
        source = CPISource(period=effective_period)
        logger.info(f"从 API 拉取 CPI 数据: {effective_period}")
        raw_data = source.flow()

        if raw_data:
            self._save_cache(raw_data)
        else:
            logger.warning("API 未返回数据")

    # ── 内部：筛选 ────────────────────────────────────

    @staticmethod
    def _point_key(d: DataPoint) -> tuple:
        """数据点的唯一键（用于去重合并）。"""
        return (d.date, d.indicator, d.region)

    def _filter_by_indicators(self, data: list[DataPoint],
                               indicators: str | list[str]) -> list[DataPoint]:
        """
        按指标名称 / UUID / 关键词筛选。

        支持：
          - UUID 精确匹配（匹配 extra.indicator_uuid）
          - 中文名精确匹配
          - 中文名模糊匹配（子串包含）
        """
        if isinstance(indicators, str):
            indicators = [indicators]

        # 构建筛选条件（全转小写以便大小写不敏感匹配）
        conditions = []
        for ind in indicators:
            ind = ind.strip()
            if not ind:
                continue

            # 判断是否是 UUID（32位hex + 4个连字符 = 36字符，或纯32位）
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
                    # 也匹配 _id
                    if d.extra.get("_id", "").lower() == cond_val.lower():
                        result.append(d)
                        break
                elif cond_type == "name":
                    d_name = d.indicator.lower()
                    # 精确匹配
                    if d_name == cond_val:
                        result.append(d)
                        break
                    # 短关键词（≤10字符）做模糊匹配（子串包含），
                    # 避免长名称如"居民消费价格指数"误匹配"居住类居民消费价格指数"
                    if len(cond_val) <= 10 and cond_val in d_name:
                        result.append(d)
                        break

        return result

    def _filter_by_group(self, data: list[DataPoint],
                          group_name: str) -> list[DataPoint]:
        """按分组筛选。"""
        uuids = CPI_GROUPS.get(group_name)
        if not uuids:
            logger.warning(f"未知分组: {group_name}，可用分组: {list(CPI_GROUPS.keys())}")
            return []

        return self._filter_by_indicators(data, uuids)

    def _filter_by_period(self, data: list[DataPoint],
                           period: str) -> list[DataPoint]:
        """按时间段过滤已缓存的数据。"""
        from crawler.sources.cpi_source import _period_to_dts

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
        from crawler.sources.cpi_source import _period_to_dts

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

        # 检查区间的首尾月份是否都有数据
        return start_key in cached_dates and end_key in cached_dates

    # ── 注册表校验 ──────────────────────────────

    def validate_registry(self, period: str = "202605") -> dict:
        """
        全量校验 CPI_UUID_INDICATORS 注册表是否与最新 API 返回一致。

        这是一个防御性检查，建议在以下时机调用：
          - 首次部署时
          - 数据异常时（如某个指标突然全部为 None）
          - 定期（如每月）巡检

        Args:
            period: 用于校验的时间段，默认最近一个月。

        Returns:
            {
                "checked": 13,
                "ok": 13,
                "mismatches": [],       # UUID 还在但名称变了
                "unknown": [],          # 全新的 UUID
                "cid_match": True,      # 页面 CID 是否仍有效
            }
        """
        from crawler.sources.cpi_source import CPISource
        return CPISource.validate_registry(period=period)
