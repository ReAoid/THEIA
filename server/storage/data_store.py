"""
向后兼容的 data_store 接口

供 main.py 使用，提供简单的 JSON 文件读写函数。
内部已迁移至 BaseStore 体系，此处保留兼容层。

函数：
  - save_data(data, filepath)              → 保存 dict 到 JSON
  - load_data(filepath)                    → 从 JSON 加载 dict
  - is_cache_valid(filepath, max_age_hours) → 检查缓存是否有效
  - get_cached_data_points(filepath)       → 加载并返回 data_points 列表
  - DEFAULT_CACHE_FILE                     → 默认缓存文件路径
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import CACHE_DIR, CACHE_MAX_AGE_HOURS

logger = logging.getLogger(__name__)

# 默认缓存文件（通用 fallback）
DEFAULT_CACHE_FILE = CACHE_DIR / "data_cache.json"


def save_data(data: dict[str, Any], filepath: str | Path) -> Path:
    """
    保存数据到 JSON 文件。

    Args:
        data: 可 JSON 序列化的 dict
        filepath: 目标文件路径

    Returns:
        文件路径
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # 确保有时间戳
    if "cached_at" not in data:
        data["cached_at"] = datetime.now().isoformat()

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    count = len(data.get("data_points", data.get("data", [])))
    logger.info(f"数据已保存: {filepath} ({count} 条)")
    return filepath


def load_data(filepath: str | Path) -> dict[str, Any] | None:
    """
    从 JSON 文件加载数据。

    Args:
        filepath: 文件路径

    Returns:
        dict 数据，文件不存在或解析失败返回 None
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"数据加载失败: {filepath} — {e}")
        return None


def is_cache_valid(filepath: str | Path,
                   max_age_hours: int | None = None) -> bool:
    """
    检查缓存文件是否在有效期内。

    Args:
        filepath: 缓存文件路径
        max_age_hours: 有效期（小时），默认 config.CACHE_MAX_AGE_HOURS

    Returns:
        True 表示缓存可用
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return False

    max_age = max_age_hours if max_age_hours is not None else CACHE_MAX_AGE_HOURS
    age_seconds = time.time() - filepath.stat().st_mtime
    return (age_seconds / 3600) < max_age


def get_cached_data_points(filepath: str | Path) -> list[dict[str, Any]] | None:
    """
    从缓存文件加载 data_points 列表。

    兼容两种格式：
      1. 新版：{ "data_points": [...] }
      2. 旧版：{ "data": [...] }

    Args:
        filepath: 缓存文件路径

    Returns:
        data_points 列表，缓存无效或不存在时返回 None
    """
    filepath = Path(filepath)

    if not is_cache_valid(filepath):
        return None

    data = load_data(filepath)
    if data is None:
        return None

    # 兼容两种字段名
    points = data.get("data_points") or data.get("data")
    if points is None:
        logger.warning(f"缓存文件格式异常: {filepath}，缺少 data_points/data 字段")
        return None

    logger.debug(f"从缓存读取: {filepath.name} ({len(points)} 条)")
    return points
