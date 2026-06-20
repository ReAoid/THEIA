"""
CPI 爬虫测试

测试策略：
  1. 纯逻辑测试（不联网）— 测试 parse()、分析函数、指标列表
  2. 集成测试（需联网）  — 加上 --real 参数才跑，测真实 API 调用

运行：
  # 只跑纯逻辑测试（默认，不联网）
  pytest tests/test_cpi.py -v

  # 跑全部（含真实 API 调用）
  pytest tests/test_cpi.py -v --real

  # 看覆盖率
  pytest tests/test_cpi.py --cov=crawler.sources.cpi_source
"""

import json
import pytest

from crawler.base import DataPoint
from crawler.sources.cpi_source import (
    CPISource,
    CPI_UUID_INDICATORS,
    CPI_GROUPS,
    CID,
    ROOT_ID,
    DEFAULT_DA,
    _period_to_dts,
    _normalize_date,
)


# ═══════════════════════════════════════════════════════════
#  Mock 数据 —— 模拟新版 esData API 返回
# ═══════════════════════════════════════════════════════════

MOCK_API_RESPONSE = {
    "success": True,
    "state": 20000,
    "message": "成功",
    "data": [
        {
            "code": "202203MM",
            "name": "2022年3月",
            "values": [
                {
                    "i_showname": "居民消费价格指数 (上年同月=100)",
                    "_id": "53180dfb9c14411ba4b762307c85920c",
                    "value": "102.0",
                    "du_name": "%",
                    "da_name": "全国",
                    "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                    "order": 1,
                    "ds_order": 1,
                    "du": "414774dee2bc47f392cf13abfa9de882",
                    "num_accuracy_value": "1",
                    "da": "000000000000",
                }
            ],
        },
        {
            "code": "202202MM",
            "name": "2022年2月",
            "values": [
                {
                    "i_showname": "居民消费价格指数 (上年同月=100)",
                    "_id": "53180dfb9c14411ba4b762307c85920c",
                    "value": "101.2",
                    "du_name": "%",
                    "da_name": "全国",
                    "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                    "order": 1,
                    "ds_order": 1,
                    "da": "000000000000",
                }
            ],
        },
        {
            "code": "202201MM",
            "name": "2022年1月",
            "values": [
                {
                    "i_showname": "居民消费价格指数 (上年同月=100)",
                    "_id": "53180dfb9c14411ba4b762307c85920c",
                    "value": "100.5",
                    "du_name": "%",
                    "da_name": "全国",
                    "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                    "order": 1,
                    "ds_order": 1,
                    "da": "000000000000",
                }
            ],
        },
    ],
}

MOCK_MULTI_INDICATOR_RESPONSE = {
    "success": True,
    "state": 20000,
    "message": "成功",
    "data": [
        {
            "code": "202605MM",
            "name": "2026年5月",
            "values": [
                {
                    "_id": "53180dfb9c14411ba4b762307c85920c",
                    "i_showname": "居民消费价格指数 (上年同月=100)",
                    "value": "101.2",
                    "du_name": "%",
                    "da_name": "全国",
                },
                {
                    "_id": "42c2d9b5d1b749c4b68c2cbd2e3d4a42",
                    "i_showname": "食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)",
                    "value": "99.1",
                    "du_name": "%",
                    "da_name": "全国",
                },
                {
                    "_id": "23db96d6f25c4acbb8801616fc2e509d",
                    "i_showname": "衣着类居民消费价格指数 (上年同月=100)",
                    "value": "101.4",
                    "du_name": "%",
                    "da_name": "全国",
                },
                {
                    "_id": "e6e42078f30e483b899b2701a766909a",
                    "i_showname": "交通通信类居民消费价格指数 (上年同月=100)",
                    "value": "105.4",
                    "du_name": "%",
                    "da_name": "全国",
                },
            ],
        },
        {
            "code": "202604MM",
            "name": "2026年4月",
            "values": [
                {
                    "_id": "53180dfb9c14411ba4b762307c85920c",
                    "i_showname": "居民消费价格指数 (上年同月=100)",
                    "value": "101.2",
                    "du_name": "%",
                    "da_name": "全国",
                },
                {
                    "_id": "42c2d9b5d1b749c4b68c2cbd2e3d4a42",
                    "i_showname": "食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)",
                    "value": "99.2",
                    "du_name": "%",
                    "da_name": "全国",
                },
                {
                    "_id": "23db96d6f25c4acbb8801616fc2e509d",
                    "i_showname": "衣着类居民消费价格指数 (上年同月=100)",
                    "value": "101.5",
                    "du_name": "%",
                    "da_name": "全国",
                },
                {
                    "_id": "e6e42078f30e483b899b2701a766909a",
                    "i_showname": "交通通信类居民消费价格指数 (上年同月=100)",
                    "value": "104.6",
                    "du_name": "%",
                    "da_name": "全国",
                },
            ],
        },
    ],
}

MOCK_ERROR_RESPONSE = {"success": False, "state": 50000, "message": "系统繁忙"}

MOCK_EMPTY_RESPONSE = {"success": True, "state": 20000, "message": "成功", "data": []}


# ═══════════════════════════════════════════════════════════
#  测试 _normalize_date / _period_to_dts 工具函数
# ═══════════════════════════════════════════════════════════

class TestUtils:
    """工具函数测试"""

    def test_normalize_date_standard(self):
        assert _normalize_date("202605MM") == "2026-05"

    def test_normalize_date_lowercase(self):
        assert _normalize_date("202601mm") == "2026-01"

    def test_normalize_date_no_mm(self):
        assert _normalize_date("2022") == "2022"

    def test_period_to_dts_single_month(self):
        assert _period_to_dts("202605") == ["202605MM"]

    def test_period_to_dts_single_month_with_mm(self):
        assert _period_to_dts("202605MM") == ["202605MM"]

    def test_period_to_dts_range(self):
        assert _period_to_dts("202406-202605") == ["202406MM-202605MM"]

    def test_period_to_dts_full_year(self):
        assert _period_to_dts("2026") == ["202601MM-202612MM"]

    def test_period_to_dts_open_range(self):
        # "1949-" 映射为最近5年，动态计算
        result = _period_to_dts("1949-")
        assert len(result) == 1
        assert "-" in result[0]
        assert result[0].endswith("MM")

    def test_period_to_dts_range_with_mm(self):
        assert _period_to_dts("202406MM-202605MM") == ["202406MM-202605MM"]


# ═══════════════════════════════════════════════════════════
#  测试 parse() 解析逻辑
# ═══════════════════════════════════════════════════════════

class TestCPISourceParse:
    """测试 CPISource.parse() —— 核心解析逻辑"""

    def setup_method(self):
        self.source = CPISource(
            indicator_ids=["53180dfb9c14411ba4b762307c85920c"],
            period="202201-202203",
        )

    def test_parse_normal(self):
        """正常解析：3 个有数据的月份"""
        data = self.source.parse(MOCK_API_RESPONSE)
        assert len(data) == 3
        # 因为 data 是按照月份先后顺序来的（API 返回的顺序）
        assert data[0].date == "2022-03"  # API 返回顺序：3月, 2月, 1月
        assert data[0].value == 102.0
        assert data[0].indicator == "居民消费价格指数 (上年同月=100)"
        assert data[0].unit == "%"
        assert data[0].region == "全国"
        assert data[0].source == "cpi"
        assert data[0].extra["indicator_uuid"] == "53180dfb9c14411ba4b762307c85920c"

    def test_parse_second_point(self):
        """第二个点（2月）"""
        data = self.source.parse(MOCK_API_RESPONSE)
        assert data[1].date == "2022-02"
        assert data[1].value == 101.2

    def test_parse_third_point(self):
        """第三个点（1月）"""
        data = self.source.parse(MOCK_API_RESPONSE)
        assert data[2].date == "2022-01"
        assert data[2].value == 100.5

    def test_parse_error(self):
        """API 返回 success=false"""
        data = self.source.parse(MOCK_ERROR_RESPONSE)
        assert data == []

    def test_parse_empty(self):
        """API 返回空 data 数组"""
        data = self.source.parse(MOCK_EMPTY_RESPONSE)
        assert data == []

    def test_parse_multi_indicator(self):
        """多指标解析：4 个指标 × 2 个月 = 8 条"""
        source = CPISource(
            indicator_ids=[
                "53180dfb9c14411ba4b762307c85920c",
                "42c2d9b5d1b749c4b68c2cbd2e3d4a42",
                "23db96d6f25c4acbb8801616fc2e509d",
                "e6e42078f30e483b899b2701a766909a",
            ],
            period="202604-202605",
        )
        data = source.parse(MOCK_MULTI_INDICATOR_RESPONSE)
        assert len(data) == 8  # 4 指标 × 2 月份

        # 第一个点：2026-05, CPI 总体
        assert data[0].date == "2026-05"
        assert data[0].value == 101.2
        assert data[0].indicator == "居民消费价格指数 (上年同月=100)"
        assert "indicator_uuid" in data[0].extra

    def test_parse_cid_check(self):
        """parse 时检测到 catalogid 不匹配应发出警告"""
        mock_bad_cid = dict(MOCK_API_RESPONSE)
        mock_bad_cid["data"][0]["values"][0]["catalogid"] = "wrong-cid"
        source = CPISource(
            indicator_ids=["53180dfb9c14411ba4b762307c85920c"],
            period="202201-202203",
        )
        # 不应抛异常，只是日志警告
        data = source.parse(mock_bad_cid)
        assert len(data) == 3  # 正常解析

    def test_parse_unknown_uuid_uses_api_name(self):
        """当 UUID 不在注册表中时，使用 API 返回的名称"""
        mock = {
            "success": True,
            "state": 20000,
            "data": [
                {
                    "code": "202605MM",
                    "name": "2026年5月",
                    "values": [
                        {
                            "_id": "brand-new-uuid-1234567890abcdef",
                            "i_showname": "全新CPI指标 (上年同月=100)",
                            "value": "100.0",
                            "du_name": "%",
                            "da_name": "全国",
                        }
                    ],
                }
            ],
        }
        source = CPISource(period="202605")
        data = source.parse(mock)
        assert len(data) == 1
        assert data[0].indicator == "全新CPI指标 (上年同月=100)"
        assert data[0].extra["indicator_uuid"] == "brand-new-uuid-1234567890abcdef"

    def test_parse_registry_name_fallback(self):
        """当 i_showname 为空时用 CPI_UUID_INDICATORS 补充"""
        mock = {
            "success": True,
            "state": 20000,
            "data": [
                {
                    "code": "202605MM",
                    "name": "2026年5月",
                    "values": [
                        {
                            "_id": "53180dfb9c14411ba4b762307c85920c",
                            "value": "101.2",
                            "du_name": "%",
                            "da_name": "全国",
                        }
                    ],
                }
            ],
        }
        source = CPISource(
            indicator_ids=["53180dfb9c14411ba4b762307c85920c"],
            period="202605",
        )
        data = source.parse(mock)
        assert len(data) == 1
        assert data[0].indicator == "居民消费价格指数 (上年同月=100)"


# ═══════════════════════════════════════════════════════════
#  测试指标注册表
# ═══════════════════════════════════════════════════════════

class TestCPIIndicators:
    """测试指标注册表（UUID 版）"""

    def test_list_all(self):
        indicators = CPISource.list_indicators()
        assert len(indicators) > 0
        # 确保关键指标存在
        uuids = [i["uuid"] for i in indicators]
        assert "53180dfb9c14411ba4b762307c85920c" in uuids
        assert "42c2d9b5d1b749c4b68c2cbd2e3d4a42" in uuids

    def test_list_all_have_names(self):
        indicators = CPISource.list_indicators()
        for ind in indicators:
            assert "uuid" in ind
            assert "name" in ind
            assert "group" in ind

    def test_contains_overall_cpi(self):
        indicators = CPISource.list_indicators()
        names = [i["name"] for i in indicators]
        assert any("居民消费价格指数" in n for n in names)

    def test_list_by_group_all_cpi(self):
        indicators = CPISource.list_indicators(group="全部CPI(13项)")
        assert len(indicators) == 13  # 13 个二级分类

    def test_list_by_group_core_cpi(self):
        indicators = CPISource.list_indicators(group="核心CPI(8项)")
        assert len(indicators) == 8

    def test_list_by_group_unknown(self):
        indicators = CPISource.list_indicators(group="不存在的分组")
        assert len(indicators) == 0


# ═══════════════════════════════════════════════════════════
#  测试 _normalize_name（名称归一化）
# ═══════════════════════════════════════════════════════════

class TestNormalizeName:
    """_normalize_name 工具函数测试"""

    def test_strip_whitespace(self):
        from crawler.sources.cpi_source import _normalize_name
        assert _normalize_name("  居民消费价格指数  ") == "居民消费价格指数"

    def test_fullwidth_to_halfwidth(self):
        from crawler.sources.cpi_source import _normalize_name
        assert _normalize_name("食品（大类）") == "食品(大类)"

    def test_bracket_inner_space(self):
        from crawler.sources.cpi_source import _normalize_name
        assert _normalize_name("居民消费价格指数 (上年同月=100)") == "居民消费价格指数(上年同月=100)"

    def test_multi_spaces(self):
        from crawler.sources.cpi_source import _normalize_name
        assert _normalize_name("a   b  c") == "a b c"

    def test_empty_string(self):
        from crawler.sources.cpi_source import _normalize_name
        assert _normalize_name("") == ""
        assert _normalize_name(None) == ""

    def test_registry_vs_api_name_comparison(self):
        """真实场景：注册表名称 vs API 名称，归一化后应相等"""
        from crawler.sources.cpi_source import _normalize_name
        # 注册表中的写法
        registry = "居民消费价格指数 (上年同月=100) "
        # API 返回的写法
        api = "居民消费价格指数 (上年同月=100)"
        assert _normalize_name(registry) == _normalize_name(api)


# ═══════════════════════════════════════════════════════════
#  测试 validate_registry（Mock 模式）
# ═══════════════════════════════════════════════════════════

class TestValidateRegistry:
    """validate_registry 逻辑测试（不联网，Mock fetch）"""

    def test_validate_all_match(self, monkeypatch):
        """所有 UUID 名称都匹配"""
        def mock_fetch(self):
            return {
                "success": True,
                "state": 20000,
                "data": [
                    {
                        "code": "202605MM",
                        "name": "2026年5月",
                        "values": [
                            {
                                "_id": "53180dfb9c14411ba4b762307c85920c",
                                "i_showname": "居民消费价格指数 (上年同月=100)",
                                "value": "101.2",
                                "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                            },
                            {
                                "_id": "42c2d9b5d1b749c4b68c2cbd2e3d4a42",
                                "i_showname": "食品烟酒及在外餐饮类居民消费价格指数(上年同月=100)",
                                "value": "99.1",
                                "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                            },
                        ],
                    }
                ],
            }
        monkeypatch.setattr(CPISource, "fetch", mock_fetch)
        result = CPISource.validate_registry(period="202605")
        assert result["checked"] == 2
        assert result["ok"] == 2
        assert result["mismatches"] == []
        assert result["unknown"] == []
        assert result["cid_match"] is True

    def test_validate_with_mismatch(self, monkeypatch):
        """某个 UUID 名称不匹配"""
        def mock_fetch(self):
            return {
                "success": True,
                "state": 20000,
                "data": [
                    {
                        "code": "202605MM",
                        "name": "2026年5月",
                        "values": [
                            {
                                "_id": "53180dfb9c14411ba4b762307c85920c",
                                "i_showname": "新名称居民消费价格指数",
                                "value": "101.2",
                                "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                            },
                        ],
                    }
                ],
            }
        monkeypatch.setattr(CPISource, "fetch", mock_fetch)
        result = CPISource.validate_registry(period="202605")
        assert result["checked"] == 1
        assert result["ok"] == 0
        assert len(result["mismatches"]) == 1
        assert result["mismatches"][0]["uuid"] == "53180dfb9c14411ba4b762307c85920c"

    def test_validate_with_unknown_uuid(self, monkeypatch):
        """API 返回了注册表中没有的新 UUID"""
        def mock_fetch(self):
            return {
                "success": True,
                "state": 20000,
                "data": [
                    {
                        "code": "202605MM",
                        "name": "2026年5月",
                        "values": [
                            {
                                "_id": "totally-new-uuid-0000000000000000",
                                "i_showname": "全新指标",
                                "value": "100.0",
                                "catalogid": "5c7452825c7c4dcba391db5ca7f335c5",
                            },
                        ],
                    }
                ],
            }
        monkeypatch.setattr(CPISource, "fetch", mock_fetch)
        result = CPISource.validate_registry(period="202605")
        assert result["checked"] == 1
        assert result["ok"] == 0
        assert len(result["unknown"]) == 1
        assert result["unknown"][0]["uuid"] == "totally-new-uuid-0000000000000000"

    def test_validate_cid_mismatch(self, monkeypatch):
        """CID 不匹配"""
        def mock_fetch(self):
            return {
                "success": True,
                "state": 20000,
                "data": [
                    {
                        "code": "202605MM",
                        "name": "2026年5月",
                        "values": [
                            {
                                "_id": "53180dfb9c14411ba4b762307c85920c",
                                "i_showname": "居民消费价格指数 (上年同月=100)",
                                "value": "101.2",
                                "catalogid": "wrong-cid-12345",
                            },
                        ],
                    }
                ],
            }
        monkeypatch.setattr(CPISource, "fetch", mock_fetch)
        result = CPISource.validate_registry(period="202605")
        assert result["cid_match"] is False


# ═══════════════════════════════════════════════════════════
#  测试分析辅助函数
# ═══════════════════════════════════════════════════════════

class TestCPIAnalysis:
    """测试同比/环比/摘要计算"""

    def setup_method(self):
        self.data = [
            DataPoint(date="2022-01", value=100.0, indicator="CPI"),
            DataPoint(date="2022-02", value=101.0, indicator="CPI"),
            DataPoint(date="2022-03", value=102.0, indicator="CPI"),
        ]

        # 含跨年数据，用于测试同比
        self.data_yoy = [
            DataPoint(date="2021-01", value=99.0, indicator="CPI"),
            DataPoint(date="2021-02", value=100.0, indicator="CPI"),
            DataPoint(date="2022-01", value=103.0, indicator="CPI"),
            DataPoint(date="2022-02", value=104.0, indicator="CPI"),
        ]

        # 多指标数据
        self.data_multi = [
            DataPoint(date="2026-05", value=101.2, indicator="总体CPI"),
            DataPoint(date="2026-05", value=99.1, indicator="食品CPI"),
            DataPoint(date="2026-04", value=101.2, indicator="总体CPI"),
            DataPoint(date="2026-04", value=99.2, indicator="食品CPI"),
        ]

    def test_summary_single_indicator(self):
        s = CPISource.summary(self.data)
        assert s["count"] == 3
        assert s["indicators"] == 1
        assert "CPI" in s["details"]
        details = s["details"]["CPI"]
        assert details["min"]["value"] == 100.0
        assert details["max"]["value"] == 102.0
        assert details["mean"] == 101.0
        assert details["latest"]["value"] == 102.0

    def test_summary_empty(self):
        s = CPISource.summary([])
        assert s["count"] == 0

    def test_summary_multi_indicator(self):
        s = CPISource.summary(self.data_multi)
        assert s["count"] == 4
        assert s["indicators"] == 2
        assert "总体CPI" in s["details"]
        assert "食品CPI" in s["details"]

    def test_calc_mom_single_indicator(self):
        """环比：（2月 vs 1月）= (101/100-1)*100 = 1%"""
        result = CPISource.calc_mom(self.data)
        assert result[0]["mom"] is None  # 第一个无环比
        assert result[1]["mom"] == 1.0
        assert result[2]["mom"] == pytest.approx(0.99, rel=0.01)

    def test_calc_mom_sorted_by_indicator_date(self):
        """多指标确保环比只对比同指标"""
        result = CPISource.calc_mom(self.data_multi)
        # 按 (indicator, date) 排序，前两个是 食品CPI(4月,5月)，后两个是 总体CPI(4月,5月)
        # 食品CPI 4月 → 无环比
        assert result[0]["mom"] is None
        # 食品CPI 5月 → (99.1/99.2-1)*100
        assert result[1]["mom"] is not None
        # 总体CPI 4月 → 无环比（前一个是食品CPI，不同指标）
        assert result[2]["mom"] is None
        # 总体CPI 5月 → (101.2/101.2-1)*100 = 0
        assert result[3]["mom"] == 0.0

    def test_calc_yoy_single_indicator(self):
        """同比：2022-01 vs 2021-01 = (103/99 - 1)*100 ≈ 4.04%"""
        result = CPISource.calc_yoy(self.data_yoy)
        assert result[0]["yoy"] is None  # 2021-01 无上年同期
        assert result[1]["yoy"] is None
        assert result[2]["yoy"] == pytest.approx(4.04, rel=0.01)
        assert result[3]["yoy"] == 4.0  # (104/100 - 1)*100

    def test_calc_yoy_empty(self):
        assert CPISource.calc_yoy([]) == []

    def test_calc_mom_empty(self):
        assert CPISource.calc_mom([]) == []


# ═══════════════════════════════════════════════════════════
#  测试 CPISource 构造
# ═══════════════════════════════════════════════════════════

class TestCPISourceInit:
    """测试 CPISource 构造参数"""

    def test_default_initializes_all_indicators(self):
        source = CPISource()
        assert len(source.indicator_ids) == len(CPI_UUID_INDICATORS)

    def test_default_period_is_latest_12_months(self):
        source = CPISource()
        assert "2024" in source.period or "2025" in source.period or "2026" in source.period

    def test_custom_indicator_ids(self):
        ids = ["53180dfb9c14411ba4b762307c85920c"]
        source = CPISource(indicator_ids=ids, period="202605")
        assert source.indicator_ids == ids
        assert source.period == "202605"

    def test_custom_das(self):
        das = [{"text": "北京市", "value": "110000000000"}]
        source = CPISource(das=das)
        assert source.das == das


# ═══════════════════════════════════════════════════════════
#  集成测试（需联网）
# ═══════════════════════════════════════════════════════════

def pytest_addoption(parser):
    parser.addoption("--real", action="store_true",
                     help="运行真实 API 集成测试（需联网）")


def pytest_configure(config):
    config.addinivalue_line("markers", "real: 标记需要联网的集成测试")


@pytest.mark.real
class TestCPIIntegration:
    """真实 API 集成测试——用 pytest --real 运行"""

    def test_real_fetch_single_month(self):
        """真实查询单月 CPI（全部 13 个指标）"""
        source = CPISource(period="202512")
        data = source.flow()
        assert len(data) > 0
        # 每个指标都应该有值
        print(f"\n[集成测试] 2026年5月 CPI 共 {len(data)} 条")
        for dp in data:
            print(f"  {dp.indicator}: {dp.value}")

    def test_real_fetch_range(self):
        """真实查询最近 12 个月 CPI"""
        source = CPISource(period="202406-202605")
        data = source.flow()
        assert len(data) > 0
        dates = sorted({d.date for d in data})
        print(f"\n[集成测试] 区间: {dates[0]} ~ {dates[-1]}, 共 {len(data)} 条数据")

    def test_real_fetch_single_indicator(self):
        """只查总体 CPI"""
        source = CPISource(
            indicator_ids=["53180dfb9c14411ba4b762307c85920c"],
            period="202601-202605",
        )
        data = source.flow()
        assert len(data) > 0
        assert all(d.indicator == "居民消费价格指数 (上年同月=100)" for d in data)
        print(f"\n[集成测试] 总体CPI 共 {len(data)} 条")
        for d in data:
            print(f"  {d.date}: {d.value}")

    def test_real_summary(self):
        """真实查询并生成摘要"""
        source = CPISource(period="202601-202605")
        data = source.flow()
        s = CPISource.summary(data)
        print(f"\n[集成测试] CPI 摘要:")
        print(f"  总条数: {s['count']}, 指标数: {s['indicators']}")
        for name, details in s["details"].items():
            print(f"  {name}: 最新 {details['latest']['value']} ({details['latest']['date']})")
        assert s["count"] > 0
        assert s["indicators"] > 0
