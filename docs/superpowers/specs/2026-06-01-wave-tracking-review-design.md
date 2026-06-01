# 行业波浪位置跟踪及复盘 — 设计文档

> 日期: 2026-06-01
> 状态: 已批准，进入实现规划阶段

## 背景

项目目前已有主升浪分析算法（`html_.py:106-196`），在「行业分析」Tab 显示当前 32 个行业的波浪阶段卡片。但有两个缺口：

1. **没有信号档案**：每次运行只输出当下快照，信号发完就消失，无法回顾「3 周前那个 pre_main 信号后来怎么样了」。
2. **没有时间轴视角**：现有「行业分析」Tab 只看现在，看不到一个行业是怎么在 main_advance / pre_main / terminal / post_main 之间演变的。

本文档为这两个缺口设计完整的跟踪 + 复盘体系。

## 范围

### 在范围内

- 一次性回填近 1 年（实际 720 交易日窗口，5 日采样后约 144 时点）所有 32 行业的波浪信号
- 行业级波浪阶段时间轴（独立 HTML 展示）
- 复盘报告（独立 HTML，含信号质量统计 + 行业生命周期 + 信号明细）
- 独立 SQLite 文件持久化
- 主入口新增 `--wave` 命令

### 不在范围内

- 主 HTML（`数据/行业轮动RRS轨迹图.html`）的任何改动
- PNG 静态图
- 波浪算法的算法层面改进（仅做接口改造以支持任意时点）
- 邮件/微信/钉钉通知
- 多用户/多账户

## 架构

### 数据流

```
[RS轨迹 from calc.py]
    ↓ 切片
[calc_wave_at(sector, as_of_date)] ── 任意时点的波浪阶段
    ↓ 写入
[wave_archive.db] ◀── wave_archive.py (SQLite)
    ↓ 读
    ├── gen_wave_timeline_html()  → 数据/波浪阶段时间轴.html
    └── gen_wave_review_html()    → 数据/波浪复盘报告.html
```

### 模块清单

| 文件 | 角色 | 状态 |
|------|------|------|
| `脚本/calc.py` | +`calc_wave_at(rr, mo, as_of_date)` 公共函数 | 改动 |
| `脚本/行业轮动RRS.py` | +`--wave` 命令触发整个流程 | 改动 |
| `脚本/wave_archive.py` | SQLite 读写 + 回填 + outcome 计算 | 新建 |
| `脚本/wave_timeline_html.py` | 行业级波浪阶段时间轴 HTML | 新建 |
| `脚本/wave_review_html.py` | 复盘报告 HTML | 新建 |
| `脚本/test_wave.py` | 单元测试 | 新建 |
| `数据/wave_archive.db` | 信号档案 + 后续表现 | 新建产物 |
| `数据/波浪阶段时间轴.html` | 时间轴 HTML | 新建产物 |
| `数据/波浪复盘报告.html` | 复盘报告 HTML | 新建产物 |
| `README.md` | 增加一节说明 | 改动 |

## 关键设计

### 1. 算法改造：calc_wave_at

**现状**（`html_.py:106-196`）的局限：
- 算法是「对全轨迹计算，再取最后一段作为 current」，无法计算「时点 T 当时」处于什么阶段
- `main_wave` 永远是历史最强浪——但 T 时点的「历史最强」应该只用 T 之前的数据算

**目标签名**

```python
# 脚本/calc.py
def calc_wave_at(rr: pd.Series, mo: pd.Series, as_of_date: str) -> dict | None:
    """计算某行业在 as_of_date 当日的波浪阶段。

    Args:
        rr: 行业 RS Ratio 时间序列（5日采样，索引为日期）
        mo: 行业 RS Momentum 时间序列（同上）
        as_of_date: 'YYYY-MM-DD'

    Returns: None（数据不足）or dict{
        phase, current_type, current_amp, current_days, current_slope,
        main_amp, main_days, main_score, latest_rs, n_waves, rs_range
    }
    """
```

**关键改造点**

1. **截断到 T**：算法只使用 `rr[rr.index <= as_of_date]`，mo 同理
2. **最小数据长度**：从 `len(rr_series) < 200` 改为「截断后还需 ≥ 200 个采样点」——否则返回 None
3. **分段起点**：直接对截断后的 `rr.values` 跑现有 `html_.py:117-155` 的算法（趋势分段 → 连段+小波合并 → 主浪评分）
4. **主浪评分**：仍按 `振幅 × √天数`，但只在 T 之前的上升浪里选最大
5. **main_advance 阈值**：用「T 之前历史最强主升 × 80%」与「T 当时 current」比较

**调用入口**：`gen_html` 里 `wave_data` 那段（`html_.py:106-196`）改为调用 `calc_wave_at`，传 `as_of_date = str(rr.index[-1].date())` 保持现有 0 行为差异。

### 2. SQLite Schema

**文件**：`数据/wave_archive.db`

**表 1：`wave_signal`** — 每行 = 某行业某采样日的波浪判断

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| sector | TEXT | NOT NULL | 行业名 |
| signal_date | TEXT | NOT NULL | 'YYYY-MM-DD'（5日采样日） |
| phase | TEXT | NOT NULL | main_advance/strong_advance/pre_main/terminal/post_main/recovery/no_main |
| current_type | TEXT | | up / down |
| current_amp | REAL | | 当前段振幅 |
| current_days | INTEGER | | 当前段天数 |
| current_slope | REAL | | 当前段斜率 |
| main_amp | REAL | | T 之前最强主升振幅 |
| main_days | INTEGER | | T 之前最强主升天数 |
| main_score | REAL | | 主升评分 |
| latest_rs | REAL | | 当日 RS 值 |
| rs_range | TEXT | | "min~max"（T 之前） |
| n_waves | INTEGER | | 已合并浪段数 |

主键：`(sector, signal_date)`；索引：`(signal_date, phase)`、`(sector, phase)`。

**表 2：`wave_outcome`** — 复盘验证用

| 字段 | 类型 | 说明 |
|------|------|------|
| sector | TEXT | |
| signal_date | TEXT | |
| phase | TEXT | |
| rs_at_signal | REAL | 信号日 RS |
| rs_p10 | REAL | 后续 10 交易日 RS（找不到则 NULL） |
| rs_p20 | REAL | 后续 20 交易日 RS |
| rs_p40 | REAL | 后续 40 交易日 RS |
| max_amp_p20 | REAL | 后续 20 日内 RS 最大升幅 |
| max_amp_p40 | REAL | 后续 40 日内 RS 最大升幅 |
| hit_main_advance | INTEGER | 后续 40 日内是否出现 main_advance (0/1) |

主键：`(sector, signal_date, phase)`。

**outcome 计算**：从 `stock_data` 直接用 RS 公式算后续 N 日的 RS（不调用 `calc_wave_at`，开销太贵）。`hit_main_advance` 需要在 outcome 计算时调一次 `calc_wave_at` 查后续 40 日内任意一日是否 phase=main_advance。

### 3. 回填流程

`wave_archive.py:backfill(archive_db, stock_data, market, pool)`：

```
1. 加载 stock_data + market（同 calc_sector_rrs 调用）
2. 对每个行业：
   rr, mo = calc_sector_rrs_for_one(...)   # 现算或缓存
   对每个 5日采样日 t（从 t[200] 起到最新）：
       result = calc_wave_at(rr, mo, str(t.date()))
       若 result 不为 None 且 phase != 'no_main'：
           UPSERT INTO wave_signal ...
3. 对 wave_signal 里每行 (sector, signal_date, phase)：
   算后续 10/20/40 交易日 RS + max_amp + hit_main_advance
   UPSERT INTO wave_outcome ...
```

**增量策略**：
- 第一次运行：全量回填
- 之后：只补 `MAX(signal_date) < today` 的日期
- 同一 `(sector, signal_date)` 重算覆盖（UPSERT）

**回填耗时估计**：32 行业 × ~144 时点 × 算法耗时（~5ms）≈ 23 秒，外加 outcome 计算 × ~2300 行 ≈ 几十秒。可接受。

### 4. 行业级波浪阶段时间轴 HTML

**文件**：`数据/波浪阶段时间轴.html`

**整体布局**

```
[标题] 行业波浪阶段时间轴 · 2025-06 ~ 2026-05 (更新于 2026-06-01)
[筛选栏] 行业多选 | 阶段着色图例 | 时间窗口滑块
[时间轴区] 一行一行业，色带显示该行业每个时点所处的浪段
[详情面板] 点击行业行 → 下方展开
[图例/方法] 折叠的方法说明
```

**核心可视化**：每个行业一行（高度 24px），横向是时间（720 天滚动），色块按 `phase` 着色：

| phase | 颜色 | 含义 |
|-------|------|------|
| main_advance | `#2E7D32` | ★★★ 主升浪中 |
| strong_advance | `#43A047` | ★★ 强势推进 |
| pre_main | `#F9A825` | 📍 主升前布局 |
| terminal | `#E53935` | ▼ 末浪衰竭 |
| recovery | `#FB8C00` | ▲ 弱势反弹 |
| post_main | `#E0E0E0` | — 主升已过 |
| no_main | `#FAFAFA` | 无数 |

**事件标记**：在 main_advance 段中央叠加 ★；在 pre_main 段中央叠加 📍。

**排序**：默认按「最新 phase 优先级」排（main → strong → pre → terminal → post → no）。

**筛选交互**：
- 行业多选：复选框，默认全选
- 阶段过滤：点图例色块 = 只显示该 phase 的行业行
- 时间窗口：双滑块选择起止日期

**详情面板**（点击行展开）：
- 该行业过去一年的所有 phase 转换（表格：起止日期/phase/振幅/天数/RS 范围）
- 主升参数卡片（amp/days/score）
- 主导趋势片段（最近一次 main_advance 的起止、距今天数）

**技术栈**：纯 HTML + 内联 JS（与现有 `html_.py` 风格一致），不引第三方库。色带用 `<div>` + 宽度百分比，32 行 × ~144 时点 = 4608 段，DOM 渲染足够流畅。

### 5. 复盘报告 HTML

**文件**：`数据/波浪复盘报告.html`

**整体结构**

```
[标题] 行业波浪信号复盘报告 · 截止 2026-06-01 · 共 X 个信号
[Tab 1] 信号质量统计（按 phase 分组）
[Tab 2] 行业生命周期（逐个行业讲故事）
[Tab 3] 信号明细（可排序/筛选的原始表）
```

#### Tab 1：信号质量统计

按 `phase` 分组，统计 `wave_outcome` 全部行（包含历史回填 + 新发出）：

| phase | 信号数 | hit_main_advance 率 | max_amp_p40 中位数 | max_amp_p40 > 8 率 | RS 后续 20 日均值 |
|-------|--------|---------------------|--------------------|--------------------|--------------------|
| main_advance | ... | ... | ... | ... | ... |
| strong_advance | ... | ... | ... | ... | ... |
| **pre_main** | ... | ... | ... | ... | ... |
| terminal | ... | ... | ... | ... | ... |
| post_main | ... | ... | ... | ... | ... |

**与现有回测报告的差异**：
- 现有 `docs/主升浪算法回测报告.md` 用的是"算法扫描整个 3 年时间窗"产生的 ~672 个滚动信号（虚拟信号）
- 本 Tab 用的是"实际跟踪出来的信号"——某个真实日子，发出了一个 phase 判断，后来真的走出来了
- 两个数字应接近但不会完全相同；这是验证算法在跟踪实践中是否稳定的最佳方式

**附加**：每个 phase 卡片可展开，看最近 10 个该 phase 信号的明细。

#### Tab 2：行业生命周期

每个行业一段叙事（数据驱动 + 模板化文字）：

```
📊 半导体
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
过去 1 年浪段演变：
  2025-08-12 ~ 2025-10-20  pre_main (回撤 45%)
  2025-10-21 ~ 2025-12-15  main_advance ★★★  +18.3RS / 88天
  2025-12-16 ~ 2026-02-10  terminal          +6.1RS / 56天
  2026-02-11 ~ 2026-04-05  post_main         +2.3RS / 53天
  2026-04-06 ~ 至今        strong_advance ★★  +9.5RS / 56天

主升参数：振幅 18.3 / 88天 / 评分 172
当前状态：strong_advance（已运行 56 天，振幅 9.5，距历史主升 80% 还差 4.0）
操作参考：持有 / 距 main_advance 临界，关注能否放量突破
```

**实现**：从 `wave_signal` 表读该行业所有记录，按 `phase` 分组生成段落。文字模板内嵌 7 种 phase → 8 种操作建议。

#### Tab 3：信号明细（辅助）

| 行业 | 日期 | phase | 当日 RS | 10日后RS | 20日后RS | 40日后RS | 最大升幅 | 后续是否主升 |
|------|------|-------|---------|----------|----------|----------|----------|--------------|

可按列排序，可按 phase/行业筛选。导出按钮（生成 CSV 复制到剪贴板）。

### 6. 错误处理

| 场景 | 行为 |
|------|------|
| `as_of_date` 早于数据起点 | `calc_wave_at` 返回 `None`；`wave_signal` 跳过；`wave_outcome` 跳过 |
| 截断后 < 200 采样点 | 同上 |
| 行业在某个 t 全空（数据丢失/新股） | 跳过该 (sector, t)，日志一行 INFO |
| SQLite 锁/写失败 | 重试 3 次，每次间隔 0.5s；最终失败则让 Python 异常向上抛（中断整个流程，避免半成品） |
| `--wave` 第一次运行 | 全量回填；输出进度（每 50 个 (sector, t) 打点） |
| 已有 db 的增量 | `MAX(signal_date) < today` 才补；同日重算覆盖 |
| 行业池变更 | 用 `sector` 列匹配；旧 sector 记录保留（不删，可手动清理） |

### 7. 测试

新建 `脚本/test_wave.py`，使用 `unittest`（与项目零依赖一致）：

1. **`TestCalcWaveAt.test_consistency_with_existing`**
   - 用一份固定 fixture（5 个行业 × 2 年 5日采样）调 `calc_wave_at(latest_date)`
   - 与现有 `html_.py:106-196` 内联算法在最新日期上的输出字段逐一比对
   - 数值字段允许 `abs(diff) < 0.01`，枚举字段要求完全相等

2. **`TestCalcWaveAt.test_truncation_monotonic`**
   - 同一 fixture，依次传 `as_of_date = [6 个月前, 3 个月前, 最新]`
   - 断言：`n_waves` 单调不增（早时点看不到后期浪段）
   - 断言：所有行业在所有合法日期返回非 None

3. **`TestWaveArchive.test_upsert`**
   - 写入 2 个 (sector, date) → 查询得到 2 行
   - 同 (sector, date) 再次写入不同 phase → phase 更新
   - 清理 fixture（用临时 db 路径）

4. **`TestWaveOutcome.test_calculation`**
   - fixture 中人为设定一段「pre_main 后续 20 日 RS +8」的轨迹
   - 跑回填 → 查询 `wave_outcome` → 断言 `max_amp_p20 > 7.5`、`hit_main_advance = 1`

5. **`TestTimelineHTML.test_smoke`**
   - 调一次 `gen_wave_timeline_html(db_path)` → 断言返回字符串含 `行业` 标题、各 phase 颜色 hex

6. **`TestReviewHTML.test_smoke`**
   - 调一次 `gen_wave_review_html(db_path)` → 断言含 "信号质量统计"、"行业生命周期"、"信号明细" 三个 tab 标识

**测试命令**：`python3 -m unittest 脚本.test_wave -v`

### 8. 命令行集成

`脚本/行业轮动RRS.py` 改动：

```python
def main():
    ...
    make_html = "--html" in sys.argv
    make_wave = "--wave" in sys.argv   # 新增
    ...
    if make_wave:
        from wave_archive import backfill, ARCHIVE_DB
        from wave_timeline_html import gen as gen_timeline
        from wave_review_html import gen as gen_review
        print("  回填波浪信号档案...", file=sys.stderr)
        backfill(ARCHIVE_DB, stock_data, market, pool)
        print("  生成时间轴 HTML...", file=sys.stderr)
        gen_timeline(ARCHIVE_DB, update_date)
        print("  生成复盘报告 HTML...", file=sys.stderr)
        gen_review(ARCHIVE_DB, update_date)
```

**用法**：

```bash
python3 脚本/行业轮动RRS.py --wave       # 回填+生成两个新 HTML（首次约 1-2 分钟）
python3 脚本/行业轮动RRS.py --html --wave # 同时生成主 HTML + 两个新 HTML
```

### 9. 文档更新

- `README.md` 增加一节「行业波浪阶段跟踪与复盘」，说明：
  - 三个新文件位置（`数据/波浪阶段时间轴.html`、`数据/波浪复盘报告.html`、`数据/wave_archive.db`）
  - 数据库 schema 概览
  - 回填/增量策略
  - 两个新 HTML 的 Tab 用法

## 提交策略

每个模块独立 commit，方便回退：

1. `calc_wave_at` 公共函数 + 测试
2. `wave_archive.py` + 测试
3. `wave_timeline_html.py` + 测试
4. `wave_review_html.py` + 测试
5. 主入口 `--wave` 集成
6. README + 文档

## 风险与权衡

| 风险 | 缓解 |
|------|------|
| 一次性回填 1 年数据耗时长（1-2 分钟） | 仅第一次慢；后续增量 < 5 秒 |
| outcome 计算需要重跑部分算法查 hit_main_advance | 在 outcome 计算时复用 `calc_wave_at`，避免重复实现 |
| 行业生命周期叙事模板可能不自然 | 先做最简版（结构化文本），用户可后续手动润色 |
| 32 行业 × 144 时点 = 4608 行，HTML DOM 略大 | 用 `<div>` 宽度百分比而非 SVG；可接受 |

## 后续不在范围

- 邮件/微信/钉钉信号通知
- 多策略对比（如对比 8 期/12 期/16 期 TRAJECTORY_INTERVAL 对回测的影响）
- 跨市场（港股/美股）行业轮动
- AI 解读（用 LLM 对每个 phase 信号生成自然语言解读）
