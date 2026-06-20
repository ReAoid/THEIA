"""
CLI 展示模块

提供终端表格输出和趋势摘要打印功能。
"""

from typing import Any

try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False


def print_table(
    data: list[dict[str, Any]] | None,
    title: str = "",
    max_rows: int = 20,
) -> None:
    """
    在终端打印数据表格。

    Args:
        data: 字典列表（每行一个字典）
        title: 表格标题
        max_rows: 最大显示行数，超过时截断并提示
    """
    if not data:
        print(f"\n📭 {title}：无数据")
        return

    # 提取所有键作为表头
    headers = list(data[0].keys()) if data else []

    # 截断
    display_data = data[:max_rows]
    truncated = len(data) > max_rows

    # 打印标题
    if title:
        print(f"\n{'─' * 60}")
        print(f"  {title} ({len(data)} 条)")
        print(f"{'─' * 60}")

    # 用 tabulate 打印
    if HAS_TABULATE:
        print(tabulate(
            [[row.get(h, "") for h in headers] for row in display_data],
            headers=headers,
            tablefmt="simple",
            numalign="right",
            stralign="left",
        ))
    else:
        # 兜底：手动打印
        col_widths = {}
        for h in headers:
            col_widths[h] = max(
                len(str(h)),
                max((len(str(row.get(h, ""))) for row in display_data), default=0)
            )
        # 表头
        header_line = "  ".join(h.ljust(col_widths[h]) for h in headers)
        print(header_line)
        print("-" * len(header_line))
        # 数据行
        for row in display_data:
            print("  ".join(
                str(row.get(h, "")).ljust(col_widths[h]) for h in headers
            ))

    if truncated:
        print(f"... 还有 {len(data) - max_rows} 条未显示（总数 {len(data)}）")


def print_trend_summary(summary: dict[str, Any]) -> None:
    """
    打印趋势摘要。

    Args:
        summary: analyze_trend() 返回的摘要字典
    """
    if not summary or summary.get("count", 0) == 0:
        print("\n📭 无数据可供分析")
        return

    print(f"\n📊 数据总览：{summary.get('count', 0)} 条数据, "
          f"{summary.get('indicators', 0)} 个指标")
    if summary.get("date_range"):
        print(f"📅 时间范围：{summary['date_range']}")

    details = summary.get("details", {})
    if not details:
        return

    print(f"\n{'─' * 60}")
    print(f"  各指标趋势摘要")
    print(f"{'─' * 60}")

    for indicator, info in details.items():
        latest = info.get("latest", {})
        trend_icon = {"up": "📈", "down": "📉", "stable": "➡️"}.get(
            info.get("trend", "stable"), "➡️"
        )
        change_str = ""
        if info.get("latest_change") is not None:
            change_str = f" ({info['latest_change']:+.2f})"

        print(f"\n  {trend_icon} {indicator}")
        print(f"     最新：{latest.get('value', 'N/A')} ({latest.get('date', '')}){change_str}")
        print(f"     均值：{info.get('mean', 'N/A')}  "
              f"  最高：{info.get('max', {}).get('value', 'N/A')} "
              f"({info.get('max', {}).get('date', '')})  "
              f"  最低：{info.get('min', {}).get('value', 'N/A')} "
              f"({info.get('min', {}).get('date', '')})")
        print(f"     波动：{info.get('volatility', 'N/A')}  "
              f" 标准差：{info.get('std', 'N/A')}")
