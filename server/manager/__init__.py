# 管理者模块
#
# 每个数据源对应一个 Manager，负责：
#   1. 缓存管理（先查本地，没有再拉 API）
#   2. 灵活的查询参数（按单指标 / 分组 / 名称查询）
#   3. 强制刷新
#
# 用法：
#   from manager.cpi_manager import CPIManager
#   mgr = CPIManager()
#   data = mgr.get_cpi(indicators="总体CPI", period="2026")
