"""
展示模块门面

统一导出 CLI、Web 和 API 展示功能。

子模块：
  cli.py    — 终端表格输出
  web.py    — Flask 网页渲染（旧版，向后兼容）
  api.py    — RESTful API Blueprint（前端数据服务层）
  server.py — API 服务启动入口
"""

from presentation.cli import print_table, print_trend_summary
from presentation.web import render_web
from presentation.api import api_bp

__all__ = [
    "print_table",
    "print_trend_summary",
    "render_web",
    "api_bp",
]
