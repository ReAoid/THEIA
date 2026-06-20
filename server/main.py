"""
国家统计局数据抓取与智能分析展示系统 - 主入口

编排全链路流程：
  爬取数据 → 缓存存储 → 运算分析 → CLI/Web 展示

使用方法：
    python main.py                    # 爬取 + CLI 展示 + Web 服务
    python main.py --web-only         # 仅启动 Web（使用缓存）
    python main.py --no-cache         # 强制重新爬取
    python main.py --cli-only         # 仅 CLI 展示
    python main.py --api-only         # 仅启动 API + 前端（使用缓存）
"""

import sys
import argparse
import logging
from datetime import datetime
from typing import Any

from config import (
    STATS_BASE_URL,
    STATS_DEFAULT_INDICATOR,
    CACHE_DIR,
    WEB_HOST,
    WEB_PORT,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DIR,
)
from storage.data_store import (
    save_data,
    load_data,
    is_cache_valid,
    get_cached_data_points,
    DEFAULT_CACHE_FILE,
)
from analysis.calculator import calculate_growth, calculate_mean, analyze_trend
from presentation.cli import print_table, print_trend_summary
from presentation.web import render_web


def setup_logging() -> None:
    """配置日志系统"""
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
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="国家统计局数据抓取与智能分析展示系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py                         爬取数据 → CLI 展示 → Web 服务
  python main.py --cli-only             仅 CLI 展示（使用缓存）
  python main.py --web-only             仅启动 Web 服务（使用缓存）
  python main.py --api-only             仅启动 API + 前端（使用缓存）
  python main.py --no-cache             强制重新爬取
  python main.py --url <URL>            指定数据页面 URL
  python main.py --indicator CPI        指定指标名称
        """,
    )
    parser.add_argument("--url", type=str, default=None, help="国家统计局数据页面 URL")
    parser.add_argument("--indicator", type=str, default=STATS_DEFAULT_INDICATOR, help="指标名称/代码")
    parser.add_argument("--cli-only", action="store_true", help="仅命令行展示")
    parser.add_argument("--web-only", action="store_true", help="仅启动旧版 Web 服务")
    parser.add_argument("--api-only", action="store_true", help="仅启动 API + 前端服务")
    parser.add_argument("--no-cache", action="store_true", help="强制重新爬取，忽略缓存")
    parser.add_argument("--port", type=int, default=WEB_PORT, help="Web 服务端口")

    return parser.parse_args()


def crawl_and_process(url: str, indicator: str, use_cache: bool = True) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """
    完整流程：获取数据 → 运算分析

    Args:
        url: 数据页面 URL
        indicator: 指标名称
        use_cache: 是否使用缓存

    Returns:
        (原始数据, 增长率数据, 移动平均数据, 趋势摘要)
    """
    cache_file = CACHE_DIR / f"{indicator}_cache.json"

    raw_data: list[dict[str, Any]] | None = None

    # 优先使用缓存
    if use_cache:
        raw_data = get_cached_data_points(cache_file)
        if raw_data:
            print(f"📦 使用缓存数据 ({cache_file.name})")
        else:
            print("⏳ 缓存不存在或已过期，开始爬取...")

    # 爬取新数据
    if raw_data is None:
        from crawler import crawl_stats_data
        raw_data = crawl_stats_data(url, indicator=indicator)

        # 保存到缓存
        cache_data = {
            "indicator": indicator,
            "source_url": url,
            "cached_at": datetime.now().isoformat(),
            "data_points": raw_data,
        }
        save_data(cache_data, cache_file)
        print(f"✅ 数据已爬取并缓存 ({len(raw_data)} 条)")

    # 运算分析
    print("\n🔢 正在计算增长率...")
    growth_data = calculate_growth(raw_data, period="year")

    print("🔢 正在计算移动平均...")
    moving_avg_data = calculate_mean(raw_data, window=12)

    print("🔢 正在分析趋势...")
    trend_summary = analyze_trend(raw_data)

    return raw_data, growth_data, moving_avg_data, trend_summary


def run_cli(raw_data: list[dict[str, Any]], growth_data: list[dict[str, Any]], moving_avg_data: list[dict[str, Any]], trend_summary: dict[str, Any]) -> None:
    """
    CLI 展示模式
    """
    print("\n" + "=" * 60)
    print("  国家统计局数据抓取与智能分析系统")
    print("=" * 60)

    # 趋势摘要
    print_trend_summary(trend_summary)

    # 原始数据表
    print_table(raw_data, title="原始数据", max_rows=20)

    # 增长率表
    print_table(growth_data, title="同比增长率数据", max_rows=20)

    # 移动平均表
    print_table(moving_avg_data, title="12个月移动平均数据", max_rows=20)


def run_web(raw_data: list[dict[str, Any]], growth_data: list[dict[str, Any]], trend_summary: dict[str, Any]) -> None:
    """
    Web 展示模式
    """
    # 合并展示数据：带上增长率
    display_data = []
    for raw, growth in zip(raw_data, growth_data):
        item = {**raw}
        if growth.get("growth") is not None:
            item["growth"] = growth["growth"]
        display_data.append(item)

    render_web(
        data=display_data,
        title="国家统计局数据",
        host=WEB_HOST,
        port=WEB_PORT,
        summary=trend_summary,
    )


def main() -> None:
    """主入口函数"""
    setup_logging()
    args = parse_args()

    # 确定 URL
    url = args.url
    if not url:
        # 使用国家统计局默认页面 — 这里需要填写实际的数据发布页面
        # 用户可以根据需要替换为具体的统计指标页面 URL
        url = f"{STATS_BASE_URL}/easyquery.htm?cn=E0103&zb={args.indicator}"

    indicator = args.indicator
    logger = logging.getLogger(__name__)

    try:
        # API-only 模式：启动 API + 前端服务
        if args.api_only:
            from presentation.server import create_app
            app = create_app(api_only=False)
            print(f"\n🌐 API + 前端服务启动: http://{WEB_HOST}:{args.port}/")
            print(f"   API 端点: http://{WEB_HOST}:{args.port}/api/v1/cpi/")
            print(f"   前端页面: http://{WEB_HOST}:{args.port}/")
            print(f"   按 Ctrl+C 停止服务\n")
            app.run(host=WEB_HOST, port=args.port, debug=False)
            return

        # Web-only 模式：不爬取，仅加载缓存
        if args.web_only:
            cache_file = CACHE_DIR / f"{indicator}_cache.json"
            raw_data = get_cached_data_points(cache_file)
            if not raw_data:
                print("❌ 无缓存数据可用，请先不带 --web-only 运行以爬取数据")
                sys.exit(1)
            growth_data = calculate_growth(raw_data, period="year")
            trend_summary = analyze_trend(raw_data)
            run_web(raw_data, growth_data, trend_summary)
            return

        # 完整流程：爬取 → 运算 → 展示
        raw_data, growth_data, moving_avg_data, trend_summary = crawl_and_process(
            url=url,
            indicator=indicator,
            use_cache=not args.no_cache,
        )

        if args.cli_only:
            run_cli(raw_data, growth_data, moving_avg_data, trend_summary)
        else:
            # CLI + Web 联动
            run_cli(raw_data, growth_data, moving_avg_data, trend_summary)
            run_web(raw_data, growth_data, trend_summary)

    except KeyboardInterrupt:
        print("\n\n⏹  用户终止运行")
        sys.exit(0)
    except Exception as e:
        logger.exception("运行异常")
        print(f"\n❌ 运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
