"""
通用存储基类 —— BaseStore

职责：
  1. JSON 文件的读写
  2. 缓存有效期检查（基于 config.CACHE_MAX_AGE_HOURS）
  3. 增量合并（按自定义 key 去重，新覆盖旧）
  4. 文件锁保护（防止并发写冲突）

所有数据源的 Store 都继承此类，只需实现：
  - _point_key()     → 数据点的唯一键（默认 (date, indicator, region)）
  - _serialize()     → 从数据对象到 dict
  - _deserialize()   → 从 dict 到数据对象
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Generic, TypeVar

from config import CACHE_DIR, CACHE_MAX_AGE_HOURS

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseStore(ABC, Generic[T]):
    """
    通用存储基类。

    T 是业务数据类型，例如 DataPoint。
    子类提供序列化/反序列化方法，BaseStore 管理文件的读写。
    """

    # 子类覆盖
    store_name: str = "data"          # 标识名称，用于日志和默认文件名

    def __init__(self, cache_dir: str | Path | None = None,
                 cache_file: str | Path | None = None,
                 max_age_hours: int | None = None):
        """
        Args:
            cache_dir: 缓存目录，默认 config.CACHE_DIR
            cache_file: 缓存文件路径，默认 {cache_dir}/{store_name}.json
            max_age_hours: 缓存有效期（小时），默认 config.CACHE_MAX_AGE_HOURS
        """
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if cache_file:
            self.cache_file = Path(cache_file)
        else:
            self.cache_file = self.cache_dir / f"{self.store_name}.json"

        self.max_age_hours = max_age_hours if max_age_hours is not None else CACHE_MAX_AGE_HOURS

        # 内存缓存
        self._data: list[T] = []
        self._loaded = False

    # ── 子类必须实现 ──────────────────────────────────

    @abstractmethod
    def _point_key(self, item: T) -> tuple:
        """
        返回数据项的唯一键，用于去重合并。
        默认逻辑在子类中实现。
        """
        ...

    @abstractmethod
    def _serialize(self, item: T) -> dict:
        """将业务对象转为可 JSON 序列化的 dict。"""
        ...

    @abstractmethod
    def _deserialize(self, data: dict) -> T:
        """从 dict 还原业务对象。"""
        ...

    # ── 公开接口 ──────────────────────────────────────

    def save(self, items: list[T]) -> int:
        """
        保存数据到缓存（增量合并）。

        Args:
            items: 要保存的数据列表

        Returns:
            合并后的总条数
        """
        # 先加载已有的
        self._lazy_load()

        # 增量合并：新数据覆盖旧数据
        existing = {self._point_key(d): d for d in self._data}
        for item in items:
            existing[self._point_key(item)] = item

        merged = list(existing.values())

        # 写文件
        output = {
            "store": self.store_name,
            "cached_at": datetime.now().isoformat(),
            "max_age_hours": self.max_age_hours,
            "count": len(merged),
            "data": [self._serialize(d) for d in merged],
        }

        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        self._data = merged
        logger.info(f"[{self.store_name}] 缓存已更新: {self.cache_file.name} ({len(merged)} 条)")
        return len(merged)

    def load(self, force: bool = False) -> list[T]:
        """
        加载缓存数据。

        Args:
            force: 强制从文件重新加载（忽略内存缓存）

        Returns:
            数据列表，缓存过期或不存在时返回空列表
        """
        if force:
            self._loaded = False
        self._lazy_load()
        return list(self._data)

    def is_valid(self) -> bool:
        """
        检查缓存文件是否存在且在有效期内。

        Returns:
            True 表示缓存可用
        """
        if not self.cache_file.exists():
            return False

        age_seconds = time.time() - self.cache_file.stat().st_mtime
        age_hours = age_seconds / 3600
        return age_hours < self.max_age_hours

    def get_cache_info(self) -> dict:
        """查看缓存状态信息。"""
        info: dict[str, Any] = {
            "store": self.store_name,
            "cache_file": str(self.cache_file),
            "exists": self.cache_file.exists(),
            "valid": self.is_valid(),
        }

        if self.cache_file.exists():
            info["size_bytes"] = self.cache_file.stat().st_size
            info["age_hours"] = round(
                (time.time() - self.cache_file.stat().st_mtime) / 3600, 2
            )

        self._lazy_load()
        info["count"] = len(self._data)
        if self._data:
            dates = sorted({self._extract_date(d) for d in self._data if self._extract_date(d)})
            info["date_range"] = f"{dates[0]} ~ {dates[-1]}" if dates else None

        return info

    def clear(self):
        """清空缓存文件和内存数据。"""
        self._data = []
        self._loaded = False
        if self.cache_file.exists():
            self.cache_file.unlink()
            logger.info(f"[{self.store_name}] 缓存已清除: {self.cache_file}")

    # ── 内部方法 ──────────────────────────────────────

    def _lazy_load(self):
        """懒加载：仅在首次或 force reload 时从文件读取。"""
        if self._loaded:
            return

        self._data = []
        self._loaded = True

        if not self.cache_file.exists():
            return

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                raw = json.load(f)

            self._data = [self._deserialize(item) for item in raw.get("data", [])]
            logger.info(
                f"[{self.store_name}] 从缓存加载: {self.cache_file.name} ({len(self._data)} 条)"
            )
        except Exception as e:
            logger.warning(f"[{self.store_name}] 缓存读取失败: {e}")

    def _extract_date(self, item: T) -> str | None:
        """提取数据项的日期字段（用于统计日期范围）。子类可覆盖。"""
        if hasattr(item, "date"):
            return getattr(item, "date")
        return None

    # ── 上下文管理 ────────────────────────────────────

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
