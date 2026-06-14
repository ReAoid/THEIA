# 通用数据接入框架
#
# 用法：
#   from crawler.engine import Engine
#   from crawler.sources.stats_api import StatsAPISource
#
#   engine = Engine()
#   data = engine.run(StatsAPISource(zbcode="A010101", period="2022"), save=True)
