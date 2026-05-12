import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import DATA_DIR, TRAJECTORY_INTERVAL, COLORS
from calc import get_trajectory, get_quad


def plot_rrg(sector_trajectories, update_date):
    plt.rcParams["font.family"] = "Heiti TC"
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(16, 14))
    fig.patch.set_facecolor("#F8F9FA")
    ax.set_facecolor("#F8F9FA")

    ax.axhline(y=0, color="#999", linestyle="--", linewidth=1, alpha=0.5)
    ax.axvline(x=0, color="#999", linestyle="--", linewidth=1, alpha=0.5)

    QUAD_CONFIG = [
        (40, 88, "L", "强势领导", "RS向上+动量向上", "#1565C0"),
        (-40, 88, "I", "转强改善", "RS向下+动量向上", "#2E7D32"),
        (-40, -88, "W", "开始走弱", "RS向上+动量向下", "#C62828"),
        (40, -88, "G", "持续低迷", "RS向下+动量向下", "#E65100"),
    ]
    for x, y, label, title, desc, color in QUAD_CONFIG:
        ax.text(x, y, f"[{label}] {title}\n{desc}",
                fontsize=10, color=color, alpha=0.6, ha="center", va="center")

    for ymin, ymax, xmin, xmax, fc in [
        (0, 100, 0.5, 1, "#E3F2FD"),
        (0, 100, 0, 0.5, "#E8F5E9"),
        (-100, 0, 0, 0.5, "#FFEBEE"),
        (-100, 0, 0.5, 1, "#FFF3E0"),
    ]:
        ax.axhspan(ymin, ymax, xmin=xmin, xmax=xmax, facecolor=fc, alpha=0.12)

    plot_data = []
    ci = 0
    for sector in sorted(sector_trajectories.keys()):
        st = sector_trajectories[sector]
        traj, lx, ly, hist_nodes = get_trajectory(st["rs_ratio"], st["rs_momentum"], TRAJECTORY_INTERVAL)
        if traj is None:
            continue
        color = COLORS[ci % len(COLORS)]
        ci += 1

        xs = [p["x"] for p in traj]
        ys = [p["y"] for p in traj]
        ax.plot(xs, ys, color=color, alpha=0.3, linewidth=1, linestyle="-", marker="", zorder=2)

        alphas = [min(1.0, 0.2 + 0.8 * (i + 1) / len(traj)) for i in range(len(traj))]
        ax.scatter(xs, ys, s=40, c=color, alpha=alphas,
                   edgecolors="white", linewidth=0.5, zorder=3)

        for hn in hist_nodes:
            marker = "s" if hn["date"] == "2026-04-23" else "D"
            ax.scatter(hn["x"], hn["y"], s=50, c=color, alpha=0.5,
                       marker=marker, edgecolors="white", linewidth=1, zorder=4)
            ax.annotate(hn["date"][5:], (hn["x"], hn["y"]), xytext=(3, -10),
                        textcoords="offset points", fontsize=6, color="#666",
                        alpha=0.6, zorder=4)

        if lx is not None:
            ax.scatter(lx, ly, s=60, c=color, alpha=0.9,
                       edgecolors="white", linewidth=2, zorder=5)
            ax.annotate(sector, (lx, ly), xytext=(4, 4),
                        textcoords="offset points",
                        fontsize=9, fontweight="bold", color=color, zorder=6)

        quad = get_quad(lx, ly)
        plot_data.append((sector, lx, ly, quad, st["stock_count"]))

    xs_all = [d[1] for d in plot_data]
    ys_all = [d[2] for d in plot_data]
    if xs_all:
        margin = max(10, max(abs(x) for x in xs_all) * 0.2)
        ax.set_xlim(-max(abs(x) for x in xs_all) - margin, max(abs(x) for x in xs_all) + margin)
        ax.set_ylim(-max(abs(y) for y in ys_all) - margin, max(abs(y) for y in ys_all) + margin)

    ax.set_xlabel("RS Ratio (63d) -> 相对大盘走强", fontsize=12, fontweight="bold", color="#333")
    ax.set_ylabel("RS Momentum (21d) -> 动量向上", fontsize=12, fontweight="bold", color="#333")
    ax.set_title(f"行业轮动 RRS 四象限图\n{update_date}  |  轨迹: 4/23->4/30->5/12  |  RS(63d) vs MO(21d)  |  {len(plot_data)}个行业",
                 fontsize=14, fontweight="bold", color="#1a1a2e", pad=18)
    ax.grid(True, alpha=0.25, linestyle=":", color="#888")
    ax.tick_params(labelsize=10)

    legend_text = (
        f"基准: 上证指数  |  ■=4/23  ◆=4/30  ●=5/12\n"
        f"RS=RS Ratio(63d相对大盘)  MO=RS Momentum(21d变化率)\n"
        f"L=Leading  I=Improving  W=Weakening  G=Lagging"
    )
    ax.text(0.98, 0.02, legend_text, transform=ax.transAxes,
            fontsize=9, color="#888", ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.8))

    plt.subplots_adjust(left=0.08, right=0.95, top=0.92, bottom=0.08)
    out_path = DATA_DIR / "行业轮动RRS轨迹图.png"
    fig.savefig(out_path, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"  PNG: {out_path}", file=sys.stderr)
    return plot_data
