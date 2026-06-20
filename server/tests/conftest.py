"""
pytest 配置：确保可以 from crawler.xxx import ...
"""
import sys
from pathlib import Path

# 把 server/ 目录加到 Python 路径，让 import crawler 能找到
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_addoption(parser):
    parser.addoption("--real", action="store_true",
                     help="运行真实 API 集成测试（需联网）")


def pytest_configure(config):
    config.addinivalue_line("markers", "real: 标记需要联网的集成测试")
