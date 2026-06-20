"""
全局配置模块
"""
import os
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent

# 数据缓存目录
CACHE_DIR = ROOT_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# 日志目录
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 数据缓存有效期（小时），-1 表示永不过期（只用 force_update 强制刷新）
CACHE_MAX_AGE_HOURS: int = -1

# HTTP 请求配置
REQUEST_TIMEOUT: int = 15        # 超时秒数
REQUEST_RETRIES: int = 3         # 重试次数
REQUEST_RETRY_DELAY: int = 5     # 重试间隔秒数
REQUEST_INTERVAL: float = 2.0    # 单次请求间隔（礼貌爬取）

# 国家统计局目标配置
STATS_BASE_URL: str = "https://data.stats.gov.cn"
STATS_DEFAULT_INDICATOR: str = "A010101"  # 居民消费价格指数(CPI)

# Web 展示服务配置
WEB_HOST: str = "127.0.0.1"
WEB_PORT: int = 5000
WEB_DEBUG: bool = True

# 日志配置
LOG_LEVEL: str = "INFO"
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
