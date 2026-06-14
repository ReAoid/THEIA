"""
数据管道 —— 处理爬回来的 DataPoint。

当前提供：
  - filter_none   扔掉 value 为 None 的
  - dedup         按 (date, indicator, region) 去重
  - save_json     存成 JSON 文件
  - save_csv      存成 CSV 文件
"""

import json
import csv
import logging
from pathlib import Path
from datetime import datetime
from typing import Callable

from .base import DataPoint

logger = logging.getLogger(__name__)


def filter_none(data: list[DataPoint]) -> list[DataPoint]:
    """扔掉 value 为 None 的数据点。"""
    ok = [d for d in data if d.value is not None]
    dropped = len(data) - len(ok)
    if dropped:
        logger.warning(f"过滤掉 {dropped} 条空值数据")
    return ok


def dedup(data: list[DataPoint]) -> list[DataPoint]:
    """按 (date, indicator, region) 去重，保留最后一条。"""
    seen = {}
    for d in data:
        key = (d.date, d.indicator, d.region)
        seen[key] = d
    dup = len(data) - len(seen)
    if dup:
        logger.info(f"去重 {dup} 条")
    return list(seen.values())


def save_json(data: list[DataPoint], filepath: str | Path) -> Path:
    """存为 JSON。"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "cached_at": datetime.now().isoformat(),
        "count": len(data),
        "data": [d.to_dict() for d in data],
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info(f"已保存 JSON: {filepath} ({len(data)} 条)")
    return filepath


def save_csv(data: list[DataPoint], filepath: str | Path) -> Path:
    """存为 CSV。"""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    rows = [d.to_dict() for d in data]
    if not rows:
        logger.warning("无数据，CSV 未写入")
        return filepath

    with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"已保存 CSV: {filepath} ({len(data)} 条)")
    return filepath


# ── 管道组合 ──────────────────────────────────────────

def default_pipeline() -> list[Callable]:
    """默认管道链：先过滤空值 → 再去重。"""
    return [filter_none, dedup]


def run_pipeline(data: list[DataPoint], pipes: list[Callable]) -> list[DataPoint]:
    """依次执行所有管道函数。"""
    for pipe in pipes:
        data = pipe(data)
    return data
