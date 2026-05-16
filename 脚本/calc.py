from collections import defaultdict
import pandas as pd

from config import RS_LOOKBACK, MO_LOOKBACK, TRAJECTORY_INTERVAL, TRAJECTORY_MAX_DAYS, HISTORICAL_DATES

def calc_sector_rrs(price_data, market, pool):
    sectors = defaultdict(list)
    for sector, items in pool.items():
        for item in items:
            sectors[sector].append(item["code"])

    sector_trajectories = {}
    for sector, codes in sectors.items():
        valid = [c for c in codes if c in price_data and len(price_data[c]) > RS_LOOKBACK + MO_LOOKBACK + 50]
        if not valid:
            continue

        rel_series = []
        for code in valid:
            stk = price_data[code]["close"]
            common = stk.index.intersection(market.index)
            if len(common) < RS_LOOKBACK + MO_LOOKBACK + 30:
                continue
            rel = stk[common] / market[common]
            rel_series.append(rel)

        if not rel_series:
            continue

        sector_rel = pd.concat(rel_series, axis=1).mean(axis=1)
        rs_ratio = sector_rel.rolling(window=RS_LOOKBACK).mean()
        rs_momentum = rs_ratio.pct_change(periods=MO_LOOKBACK) * 100
        rs_ratio_val = (sector_rel / rs_ratio - 1) * 100

        sector_trajectories[sector] = {
            "rs_ratio": rs_ratio_val.dropna(),
            "rs_momentum": rs_momentum.dropna(),
            "stock_count": len(valid),
        }

    return sector_trajectories


def get_trajectory(rr, mo, interval=None):
    if interval is None:
        interval = TRAJECTORY_INTERVAL
    last = min(len(rr), len(mo))
    rr = rr.iloc[-last:]
    mo = mo.iloc[-last:]
    common_idx = rr.index.intersection(mo.index)
    rr = rr[common_idx]
    mo = mo[common_idx]
    if len(rr) < 2:
        return None, None, None, []

    # 按固定间隔从最新往前采样 + 历史日期的精确位置
    window = min(len(rr), TRAJECTORY_MAX_DAYS)
    waypoints = {}
    for idx in range(-1, -window - 1, -interval):
        abs_pos = len(rr) + idx
        waypoints[abs_pos] = {
            "x": float(rr.iloc[idx]),
            "y": float(mo.iloc[idx]),
            "date": str(rr.index[idx].date()),
        }

    hist_nodes = []
    for date_str in HISTORICAL_DATES:
        date_ts = pd.Timestamp(date_str)
        if date_ts not in rr.index:
            continue
        abs_pos = rr.index.get_loc(date_ts)
        pt = {"x": float(rr.loc[date_ts]), "y": float(mo.loc[date_ts]), "date": date_str}
        waypoints[abs_pos] = pt
        hist_nodes.append(pt)

    sorted_pos = sorted(waypoints.keys())
    points = [waypoints[p] for p in sorted_pos]
    latest_x = float(rr.iloc[-1])
    latest_y = float(mo.iloc[-1])
    return points, latest_x, latest_y, hist_nodes


def calc_stock_rs_data(price_data, market, pool):
    result = {}
    for sector, items in pool.items():
        for item in items:
            code = item["code"]
            if code not in price_data:
                continue
            stk = price_data[code]["close"]
            common = stk.index.intersection(market.index)
            if len(common) < RS_LOOKBACK + MO_LOOKBACK + 30:
                continue
            rel = stk[common] / market[common]
            rr = rel.rolling(window=RS_LOOKBACK).mean()
            rr_val = (rel / rr - 1) * 100
            mo = rr.pct_change(periods=MO_LOOKBACK) * 100
            rr_v = rr_val.dropna()
            mo_v = mo.dropna()
            if len(rr_v) < 2 or len(mo_v) < 2:
                continue
            result[code] = {
                "rs_ratio": float(rr_v.iloc[-1]),
                "rs_momentum": float(mo_v.iloc[-1]),
                "quad": get_quad(float(rr_v.iloc[-1]), float(mo_v.iloc[-1])),
            }
    return result


def get_quad(x, y):
    if x >= 0 and y >= 0:
        return "L"
    if y >= 0:
        return "I"
    if x >= 0:
        return "W"
    return "G"
