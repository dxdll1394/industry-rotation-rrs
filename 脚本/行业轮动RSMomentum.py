#!/usr/bin/env python3
"""
行业轮动相对强弱(RRS)四象限图 v1.0
======================================
维度:
  X轴 = 相对强弱 RSRatio (行业价格 / 大盘价格, 63个交易日≈3个月)
  Y轴 = 相对动量 RSMomentum (RSRatio的21日变化率 ≈1个月)

四个象限:
  L Leading  (RS↑ MO↑)   - 强势领导板块
  I Improving (RS↓ MO↑)  - 正在改善/转强
  W Weakening (RS↑ MO↓)  - 开始走弱
  L Lagging  (RS↓ MO↓)   - 持续落后/低迷

数据源: akshare stock_value_em() 缓存 (datacenter-web.eastmoney.com)
市场基准: 上证指数 sh000001
"""
import json, sys, time
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent.parent
CACHE_DIR = Path.home() / ".openclaw" / "workspace" / "自选股" / "大周期股池" / "数据" / "估值缓存"
POOL_FILE = Path.home() / ".openclaw" / "workspace" / "自选股" / "大周期股池" / "数据" / "大周期股池.json"
MARKET_DB = Path.home() / ".openclaw" / "workspace" / "自选股" / "数据" / "市场数据.db"
CLOSE_CACHE_DIR = BASE / "数据/收盘价缓存"

SECTORS_ORDER = ["石油石化","煤炭","有色金属","钢铁","化工","建材","工程机械","航运港口","金融","农牧"]

# -- RS 参数 --
CLOSE_CACHE_DIR = Path.home() / ".openclaw" / "workspace" / "自选股" / "行业轮动RRS" / "数据/收盘价缓存"
CLOSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

RS_LOOKBACK = 63   # 3个月 ≈ 63个交易日
MO_LOOKBACK = 21   # 1个月 ≈ 21个交易日

def load_pool():
    with open(POOL_FILE) as f:
        sectors = json.load(f)
    stocks = []
    for sector, items in sectors.items():
        for item in items:
            stocks.append({**item, "sector": sector})
    return stocks

def load_cache(code):
    p = CACHE_DIR / f"{code}.json"
    if p.exists():
        return json.loads(p.read_text())
    return None

def load_market_data():
    """加载上证指数数据"""
    import sqlite3
    conn = sqlite3.connect(str(MARKET_DB))
    rows = conn.execute(
        "SELECT date, close FROM index_daily WHERE symbol = 'sh000001' ORDER BY date"
    ).fetchall()
    conn.close()
    dates = [r[0] for r in rows]
    closes = [float(r[1]) for r in rows]
    idx = pd.to_datetime(dates)
    return pd.Series(closes, index=idx)

def get_close_prices(stock_code):
    """从缓存中提取每日收盘价"""
    cache = load_cache(stock_code)
    if not cache:
        return None
    dates = [r["date"] for r in cache]
    # Close price isn't in PE/PB cache - use stock_value_em instead
    return None

def get_close_cache_path(code):
    return CLOSE_CACHE_DIR / f"{code}.parquet"

def save_close_cache(code, df):
    path = get_close_cache_path(code)
    df.to_parquet(path)

def load_close_cache(code):
    path = get_close_cache_path(code)
    if path.exists():
        return pd.read_parquet(path)
    return None

def fetch_stock_close_data(use_cache=True):
    """用 stock_value_em 获取所有股票的最新收盘价数据"""
    import akshare as ak
    stocks = load_pool()
    all_data = {}
    total = len(stocks)
    done = 0
    for s in stocks:
        code = s["code"]
        if use_cache:
            cached = load_close_cache(code)
            if cached is not None:
                all_data[code] = cached
                done += 1
                continue
        try:
            df = ak.stock_value_em(symbol=code)
            if df is not None and not df.empty:
                df = df.rename(columns={"数据日期": "date", "当日收盘价": "close", "当日涨跌幅": "change_pct"})
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")[["close", "change_pct"]]
                all_data[code] = df
                save_close_cache(code, df)
            done += 1
        except Exception as e:
            print(f"  ⚠️ {s['name']}({code}): {e}", file=sys.stderr)
            done += 1
        if done % 10 == 0:
            print(f"  [{done}/{total}]", file=sys.stderr)
        time.sleep(0.3)
    return all_data

def calc_sector_rs(data_dict, market_data, stocks_info):
    """
    计算各行业的RS Ratio和RS Momentum
    """

    # 1. 收集所有股票价格序列
    price_data = {}
    sectors = defaultdict(list)

    for s in load_pool():
        code = s["code"]
        name = s["name"]
        sector = s["sector"]
        sectors[sector].append(code)

        if code in data_dict:
            price_data[code] = data_dict[code]["close"]
        else:
            # 从缓存尝试
            cache = load_cache(code)
            if cache:
                dates = [r["date"] for r in cache]
                # PE/PB缓存没有收盘价
                pass

    # 2. 计算每只股票的相对价格 (stock / market)
    rs_results = {}
    for sector in SECTORS_ORDER:
        codes = sectors.get(sector, [])
        if not codes:
            continue

        # 找到该行业有数据的股票
        valid_codes = [c for c in codes if c in price_data and len(price_data[c]) > RS_LOOKBACK + MO_LOOKBACK]
        if not valid_codes:
            continue

        # 对齐日期到市场数据
        all_returns = []
        for code in valid_codes:
            stock_series = price_data[code]
            common_dates = stock_series.index.intersection(market_data.index)
            if len(common_dates) < RS_LOOKBACK + MO_LOOKBACK:
                continue

            # 计算相对价格 = 股票价格 / 上证指数
            rel_price = stock_series[common_dates] / market_data[common_dates]
            all_returns.append(rel_price)

        if not all_returns:
            continue

        # 行业平均相对价格（等权）
        sector_rel = pd.concat(all_returns, axis=1).mean(axis=1)
        rs_results[sector] = sector_rel

    return rs_results

def calc_rrs(rel_price_series):
    """
    计算RRS (Relative Rotation Graph) 指标
    RS_Ratio = 相对价格线，用63日均线平滑
    RS_Momentum = RS_Ratio的21日变化率
    """
    rs_ratio = rel_price_series.rolling(window=RS_LOOKBACK).mean()
    # 转换成百分比: (当前值 / N天前 - 1) * 100
    rs_momentum = rs_ratio.pct_change(periods=MO_LOOKBACK) * 100
    # RS_Ratio也转换成偏离度: (当前 / 均值 - 1) * 100
    rs_ratio_val = (rel_price_series / rs_ratio - 1) * 100

    return rs_ratio_val, rs_momentum

def plot_rrg(rs_results, update_date):
    """生成行业轮动RRS四象限图"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    plt.rcParams["font.family"] = "Heiti TC"
    plt.rcParams["axes.unicode_minus"] = False

    # 计算各行业当前值
    sector_points = {}
    for sector, rel_price in rs_results.items():
        rs_ratio, rs_momentum = calc_rrs(rel_price)
        if len(rs_ratio.dropna()) == 0 or len(rs_momentum.dropna()) == 0:
            continue
        latest_rr = rs_ratio.iloc[-1]
        latest_mo = rs_momentum.iloc[-1]
        if pd.isna(latest_rr) or pd.isna(latest_mo):
            continue
        sector_points[sector] = {
            "x": float(latest_rr),
            "y": float(latest_mo),
            "stock_count": len([stk for stk in load_pool() if stk["sector"] == sector])
        }

    # -- 绘图 --
    fig, ax = plt.subplots(figsize=(14, 12))
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    # 四分界线
    ax.axhline(y=0, color="#999999", linestyle="--", linewidth=1.2, alpha=0.6)
    ax.axvline(x=0, color="#999999", linestyle="--", linewidth=1.2, alpha=0.6)

    # 象限背景
    ax.axhspan(0, 100, xmin=0.5, xmax=1, facecolor="#E3F2FD", alpha=0.15)    # Leading
    ax.axhspan(0, 100, xmin=0, xmax=0.5, facecolor="#E8F5E9", alpha=0.15)     # Improving
    ax.axhspan(-100, 0, xmin=0, xmax=0.5, facecolor="#FFEBEE", alpha=0.15)    # Weakening
    ax.axhspan(-100, 0, xmin=0.5, xmax=1, facecolor="#FFF3E0", alpha=0.15)   # Lagging

    # 象限标签
    ax.text(40, 85, "L Leading\n强势领导\nRS↑ 动量↑",
            fontsize=11, color="#1565C0", alpha=0.7, ha="center", va="center")
    ax.text(-40, 85, "I Improving\n转强改善\nRS↓ 动量↑",
            fontsize=11, color="#2E7D32", alpha=0.7, ha="center", va="center")
    ax.text(-40, -85, "W Weakening\n开始走弱\nRS↑ 动量↓",
            fontsize=11, color="#C62828", alpha=0.7, ha="center", va="center")
    ax.text(40, -85, "L Lagging\n持续低迷\nRS↓ 动量↓",
            fontsize=11, color="#E65100", alpha=0.7, ha="center", va="center")

    # 气泡图
    colors = {
        "石油石化": "#4A90D9", "煤炭": "#333333", "有色金属": "#D4A017",
        "钢铁": "#8B4513", "化工": "#6B8E23", "建材": "#CD853F",
        "工程机械": "#4682B4", "航运港口": "#2E8B57", "金融": "#8B0000", "农牧": "#228B22",
    }

    for sector in SECTORS_ORDER:
        if sector not in sector_points:
            continue
        pt = sector_points[sector]
        x, y = pt["x"], pt["y"]
        size = max(300, pt["stock_count"] * 60)
        color = colors.get(sector, "#666")
        ax.scatter(x, y, s=size, c=color, alpha=0.7, edgecolors="white", linewidth=2, zorder=5)
        ax.annotate(f"{sector}\n({pt['stock_count']}只)",
                    (x, y), xytext=(3, 3), textcoords="offset points",
                    fontsize=10, fontweight="bold", color=color, zorder=6)

    # 坐标轴
    margin = 15
    max_x = max(abs(p["x"]) for p in sector_points.values()) + margin
    max_y = max(abs(p["y"]) for p in sector_points.values()) + margin
    ax.set_xlim(-max_x, max_x)
    ax.set_ylim(-max_y, max_y)
    ax.set_xlabel("RS Ratio \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u25b6\n相对强弱 (63日相对大盘)", fontsize=12, fontweight="bold", color="#333")
    ax.set_ylabel("RS Momentum \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u25b6\n相对动量 (21日变化)", fontsize=12, fontweight="bold", color="#333")
    ax.set_title(f"大周期股池 行业轮动 RRS 四象限图\n{update_date}  |  RSRatio(63d) vs RSMomentum(21d)",
                 fontsize=14, fontweight="bold", color="#1a1a2e", pad=18)

    ax.grid(True, alpha=0.3, linestyle=":", color="#888")
    ax.tick_params(labelsize=11)

    # 图例说明
    legend_text = (
        f"基准: 上证指数  |  气泡大小=成分股数\n"
        f"RS Ratio = 行业价 / 上证价 (63日均线平滑)\n"
        f"RS Momentum = RSRatio的21日变化率"
    )
    ax.text(0.98, 0.02, legend_text, transform=ax.transAxes,
            fontsize=9, color="#888", ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.8))

    plt.tight_layout()
    out_path = BASE / "数据/行业轮动RRS四象限图.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"✅ PNG: {out_path}", file=sys.stderr)
    return out_path

def plot_rrg_html(rs_results, update_date):
    """生成交互式HTML版本"""
    import json as _json

    colors = {
        "石油石化": "#4A90D9", "煤炭": "#333333", "有色金属": "#D4A017",
        "钢铁": "#8B4513", "化工": "#6B8E23", "建材": "#CD853F",
        "工程机械": "#4682B4", "航运港口": "#2E8B57", "金融": "#8B0000", "农牧": "#228B22",
    }

    series_data = []
    for sector in SECTORS_ORDER:
        if sector not in rs_results:
            continue
        rel_price = rs_results[sector]
        rs_ratio, rs_momentum = calc_rrs(rel_price)
        latest_rr = rs_ratio.iloc[-1] if len(rs_ratio.dropna()) > 0 else None
        latest_mo = rs_momentum.iloc[-1] if len(rs_momentum.dropna()) > 0 else None
        if latest_rr is None or latest_mo is None or pd.isna(latest_rr) or pd.isna(latest_mo):
            continue
        count = len([stk for stk in load_pool() if stk["sector"] == sector])
        series_data.append({
            "name": sector,
            "value": [round(latest_rr, 2), round(latest_mo, 2), count, colors.get(sector, "#666")],
            "symbolSize": 18 + count * 2,
        })

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>行业轮动RRS四象限图</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #f5f5f5; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 22px; color: #1a1a2e; }}
  .meta {{ color: #888; font-size: 13px; margin: 6px 0 14px; }}
  #chart {{ width: 100%; height: 800px; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 16px 0; font-size: 12px; }}
  .legend-item {{ padding: 4px 10px; border-radius: 4px; background: #fff; }}
  .footer {{ text-align: center; color: #aaa; font-size: 11px; margin: 16px 0; }}
</style>
</head>
<body>
<div class="container">
  <h1>行业轮动 RRS 四象限图</h1>
  <div class="meta">{update_date} | RS Ratio(63d) vs RS Momentum(21d) | 基准: 上证指数</div>
  <div id="chart"></div>
  <div class="legend">
    <span class="legend-item">L Leading 强势领导 &nbsp;(RS↑ MO↑)</span>
    <span class="legend-item">I Improving 转强改善 &nbsp;(RS↓ MO↑)</span>
    <span class="legend-item">W Weakening 开始走弱 &nbsp;(RS↑ MO↓)</span>
    <span class="legend-item">L Lagging 持续低迷 &nbsp;(RS↓ MO↓)</span>
  </div>
  <div class="footer">数据源: 东方财富 | RS Ratio = 行业价/基准价(63日均线) | RS Momentum = RSRatio的21日变化率</div>
</div>
<script>
const chart = echarts.init(document.getElementById('chart'));
const option = {{
  tooltip: {{
    formatter: function(p) {{
      if (!p.value) return '';
      const [rs, mo, cnt] = p.value;
      const quad = rs >= 0 ? (mo >= 0 ? 'Leading' : 'Weakening') : (mo >= 0 ? 'Improving' : 'Lagging');
      return `<strong>${{p.name}}</strong><br/>
              RS Ratio: ${{rs.toFixed(1)}}<br/>
              RS Momentum: ${{mo.toFixed(1)}}<br/>
              象限: ${{quad}}`;
    }}
  }},
  xAxis: {{
    name: 'RS Ratio (63d) → 相对大盘走强',
    nameLocation: 'center', nameGap: 40,
    splitLine: {{ show: true, lineStyle: {{ type: 'dashed', color: '#ccc' }} }},
  }},
  yAxis: {{
    name: 'RS Momentum (21d) → 动量向上',
    nameLocation: 'center', nameGap: 45,
    splitLine: {{ show: true, lineStyle: {{ type: 'dashed', color: '#ccc' }} }},
  }},
  series: [{{
    type: 'scatter',
    data: {_json.dumps(series_data, ensure_ascii=False)},
    itemStyle: {{ opacity: 0.8, borderColor: '#fff', borderWidth: 2 }},
    label: {{
      show: true, formatter: p => p.name,
      fontSize: 12, fontWeight: 'bold', position: 'right',
    }},
    markArea: {{
      silent: true,
      data: [
        [{{ xAxis: 0, yAxis: 0 }}, {{ xAxis: 999, yAxis: 999, itemStyle: {{ color: '#E3F2FD', opacity: 0.2 }} }}],
        [{{ xAxis: -999, yAxis: 0 }}, {{ xAxis: 0, yAxis: 999, itemStyle: {{ color: '#E8F5E9', opacity: 0.2 }} }}],
        [{{ xAxis: -999, yAxis: -999 }}, {{ xAxis: 0, yAxis: 0, itemStyle: {{ color: '#FFEBEE', opacity: 0.2 }} }}],
        [{{ xAxis: 0, yAxis: -999 }}, {{ xAxis: 999, yAxis: 0, itemStyle: {{ color: '#FFF3E0', opacity: 0.2 }} }}],
      ]
    }},
  }}],
  grid: {{ top: 60, bottom: 60, left: 70, right: 50 }},
}};
chart.setOption(option);
window.addEventListener('resize', () => chart.resize());
</script>
</body>
</html>"""
    out_path = BASE / "数据/行业轮动RRS四象限图.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"✅ HTML: {out_path}", file=sys.stderr)

def main():
    use_cache = "--read" in sys.argv or "--force" not in sys.argv
    force = "--force" in sys.argv
    make_html = "--html" in sys.argv

    if force:
        use_cache = False

    print("📡 获取股票收盘价数据 (stock_value_em)...", file=sys.stderr)

    # 1. 获取市场基准数据
    market = load_market_data()
    print(f"  上证指数: {len(market)} 天数据 ({market.index[0].date()}~{market.index[-1].date()})", file=sys.stderr)

    # 2. 获取个股数据
    stock_data = fetch_stock_close_data(use_cache=use_cache)
    print(f"  {len(stock_data)} 只股票数据加载完成", file=sys.stderr)

    # 3. 计算行业RRS
    rs_results = calc_sector_rs(stock_data, market, load_pool())
    print(f"  {len(rs_results)} 个行业计算完成\n", file=sys.stderr)

    # 4. 终端输出
    print(f"{'行业':8s} {'RS_Ratio':>9s} {'RS_Mo':>7s} {'象限':>12s}")
    print("  " + "-" * 42)
    for sector in SECTORS_ORDER:
        if sector not in rs_results:
            continue
        rel_price = rs_results[sector]
        rr, mo = calc_rrs(rel_price)
        x = rr.iloc[-1] if len(rr.dropna()) > 0 else None
        y = mo.iloc[-1] if len(mo.dropna()) > 0 else None
        if x is None or y is None or pd.isna(x) or pd.isna(y):
            continue
        if x >= 0 and y >= 0:
            quad = "Leading"
        elif x < 0 and y >= 0:
            quad = "Improving"
        elif x >= 0 and y < 0:
            quad = "Weakening"
        else:
            quad = "Lagging"
        print(f"{sector:8s} {x:9.2f} {y:7.2f} {quad:>12s}")

    # 5. 生成图表
    plot_rrg(rs_results, datetime.now().strftime("%Y-%m-%d"))
    if make_html:
        plot_rrg_html(rs_results, datetime.now().strftime("%Y-%m-%d"))

if __name__ == "__main__":
    main()
