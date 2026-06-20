"""
数据存储模块

每个数据源有自己对应的 Store，继承 BaseStore 统一接口。

当前实现：
  - BaseStore    — 通用 JSON 文件存储基类
  - CPIStore     — CPI 数据专用存储
  - data_store   — 向后兼容接口（供 main.py 使用）

用法：
    from storage.base import BaseStore
    from storage.cpi_store import CPIStore

    store = CPIStore()
    store.save(data_points)
    loaded = store.load()
"""
