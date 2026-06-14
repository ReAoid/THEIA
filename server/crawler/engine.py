"""
引擎 —— 串起完整流程。

用法：
    engine = Engine()
    engine.run(StatsAPISource(zbcode="A010101", period="2022"))
    engine.run(HTMLTableSource(url="..."), save=True)
"""

import logging
from pathlib import Path
from typing import Callable

from .base import DataSource, DataPoint
from .pipelines import default_pipeline, run_pipeline

logger = logging.getLogger(__name__)


class Engine:
    """
    通用数据接入引擎。

    流程：
      source.flow()           → fetch + parse
      run_pipeline(data)      → 清洗
      save_func(data)         → 存储（可选）
    """

    def __init__(self, pipeline: list[Callable] = None):
        self.pipeline = pipeline or default_pipeline()

    def run(
        self,
        source: DataSource,
        save: bool = False,
        save_dir: str | Path = None,
        save_fmt: str = "json",
    ) -> list[DataPoint]:
        """
        运行一个数据源。

        Args:
            source: 数据源实例
            save: 是否自动存文件
            save_dir: 存到哪个目录，默认 server/cache
            save_fmt: json 或 csv

        Returns:
            清洗后的 DataPoint 列表
        """

        logger.info(f"[引擎] 启动: {source.name}")

        # 1. 取数据 + 解析
        data = source.flow()

        # 2. 清洗
        data = run_pipeline(data, self.pipeline)

        # 3. 存储
        if save:
            from .pipelines import save_json, save_csv

            save_dir = Path(save_dir or (Path(__file__).parent.parent / "cache"))
            save_dir.mkdir(parents=True, exist_ok=True)

            if save_fmt == "csv":
                save_csv(data, save_dir / f"{source.name}.csv")
            else:
                save_json(data, save_dir / f"{source.name}.json")

        logger.info(f"[引擎] 完成: {source.name} → {len(data)} 条有效数据")
        return data
