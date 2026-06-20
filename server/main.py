"""
THEIA CPI 数据服务 — 主入口

启动 REST API + 前端仪表盘。
数据通过 CPIManager 自动从本地缓存或国家统计局 API 获取。

使用方法：
    python main.py
    python main.py --port 8080
    python main.py --host 0.0.0.0 --debug
"""

import sys
import argparse
import logging
from datetime import datetime

from config import WEB_HOST, WEB_PORT, LOG_LEVEL, LOG_FORMAT, LOG_DIR


def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"stats_{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="THEIA CPI 数据服务",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py                      启动 API + 前端（默认）
  python main.py --port 8080          指定端口
  python main.py --host 0.0.0.0       允许外部访问
  python main.py --api-only           仅 API，不托管前端
        """,
    )
    parser.add_argument("--host", type=str, default=WEB_HOST, help=f"监听地址，默认 {WEB_HOST}")
    parser.add_argument("--port", type=int, default=WEB_PORT, help=f"监听端口，默认 {WEB_PORT}")
    parser.add_argument("--debug", action="store_true", default=False, help="调试模式")
    parser.add_argument("--api-only", action="store_true", help="仅 API，不托管前端")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()

    from presentation.server import create_app
    app = create_app(api_only=args.api_only)

    mode_str = "API + 前端" if not args.api_only else "仅 API"
    print(f"\n{'=' * 50}")
    print(f"  THEIA CPI 数据服务")
    print(f"  模式: {mode_str}")
    print(f"  API:  http://{args.host}:{args.port}/api/v1/")
    if not args.api_only:
        print(f"  前端: http://{args.host}:{args.port}/")
    print(f"{'=' * 50}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
