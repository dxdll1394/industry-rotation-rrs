#!/usr/bin/env python3
"""
行业轮动RRS四象限图 v2.0 — 带轨迹线
======================================
维度: X=RSRatio(63d)  Y=RSMomentum(21d)
特点: 每个行业显示过去N个时间点的轨迹线，看轮动方向

用法:
  python3 行业轮动RRS.py            # 默认（只读缓存）
  python3 行业轮动RRS.py --force    # 强制刷新数据
  python3 行业轮动RRS.py --html     # +生成HTML交互版
  python3 行业轮动RRS.py --cron     # 定时模式（仅周六更新）
"""
import sys
from datetime import datetime, date

from config import DATA_DIR, TRAJECTORY_INTERVAL
from data import load_pool, load_market_data, fetch_all_close_data
from calc import calc_sector_rrs, calc_stock_rs_data, calc_stock_trajectory_data, get_trajectory, get_quad
from png import plot_rrg
from html_ import gen_html


def main():
    force = "--force" in sys.argv
    make_html = "--html" in sys.argv
    is_cron = "--cron" in sys.argv
    use_cache = not force

    pool = load_pool()

    if is_cron:
        today = date.today()
        if today.weekday() != 5:
            print(f"  [跳过] 非周六(周{['一','二','三','四','五','六','日'][today.weekday()]})，不更新", file=sys.stderr)
            use_cache = True
        else:
            cache_file = DATA_DIR / ".last_update"
            days_since_last = 999
            if cache_file.exists():
                last = datetime.strptime(cache_file.read_text().strip(), "%Y-%m-%d").date()
                days_since_last = (today - last).days
            if days_since_last < 7:
                print(f"  [跳过] 上周已更新，距现在{days_since_last}天", file=sys.stderr)
                use_cache = True
            else:
                use_cache = False
                cache_file.write_text(today.strftime("%Y-%m-%d"))
                print(f"  [更新] 周六例行更新", file=sys.stderr)

    print(f"行业轮动RRS v2.0", file=sys.stderr)
    print(f"  行业数: {len(pool)}", file=sys.stderr)
    print(f"  股票数: {sum(len(v) for v in pool.values())}", file=sys.stderr)

    market = load_market_data()
    print(f"  上证指数: {len(market)}天", file=sys.stderr)

    print(f"  获取数据{'缓存' if use_cache else '强制刷新'}...", file=sys.stderr)
    stock_data, _ = fetch_all_close_data(force=force)
    print(f"  已加载: {len(stock_data)}只", file=sys.stderr)

    trajectories = calc_sector_rrs(stock_data, market, pool)
    print(f"  有效行业: {len(trajectories)}个\n", file=sys.stderr)

    print(f"{'行业':10s} {'RS_Ratio':>9s} {'MO':>7s} {'象限':>10s} {'只数':>4s}")
    print("  " + "-" * 48)
    for sector in sorted(trajectories.keys()):
        st = trajectories[sector]
        _, lx, ly, hist_nodes = get_trajectory(st["rs_ratio"], st["rs_momentum"], TRAJECTORY_INTERVAL)
        if lx is not None:
            quad = get_quad(lx, ly)
            hist_quads = ""
            for hn in hist_nodes:
                hq = get_quad(hn["x"], hn["y"])
                hist_quads += f" {hn['date'][5:]}={hq}"
            print(f"{sector:10s} {lx:9.2f} {ly:7.2f} {quad:>10s} {st['stock_count']:4d}{hist_quads}")

    update_date = datetime.now().strftime("%Y-%m-%d")
    plot_rrg(trajectories, update_date)
    if make_html:
        stock_rs = calc_stock_rs_data(stock_data, market, pool)
        stock_traj = calc_stock_trajectory_data(stock_data, market, pool)
        gen_html(trajectories, update_date, pool=pool, stock_rs=stock_rs, stock_traj=stock_traj)


if __name__ == "__main__":
    main()
