import sys, json

from config import DATA_DIR, TRAJECTORY_INTERVAL, HISTORICAL_DATES, COLORS
from calc import get_trajectory, get_quad


LATEST_DATE_LABEL = HISTORICAL_DATES[-1][5:]  # "05-12"


def gen_html(trajectories, update_date):
    sectors_data = []
    ci = 0
    for sector in sorted(trajectories.keys()):
        st = trajectories[sector]
        traj, lx, ly, hist_nodes = get_trajectory(st["rs_ratio"], st["rs_momentum"], TRAJECTORY_INTERVAL)
        if traj is None or lx is None:
            continue
        color = COLORS[ci % len(COLORS)]
        ci += 1

        hist_map = {}
        for hn in hist_nodes:
            hist_map[hn["date"]] = [round(hn["x"], 2), round(hn["y"], 2)]

        trajectory_path = [{"value": [round(p["x"], 2), round(p["y"], 2)], "date": p["date"]} for p in traj]
        latest_val = [round(lx, 2), round(ly, 2)]
        arrows = [[trajectory_path[i]["value"], trajectory_path[i + 1]["value"]] for i in range(len(trajectory_path) - 1)]

        sectors_data.append({
            "name": sector,
            "color": color,
            "trajectory": trajectory_path,
            "arrows": arrows,
            "latest": latest_val,
            "stockCount": st["stock_count"],
            "latestDate": LATEST_DATE_LABEL,
            "histMap": hist_map,
            "quad": get_quad(lx, ly),
        })

    hist_dates = HISTORICAL_DATES[:-1]
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
</style>
</head>
<body>
<div class="container">
  <h1>行业轮动 RRS 轨迹图</h1>
  <div class="meta">{update_date} | RS Ratio(63d) vs RS Momentum(21d) | 基准: 上证指数 | {len(sectors_data)}个行业</div>
  <div id="chart"></div>
  <div class="controls">
    <button onclick="toggleLines()">切换轨迹线显隐</button>
    <button onclick="toggleMode()" id="modeBtn">单行业模式</button>
    <button onclick="zoomChart(0.7)">放大</button>
    <button onclick="zoomChart(1.4)">缩小</button>
    <button onclick="chart.dispatchAction({{type:'legendAllSelect'}});setTimeout(updateArrows,50)" style="margin-left:6px;">显示全部</button>
    <span style="margin-left:12px;">
      <span class="date-marker" style="background:#666;"></span>4/23
      <span class="date-marker" style="background:#999;width:12px;height:12px;"></span>4/30
      <span class="date-marker" style="background:#222;width:14px;height:14px;"></span>当前
    </span>
  </div>
  <div class="legend">
    <span class="legend-item">[L] Leading 强势</span>
    <span class="legend-item">[I] Improving 改善</span>
    <span class="legend-item">[W] Weakening 走弱</span>
    <span class="legend-item">[G] Lagging 低迷</span>
  </div>
  <div class="footer">数据:东方财富 个股等权聚合 | 每周六更新 | 方块=4/23 菱形=4/30 圆点=当前 | 悬停查看行业轨迹</div>
</div>
<script>
const sectorsData = {sectors_json};
const histSeries = {hist_series_json};
const HIST_DATES = {hist_dates_json};

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

const chart = echarts.init(document.getElementById('chart'));
let showLines = true;
let isolateMode = false;
let isolatedSector = null;

function isolate(sector) {{
  isolatedSector = sector;
  chart.setOption(buildOption(showLines, sector), true);
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

function buildOption(showLines, filterSector) {{
  const active = filterSector
    ? sectorsData.filter(s => s.name === filterSector)
    : sectorsData;

  const lineSeries = active.map(s => ({{
    name: s.name,
    type: 'line',
    data: s.trajectory,
    smooth: false,
    symbol: 'none',
    lineStyle: {{ color: s.color, width: 2, opacity: 0.45 }},
    emphasis: {{ lineStyle: {{ width: 4, opacity: 0.95 }} }},
    markLine: {{ data: [] }},
    z: 1,
  }}));

  // 轨迹节点散点（不可见，用于点击 + 日期标签锚点）
  const scatterOnLine = active.map(s => ({{
    name: s.name,
    type: 'scatter',
    data: s.trajectory,
    symbol: 'circle', symbolSize: 1,
    tooltip: {{ show: false }},
    label: {{
      show: filterSector != null,
      formatter: p => p.data.date.slice(5).replace('-', '/'),
      fontSize: 8, color: '#666', position: 'top',
    }},
    z: 2,
  }}));

  const latestSeries = active.map(s => ({{
    name: s.name,
    type: 'scatter',
    data: [{{ name: s.name, value: [...s.latest, s.stockCount] }}],
    symbolSize: 14,
    itemStyle: {{ color: s.color, opacity: 0.9, borderColor: '#fff', borderWidth: 1.5 }},
    label: {{ show: true, formatter: s.name + ' (' + s.latestDate + ')', fontSize: 11, fontWeight: 'bold', position: 'right' }},
    emphasis: {{ scale: 1.5 }},
    z: 5,
  }}));

  const histChartSeries = histSeries.map((hs, idx) => ({{
    name: fmtDate(hs.date),
    type: 'scatter',
    data: filterSector ? hs.items.filter(item => item.name === filterSector) : hs.items,
    symbol: idx === 0 ? 'rect' : 'diamond',
    symbolSize: idx === 0 ? 11 : 13,
    label: {{ show: true, formatter: fmtDate(hs.date), fontSize: 8, color: '#888', position: 'bottom' }},
    z: 3,
  }}));

  const series = [];
  if (showLines) series.push(...lineSeries, ...scatterOnLine);
  series.push(...latestSeries, ...histChartSeries);
  series[series.length - histChartSeries.length].markArea = markArea;

  return {{
    tooltip: {{
      formatter: function(p) {{
        if (!p.value) return '';
        const [x, y, extra] = p.value;
        const q = getQuad(x, y);
        const name = p.name || p.seriesName || '';
        const suffix = extra != null && typeof extra === 'number' ? ` | 成分股: ${{extra}}只` : '';
        return `<strong>${{name}}</strong><br/>RS: ${{x.toFixed(1)}} | MO: ${{y.toFixed(1)}}<br/>象限: ${{quads[q]}}${{suffix}}`;
      }}
    }},
    legend: {{
      show: true, bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8,
      textStyle: {{fontSize: 11}},
      formatter: name => {{
        const s = sectorsData.find(d => d.name === name);
        const idx = {{L:0,I:1,W:2,G:3}}[s.quad];
        return s ? ['[L] ','[I] ','[W] ','[G] '][idx != null ? idx : 3] + name : name;
      }},
      data: [...sectorsData].sort((a, b) => {{
        const q = {{L:0, I:1, W:2, G:3}};
        return (q[a.quad]||9) - (q[b.quad]||9) || a.name.localeCompare(b.name);
      }}).map(s => ({{
        name: s.name,
        textStyle: {{ color: {{L:'#1565C0', I:'#2E7D32', W:'#E65100', G:'#999'}}[s.quad] || '#333' }},
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
  chart.setOption(buildOption(showLines, null), true);
}}

chart.setOption(buildOption(true, null));
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
  const n = sectorsData.length;
  const histStart = showLines ? n * 3 : n;
  histSeries.forEach((_, i) => {{
    chart.dispatchAction({{ type: 'highlight', seriesIndex: histStart + i, dataName: sector }});
  }});
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
    const sel = chart.getOption()[0].legend[0].selected || {{}};
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

let clickBusy = false;

chart.on('click', function(params) {{
  if (params.componentType === 'legend' || clickBusy) return;
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
