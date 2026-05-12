from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "数据"
CLOSE_CACHE_DIR = DATA_DIR / "收盘价缓存"
POOL_FILE = DATA_DIR / "综合股池.json"
MARKET_DB = Path.home() / ".openclaw" / "workspace" / "自选股" / "数据" / "市场数据.db"

RS_LOOKBACK = 63
MO_LOOKBACK = 21
TRAJECTORY_INTERVAL = 5
TRAJECTORY_MAX_DAYS = 180

HISTORICAL_DATES = ["2026-04-23", "2026-04-30", "2026-05-12"]

COLORS = [
    "#e6194B", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
    "#469990", "#dcbeff", "#9A6324", "#fffac8", "#800000",
    "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9",
    "#e6beff", "#ffb347", "#4a6fa5", "#5f9c6e", "#d4915c",
    "#8b6b8b", "#6b8e23", "#2e6b8b", "#8b4513", "#4682b4",
]
