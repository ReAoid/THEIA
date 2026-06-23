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
    data = mgr.get_cpi(group="八大标准分项")

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
    CID_PERIODS,
    CPI_UUID_INDICATORS,
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
                - None / "all" → 全部 10 项
                - "总体CPI"    → 只返回总体居民消费价格指数
                - "居住"       → 按名称模糊匹配（含"居住"的指标）
                - ["居住","教育"] → 多个模糊匹配（取并集）
                - UUID 字符串   → 精确匹配 indicator_uuid
            group: 分组名，如 "总CPI"、"八大标准分项"、"核心CPI"。
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

        # 2. 判断是否需要从 API 拉取
        #    - 强制刷新：拉取指定时间段
        #    - 本地无数据：拉默认最近 12 个月
        #    - 本地数据不全（缺某时间段）：自动补全
        need_fetch = force_update
        if not need_fetch and not self._all_data:
            need_fetch = True
            period = period or "202406-202605"
        if not need_fetch and period is not None:
            need_fetch = not self._cache_covers_period(period)

        # 3. 从 API 拉取（无 7 天过期限制，本地有就直接用）
        if need_fetch:
            self._fetch_from_api(period=period)

        # 4. 筛选指标
        data = self._all_data
        if group:
            data = self._filter_by_group(data, group)
        elif indicators is not None and indicators != "all":
            data = self._filter_by_indicators(data, indicators)

        # 5. 按时间段过滤
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
        """快捷获取核心 CPI（不包括食品和能源）"""
        return self.get_by_group("核心CPI", period=period,
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

    def _fetch_from_api(self, period: str | None = None):
        """
        从 API 拉取数据（自动处理跨 CID 周期）。

        如果 period 跨越多个 CID 周期，对每个周期分别发起 API 请求并合并。

        Args:
            period: 要拉取的时间段，None 则默认最近 12 个月。
        """
        from crawler.sources.cpi_source import (
            _period_to_dts,
            get_period_config_for_range,
            CPISource,
        )

        effective_period = period or "202406-202605"

        # 解析起止年份
        dts = _period_to_dts(effective_period)
        if not dts:
            logger.warning(f"无法解析 period: {effective_period}")
            source = CPISource(period=effective_period)
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
            source = CPISource(period=effective_period)
            raw_data = source.flow()
            if raw_data:
                self._save_cache(raw_data)
            return

        # 找出所有涉及的 CID 周期
        period_configs = get_period_config_for_range(start_year, end_year)

        if not period_configs:
            source = CPISource(period=effective_period)
            raw_data = source.flow()
            if raw_data:
                self._save_cache(raw_data)
            return

        all_data: list[DataPoint] = []

        for cfg in period_configs:
            logger.info(f"拉取 {cfg['label']} 周期数据")
            try:
                source = CPISource(
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
                logger.error(f"拉取 {cfg['label']} 失败: {e}")

        if all_data:
            self._save_cache(all_data)
        else:
            logger.warning("API 未返回任何数据")

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

        自动处理跨周期同义指标：查询任一周期名称/UUID，
        会自动包含其他周期的同名指标。
        """
        if isinstance(indicators, str):
            indicators = [indicators]

        from crawler.sources.cpi_source import CPI_CROSS_PERIOD_ALIASES, CPI_UUID_INDICATORS

        # ── 名称 → UUID 查找 ──
        # 用列表而不是字典，避免归一化后 key 碰撞覆盖
        def _norm(name: str) -> str:
            return name.replace(" ", "").replace("(", "").replace(")", "").lower()

        uuid_entries: list[tuple[str, str]] = [
            (name, uuid) for uuid, name in CPI_UUID_INDICATORS.items()
        ]

        # ── 收集所有目标 UUID（含别名展开） ──
        target_uuids: set[str] = set()

        for ind in indicators:
            ind = ind.strip()
            if not ind:
                continue

            # 判断是不是 UUID
            cleaned = ind.replace("-", "")
            is_uuid = len(cleaned) == 32 and all(c in "0123456789abcdefABCDEF" for c in cleaned)

            if is_uuid:
                target_uuids.add(ind.lower())
            else:
                norm_input = _norm(ind)
                # 逐个匹配，精确匹配优先
                for raw_name, uuid in uuid_entries:
                    if _norm(raw_name) == norm_input:
                        target_uuids.add(uuid.lower())
                # 短关键词子串匹配
                if len(ind) <= 10:
                    for raw_name, uuid in uuid_entries:
                        if norm_input in _norm(raw_name):
                            target_uuids.add(uuid.lower())

        # ── 跨周期别名展开 ──
        def _expand(uuids: set[str]) -> set[str]:
            result_set = set(uuids)
            for u in list(uuids):
                # 正向：新 UUID → 旧 UUID
                for alias in CPI_CROSS_PERIOD_ALIASES.get(u, []):
                    result_set.add(alias.lower())
                # 反向：旧 UUID → 新 UUID
                for new_uuid, old_uuids in CPI_CROSS_PERIOD_ALIASES.items():
                    if any(u == o.lower() for o in old_uuids):
                        result_set.add(new_uuid.lower())
                        for alias in CPI_CROSS_PERIOD_ALIASES.get(new_uuid, []):
                            result_set.add(alias.lower())
            return result_set

        all_target_uuids = _expand(target_uuids)

        # ── 执行筛选：匹配 UUID 或名称 ──
        result = []
        for d in data:
            d_uuid = d.extra.get("indicator_uuid", "").lower()
            d_id = d.extra.get("_id", "").lower()

            # UUID 匹配（含别名展开后的）
            if d_uuid in all_target_uuids or d_id in all_target_uuids:
                result.append(d)
                continue

            # 名称匹配
            if not target_uuids:
                # 如果用户传的是名称，也用名称匹配
                d_name = d.indicator.lower()
                for ind in indicators:
                    ind = ind.strip()
                    if not ind:
                        continue
                    # 精确匹配
                    if d_name == ind.lower():
                        result.append(d)
                        break
                    # 短关键词模糊匹配
                    if len(ind) <= 10 and ind.lower() in d_name:
                        result.append(d)
                        break
                    # 标准化后匹配（去空格、去括号）
                    if _norm(d_name) == _norm(ind):
                        result.append(d)
                        break
                    # 标准化后子串匹配
                    norm_input = _norm(ind)
                    norm_dname = _norm(d_name)
                    if len(norm_input) <= 10 and norm_input in norm_dname:
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

    # ── 数据完整性检查 ──────────────────────────────

    def check_completeness(self) -> dict:
        """
        检查 CPI 数据完整性（2000-01 ~ 最新月份）。

        验证每个月份是否都有对应周期的所有预期指标，
        检查数据连续性，统计各周期的完成度。

        Returns:
            {
                "total_expected_months": int,
                "total_records": int,
                "months_with_data": int,
                "months_ok": int,
                "months_missing_count": int,
                "months_incomplete_count": int,
                "months_missing": [str],
                "months_incomplete": [str],
                "gaps": [str],
                "by_period": { "2000-2015": {"total": 192, "ok": 180, "pct": 93.8}, ... },
                "period_indicator_names": { "2000-2015": ["居民消费价格指数", ...], ... },
                "all_ok": bool,
            }
        """
        from collections import defaultdict

        self._load_cache()
        if not self._all_data:
            return {"total_records": 0, "all_ok": False, "error": "缓存中没有数据"}

        data_dicts = [d.to_dict() for d in self._all_data]

        # 获取数据的时间范围
        all_dates = sorted({d.date for d in self._all_data if d.date})
        if not all_dates:
            return {"total_records": len(data_dicts), "all_ok": False, "error": "无日期信息"}

        start_year = int(all_dates[0][:4])
        start_month = int(all_dates[0][5:7])
        end_year = int(all_dates[-1][:4])
        end_month = int(all_dates[-1][5:7])

        # 按月份分组
        by_month: dict[str, list[dict]] = defaultdict(list)
        for item in data_dicts:
            by_month[item["date"]].append(item)

        # 生成所有预期月份
        all_expected_months = []
        year = start_year
        month = start_month
        while year < end_year or (year == end_year and month <= end_month):
            all_expected_months.append(f"{year:04d}-{month:02d}")
            month += 1
            if month > 12:
                month = 1
                year += 1

        # 周期指标注册表
        period_indicator_names = {}
        for period in CID_PERIODS:
            names = []
            for uuid in period["indicator_ids"]:
                name = CPI_UUID_INDICATORS.get(uuid, uuid)
                names.append(name)
            period_indicator_names[period["label"]] = names

        def get_expected_indicators(y: int) -> list[str]:
            for p in CID_PERIODS:
                if p["years"][0] <= y <= p["years"][1]:
                    return list(p["indicator_ids"])
            return []

        # 按周期分组月份
        by_period: dict[str, list[str]] = defaultdict(list)
        for ym in all_expected_months:
            y = int(ym[:4])
            for p in CID_PERIODS:
                if p["years"][0] <= y <= p["years"][1]:
                    by_period[p["label"]].append(ym)
                    break

        # 检查每个月份
        months_missing = []
        months_incomplete = []
        months_ok = []

        for ym in all_expected_months:
            y = int(ym[:4])
            expected_indicators = get_expected_indicators(y)
            expected_count = len(expected_indicators)

            records = by_month.get(ym, [])
            actual_count = len(records)

            if actual_count == 0:
                months_missing.append(ym)
            elif actual_count < expected_count:
                months_incomplete.append(ym)
            else:
                months_ok.append(ym)

        # 数据连续性检查
        gaps = []
        prev_month_num = None
        for ym in all_expected_months:
            y = int(ym[:4])
            m = int(ym[5:7])
            month_num = y * 12 + m
            if ym in by_month and len(by_month[ym]) > 0:
                if prev_month_num is not None and month_num - prev_month_num > 1:
                    gaps.append(ym)
                prev_month_num = month_num

        # 周期完成度
        period_stats = {}
        for label, pmonths in by_period.items():
            total = len(pmonths)
            ok_count = sum(1 for ym in pmonths if ym in months_ok)
            pct = round(ok_count / total * 100, 1) if total > 0 else 0
            period_stats[label] = {
                "total": total,
                "ok": ok_count,
                "pct": pct,
            }

        return {
            "total_expected_months": len(all_expected_months),
            "total_records": len(data_dicts),
            "months_with_data": len(months_ok) + len(months_incomplete),
            "months_ok": len(months_ok),
            "months_missing_count": len(months_missing),
            "months_incomplete_count": len(months_incomplete),
            "months_missing": months_missing,
            "months_incomplete": months_incomplete,
            "gaps": gaps,
            "by_period": period_stats,
            "period_indicator_names": period_indicator_names,
            "all_ok": len(months_missing) == 0 and len(months_incomplete) == 0 and len(gaps) == 0,
        }

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
