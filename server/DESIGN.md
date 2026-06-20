# THEIA CPI 数据服务 — 设计文档

## 一、架构

```
┌────────────────────────────────────────────────────┐
│                    main.py                         │
│             (启动 API + 前端服务)                    │
└──────────────────┬─────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────┐
│              presentation/server.py                 │
│          (Flask 应用工厂 + 静态文件托管)               │
└──────┬──────────────────────────┬──────────────────┘
       │                          │
┌──────▼──────┐          ┌───────▼────────┐
│  api.py     │          │  client/       │
│  Blueprint  │          │  HTML/CSS/JS   │
│  8 endpoints│          │  Chart.js      │
└──────┬──────┘          └────────────────┘
       │ 调用
┌──────▼──────────────────────────────────────────────┐
│              analysis/calculator.py                  │
│   纯函数：增长率 / 移动平均 / 趋势分析 / 图表数据      │
└──────┬──────────────────────────────────────────────┘
       │ 调用
┌──────▼──────────────────────────────────────────────┐
│              manager/cpi_manager.py                  │
│   数据编排：缓存命中？→ 取哪段？→ 筛选哪些指标？       │
└──────┬──────────────────────────────────────────────┘
       │
  ┌────┴────────────┐
  │                 │
  ▼                 ▼
storage/        crawler/
cpi_store.py    sources/cpi_source.py
(本地缓存)       (统计局 API)
```

## 二、分层职责

| 层 | 职责 | 关键文件 |
|----|------|---------|
| **crawler** | fetch + parse → DataPoint | `cpi_source.py`, `base.py` |
| **storage** | JSON 文件读写、去重合并、缓存有效期 | `base.py`, `cpi_store.py` |
| **analysis** | 纯函数计算，入参出参都是 `list[DataPoint]` | `calculator.py` |
| **manager** | 编排：缓存/API/筛选/分组 | `cpi_manager.py` |
| **presentation** | 输出格式包装（API JSON / CLI 表格） | `api.py`, `cli.py`, `server.py` |
| **client** | 纯前端展示 | `index.html`, `js/`, `css/` |

## 三、数据模型

```python
@dataclass
class DataPoint:
    date: str              # "2026-01"
    value: float | None    # 数值
    indicator: str         # 指标名称
    region: str            # 地区，默认"全国"
    unit: str              # 单位
    source: str            # 数据来源
    extra: dict            # 扩展字段（UUID、周期等）
```

## 四、CPI 数据周期

国家统计局 esData API 对不同年份段使用不同的 CID 和 indicatorIds：

| 周期 | 年份 | 指标数 |
|------|------|--------|
| 2026-2030 | 2026~2030 | 13 项 |
| 2021-2025 | 2021~2025 | 13 项 |
| 2016-2020 | 2016~2020 | 9 项 |
| 2000-2015 | 2000~2015 | 9 项 |

CPISource 根据查询年份自动选择对应周期的 CID。
