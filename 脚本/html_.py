import sys, json

from config import DATA_DIR, TRAJECTORY_INTERVAL, HISTORICAL_DATES, COLORS
from calc import get_trajectory, get_quad


def gen_html(trajectories, update_date, pool=None, stock_rs=None, stock_traj=None):
    stock_rs = stock_rs or {}
    
    # Load ETF data
    import pandas as pd, numpy as np
    from pathlib import Path
    INDUSTRY_ETF = {
        "交通运输": "159729", "传媒": "512980", "光伏电池": "515790",
        "军工": "512660", "农牧": "159616", "化工": "516020",
        "医药生物": "512010", "半导体": "512480", "家电": "159996",
        "建材": "159745", "房地产": "512200", "有色金属": "512400",
        "煤炭": "515220", "环保": "512580", "电力": "159611",
        "电子": "159997", "通信": "515880", "计算机": "512720",
        "金融": "510230", "钢铁": "515210", "锂电": "561160",
        "食品饮料": "515170", "建筑": "516950", "汽车": "516110",
    }
    etf_rs_cache = {}
    for sector, code in INDUSTRY_ETF.items():
        cache_file = DATA_DIR / "收盘价缓存" / f"etf_{code}.parquet"
        if cache_file.exists():
            import pandas as pd
            df = pd.read_parquet(cache_file)
            if "close" in df.columns:
                s = df["close"].dropna().copy()
                s.index = pd.to_datetime(s.index)
                etf_rs_cache[code] = s
    
    from data import load_market_data
    etf_market = load_market_data()
    
    sectors_data = []
    ci = 0
    actual_latest_date = None
    for sector in sorted(trajectories.keys()):
        st = trajectories[sector]
        traj, lx, ly, hist_nodes = get_trajectory(st["rs_ratio"], st["rs_momentum"], TRAJECTORY_INTERVAL)
        if traj is None or lx is None:
            continue
        color = COLORS[ci % len(COLORS)]
        ci += 1
        if actual_latest_date is None and traj:
            actual_latest_date = traj[-1]["date"]

        hist_map = {}
        for hn in hist_nodes:
            hist_map[hn["date"]] = [round(hn["x"], 2), round(hn["y"], 2)]

        trajectory_path = [{"value": [round(p["x"], 2), round(p["y"], 2)], "date": p["date"]} for p in traj]
        latest_val = [round(lx, 2), round(ly, 2)]
        arrows = [[trajectory_path[i]["value"], trajectory_path[i + 1]["value"]] for i in range(len(trajectory_path) - 1)]

        stocks = (pool or {}).get(sector, [])
        stock_list = []
        for s in stocks:
            sr = stock_rs.get(s["code"], {})
            stock_list.append({
                "code": s["code"],
                "name": s["name"],
                "rs_ratio": sr.get("rs_ratio"),
                "rs_momentum": sr.get("rs_momentum"),
                "quad": sr.get("quad"),
            })
        # Compute ETF RS for this sector
        etf_latest_rs = None
        etf_trajectory = []
        etf_code = INDUSTRY_ETF.get(sector, "")
        if etf_code and etf_code in etf_rs_cache:
            etf_s = etf_rs_cache[etf_code]
            common = etf_s.index.intersection(etf_market.index)
            if len(common) > 200:
                etf_rel = etf_s[common] / etf_market[common]
                rr = etf_rel.rolling(window=63).mean()
                etf_rs_val = ((etf_rel / rr - 1) * 100).dropna()
                if len(etf_rs_val) > 0:
                    import numpy as np
                    etf_latest_rs = round(float(etf_rs_val.iloc[-1]), 2)
                    # Compute ETF trajectory for trend direction
                    etf_traj, _, _, _ = get_trajectory(etf_rs_val, etf_rs_val, TRAJECTORY_INTERVAL)
                    if etf_traj:
                        etf_trajectory = [{"value": [round(p["x"], 2), round(p["y"], 2)], "date": p["date"]} for p in etf_traj]

        sectors_data.append({
            "name": sector,
            "color": color,
            "trajectory": trajectory_path,
            "arrows": arrows,
            "latest": latest_val,
            "stockCount": st["stock_count"],
            "stockList": stock_list,
            "latestDate": actual_latest_date[5:] if actual_latest_date else "",
            "histMap": hist_map,
            "quad": get_quad(lx, ly),
            "etfCode": INDUSTRY_ETF.get(sector, ""),
            "etfRS": etf_latest_rs,
            "etfTrajectory": etf_trajectory,
        })

    hist_dates = HISTORICAL_DATES[:]
    hist_series_list = []
    for d in hist_dates:
        items = []
        for sd in sectors_data:
            if d in sd.get("histMap", {}):
                items.append({
                    "name": sd["name"],
                    "value": [sd["histMap"][d][0], sd["histMap"][d][1]],
                    "itemStyle": {"color": sd["color"]},
                })
        hist_series_list.append({"date": d, "items": items})

    sectors_json = json.dumps(sectors_data, ensure_ascii=False)
    hist_series_json = json.dumps(hist_series_list, ensure_ascii=False)
    hist_dates_json = json.dumps(hist_dates, ensure_ascii=False)
    stock_traj_json = json.dumps(stock_traj or {}, ensure_ascii=False)
    snapshot_dates = sorted(set(p["date"] for sd in sectors_data for p in sd["trajectory"]))
    snapshot_dates_json = json.dumps(snapshot_dates, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>行业轮动RRS轨迹图</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#f5f5f5; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }}
  .container {{ max-width:1300px; margin:0 auto; padding:20px; }}
  h1 {{ font-size:20px; color:#1a1a2e; }}
  .meta {{ color:#888; font-size:12px; margin:4px 0 12px; }}
  #chart {{ width:100%; height:900px; background:#fff; border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,0.08); }}
  .controls {{ text-align:center; margin:8px 0; font-size:12px; }}
  .controls button {{ background:#1a1a2e; color:#fff; border:none; padding:4px 14px; border-radius:4px; cursor:pointer; font-size:11px; }}
  .controls button:hover {{ background:#e94560; }}
  .legend {{ display:flex; flex-wrap:wrap; gap:4px; margin:8px 0; font-size:11px; }}
  .legend-item {{ padding:2px 8px; border-radius:3px; background:#fff; font-size:11px; }}
  .date-marker {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:2px; }}
  .footer {{ text-align:center; color:#aaa; font-size:10px; margin:8px 0; }}
  .modal-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,0.3); z-index:999; }}
  .modal {{ display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:#fff; border-radius:10px; padding:20px 24px; min-width:300px; max-width:420px; max-height:80vh; overflow-y:auto; box-shadow:0 4px 20px rgba(0,0,0,0.2); z-index:1000; }}
  .modal h3 {{ margin:0 0 12px; font-size:16px; }}
  .modal .close {{ float:right; cursor:pointer; font-size:18px; color:#999; border:none; background:none; }}
  .modal .close:hover {{ color:#333; }}
  .modal table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  .modal td {{ padding:4px 6px; border-bottom:1px solid #eee; }}
  .modal td:first-child {{ color:#888; width:80px; }}
  .modal .quad-badge {{ display:inline-block; padding:1px 8px; border-radius:3px; font-size:11px; color:#fff; margin-left:8px; }}
  .tabs {{ text-align:center; margin:0 0 10px; }}
  .tabs button {{ background:#e0e0e0; color:#333; border:none; padding:6px 18px; border-radius:4px 4px 0 0; cursor:pointer; font-size:12px; margin:0 2px; }}
  .tabs button.active {{ background:#fff; color:#1a1a2e; font-weight:bold; box-shadow:0 -1px 3px rgba(0,0,0,0.06); }}
  .color-sq {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:2px; vertical-align:middle; }}
  #trendTable {{ display:none; }}
  #trendTable .wrap {{ overflow-x:auto; background:#fff; border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,0.08); padding:12px; }}
  #trendTable table {{ border-collapse:collapse; font-size:11px; white-space:nowrap; }}
  #trendTable th {{ position:sticky; top:0; background:#f8f9fa; padding:4px 6px; border:1px solid #eee; text-align:center; font-weight:600; }}
  #trendTable td {{ padding:3px 5px; border:1px solid #eee; text-align:center; }}
  #trendTable .sector-name {{ text-align:left; font-weight:500; position:sticky; left:0; background:#fff; z-index:1; }}
  #trendTable .q-L {{ color:#1565C0; font-weight:bold; }}
  #trendTable .q-I {{ color:#2E7D32; font-weight:bold; }}
  #trendTable .q-W {{ color:#E65100; font-weight:bold; }}
  #trendTable .q-G {{ color:#999; }}
  #trendTable .chg-up {{ color:#d32f2f; }}
  #trendTable .chg-down {{ color:#2E7D32; }}
  #trendTable .chg-sign {{ font-size:9px; }}
  #trendTable .exp-btn {{ cursor:pointer; font-size:10px; color:#999; user-select:none; padding:0 4px; }}
  #trendTable .exp-btn:hover {{ color:#333; }}
  #trendTable [data-go-stock]:hover {{ color:#1565C0; text-decoration:underline; }}
  #trendTable .stock-row td {{ background:#fafafa; padding:2px 10px; font-size:10px; text-align:left; }}
  #trendTable .stock-row .s-code {{ color:#999; }}
  #trendTable .stock-row .s-name {{ color:#333; }}
  #trendTable .stock-row .s-rs {{ font-size:9px; margin-left:8px; }}
  #stockTrendTable {{ display:none; }}
  #stockTrendTable .wrap {{ background:#fff; border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,0.08); padding:12px; }}
  #stockTrendTable table {{ border-collapse:collapse; font-size:10px; white-space:nowrap; width:100%; }}
  #stockTrendTable th {{ position:sticky; top:0; background:#f8f9fa; padding:3px 4px; border:1px solid #eee; text-align:center; font-weight:600; font-size:10px; }}
  #stockTrendTable td {{ padding:2px 4px; border:1px solid #eee; text-align:center; font-size:10px; }}
  #stockTrendTable .st-name {{ text-align:left; font-weight:500; position:sticky; left:0; z-index:1; background:inherit; }}
  #stockTrendTable .st-code {{ color:#999; font-weight:400; }}
  #stockTrendTable .st-row-q-L {{ background:#E3F2FD; }}
  #stockTrendTable .st-row-q-I {{ background:#E8F5E9; }}
  #stockTrendTable .st-row-q-W {{ background:#FFF3E0; }}
  #stockTrendTable .st-row-q-G {{ background:#f8f8f8; }}
  .snap-bar {{ text-align:center; margin:6px 0; font-size:12px; display:flex; align-items:center; justify-content:center; gap:6px; flex-wrap:wrap; }}
  .snap-bar label {{ font-size:11px; color:#888; cursor:pointer; }}
  .snap-bar input[type="range"] {{ width:160px; vertical-align:middle; }}
  .snap-date {{ font-size:12px; font-weight:bold; color:#1a1a2e; min-width:80px; display:inline-block; text-align:center; }}
  .snap-bar .snap-btn {{ background:#1a1a2e; color:#fff; border:none; padding:2px 8px; border-radius:3px; cursor:pointer; font-size:10px; }}
  .snap-bar .snap-btn:hover {{ background:#e94560; }}
</style>
</head>
<body>
<div class="container">
  <div class="tabs">
    <button id="tabChart" class="active" onclick="switchTab('chart')">📊 四象限图</button>
    <button id="tabTrend" onclick="switchTab('trend')">📈 趋势变化表</button>
    <button id="tabStockTrend" onclick="switchTab('stockTrend')">📋 个股趋势表</button>
  </div>
  <h1>行业轮动 RRS 轨迹图</h1>
  <div class="meta">{update_date} | RS Ratio(63d) vs RS Momentum(21d) | 基准: 上证指数 | {len(sectors_data)}个行业</div>
  <div id="chart"></div>
  <div class="controls">
    <button onclick="toggleLines()">切换轨迹线显隐</button>
    <button onclick="toggleMode()" id="modeBtn">单行业模式</button>
    <button onclick="zoomChart(0.7)">放大</button>
    <button onclick="zoomChart(1.4)">缩小</button>
    <button onclick="hideAll()" style="margin-left:6px;">隐藏全部</button>
    <button onclick="chart.dispatchAction({{type:'legendAllSelect'}});setTimeout(updateArrows,50)">显示全部</button>
    <span style="margin-left:10px;">
      <button onclick="filterQuad('L')" style="background:#1565C0;">L</button>
      <button onclick="filterQuad('I')" style="background:#2E7D32;">I</button>
      <button onclick="filterQuad('W')" style="background:#E65100;">W</button>
      <button onclick="filterQuad('G')" style="background:#999;">G</button>
    </span>
    <span style="margin-left:12px;">
      <span class="date-marker" style="background:#666;"></span>{hist_dates[0][5:]}
      <span class="date-marker" style="background:#999;width:12px;height:12px;"></span>{hist_dates[1][5:]}
      <span class="date-marker" style="background:#999;width:12px;height:12px;"></span>{hist_dates[2][5:]}
      <span class="date-marker" style="background:#222;width:14px;height:14px;"></span>当前
    </span>
  </div>
  <div class="snap-bar">
    <span style="font-size:11px;color:#888">⏱ 快照</span>
    <input type="range" id="snapSlider" min="0" max="0" value="0" step="1" oninput="onSnapPreview(this)" onchange="onSnapCommit(this)">
    <span class="snap-date" id="snapDateLabel">关闭</span>
    <label><input type="checkbox" id="compareCheck" onchange="onCompareToggle()"> 对比当前</label>
    <button class="snap-btn" onclick="clearSnapshot()">✕ 重置</button>
  </div>
  <div class="legend">
    <span class="legend-item">[L] Leading 强势</span>
    <span class="legend-item">[I] Improving 改善</span>
    <span class="legend-item">[W] Weakening 走弱</span>
    <span class="legend-item">[G] Lagging 低迷</span>
  </div>
   <div class="footer">数据:东方财富 个股等权聚合 | 每周六更新 | 方块={hist_dates[0][5:]} 菱形={hist_dates[1][5:]},{hist_dates[2][5:]} 圆点=当前 | 点击圆点查看成分股</div>
</div>
<div id="trendTable">
  <div class="wrap" id="trendWrap"></div>
</div>
<div id="stockTrendTable">
  <div class="wrap">
    <div style="margin-bottom:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <input id="stockSearch" placeholder="搜索股票名称/代码..." oninput="buildStockTrendTable()" style="padding:4px 8px;border:1px solid #ddd;border-radius:4px;font-size:12px;width:200px">
      <select id="stockSectorFilter" onchange="buildStockTrendTable()" style="padding:3px 6px;border:1px solid #ddd;border-radius:4px;font-size:11px">
        <option value="">全部行业</option>
      </select>
      <span style="font-size:11px;color:#888">象限:</span>
      <button onclick="stockQuadFilter='';buildStockTrendTable()" style="padding:2px 10px;border:1px solid #ddd;border-radius:3px;cursor:pointer;font-size:11px;background:#fff">全部</button>
      <button onclick="stockQuadFilter='L';buildStockTrendTable()" style="padding:2px 10px;border:1px solid #1565C0;border-radius:3px;cursor:pointer;font-size:11px;color:#1565C0;font-weight:bold">L</button>
      <button onclick="stockQuadFilter='I';buildStockTrendTable()" style="padding:2px 10px;border:1px solid #2E7D32;border-radius:3px;cursor:pointer;font-size:11px;color:#2E7D32;font-weight:bold">I</button>
      <button onclick="stockQuadFilter='W';buildStockTrendTable()" style="padding:2px 10px;border:1px solid #E65100;border-radius:3px;cursor:pointer;font-size:11px;color:#E65100;font-weight:bold">W</button>
      <button onclick="stockQuadFilter='G';buildStockTrendTable()" style="padding:2px 10px;border:1px solid #999;border-radius:3px;cursor:pointer;font-size:11px;color:#999;font-weight:bold">G</button>
      <span id="stockCount" style="font-size:11px;color:#888;margin-left:4px"></span>
    </div>
    <div style="overflow-x:auto" id="stockTrendWrap"></div>
  </div>
</div>
<div class="modal-overlay" id="modalOverlay" onclick="closeModal()"></div>
<div class="modal" id="stockModal">
  <button class="close" onclick="closeModal()">&times;</button>
  <h3 id="modalTitle"></h3>
  <table id="modalTable"></table>
</div>
<script>
const sectorsData = {sectors_json};
const histSeries = {hist_series_json};
const HIST_DATES = {hist_dates_json};
let stockTrajData = {stock_traj_json};
const snapshotDates = {snapshot_dates_json};

const quads = {{'L':'Leading','I':'Improving','W':'Weakening','G':'Lagging'}};

function getQuad(x, y) {{
  if (x >= 0 && y >= 0) return 'L';
  if (x < 0 && y >= 0) return 'I';
  if (x >= 0 && y < 0) return 'W';
  return 'G';
}}

function fmtDate(d) {{
  return d.slice(5).replace('-', '/');
}}

const allX = sectorsData.flatMap(s => [...s.trajectory.map(p => p.value[0]), s.latest[0]]);
const allY = sectorsData.flatMap(s => [...s.trajectory.map(p => p.value[1]), s.latest[1]]);
const xAbs = Math.max(...allX.map(Math.abs), 1);
const yAbs = Math.max(...allY.map(Math.abs), 1);
const xLimit = xAbs * 1.25;
const yLimit = yAbs * 1.25;

const markArea = {{
  silent: true, data: [
    [{{xAxis: 0, yAxis: 0}}, {{xAxis: xLimit, yAxis: yLimit, itemStyle: {{color: '#E3F2FD', opacity: 0.12}}}}],
    [{{xAxis: -xLimit, yAxis: 0}}, {{xAxis: 0, yAxis: yLimit, itemStyle: {{color: '#E8F5E9', opacity: 0.12}}}}],
    [{{xAxis: -xLimit, yAxis: -yLimit}}, {{xAxis: 0, yAxis: 0, itemStyle: {{color: '#FFEBEE', opacity: 0.12}}}}],
    [{{xAxis: 0, yAxis: -yLimit}}, {{xAxis: xLimit, yAxis: 0, itemStyle: {{color: '#FFF3E0', opacity: 0.12}}}}],
  ]
}};

let trendSortCol = -1, trendSortDir = 1, trendSortMode = null;
let expandedSectors = new Set();
let stockTrendSortCol = -1, stockTrendSortDir = -1, stockTrendSortMode = null;
let stockQuadFilter = '';
let stockSectorFilter = '';
let snapshotDate = null;
let compareMode = false;

function setTrendSort(mode) {{
  if (trendSortMode === mode) {{ trendSortDir *= -1; }}
  else {{ trendSortMode = mode; trendSortDir = 1; trendSortCol = -1; }}
  buildTrendTable();
}}

document.getElementById('trendWrap').addEventListener('click', function(e) {{
  const btn = e.target.closest('[data-trend-sort]');
  if (btn) {{ setTrendSort(btn.dataset.trendSort); return; }}
  const dateBtn = e.target.closest('[data-trend-date]');
  if (dateBtn) {{
    const di = parseInt(dateBtn.dataset.trendDate);
    const active = di === trendSortCol && trendSortMode === 'date';
    trendSortCol = di;
    trendSortMode = 'date';
    trendSortDir = active && trendSortDir > 0 ? -1 : 1;
    buildTrendTable();
    return;
  }}
  const exp = e.target.closest('.exp-btn');
  if (exp) {{
    const sector = exp.dataset.sector;
    if (expandedSectors.has(sector)) expandedSectors.delete(sector);
    else expandedSectors.add(sector);
    buildTrendTable();
    return;
  }}
  const go = e.target.closest('[data-go-stock]');
  if (go) {{
    const sector = go.dataset.goStock;
    stockSectorFilter = sector;
    document.getElementById('stockSectorFilter').value = sector;
    switchTab('stockTrend');
  }}
}});

const QC = {{L:'#1565C0',I:'#2E7D32',W:'#E65100',G:'#999'}};
const QN = {{L:'Leading',I:'Improving',W:'Weakening',G:'Lagging'}};

function consecDir(vals) {{
  // vals = [[x,y], ...] ordered latest-first
  if (vals.length < 2) return 0;
  const diff = vals[0][0] - vals[1][0];
  let dir = diff > 0 ? 1 : diff < 0 ? -1 : 0;
  if (dir === 0) return 0;
  let n = 1;
  for (let i = 1; i < vals.length - 1; i++) {{
    const d = vals[i][0] - vals[i+1][0];
    if ((d > 0 && dir > 0) || (d < 0 && dir < 0)) n++;
    else break;
  }}
  return dir * n;
}}

function setTrendSort(mode) {{
  if (trendSortMode === mode) {{ trendSortDir *= -1; }}
  else {{ trendSortMode = mode; trendSortDir = 1; trendSortCol = -1; }}
  buildTrendTable();
}}

function buildTrendTable() {{
  var snap = snapshotDate;
  var allDates = [...new Set(sectorsData.flatMap(function(s) {{ return s.trajectory.map(function(p) {{ return p.date; }}); }}))].sort();
  var dates = (snap ? allDates.filter(function(d) {{ return d <= snap; }}) : allDates).reverse();
  var sorted = [...sectorsData];
  var qOrd = {{L:0, I:1, W:2, G:3}};

  if (trendSortMode === 'name') {{
    sorted.sort(function(a, b) {{ return a.name.localeCompare(b.name) * trendSortDir; }});
  }} else if (trendSortMode === 'rs') {{
    sorted.sort(function(a, b) {{ return (getSectorLatest(a, snap)[0] - getSectorLatest(b, snap)[0]) * trendSortDir; }});
  }} else if (trendSortMode === 'mo') {{
    sorted.sort(function(a, b) {{ return (getSectorLatest(a, snap)[1] - getSectorLatest(b, snap)[1]) * trendSortDir; }});
  }} else if (trendSortMode === 'quad') {{
    sorted.sort(function(a, b) {{ return ((qOrd[snap ? getSnapQuad(a, snap) : a.quad]||9) - (qOrd[snap ? getSnapQuad(b, snap) : b.quad]||9)) * trendSortDir || a.name.localeCompare(b.name); }});
  }} else if (trendSortMode === 'trend') {{
    sorted.sort(function(a, b) {{
      var da = getTrajUpto(a, snap).map(function(p) {{ return p.value; }}).reverse();
      var db = getTrajUpto(b, snap).map(function(p) {{ return p.value; }}).reverse();
      return (consecDir(da) - consecDir(db)) * trendSortDir;
    }});
  }} else if (trendSortMode === 'count') {{
    sorted.sort(function(a, b) {{ return (a.stockCount - b.stockCount) * trendSortDir; }});
  }} else if (trendSortMode === 'date' && trendSortCol >= 0) {{
    var col = trendSortCol;
    sorted.sort(function(a, b) {{
      var va = getTrajUpto(a, snap).find(function(p) {{ return p.date === dates[col]; }})?.value[0] ?? -999;
      var vb = getTrajUpto(b, snap).find(function(p) {{ return p.date === dates[col]; }})?.value[0] ?? -999;
      return (vb - va) * trendSortDir;
    }});
  }} else {{
    sorted.sort(function(a, b) {{ return getSectorLatest(b, snap)[0] - getSectorLatest(a, snap)[0]; }});
  }}

  const nCols = dates.length + 1;
  let html = '<div style="margin-bottom:6px;font-size:10px;display:flex;align-items:center;gap:4px;flex-wrap:wrap">';
  html += '<span style="color:#888;margin-right:4px">排序:</span>';
  const sorts = [['name','名称'],['rs','最新RS'],['mo','最新MO'],['trend','RS趋势'],['quad','象限'],['count','数量']];
  sorts.forEach(([k, label]) => {{
    const active = trendSortMode === k;
    const arrow = active ? (trendSortDir > 0 ? '▲' : '▼') : '';
    html += '<span data-trend-sort="' + k + '" style="cursor:pointer;padding:1px 6px;border-radius:3px;background:' + (active ? '#1a1a2e' : '#e0e0e0') + ';color:' + (active ? '#fff' : '#333') + '">' + label + ' ' + arrow + '</span>';
  }});
  html += '<span style="margin-left:8px">';
  html += '<span class="color-sq" style="background:#1565C0"></span><b style="color:#1565C0">L</b> Leading</span>';
  html += '<span style="margin-right:10px"><span class="color-sq" style="background:#2E7D32"></span><b style="color:#2E7D32">I</b> Improving</span>';
  html += '<span style="margin-right:10px"><span class="color-sq" style="background:#E65100"></span><b style="color:#E65100">W</b> Weakening</span>';
  html += '<span><span class="color-sq" style="background:#999"></span><b style="color:#999">G</b> Lagging</span>';
  html += '<span style="margin-left:12px;color:#aaa;font-size:9px">↑N/↓N = RS连升/连降N期 | 格中↑↓为RS变化 | ↑+L/I=趋势加速 ↓+L/W=减速预警</span>';
  html += '<div style="font-size:9px;color:#bbb;margin-top:2px">RS↑+MO↑=走强加速  RS↑+MO↓=走强减速  RS↓+MO↑=走弱逆转  RS↓+MO↓=双降恶化</div>';
  html += '</div>';
  html += '<table><thead><tr><th class="sector-name">行业 <span style="font-weight:400;font-size:9px;color:#999">ETF</span></th>';
  dates.forEach((d, di) => {{
    const active = di === trendSortCol && trendSortMode === 'date';
    const arrow = active ? (trendSortDir > 0 ? ' ▲' : ' ▼') : '';
    html += '<th data-trend-date="' + di + '" style="cursor:pointer">' + d.slice(5).replace('-','/') + '<br><span style="font-weight:400;font-size:9px">RS/MO' + arrow + '</span></th>';
  }});
  html += '</tr></thead><tbody>';
  sorted.forEach(s => {{
    const map = {{}};
    getTrajUpto(s, snap).forEach(function(p) {{ map[p.date] = p.value; }});
    const exp = expandedSectors.has(s.name);
    const cd = consecDir(getTrajUpto(s, snap).map(function(p) {{ return p.value; }}).reverse());
    const cdHtml = cd > 0 ? '<span style="color:#d32f2f;font-size:10px;font-weight:bold" title="RS连续上升' + cd + '期">↑' + cd + '</span>' : cd < 0 ? '<span style="color:#2E7D32;font-size:10px;font-weight:bold" title="RS连续下降' + Math.abs(cd) + '期">↓' + Math.abs(cd) + '</span>' : '';
    const etfCd = s.etfTrajectory && s.etfTrajectory.length > 1 ? consecDir(s.etfTrajectory.map(p => p.value).reverse()) : 0;
    const etfCdHtml = etfCd !== 0 ? ' <span style="color:#888;font-size:9px">ETF' + (etfCd > 0 ? '<span style="color:#d32f2f">↑' + etfCd + '</span>' : '<span style="color:#2E7D32">↓' + Math.abs(etfCd) + '</span>') + '</span>' : '';
    const etfHtml = s.etfCode ? '<span style="color:#888;font-size:9px;margin-left:4px">' + s.etfCode + '</span>' : '';
    const etfRsHtml = s.etfRS != null ? '<span style="color:#888;font-size:9px;margin-left:4px">ETF:' + s.etfRS.toFixed(1) + '</span>' : '';
    html += '<tr><td class="sector-name q-' + s.quad + '"><span class="exp-btn" data-sector="' + s.name.replace(/"/g, '&quot;') + '">' + (exp ? '−' : '+') + '</span><span data-go-stock="' + s.name.replace(/"/g, '&quot;') + '" style="cursor:pointer">' + s.name + '</span> ' + cdHtml + etfCdHtml + etfHtml + etfRsHtml + '</td>';
    dates.forEach((d, di) => {{
      const v = map[d];
      if (!v) {{ html += '<td>-</td>'; return; }}
      const [x, y] = v;
      const q = getQuad(x, y);
      let chg = '';
      if (di > 0) {{
        const pv = map[dates[di-1]];
        if (pv) {{
          const diff = x - pv[0];
          chg = diff > 0 ? '<span class="chg-up">↑</span>' : diff < 0 ? '<span class="chg-down">↓</span>' : '→';
        }}
      }}
      html += '<td class="q-' + q + '">' + x.toFixed(1) + ' / ' + y.toFixed(1) + ' <span class="chg-sign">' + chg + '</span></td>';
    }});
    html += '</tr>';
    if (exp && s.stockList) {{
      html += '<tr class="stock-row"><td colspan="' + nCols + '"><div style="display:flex;flex-direction:column;gap:2px">';
      if (s.etfCode) {{
        const ex = s.etfCode.startsWith('51') || s.etfCode.startsWith('56') ? 'sh' : 'sz';
        const url = 'https://quote.eastmoney.com/' + ex + s.etfCode + '.html';
        html += '<div><a href="' + url + '" target="_blank" style="color:#E65100;text-decoration:none;font-size:11px">📦 ' + s.etfCode + ' ETF.' + s.name + (s.etfRS != null ? ' RS=' + s.etfRS.toFixed(1) : '') + '</a></div>';
      }}
      s.stockList.forEach(st => {{
        const qc = {{L:'#1565C0',I:'#2E7D32',W:'#E65100',G:'#999'}};
        const ex = st.code.startsWith('6') ? 'sh' : (st.code.startsWith('8') || st.code.startsWith('4') ? 'bj' : 'sz');
        const url = 'https://quote.eastmoney.com/' + ex + st.code + '.html';
        const rs = st.rs_ratio != null ? '<span class="s-rs" style="color:' + qc[st.quad] + '">RS ' + st.rs_ratio.toFixed(1) + ' / MO ' + st.rs_momentum.toFixed(1) + '</span>' : '';
        html += '<div><a href="' + url + '" target="_blank" style="text-decoration:none"><span class="s-code">' + st.code + '</span> <span class="s-name">' + st.name + '</span></a>' + rs + '</div> ';
      }});
      html += '</div></td></tr>';
    }}
  }});
  html += '</tbody></table>';
  document.getElementById('trendWrap').innerHTML = html;
}}

function buildStockTrendTable() {{
  var snap = snapshotDate;
  stockSectorFilter = document.getElementById('stockSectorFilter').value;
  var search = (document.getElementById('stockSearch').value || '').trim().toLowerCase();
  var entries = Object.entries(stockTrajData);

  function getStockTraj(st, snap) {{
    return snap && st.trajectory ? st.trajectory.filter(function(p) {{ return p.date <= snap; }}) : (st.trajectory || []);
  }}

  // collect all dates
  var allDates = new Set();
  entries.forEach(function(e) {{ getStockTraj(e[1], snap).forEach(function(p) {{ allDates.add(p.date); }}); }});
  var dates = [...allDates].sort().reverse();

  // filter + sort
  let filtered = entries.filter(([code, st]) => {{
    if (stockQuadFilter && st.quad !== stockQuadFilter) return false;
    if (stockSectorFilter && st.sector !== stockSectorFilter) return false;
    if (search) {{
      const m = search.toLowerCase();
      return code.includes(m) || st.name.toLowerCase().includes(m) || st.sector.toLowerCase().includes(m);
    }}
    return true;
  }});

  const qOrd = {{L:0, I:1, W:2, G:3}};
  function getStkLatest(st, snap) {{
    if (!snap || !st.trajectory) return st.latest;
    var p = st.trajectory.find(function(q) {{ return q.date === snap; }});
    return p ? p.value : st.latest;
  }}
  function getStkTraj(st, snap) {{
    return snap && st.trajectory ? st.trajectory.filter(function(p) {{ return p.date <= snap; }}) : (st.trajectory || []);
  }}
  if (stockTrendSortMode === 'name') {{
    filtered.sort(function(a, b) {{ return a[1].name.localeCompare(b[1].name) * stockTrendSortDir; }});
  }} else if (stockTrendSortMode === 'code') {{
    filtered.sort(function(a, b) {{ return a[0].localeCompare(b[0]) * stockTrendSortDir; }});
  }} else if (stockTrendSortMode === 'sector') {{
    filtered.sort(function(a, b) {{ return a[1].sector.localeCompare(b[1].sector) * stockTrendSortDir || a[1].name.localeCompare(b[1].name); }});
  }} else if (stockTrendSortMode === 'rs') {{
    filtered.sort(function(a, b) {{ return (getStkLatest(a[1], snap)[0] - getStkLatest(b[1], snap)[0]) * stockTrendSortDir; }});
  }} else if (stockTrendSortMode === 'mo') {{
    filtered.sort(function(a, b) {{ return (getStkLatest(a[1], snap)[1] - getStkLatest(b[1], snap)[1]) * stockTrendSortDir; }});
  }} else if (stockTrendSortMode === 'quad') {{
    filtered.sort(function(a, b) {{
      var qa = snap ? getQuad(getStkLatest(a[1], snap)[0], getStkLatest(a[1], snap)[1]) : a[1].quad;
      var qb = snap ? getQuad(getStkLatest(b[1], snap)[0], getStkLatest(b[1], snap)[1]) : b[1].quad;
      return ((qOrd[qa]||9) - (qOrd[qb]||9)) * stockTrendSortDir || a[1].name.localeCompare(b[1].name);
    }});
  }} else if (stockTrendSortMode === 'trend') {{
    filtered.sort(function(a, b) {{
      var da = getStkTraj(a[1], snap).map(function(p) {{ return p.value; }});
      var db = getStkTraj(b[1], snap).map(function(p) {{ return p.value; }});
      return (consecDir(da) - consecDir(db)) * stockTrendSortDir;
    }});
  }} else if (stockTrendSortMode === 'date' && stockTrendSortCol >= 0) {{
    var col = stockTrendSortCol;
    filtered.sort(function(a, b) {{
      var va = getStkTraj(a[1], snap).find(function(p) {{ return p.date === dates[col]; }})?.value[0] ?? -999;
      var vb = getStkTraj(b[1], snap).find(function(p) {{ return p.date === dates[col]; }})?.value[0] ?? -999;
      return (va - vb) * stockTrendSortDir;
    }});
  }} else {{
    filtered.sort(function(a, b) {{ return getStkLatest(b[1], snap)[0] - getStkLatest(a[1], snap)[0]; }});
  }}

  const totalStocks = Object.keys(stockTrajData).length;
  document.getElementById('stockCount').textContent = '${{filtered.length}} / ${{totalStocks}} 只';

  const nCols = dates.length + 1;
  let html = '';
  html += '<div style="margin-bottom:4px;font-size:10px;display:flex;align-items:center;gap:4px;flex-wrap:wrap">';
  html += '<span style="color:#888;margin-right:4px">排序:</span>';
  const sorts = [['name','名称'],['code','代码'],['sector','行业'],['rs','最新RS'],['mo','最新MO'],['trend','RS趋势'],['quad','象限']];
  sorts.forEach(([k, label]) => {{
    const active = stockTrendSortMode === k;
    const arrow = active ? (stockTrendSortDir > 0 ? '▲' : '▼') : '';
    html += '<span data-stock-sort="' + k + '" style="cursor:pointer;padding:1px 6px;border-radius:3px;background:' + (active ? '#1a1a2e' : '#e0e0e0') + ';color:' + (active ? '#fff' : '#333') + '">' + label + ' ' + arrow + '</span>';
  }});
  html += '<span style="margin-left:12px;color:#aaa;font-size:9px">↑N/↓N = RS连升/连降N期 | 格中↑↓为RS变化方向 | ↑+L/I=加速 ↓+L/W=减速预警</span>';
  html += '<div style="font-size:9px;color:#bbb;margin-top:2px">RS↑+MO↑=走强加速  RS↑+MO↓=走强减速  RS↓+MO↑=走弱逆转  RS↓+MO↓=双降恶化</div>';
  html += '</div>';
  html += '<table><thead><tr><th class="st-name" style="min-width:60px">名称 <span style="font-weight:400;font-size:9px;color:#999">代码</span></th><th style="min-width:40px">行业</th>';

  const dateActive = stockTrendSortMode === 'date';
  dates.forEach((d, di) => {{
    const a = di === stockTrendSortCol && dateActive;
    const arrow = a ? (stockTrendSortDir > 0 ? '▲' : '▼') : '';
    html += '<th data-stock-date="' + di + '" style="cursor:pointer">' + d.slice(5).replace('-','/') + '<br><span style="font-weight:400;font-size:9px">RS/MO' + arrow + '</span></th>';
  }});

  html += '</tr></thead><tbody>';
  filtered.forEach(([code, st]) => {{
    const map = {{}};
    getStkTraj(st, snap).forEach(function(p) {{ map[p.date] = p.value; }});
    const ex = code.startsWith('6') ? 'sh' : (code.startsWith('8') || code.startsWith('4') ? 'bj' : 'sz');
    const emUrl = 'https://quote.eastmoney.com/' + ex + code + '.html';
    const cd = consecDir(getStkTraj(st, snap).map(function(p) {{ return p.value; }}).reverse());
    const cdHtml = cd > 0 ? '<span style="color:#d32f2f;font-size:10px;font-weight:bold" title="RS连续上升' + cd + '期">↑' + cd + '</span>' : cd < 0 ? '<span style="color:#2E7D32;font-size:10px;font-weight:bold" title="RS连续下降' + Math.abs(cd) + '期">↓' + Math.abs(cd) + '</span>' : '';
    const sec = sectorsData.find(sd => sd.name === st.sector);
    const etfTag = sec && sec.etfCode ? '<span style="color:#E65100;font-size:9px;margin-left:4px">' + sec.etfCode + '</span>' : '';
    html += '<tr class="st-row-q-' + st.quad + '"><td class="st-name q-' + st.quad + '"><a href="' + emUrl + '" target="_blank" style="text-decoration:none;color:inherit">' + st.name + ' <span class="st-code">' + code + '</span></a> ' + cdHtml + '</td><td style="font-size:9px;color:#888">' + st.sector + etfTag + '</td>';
    dates.forEach((d, di) => {{
      const v = map[d];
      if (!v) {{ html += '<td>-</td>'; return; }}
      const [x, y] = v;
      const q = getQuad(x, y);
      let chg = '';
      if (di > 0) {{
        const pv = map[dates[di-1]];
        if (pv) {{
          const diff = x - pv[0];
          chg = diff > 0 ? '<span class="chg-up">↑</span>' : diff < 0 ? '<span class="chg-down">↓</span>' : '→';
        }}
      }}
      html += '<td class="q-' + q + '">' + x.toFixed(1) + ' / ' + y.toFixed(1) + ' <span class="chg-sign">' + chg + '</span></td>';
    }});
    html += '</tr>';
  }});
  html += '</tbody></table>';
  document.getElementById('stockTrendWrap').innerHTML = html;
}}

document.getElementById('stockTrendWrap').addEventListener('click', function(e) {{
  const btn = e.target.closest('[data-stock-sort]');
  if (btn) {{
    const mode = btn.dataset.stockSort;
    if (stockTrendSortMode === mode) {{ stockTrendSortDir *= -1; }}
    else {{ stockTrendSortMode = mode; stockTrendSortDir = 1; stockTrendSortCol = -1; }}
    buildStockTrendTable();
    return;
  }}
  const dateBtn = e.target.closest('[data-stock-date]');
  if (dateBtn) {{
    const di = parseInt(dateBtn.dataset.stockDate);
    const active = di === stockTrendSortCol && stockTrendSortMode === 'date';
    stockTrendSortCol = di;
    stockTrendSortMode = 'date';
    stockTrendSortDir = active && stockTrendSortDir > 0 ? -1 : 1;
    buildStockTrendTable();
  }}
}});

function switchTab(tab) {{
  document.getElementById('tabChart').className = tab === 'chart' ? 'active' : '';
  document.getElementById('tabTrend').className = tab === 'trend' ? 'active' : '';
  document.getElementById('tabStockTrend').className = tab === 'stockTrend' ? 'active' : '';
  document.getElementById('chart').style.display = tab === 'chart' ? 'block' : 'none';
  document.querySelector('.controls').style.display = tab === 'chart' ? 'block' : 'none';
  document.querySelector('.snap-bar').style.display = 'flex';
  document.querySelector('.legend').style.display = tab === 'chart' ? 'flex' : 'none';
  document.querySelector('.footer').style.display = tab === 'chart' ? 'block' : 'none';
  document.getElementById('trendTable').style.display = tab === 'trend' ? 'block' : 'none';
  document.getElementById('stockTrendTable').style.display = tab === 'stockTrend' ? 'block' : 'none';
  if (tab === 'trend') buildTrendTable();
  if (tab === 'stockTrend') buildStockTrendTable();
  if (tab === 'chart') chart.resize();
}}

const chart = echarts.init(document.getElementById('chart'));
let showLines = true;
let isolateMode = false;
let isolatedSector = null;

function isolate(sector) {{
  isolatedSector = sector;
  chart.setOption(buildOption(showLines, sector, snapshotDate), true);
  setTimeout(() => updateArrows(sector ? 1 : 30), 50);
}}

function updateArrows(n) {{
  const allSeries = (chart.getOption().series || []).map(s => {{
    if (s.type !== 'line' || s._clickOnly) return s;
    const show = n <= 1;
    return {{
      ...s,
      markLine: show ? {{
        silent: true,
        symbol: ['none', 'arrow'],
        symbolSize: [10, 26],
        data: (sectorsData.find(d => d.name === s.name)?.arrows || []).map(a => [{{coord: a[0]}}, {{coord: a[1]}}]),
        lineStyle: {{ color: s.lineStyle?.color || '#666', width: 0.5, opacity: 0.2 }},
        label: {{ show: false }},
      }} : {{ data: [] }},
    }};
  }});
  chart.setOption({{ series: allSeries }});
}}

function getSnapPos(s, date) {{
  const p = s.trajectory.find(q => q.date === date);
  return p ? p.value : null;
}}
function getSnapQuad(s, date) {{
  const pos = getSnapPos(s, date);
  return pos ? getQuad(pos[0], pos[1]) : s.quad;
}}
function getQuadColor(q) {{
  return {{L:'#1565C0',I:'#2E7D32',W:'#E65100',G:'#999'}}[q] || '#333';
}}
function getSectorLatest(s, snap) {{
  if (!snap) return s.latest;
  var p = s.trajectory.find(function(q) {{ return q.date === snap; }});
  return p ? p.value : s.latest;
}}
function getTrajUpto(s, snap) {{
  return snap ? s.trajectory.filter(function(p) {{ return p.date <= snap; }}) : s.trajectory;
}}

function buildOption(showLines, filterSector, snapDate) {{
  const hasSnap = snapDate != null;
  const active = filterSector
    ? sectorsData.filter(s => s.name === filterSector)
    : sectorsData;

  const lineSeries = active.map(s => {{
    let traj = s.trajectory;
    if (hasSnap) traj = traj.filter(p => p.date <= snapDate);
    return {{
      name: s.name,
      type: 'line',
      data: traj,
      smooth: false,
      lineStyle: {{ color: s.color, width: 2, opacity: 0.45 }},
      emphasis: {{ lineStyle: {{ width: 4, opacity: 0.95 }} }},
      markLine: {{ data: [] }},
      z: 1,
    }};
  }});

  const scatterOnLine = active.map(s => {{
    let traj = s.trajectory;
    if (hasSnap) traj = traj.filter(p => p.date <= snapDate);
    return {{
      name: s.name,
      type: 'scatter',
      data: traj,
      symbol: 'circle', symbolSize: 1,
      tooltip: {{ show: false }},
      label: {{
        show: filterSector != null,
        formatter: p => p.data.date.slice(5).replace('-', '/'),
        fontSize: 8, color: '#666', position: 'top',
      }},
      z: 2,
    }};
  }});

  const markerSeries = active.map(s => {{
    const pts = [];
    histSeries.forEach((hs, idx) => {{
      if (hasSnap && hs.date > snapDate) return;
      const item = hs.items.find(i => i.name === s.name);
      if (!item) return;
      pts.push({{
        name: s.name, value: item.value,
        symbol: idx === 0 ? 'rect' : 'diamond',
        symbolSize: idx === 0 ? 11 : 13,
        label: {{ show: true, formatter: fmtDate(hs.date), fontSize: 8, color: '#888', position: 'bottom' }},
        itemStyle: {{ color: s.color }},
      }});
    }});
    let lx = s.latest[0], ly = s.latest[1];
    let ld = s.latestDate;
    if (hasSnap) {{
      const snap = getSnapPos(s, snapDate);
      if (snap) {{ lx = snap[0]; ly = snap[1]; ld = snapDate.slice(5); }}
    }}
    pts.push({{
      name: s.name, value: [lx, ly, s.stockCount], etfCode: s.etfCode, etfRS: s.etfRS,
      symbol: 'circle', symbolSize: 14,
      label: {{ show: true, formatter: s.name + ' (' + ld + ')', fontSize: 11, fontWeight: 'bold', position: 'right' }},
      itemStyle: {{ color: s.color, opacity: 0.9, borderColor: '#fff', borderWidth: 1.5 }},
      emphasis: {{ scale: 1.5 }},
    }});
    if (compareMode && hasSnap) {{
      pts.push({{
        name: s.name, value: [...s.latest, s.stockCount],
        symbol: 'circle', symbolSize: 7,
        itemStyle: {{ color: '#fff', borderColor: s.color, borderWidth: 2, opacity: 0.6 }},
        label: {{ show: false }},
        emphasis: {{ scale: 1.5 }},
      }});
    }}
    return {{ name: s.name, type: 'scatter', data: pts, z: 5 }};
  }});

  const series = [];
  if (showLines) series.push(...lineSeries, ...scatterOnLine);
  if (markerSeries.length) markerSeries[0].markArea = markArea;
  series.push(...markerSeries);

  return {{
    tooltip: {{
      formatter: function(p) {{
        if (!p.value) return '';
        const [x, y, extra] = p.value;
        const q = getQuad(x, y);
        const name = p.name || p.seriesName || '';
        const suffix = extra != null && typeof extra === 'number' ? ` | 成分股: ${{extra}}只` : '';
        const etf = p.data.etfCode ? ` | ETF(${{p.data.etfCode}}): ${{p.data.etfRS.toFixed(1)}}` : '';
        const tag = hasSnap ? ` 📷${{snapDate.slice(5)}}` : '';
        return `<strong>${{name}}</strong><br/>RS: ${{x.toFixed(1)}} | MO: ${{y.toFixed(1)}}<br/>象限: ${{quads[q]}}${{suffix}}${{tag}}${{etf}}`;
      }}
    }},
    legend: {{
      show: true, bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8,
      textStyle: {{fontSize: 11}},
      formatter: name => {{
        const s = sectorsData.find(d => d.name === name);
        if (!s) return name;
        const q = hasSnap ? getSnapQuad(s, snapDate) : s.quad;
        const idx = {{L:0,I:1,W:2,G:3}}[q];
        const tag = hasSnap ? '📷' : '';
        return (['[L] ','[I] ','[W] ','[G] '][idx != null ? idx : 3]) + tag + name;
      }},
      data: [...sectorsData].sort((a, b) => {{
        const q = {{L:0, I:1, W:2, G:3}};
        const qa = hasSnap ? getSnapQuad(a, snapDate) : a.quad;
        const qb = hasSnap ? getSnapQuad(b, snapDate) : b.quad;
        return (q[qa]||9) - (q[qb]||9) || a.name.localeCompare(b.name);
      }}).map(s => ({{
        name: s.name,
        textStyle: {{ color: getQuadColor(hasSnap ? getSnapQuad(s, snapDate) : s.quad) }},
      }})),
    }},
    xAxis: {{
      name: 'RS Ratio -> 相对大盘走强', nameLocation: 'center', nameGap: 35,
      splitLine: {{show: true, lineStyle: {{type: 'dashed', color: '#ddd'}}}},
      axisLine: {{show: true}},
      min: -xLimit, max: xLimit,
    }},
    yAxis: {{
      name: 'RS Momentum -> 动量向上', nameLocation: 'center', nameGap: 40,
      splitLine: {{show: true, lineStyle: {{type: 'dashed', color: '#ddd'}}}},
      axisLine: {{show: true}},
      min: -yLimit, max: yLimit,
    }},
    series: series,
    dataZoom: [{{ type: 'inside', xAxisIndex: [0], yAxisIndex: [0], zoomSensitivity: 0.12 }}],
    toolbox: {{ feature: {{ dataZoom: {{ xAxisIndex: [0], yAxisIndex: [0] }}, restore: {{}} }}, right: 20, top: 10 }},
    grid: {{ top: 40, bottom: 60, left: 65, right: 40 }},
  }};
}}

function toggleLines() {{
  showLines = !showLines;
  chart.setOption(buildOption(showLines, null, snapshotDate), true);
}}

function hideAll() {{
  sectorsData.forEach(s => chart.dispatchAction({{type: 'legendUnSelect', name: s.name}}));
  setTimeout(() => updateArrows(0), 50);
}}

function filterQuad(q) {{
  sectorsData.forEach(s => chart.dispatchAction({{type: s.quad === q ? 'legendSelect' : 'legendUnSelect', name: s.name}}));
  setTimeout(() => updateArrows(sectorsData.filter(s => s.quad === q).length), 50);
}}

chart.setOption(buildOption(true, null, null));
setTimeout(() => updateArrows(30), 100);

function resolveSector(params) {{
  if (params.seriesName && sectorsData.some(sd => sd.name === params.seriesName)) return params.seriesName;
  if (params.data && params.data.name && sectorsData.some(sd => sd.name === params.data.name)) return params.data.name;
  return null;
}}

chart.on('mouseover', function(params) {{
  const sector = resolveSector(params);
  if (!sector) return;
  chart.dispatchAction({{ type: 'downplay' }});
  chart.dispatchAction({{ type: 'highlight', name: sector }});
}});

chart.on('globalout', function() {{
  chart.dispatchAction({{ type: 'downplay' }});
}});

function toggleMode() {{
  isolateMode = !isolateMode;
  document.getElementById('modeBtn').textContent = isolateMode ? '多行业模式' : '单行业模式';
  if (!isolateMode && isolatedSector) {{
    isolate(null);
  }}
}}

chart.on('legendselectchanged', function(params) {{
  if (isolateMode) {{
    isolate(params.name === isolatedSector ? null : params.name);
    return;
  }}
  setTimeout(() => {{
    const sel = chart.getOption().legend?.[0]?.selected || {{}};
    updateArrows(Object.values(sel).filter(v => v).length);
  }}, 50);
}});

function zoomChart(factor) {{
  const dz = chart.getOption().dataZoom[0];
  const s = dz.start || 0;
  const e = dz.end || 100;
  const c = (s + e) / 2;
  const half = ((e - s) * factor) / 2;
  chart.dispatchAction({{ type: 'dataZoom', start: Math.max(0, c - half), end: Math.min(100, c + half) }});
}}

// snapshot
let snapPending = null;
function onSnapPreview(el) {{
  const idx = parseInt(el.value);
  const d = idx === 0 ? null : snapshotDates[idx];
  const label = document.getElementById('snapDateLabel');
  label.textContent = d ? d.slice(5).replace('-', '/') : '关闭';
  label.style.color = d ? '#e94560' : '#1a1a2e';
  // defer expensive rebuild
  if (snapPending) clearTimeout(snapPending);
  snapPending = setTimeout(() => onSnapCommit(el), 200);
}}
function onSnapCommit(el) {{
  snapPending = null;
  const idx = parseInt(el.value);
  snapshotDate = idx === 0 ? null : snapshotDates[idx];
  chart.setOption(buildOption(showLines, isolatedSector, snapshotDate), true);
  setTimeout(() => updateArrows(30), 50);
}}
function onCompareToggle() {{
  compareMode = document.getElementById('compareCheck').checked;
  if (snapshotDate) chart.setOption(buildOption(showLines, isolatedSector, snapshotDate), true);
}}
function clearSnapshot() {{
  snapshotDate = null;
  compareMode = false;
  document.getElementById('snapSlider').value = 0;
  document.getElementById('snapDateLabel').textContent = '关闭';
  document.getElementById('snapDateLabel').style.color = '#1a1a2e';
  document.getElementById('compareCheck').checked = false;
  chart.setOption(buildOption(showLines, isolatedSector, null), true);
  setTimeout(() => updateArrows(30), 50);
}}
// init slider
document.getElementById('snapSlider').max = snapshotDates.length - 1;
// populate stock sector filter
document.getElementById('stockSectorFilter').innerHTML = '<option value="">全部行业</option>' + sectorsData.map(s => '<option value="' + s.name + '">' + s.name + '</option>').join('');

let clickBusy = false;

function showStockModal(sector) {{
  const s = sectorsData.find(d => d.name === sector);
  if (!s || !s.stockList) return;
  const qc = {{L:'#1565C0',I:'#2E7D32',W:'#E65100',G:'#999'}};
  const qn = {{L:'Leading',I:'Improving',W:'Weakening',G:'Lagging'}};
  document.getElementById('modalTitle').innerHTML = s.name + ' <span class="quad-badge" style="background:' + qc[s.quad] + '">[' + s.quad + '] ' + qn[s.quad] + '</span>';
  const tbody = document.getElementById('modalTable');
  tbody.innerHTML = s.stockList.map(st => {{
    const ex = st.code.startsWith('6') ? 'sh' : (st.code.startsWith('8') || st.code.startsWith('4') ? 'bj' : 'sz');
    return '<tr><td><a href="https://quote.eastmoney.com/' + ex + st.code + '.html" target="_blank" style="color:#1565C0;text-decoration:none">' + st.code + '</a></td><td>' + st.name + '</td></tr>';
  }}).join('');
  document.getElementById('modalOverlay').style.display = 'block';
  document.getElementById('stockModal').style.display = 'block';
}}

function closeModal() {{
  document.getElementById('modalOverlay').style.display = 'none';
  document.getElementById('stockModal').style.display = 'none';
}}

chart.on('click', function(params) {{
  if (params.componentType === 'legend' || clickBusy) return;
  if (params.seriesType === 'scatter' && params.value && params.value.length === 3) {{
    const sector = resolveSector(params);
    if (sector) showStockModal(sector);
    return;
  }}
  const sector = resolveSector(params);
  if (!sector) return;
  clickBusy = true;
  setTimeout(() => {{ clickBusy = false; }}, 400);
  if (!isolateMode) {{
    isolateMode = true;
    document.getElementById('modeBtn').textContent = '多行业模式';
  }}
  if (sector === isolatedSector && isolateMode) {{
    isolate(null);
  }} else {{
    isolate(sector);
  }}
}});

window.addEventListener('resize', () => chart.resize());
</script>
</body>
</html>"""
    out_path = DATA_DIR / "行业轮动RRS轨迹图.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  HTML: {out_path}", file=sys.stderr)
