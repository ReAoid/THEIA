"""
中间件 —— 请求前后的钩子。

当前提供：
  - RateLimit  限制请求频率
  - Retry      失败自动重试
  - Log        记录每次请求
"""

import time
import logging

logger = logging.getLogger(__name__)


def rate_limit(interval: float = 2.0):
    """限制请求频率，两次请求至少间隔 interval 秒。"""
    last = [0.0]

    def decorator(func):
        def wrapper(*args, **kwargs):
            now = time.time()
            gap = now - last[0]
            if gap < interval:
                time.sleep(interval - gap)
            last[0] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator


def retry(max_times: int = 3, delay: float = 1.0):
    """失败重试，指数退避。"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_times + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    wait = delay * (2 ** (attempt - 1))
                    logger.warning(f"第 {attempt} 次失败: {e}，{wait:.1f}s 后重试")
                    time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def log_request(func):
    """记录请求的 URL 和耗时。"""
    def wrapper(*args, **kwargs):
        url = kwargs.get("url", args[0] if args else "?")
        start = time.time()
        logger.info(f"[请求] {url}")
        result = func(*args, **kwargs)
        cost = time.time() - start
        logger.info(f"[完成] {url} ({cost:.2f}s)")
        return result
    return wrapper
