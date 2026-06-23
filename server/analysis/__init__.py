"""
运算分析模块门面

统一导出 calculator 的全部功能。

函数：
  calculate_mean(data, window)     → 移动平均
  analyze_trend(data)              → 趋势分析
  prepare_chart_data(data)         → Chart.js 折线图数据
"""

from analysis.calculator import (
    calculate_mean,
    analyze_trend,
    prepare_chart_data,
)

__all__ = [
    "calculate_mean",
    "analyze_trend",
    "prepare_chart_data",
]
