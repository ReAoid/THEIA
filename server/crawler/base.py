"""
数据格式 + 数据源基类

所有爬虫的输出都统一成 DataPoint，下游统一消费。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DataPoint:
    """
    统一数据点。

    不管从哪个网站爬的，最终都转成这个格式吐出去。
    """
    date: str                           # "2022-01"
    value: float | int | None           # 数值
    indicator: str = ""                 # 指标名
    region: str = "全国"                 # 地区
    unit: str = ""                      # 单位
    source: str = ""                    # 来源，如 "stats_api"
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "value": self.value,
            "indicator": self.indicator,
            "region": self.region,
            "unit": self.unit,
            "source": self.source,
            **self.extra,
        }


class DataSource(ABC):
    """
    数据源基类。

    每个爬虫就是一个 DataSource，只需实现：
      - fetch()   怎么拿原始数据
      - parse()   怎么从原始数据里提取 DataPoint

    引擎负责调用 flow() 串起全流程。
    """

    name: str = ""          # 唯一标识，子类必须写

    def __init__(self, **kwargs):
        self.config = kwargs

    @abstractmethod
    def fetch(self) -> Any:
        """拿原始数据。返回 HTML 字符串 / JSON 字典 / 文件路径……"""
        ...

    @abstractmethod
    def parse(self, raw: Any) -> list[DataPoint]:
        """从原始数据里解析出 DataPoint 列表。"""
        ...

    def flow(self) -> list[DataPoint]:
        """fetch + parse 的完整流程。引擎会调这个。"""
        raw = self.fetch()
        data = self.parse(raw)
        logger.info(f"[{self.name}] 解析完成，共 {len(data)} 条")
        return data
