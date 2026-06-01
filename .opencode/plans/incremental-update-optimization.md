# 增量更新优化实现计划

## 改动1: `脚本/data.py` — `fetch_all_close_data()` 真增量拉取

**改前问题：** 缓存仅差1天数据时，`ak.stock_value_em()` 仍然拉取全量8年历史（2000+行），然后 concat 合并去重。

**改后逻辑：**
- 缓存不存在 → 仍用 `ak.stock_value_em()` 拉全量历史（首次初始化）
- 缓存存在但落后 → 用 `ak.stock_zh_a_hist(start_date=缓存最后日期+1天)` 只拉增量行（通常5行）
- 缓存已最新 → 跳过，不请求（逻辑不变）
- API请求失败 → 降级使用旧缓存数据
- 删除原来的第二次 `load_close_cache()` 重复读取

**关键差异对比：**

| 场景 | 改前 | 改后 |
|------|------|------|
| 缓存落后1天 | stock_value_em 拉2034行 | stock_zh_a_hist 拉5行 |
| 缓存不存在 | stock_value_em 拉2034行 | stock_value_em 拉2034行（不变） |
| 合并方式 | concat全量+全量去重 | concat缓存+增量去重 |
| 降级策略 | 无 | 用旧缓存兜底 |

## 改动2: `脚本/行业轮动RRS.py` — `_update_market_index()` 加缓存判断

**改前问题：** 每次运行都执行指数更新脚本，即使数据已最新。

**改后：** 先查询 `market_data.db` 最新日期，若已 >= 今天则跳过。

## 需要修改的具体位置

1. `脚本/data.py:83-123` — 整个 `fetch_all_close_data()` 函数体重写
2. `脚本/行业轮动RRS.py:18` — import 加上 `MARKET_DB`
3. `脚本/行业轮动RRS.py:27-38` — `_update_market_index()` 函数加上数据库检查
