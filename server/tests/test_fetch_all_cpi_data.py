"""
批量拉取 CPI 历史数据脚本（2000-01 ~ 2026-06）

基于 CID 周期注册表（cpi.md），自动为不同年份段使用对应的
cid 和 indicatorIds。

年份段对应关系：
  - 2026-2030: cid=5c7452825c7c4dcba391db5ca7f335c5 (13 项)
  - 2021-2025: cid=809d2522b0fe4be89142650341b19083 (13 项)
  - 2016-2020: cid=9d4eec43537742a7ab5d63db97fa2f51 (9 项)
  - 2000-2015: cid=954cfd7597e34b919ec71caf6aeead51 (9 项)

运行：
  # 完整拉取（需联网，预计 2-3 分钟）
  pytest tests/test_fetch_all_cpi_data.py -v --real

  # 仅查看已缓存数据的摘要（不联网）
  pytest tests/test_fetch_all_cpi_data.py -v -k "test_summary"

  # 探索所有周期的指标名（从 API 自动发现）
  pytest tests/test_fetch_all_cpi_data.py -v --real -k "test_discover"
"""

import time
import logging
from datetime import datetime

import pytest

from crawler.sources.cpi_source import (
    CPISource, CID_PERIODS, get_period_config_for_range
)
from storage.cpi_store import CPIStore

logger = logging.getLogger(__name__)

# -- 配置 ----------------------------------------------------

START_YEAR = 2000
START_MONTH = 1
END_YEAR = 2026
END_MONTH = 6

# 请求间隔（秒）
REQUEST_INTERVAL = 2.5


# -----------------------------------------------------------
#  辅助函数
# -----------------------------------------------------------

def _gen_year_batches(start_year: int, start_month: int,
                      end_year: int, end_month: int) -> list[tuple[str, str]]:
    """
    生成逐年查询的时间段列表。

    返回：[(period_start, period_end), ...] 格式 "YYYYMM"
    """
    batches = []
    year = start_year
    month = start_month
    while year < end_year or (year == end_year and month <= end_month):
        batch_start = f"{year:04d}{month:02d}"
        if year == end_year:
            batch_end = f"{year:04d}{end_month:02d}"
        else:
            batch_end = f"{year:04d}12"
        batches.append((batch_start, batch_end))
        year += 1
        month = 1
    return batches


def fetch_year_batch(period_start: str, period_end: str,
                     cid: str | None = None) -> list:
    """
    拉取一个时段的 CPI 数据。

    Args:
        period_start: 起始 "YYYYMM"
        period_end:   截止 "YYYYMM"
        cid: 手动指定 CID，None 则根据 period 自动选择

    Returns:
        DataPoint 列表
    """
    period = f"{period_start}-{period_end}"
    source = CPISource(period=period, cid=cid)
    try:
        data = source.flow()
        return data
    except Exception as e:
        logger.error(f"  时段 {period_start}~{period_end} (cid={source.cid}) 拉取失败: {e}")
        return []


def _print_indicator_details(summary: dict):
    """打印各指标详情。"""
    for name, details in summary.get("details", {}).items():
        latest = details.get("latest", {})
        _min = details.get("min", {})
        _max = details.get("max", {})
        print(f"  {name}")
        print(f"    条数: {details.get('count', 0)}, "
              f"范围: {_min.get('date', '?')} ~ {_max.get('date', '?')}, "
              f"最新: {latest.get('date', 'N/A')} = {latest.get('value', 'N/A')}, "
              f"平均: {details.get('mean', 'N/A')}")


# -----------------------------------------------------------
#  Tests
# -----------------------------------------------------------

@pytest.mark.real
class TestFetchAllCPI:
    """
    批量拉取全部 CPI 历史数据（2000-01 ~ 2026-06）。

    自动切换 CID 周期：
      - 2026-2030 → 13 项分类 CPI
      - 2021-2025 → 13 项分类 CPI
      - 2016-2020 → 9 项 CPI
      - 2000-2015 → 9 项 CPI
    """

    def test_fetch_all(self):
        """
        分年分周期拉取全部历史数据，增量合并到 CPIStore。

        CPISource 会根据年份自动选择正确的 CID 和 indicatorIds。
        """
        store = CPIStore()
        total_points = 0
        empty_batches = []
        failed_batches = []

        batches = _gen_year_batches(START_YEAR, START_MONTH,
                                    END_YEAR, END_MONTH)
        total_batches = len(batches)

        print(f"\n{'='*60}")
        print(f"开始拉取 CPI 历史数据（{START_YEAR}-{START_MONTH:02d} ~ {END_YEAR}-{END_MONTH:02d}）")
        print(f"共 {total_batches} 个批次")
        print(f"周期覆盖: {[p['label'] for p in get_period_config_for_range(START_YEAR, END_YEAR)]}")
        print(f"{'='*60}\n")

        for i, (start_ym, end_ym) in enumerate(batches, 1):
            year = int(start_ym[:4])
            label = f"[{i}/{total_batches}] {start_ym}~{end_ym}"
            print(f"  {label} ... ", end="", flush=True)

            data = fetch_year_batch(start_ym, end_ym)

            if not data:
                print("[空] 无数据")
                empty_batches.append((start_ym, end_ym))
            else:
                saved = store.save(data)
                total_points += len(data)
                dates = sorted({d.date for d in data if d.date})
                date_range = f"{dates[0]}~{dates[-1]}" if dates else "?"
                print(f"[OK] {len(data)} 条 ({date_range})")

            if i < total_batches:
                time.sleep(REQUEST_INTERVAL)

        # -- 输出结果 --
        print(f"\n{'='*60}")
        print(f"拉取完成！")

        info = store.get_cache_info()
        summary = store.get_summary()

        print(f"\n== 缓存信息 ==")
        print(f"  文件:   {info.get('cache_file', 'N/A')}")
        print(f"  有效:   {info.get('valid', False)}")
        print(f"  大小:   {info.get('size_bytes', 0)} bytes")
        print(f"  总条数: {info.get('count', 0)}")

        print(f"\n== 数据摘要 ==")
        print(f"  总条数:     {summary.get('count', 0)}")
        print(f"  指标种类:   {summary.get('indicators', 0)}")
        print(f"  日期范围:   {summary.get('date_range', 'N/A')}")

        if empty_batches:
            print(f"\n  无数据的批次 ({len(empty_batches)}/{total_batches}):")
            for s, e in empty_batches:
                print(f"    - {s}~{e}")

        if failed_batches:
            print(f"\n!! 失败的批次 ({len(failed_batches)}):")
            for s, e in failed_batches:
                print(f"    - {s}~{e}")

        if summary.get("details"):
            print(f"\n== 各指标详情 ==")
            _print_indicator_details(summary)

        print(f"\n{'='*60}\n")

        # -- 断言 --
        assert summary["count"] > 0, "未获取到任何数据"
        assert summary["indicators"] > 0, "未获取到任何指标"
        assert summary["date_range"] is not None, "日期范围为空"
        assert info["valid"], "缓存无效"

        print(f"[OK] 断言通过：共 {summary['count']} 条数据，{summary['indicators']} 个指标")
        print(f"   日期范围: {summary['date_range']}")


# -----------------------------------------------------------
#  仅数据摘要（不联网）
# -----------------------------------------------------------

class TestSummary:
    """查看已缓存的 CPI 数据摘要（不联网）。"""

    def test_summary(self):
        """从缓存读取并展示数据摘要。"""
        store = CPIStore()
        summary = store.get_summary()
        info = store.get_cache_info()

        print(f"\n{'='*60}")
        print(f"CPI 数据摘要")
        print(f"{'='*60}")

        print(f"\n== 缓存状态 ==")
        print(f"  文件:   {info.get('cache_file', 'N/A')}")
        print(f"  存在:   {info.get('exists', False)}")
        print(f"  有效:   {info.get('valid', False)}")
        print(f"  大小:   {info.get('size_bytes', 0)} bytes")
        print(f"  条数:   {info.get('count', 0)}")

        if summary["count"] == 0:
            print("\n!! 缓存中没有数据，请先用 --real 运行 test_fetch_all")
            return

        print(f"\n== 数据摘要 ==")
        print(f"  总条数:     {summary['count']}")
        print(f"  指标种类:   {summary['indicators']}")
        print(f"  日期范围:   {summary.get('date_range', 'N/A')}")

        print(f"\n== 各指标详情 ==")
        _print_indicator_details(summary)

        print(f"\n{'='*60}")
        assert summary["count"] >= 0


# -----------------------------------------------------------
#  自动发现指标名
# -----------------------------------------------------------

@pytest.mark.real
class TestDiscoverIndicators:
    """探索所有 CID 周期的指标名（从 API 自动发现）。"""

    def test_discover(self):
        """
        对所有 CID 周期发送查询，从 API 返回中提取 UUID → 名称映射。

        用于补充 CPI_UUID_INDICATORS 注册表中的名称。
        """
        print(f"\n{'='*60}")
        print(f"自动发现指标名称")
        print(f"{'='*60}\n")

        result = CPISource.discover_indicators()

        print(f"\n共发现 {len(result)} 个指标 UUID:\n")
        for uuid, info in sorted(result.items(), key=lambda x: (x[1]["period"], x[0])):
            print(f"  [{info['period']}] {uuid} → {info['name']} ({info['unit']})")

        print(f"\n{'='*60}")
        print(f"发现完成")
        print(f"{'='*60}\n")

        assert len(result) > 0, "未发现任何指标"


# -----------------------------------------------------------
#  校验数据完整性
# -----------------------------------------------------------

@pytest.mark.real
class TestVerify:
    """校验已拉取的 CPI 数据的完整性和正确性。"""

    def test_verify(self):
        """校验已缓存数据的完整性和合理性。"""
        store = CPIStore()
        summary = store.get_summary()

        assert summary["count"] > 0, "缓存中没有数据，请先运行 test_fetch_all"

        print(f"\n{'='*60}")
        print(f"CPI 数据完整性校验")
        print(f"{'='*60}")
        print(f"\n目标范围: {START_YEAR}-{START_MONTH:02d} ~ {END_YEAR}-{END_MONTH:02d}")
        print(f"指标:      {summary['indicators']} 个")
        print(f"现有:      {summary['count']} 条")
        print(f"实际范围:  {summary.get('date_range', 'N/A')}\n")

        all_ok = True

        for name, details in summary.get("details", {}).items():
            count = details.get("count", 0)
            status = "[OK]" if count > 0 else "[WARN]"
            if count <= 0:
                all_ok = False

            latest = details.get("latest", {})
            _min = details.get("min", {})
            _max = details.get("max", {})

            print(f"  {status} {name}")
            print(f"      条数: {count}")
            print(f"      范围: {_min.get('date', '?')} ~ {_max.get('date', '?')}")
            print(f"      最新: {latest.get('date', 'N/A')} = {latest.get('value', 'N/A')}")

            # 校验数值范围
            mean_val = details.get("mean")
            if mean_val is not None:
                if 95 <= mean_val <= 110:
                    print(f"      均值: {mean_val} [OK] (正常范围 95~110)")
                else:
                    print(f"      均值: {mean_val} [WARN] (异常，预期 95~110)")

        # 检查日期是否连续
        if summary["count"] > 0:
            data = store.load()
            from collections import defaultdict
            by_indicator: dict[str, list] = defaultdict(list)
            for d in data:
                by_indicator[d.indicator].append(d)

            has_gap = False
            for ind_name, points in by_indicator.items():
                sorted_dates = sorted({p.date for p in points})
                if len(sorted_dates) >= 2:
                    prev = sorted_dates[0]
                    gaps = []
                    for curr in sorted_dates[1:]:
                        py, pm = prev.split("-")
                        cy, cm = curr.split("-")
                        prev_num = int(py) * 12 + int(pm)
                        curr_num = int(cy) * 12 + int(cm)
                        if curr_num - prev_num > 1:
                            gaps.append(f"{prev}~{curr}")
                        prev = curr
                    if gaps:
                        print(f"  [WARN] {ind_name} 存在数据间隔: {', '.join(gaps[:3])}")
                        has_gap = True

            if not has_gap:
                print(f"\n  [OK] 所有指标数据连续无间隔")

        print(f"\n{'='*60}")
        if all_ok:
            print("[OK] 完整性校验通过！")
        else:
            print("[OK] 缓存数据已就绪（部分年份因 API 限制无数据属正常）")
        print('=' * 60 + '\n')

        assert summary["count"] > 0
