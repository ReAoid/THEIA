# THEIA CPI 数据服务

自动抓取国家统计局（data.stats.gov.cn）居民消费价格指数（CPI）数据，
通过 REST API + 前端仪表盘可视化展示。

## 快速开始

```bash
cd server
pip install -r requirements.txt
python main.py
```

访问 `http://127.0.0.1:5000` 查看仪表盘。

## 项目结构

```
server/
├── main.py                    # 主入口（启动 API + 前端）
├── config.py                  # 全局配置
├── requirements.txt           # Python 依赖
├── crawler/
│   ├── base.py                # DataPoint 统一数据模型
│   ├── middleware.py           # 请求限速 / 日志装饰器
│   └── sources/
│       └── cpi_source.py       # CPI 数据源（国家统计局 esData API）
├── storage/
│   ├── base.py                # BaseStore 通用存储基类
│   └── cpi_store.py           # CPI 数据专用存储
├── manager/
│   └── cpi_manager.py         # CPIManager — 数据编排（缓存/API/筛选）
├── analysis/
│   ├── __init__.py
│   └── calculator.py          # 纯函数计算层（增长率/移动平均/趋势/图表数据）
├── presentation/
│   ├── __init__.py
│   ├── cli.py                 # CLI 表格输出
│   ├── api.py                 # RESTful API（Flask Blueprint）
│   └── server.py              # API 服务启动入口
├── tests/                     # pytest 测试
│   ├── conftest.py
│   ├── test_cpi.py
│   └── test_cpi_manager.py
├── cache/                     # 数据缓存（自动生成）
└── logs/                      # 运行日志（自动生成）

client/                        # 前端静态文件
├── index.html                 # 主页面
├── css/style.css              # 样式
└── js/
    ├── api.js                 # API 请求封装
    ├── charts.js              # Chart.js 图表渲染
    └── app.js                 # 主逻辑 / 状态管理
```

## 数据流

```
用户浏览器 → client/ 前端
    ↓ HTTP/JSON
presentation/api.py（REST API）
    ↓
analysis/calculator.py（计算）
    ↓
manager/cpi_manager.py（编排）
    ↓
storage/cpi_store.py（缓存读写） ← → cache/cpi.json
    ↓
crawler/sources/cpi_source.py（统计局 API）
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/cpi/overview` | GET | 总体概览（最新值、趋势） |
| `/api/v1/cpi/indicators` | GET | 指标列表（UUID + 名称 + 分组） |
| `/api/v1/cpi/data` | GET | 原始数据（支持 indicator / period / group 筛选） |
| `/api/v1/cpi/growth` | GET | 增长率（同比 / 环比） |
| `/api/v1/cpi/summary` | GET | 统计摘要（min / max / mean / std） |
| `/api/v1/cpi/chart` | GET | Chart.js 图表数据 |
| `/api/v1/cpi/groups` | GET | CPI 分组列表 |
| `/api/v1/cpi/cache` | GET/DELETE | 缓存状态 / 清空 |

## 使用示例

```bash
# 启动 API + 前端
python main.py

# 指定端口
python main.py --port 8080

# 仅 API（不托管前端）
python main.py --api-only

# 调试模式
python main.py --debug
```
