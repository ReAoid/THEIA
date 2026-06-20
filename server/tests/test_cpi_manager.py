"""
CPI Manager 测试

测试策略：
  1. 纯逻辑测试（不联网）— 测试筛选、缓存读写、关键词匹配
  2. 集成测试（需联网）  — 加上 --real 参数才跑

运行：
  pytest tests/test_cpi_manager.py -v
  pytest tests/test_cpi_manager.py -v --real
"""

import json
import pytest
from pathlib import Path
from datetime import datetime

from crawler.base import DataPoint
from crawler.sources.cpi_source import CPI_UUID_INDICATORS, CPI_GROUPS
from manager.cpi_manager import CPIManager


# ═══════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def sample_data() -> list[DataPoint]:
    """构造一组模拟 CPI 数据（4 指标 × 3 个月 = 12 条）。"""
    return [
        # 2026-05
        DataPoint(date="2026-05", value=101.2,
                  indicator="居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "53180dfb9c14411ba4b762307c85920c"}),
        DataPoint(date="2026-05", value=99.1,
                  indicator="食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "42c2d9b5d1b749c4b68c2cbd2e3d4a42"}),
        DataPoint(date="2026-05", value=99.8,
                  indicator="居住类居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "4fb7ea343fc7403bb412cf48fb2f3f0e"}),
        DataPoint(date="2026-05", value=101.3,
                  indicator="教育文化娱乐类居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "e2636c6c7549458ca90057f9b7eff442"}),
        # 2026-04
        DataPoint(date="2026-04", value=101.2,
                  indicator="居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "53180dfb9c14411ba4b762307c85920c"}),
        DataPoint(date="2026-04", value=99.2,
                  indicator="食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "42c2d9b5d1b749c4b68c2cbd2e3d4a42"}),
        DataPoint(date="2026-04", value=99.8,
                  indicator="居住类居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "4fb7ea343fc7403bb412cf48fb2f3f0e"}),
        DataPoint(date="2026-04", value=101.3,
                  indicator="教育文化娱乐类居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "e2636c6c7549458ca90057f9b7eff442"}),
        # 2026-03
        DataPoint(date="2026-03", value=101.0,
                  indicator="居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "53180dfb9c14411ba4b762307c85920c"}),
        DataPoint(date="2026-03", value=100.4,
                  indicator="食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "42c2d9b5d1b749c4b68c2cbd2e3d4a42"}),
        DataPoint(date="2026-03", value=99.8,
                  indicator="居住类居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "4fb7ea343fc7403bb412cf48fb2f3f0e"}),
        DataPoint(date="2026-03", value=101.1,
                  indicator="教育文化娱乐类居民消费价格指数 (上年同月=100)",
                  region="全国", unit="%", source="cpi",
                  extra={"indicator_uuid": "e2636c6c7549458ca90057f9b7eff442"}),
    ]


@pytest.fixture
def mgr_with_cache(tmp_path, sample_data) -> CPIManager:
    """创建一个使用临时目录的管理者，并预先写入缓存。"""
    mgr = CPIManager(cache_dir=tmp_path)
    # 直接向缓存注入数据
    mgr._all_data = sample_data
    mgr._cache_loaded = True
    mgr._save_cache(sample_data)
    return mgr


# ═══════════════════════════════════════════════════════════
#  测试缓存读写
# ═══════════════════════════════════════════════════════════

class TestCache:
    """缓存读写测试"""

    def test_no_cache_on_first_init(self, tmp_path):
        mgr = CPIManager(cache_dir=tmp_path)
        info = mgr.get_cache_info()
        assert info["cached"] is False
        assert info["count"] == 0

    def test_save_and_load_cache(self, tmp_path, sample_data):
        mgr = CPIManager(cache_dir=tmp_path)
        mgr._save_cache(sample_data)

        # 新实例读缓存
        mgr2 = CPIManager(cache_dir=tmp_path)
        mgr2._load_cache()
        assert len(mgr2._all_data) == len(sample_data)

    def test_cache_persistence(self, tmp_path, sample_data):
        """缓存文件内容验证"""
        mgr = CPIManager(cache_dir=tmp_path)
        mgr._save_cache(sample_data)

        cache_file = tmp_path / "cpi.json"
        assert cache_file.exists()

        with open(cache_file, "r", encoding="utf-8") as f:
            raw = json.load(f)

        assert raw["count"] == len(sample_data)
        assert "cached_at" in raw
        assert len(raw["data"]) == len(sample_data)

    def test_clear_cache(self, tmp_path, sample_data):
        mgr = CPIManager(cache_dir=tmp_path)
        mgr._save_cache(sample_data)
        mgr.clear_cache()
        assert mgr._all_data == []
        assert not mgr._cache_file.exists()


# ═══════════════════════════════════════════════════════════
#  测试指标筛选
# ═══════════════════════════════════════════════════════════

class TestFilterIndicators:
    """指标筛选测试"""

    def test_filter_by_exact_name(self, mgr_with_cache):
        data = mgr_with_cache.get_cpi(indicators="居民消费价格指数 (上年同月=100)")
        assert len(data) == 3  # 3 个月
        assert all(d.indicator == "居民消费价格指数 (上年同月=100)" for d in data)

    def test_filter_by_fuzzy_name(self, mgr_with_cache):
        """模糊匹配：含"居住"的指标"""
        data = mgr_with_cache.get_cpi(indicators="居住")
        assert len(data) == 3  # 3 个月
        assert all("居住" in d.indicator for d in data)

    def test_filter_by_uuid(self, mgr_with_cache):
        """UUID 精确匹配"""
        uuid = "53180dfb9c14411ba4b762307c85920c"
        data = mgr_with_cache.get_cpi(indicators=uuid)
        assert len(data) == 3
        assert all(d.extra["indicator_uuid"] == uuid for d in data)

    def test_filter_multiple_keywords(self, mgr_with_cache):
        """多关键词取并集：居住 + 教育"""
        data = mgr_with_cache.get_cpi(indicators=["居住", "教育"])
        assert len(data) == 6  # (居住 3 + 教育 3)
        assert all("居住" in d.indicator or "教育" in d.indicator for d in data)

    def test_filter_no_match(self, mgr_with_cache):
        data = mgr_with_cache.get_cpi(indicators="不存在的指标")
        assert len(data) == 0

    def test_filter_none_returns_all(self, mgr_with_cache):
        data = mgr_with_cache.get_cpi(indicators=None)
        assert len(data) == 12  # 4 指标 × 3 月

    def test_filter_by_group_all(self, mgr_with_cache):
        data = mgr_with_cache.get_cpi(group="全部CPI(13项)")
        # 缓存中只有 4 个 uuid 匹配该分组，应该返回全部 12 条
        assert len(data) == 12

    def test_filter_by_group_core_cpi(self, mgr_with_cache):
        data = mgr_with_cache.get_cpi(group="核心CPI(8项)")
        # 4 个指标都在核心CPI分组中
        assert len(data) == 12

    def test_filter_unknown_group(self, mgr_with_cache):
        data = mgr_with_cache.get_cpi(group="不存在的分组")
        assert len(data) == 0


# ═══════════════════════════════════════════════════════════
#  测试时间段筛选
# ═══════════════════════════════════════════════════════════

class TestFilterPeriod:
    """时间段筛选测试"""

    def test_filter_single_month(self, mgr_with_cache):
        """只查 2026-05"""
        data = mgr_with_cache.get_cpi(period="202605")
        assert len(data) == 4  # 4 个指标
        assert all(d.date == "2026-05" for d in data)

    def test_filter_month_range(self, mgr_with_cache):
        """范围 202604-202605"""
        data = mgr_with_cache.get_cpi(period="202604-202605")
        assert len(data) == 8  # 4 指标 × 2 月
        dates = {d.date for d in data}
        assert dates == {"2026-04", "2026-05"}

    def test_filter_full_year(self, mgr_with_cache):
        """查 2026 全年"""
        data = mgr_with_cache.get_cpi(period="2026")
        assert len(data) == 12  # 4 指标 × 3 月（缓存只有 3-5 月）

    def test_filter_outside_range(self, mgr_with_cache):
        """查缓存之外的时间段 → 返回空"""
        data = mgr_with_cache.get_cpi(period="2022")
        # 缓存没有 2022 年数据，且没有 force_update，不会触发 API
        # 再按时间段筛选后应为空
        assert len(data) == 0

    def test_filter_combined_indicator_and_period(self, mgr_with_cache):
        """同时按指标和时间筛选"""
        data = mgr_with_cache.get_cpi(indicators="居住", period="202605")
        assert len(data) == 1
        assert data[0].date == "2026-05"
        assert "居住" in data[0].indicator


# ═══════════════════════════════════════════════════════════
#  测试便捷方法
# ═══════════════════════════════════════════════════════════

class TestConvenienceMethods:
    """便捷方法测试"""

    def test_get_overall_cpi(self, mgr_with_cache):
        """get_overall_cpi 应返回总体 CPI"""
        data = mgr_with_cache.get_overall_cpi()
        assert len(data) == 3  # 3 个月
        assert all("居民消费价格指数" in d.indicator for d in data)

    def test_get_core_cpi(self, mgr_with_cache):
        """get_core_cpi 应返回核心 8 项"""
        data = mgr_with_cache.get_core_cpi()
        # 样本中的 4 个指标都在核心CPI里
        assert len(data) == 12


# ═══════════════════════════════════════════════════════════
#  测试缓存覆盖判断
# ═══════════════════════════════════════════════════════════

class TestCacheCoverage:
    """缓存覆盖判断测试"""

    def test_cache_covers_exact_period(self, mgr_with_cache):
        assert mgr_with_cache._cache_covers_period("202603") is True
        assert mgr_with_cache._cache_covers_period("202605") is True

    def test_cache_does_not_cover(self, mgr_with_cache):
        assert mgr_with_cache._cache_covers_period("2022") is False

    def test_cache_covers_range(self, mgr_with_cache):
        assert mgr_with_cache._cache_covers_period("202603-202605") is True

    def test_cache_covers_partial_range(self, mgr_with_cache):
        # 缓存有 3-5 月，但请求 2-5 月 → 2月不在缓存
        assert mgr_with_cache._cache_covers_period("202602-202605") is False


# ═══════════════════════════════════════════════════════════
#  测试缓存增量合并
# ═══════════════════════════════════════════════════════════

class TestCacheMerge:
    """缓存增量合并测试"""

    def test_merge_new_data_overwrites_old(self, tmp_path):
        """同 key 数据，新覆盖旧"""
        mgr = CPIManager(cache_dir=tmp_path)

        old = [
            DataPoint(date="2026-05", value=100.0,
                      indicator="居民消费价格指数 (上年同月=100)",
                      region="全国", unit="%", source="cpi")
        ]
        mgr._save_cache(old)

        new = [
            DataPoint(date="2026-05", value=101.2,
                      indicator="居民消费价格指数 (上年同月=100)",
                      region="全国", unit="%", source="cpi")
        ]
        mgr._save_cache(new)

        assert len(mgr._all_data) == 1
        assert mgr._all_data[0].value == 101.2  # 新值覆盖旧值

    def test_merge_appends_new_keys(self, tmp_path):
        """新数据增加新的 key"""
        mgr = CPIManager(cache_dir=tmp_path)

        old = [
            DataPoint(date="2026-05", value=101.2,
                      indicator="居民消费价格指数 (上年同月=100)",
                      region="全国", unit="%", source="cpi")
        ]
        mgr._save_cache(old)

        new = [
            DataPoint(date="2026-04", value=101.0,
                      indicator="居民消费价格指数 (上年同月=100)",
                      region="全国", unit="%", source="cpi")
        ]
        mgr._save_cache(new)

        assert len(mgr._all_data) == 2  # 新旧共存


# ═══════════════════════════════════════════════════════════
#  测试注册表校验委托
# ═══════════════════════════════════════════════════════════

class TestManagerValidateRegistry:
    """CPIManager.validate_registry 应委托给 CPISource.validate_registry"""

    def test_validate_delegates_to_source(self, tmp_path, monkeypatch):
        from crawler.sources.cpi_source import CPISource

        called = False

        def mock_validate(period="202605"):
            nonlocal called
            called = True
            return {"checked": 2, "ok": 2, "mismatches": [], "unknown": [], "cid_match": True}

        monkeypatch.setattr(CPISource, "validate_registry", staticmethod(mock_validate))

        mgr = CPIManager(cache_dir=tmp_path)
        result = mgr.validate_registry(period="202605")
        assert called
        assert result["checked"] == 2
        assert result["ok"] == 2


# ═══════════════════════════════════════════════════════════
#  集成测试（需联网）
# ═══════════════════════════════════════════════════════════

@pytest.mark.real
class TestCPIManagerIntegration:
    """真实 API 集成测试——用 pytest --real 运行"""

    def test_real_fetch_and_cache(self, tmp_path):
        """真实拉取并缓存"""
        mgr = CPIManager(cache_dir=tmp_path)
        data = mgr.get_cpi(period="202605", force_update=True)
        assert len(data) > 0
        print(f"\n[集成测试] 拉取 {len(data)} 条数据")

        # 第二次应走缓存
        data2 = mgr.get_cpi(period="202605")
        assert len(data2) == len(data)

    def test_real_get_overall_cpi(self, tmp_path):
        """真实获取总体 CPI"""
        mgr = CPIManager(cache_dir=tmp_path)
        data = mgr.get_overall_cpi(period="202605", force_update=True)
        assert len(data) > 0
        for d in data:
            print(f"  总体CPI {d.date}: {d.value}")
            assert d.value is not None

    def test_real_get_by_group(self, tmp_path):
        """真实按分组获取"""
        mgr = CPIManager(cache_dir=tmp_path)
        data = mgr.get_by_group("核心CPI(8项)", period="202605",
                                force_update=True)
        assert len(data) > 0
        print(f"\n[集成测试] 核心CPI(8项): {len(data)} 条")

    def test_real_force_update(self, tmp_path):
        """强制更新应覆盖缓存"""
        mgr = CPIManager(cache_dir=tmp_path)
        # 第一次拉取
        data1 = mgr.get_cpi(period="202605", force_update=True)
        # 强制更新
        data2 = mgr.get_cpi(period="202605", force_update=True)
        assert len(data2) == len(data1)
