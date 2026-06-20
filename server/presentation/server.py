"""
API 服务启动入口。

提供两种模式：
  1. 独立 API 服务（默认）：启动 REST API + 静态文件托管
  2. 嵌入模式：返回 Flask app 实例，供 main.py 集成

用法：
    python -m presentation.server
    # 访问 http://127.0.0.1:5000 查看前端页面
    # API 端点：http://127.0.0.1:5000/api/v1/cpi/...
"""

import logging
import sys
from pathlib import Path
from typing import Any

from flask import Flask, send_from_directory, jsonify

from config import WEB_HOST, WEB_PORT, WEB_DEBUG

from presentation.api import api_bp

logger = logging.getLogger(__name__)

# ── 路径 ──────────────────────────────────────────────────

# 项目根目录（server/）
ROOT_DIR = Path(__file__).resolve().parent.parent

# client 静态文件目录（THEIA/client/）
CLIENT_DIR = ROOT_DIR.parent / "client"


# ── 应用工厂 ─────────────────────────────────────────────

def create_app(api_only: bool = False, client_dir: str | Path | None = None) -> Flask:
    """
    创建 Flask 应用。

    Args:
        api_only: True 则不托管前端静态文件
        client_dir: client 静态文件目录，默认 THEIA/client/

    Returns:
        Flask 应用实例
    """
    app = Flask(__name__, static_folder=None)  # 不用 Flask 默认静态路由

    # 注册 API Blueprint
    app.register_blueprint(api_bp)

    if not api_only:
        _serve_client(app, client_dir or CLIENT_DIR)

    # 全局错误处理器
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not Found", "code": 404}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal Server Error", "code": 500}), 500

    return app


def _serve_client(app: Flask, client_dir: Path):
    """
    配置静态文件路由，托管 client/ 目录。

    client/index.html → GET /
    client/js/xxx.js  → GET /js/xxx.js
    client/css/xxx.css → GET /css/xxx.css
    """
    client_dir = Path(client_dir)

    if not client_dir.exists():
        logger.warning(f"client 目录不存在: {client_dir}，仅提供 API 服务")
        return

    logger.info(f"托管前端静态文件: {client_dir}")

    @app.route("/")
    def index():
        return send_from_directory(str(client_dir), "index.html")

    @app.route("/<path:path>")
    def static_files(path: str):
        file_path = client_dir / path
        if file_path.exists() and file_path.is_file():
            return send_from_directory(str(client_dir), path)
        # SPA fallback：所有未匹配路由返回 index.html
        return send_from_directory(str(client_dir), "index.html")


# ── 独立启动 ─────────────────────────────────────────────

def main():
    """独立启动 API 服务。"""
    import argparse

    parser = argparse.ArgumentParser(description="THEIA CPI API 服务")
    parser.add_argument("--host", default=WEB_HOST, help=f"监听地址，默认 {WEB_HOST}")
    parser.add_argument("--port", type=int, default=WEB_PORT, help=f"监听端口，默认 {WEB_PORT}")
    parser.add_argument("--debug", action="store_true", default=WEB_DEBUG, help="调试模式")
    parser.add_argument("--api-only", action="store_true", help="仅 API，不托管前端")
    parser.add_argument("--client-dir", default=None, help="前端静态文件目录")
    args = parser.parse_args()

    # 日志
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    app = create_app(api_only=args.api_only, client_dir=args.client_dir)

    print(f"\n{'=' * 50}")
    print(f"  THEIA CPI 数据服务")
    print(f"  API:     http://{args.host}:{args.port}/api/v1/")
    if not args.api_only:
        print(f"  Frontend: http://{args.host}:{args.port}/")
    print(f"{'=' * 50}\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
