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

def _etf_sina_symbol(code):
    return ("sh" if code.startswith(("5", "6")) else "sz") + code

def fetch_etf_close_data(force=False, latest_market_date=None):
    import akshare as ak
    ensure_dirs()
    total = len(INDUSTRY_ETF)
    done = 0
    for sector, code in INDUSTRY_ETF.items():
        cache_file = CLOSE_CACHE_DIR / f"etf_{code}.parquet"
        if not force and cache_file.exists():
            cached = pd.read_parquet(cache_file)
            if "close" in cached.columns:
                cache_last = cached.index.max()
                if hasattr(cache_last, "date"):
                    cache_last = cache_last.date()
                if latest_market_date is not None and cache_last >= latest_market_date:
                    done += 1
                    continue

        try:
            df = ak.fund_etf_hist_sina(symbol=_etf_sina_symbol(code))
            if df is not None and not df.empty:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")[["close"]]
                df = df[~df.index.duplicated(keep="last")]
                if not force and cache_file.exists():
                    old = pd.read_parquet(cache_file)
                    df = pd.concat([old, df])
                    df = df[~df.index.duplicated(keep="last")].sort_index()
                df.to_parquet(cache_file)
        except Exception:
            if not force and cache_file.exists():
                done += 1
                continue
        done += 1
        if done % 5 == 0:
            print(f"  ETF [{done}/{total}]", file=sys.stderr)

def _try_zh_a_hist(code, start_date, end_date):
    import akshare as ak
    df = ak.stock_zh_a_hist(symbol=code, period="daily",
                            start_date=start_date, end_date=end_date, adjust="qfq")
    if df is None or df.empty:
        return None
    df = df.rename(columns={"日期": "date", "收盘": "close", "涨跌幅": "change_pct"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")[["close", "change_pct"]]
    return df[~df.index.duplicated(keep="last")]


def _try_value_em(code):
    import akshare as ak
    df = ak.stock_value_em(symbol=code)
    if df is None or df.empty:
        return None
    df = df.rename(columns={"数据日期": "date", "当日收盘价": "close", "当日涨跌幅": "change_pct"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")[["close", "change_pct"]]
    return df[~df.index.duplicated(keep="last")]


def fetch_all_close_data(force=False, latest_market_date=None):
    from datetime import date, timedelta
    ensure_dirs()
    pool = load_pool()
    stocks = [{**item, "sector": sector} for sector, items in pool.items() for item in items]

    all_data = {}
    total = len(stocks)
    done = 0
    for s in stocks:
        code = s["code"]
        cached = None
        if not force:
            cached = load_close_cache(code)
            if cached is not None:
                cache_last = cached.index.max().date()
                if latest_market_date is not None and cache_last >= latest_market_date:
                    all_data[code] = cached
                    done += 1
                    continue

        fetched = None
        if cached is not None:
            start_date = (cache_last + timedelta(days=1)).strftime("%Y%m%d")
            today_str = date.today().strftime("%Y%m%d")
            try:
                fetched = _try_zh_a_hist(code, start_date, today_str)
            except Exception:
                pass

        if fetched is None:
            try:
                fetched = _try_value_em(code)
            except Exception as e:
                print(f"  {s['name']}({code}) fail: {e}", file=sys.stderr)

        if cached is not None:
            if fetched is not None:
                df = pd.concat([cached, fetched])
                df = df[~df.index.duplicated(keep="last")].sort_index()
            else:
                df = cached
        elif fetched is not None:
            df = fetched
        else:
            done += 1
            time.sleep(0.3)
            continue

        all_data[code] = df
        save_close_cache(code, df)
        done += 1
        if done % 20 == 0:
            print(f"  [{done}/{total}]", file=sys.stderr)
        time.sleep(0.3)
    return all_data, stocks
