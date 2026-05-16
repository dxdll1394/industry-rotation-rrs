import json, sys, time, sqlite3
import pandas as pd

from config import POOL_FILE, CLOSE_CACHE_DIR, MARKET_DB

def ensure_dirs():
    CLOSE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def load_pool():
    with open(POOL_FILE, encoding="utf-8") as f:
        return json.load(f)

def load_close_cache(code):
    p = CLOSE_CACHE_DIR / f"{code}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return None

def save_close_cache(code, df):
    p = CLOSE_CACHE_DIR / f"{code}.parquet"
    df.to_parquet(p)

def load_market_data():
    conn = sqlite3.connect(str(MARKET_DB))
    rows = conn.execute(
        "SELECT date, close FROM index_daily WHERE symbol='sh000001' ORDER BY date"
    ).fetchall()
    conn.close()
    dates = [r[0] for r in rows]
    closes = [float(r[1]) for r in rows]
    return pd.Series(closes, index=pd.to_datetime(dates))

def fetch_all_close_data(force=False, max_cache_age_days=7):
    import akshare as ak
    from datetime import date
    ensure_dirs()
    pool = load_pool()
    stocks = [{**item, "sector": sector} for sector, items in pool.items() for item in items]

    all_data = {}
    total = len(stocks)
    done = 0
    today = date.today()
    for s in stocks:
        code = s["code"]
        if not force:
            cached = load_close_cache(code)
            if cached is not None:
                cache_last = cached.index.max().date()
                if (today - cache_last).days < max_cache_age_days:
                    all_data[code] = cached
                    done += 1
                    continue
        try:
            df = ak.stock_value_em(symbol=code)
            if df is not None and not df.empty:
                df = df.rename(columns={"数据日期": "date", "当日收盘价": "close", "当日涨跌幅": "change_pct"})
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")[["close", "change_pct"]]
                df = df[~df.index.duplicated(keep="last")]
                if not force:
                    cached = load_close_cache(code)
                    if cached is not None:
                        df = pd.concat([cached, df])
                        df = df[~df.index.duplicated(keep="last")].sort_index()
                all_data[code] = df
                save_close_cache(code, df)
        except Exception as e:
            print(f"  {s['name']}({code}) fail: {e}", file=sys.stderr)
        done += 1
        if done % 20 == 0:
            print(f"  [{done}/{total}]", file=sys.stderr)
        time.sleep(0.3)
    return all_data, stocks
