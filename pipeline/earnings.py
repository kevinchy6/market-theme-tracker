"""Earnings calendar built from Yahoo Finance per-ticker earnings dates.

- weekly full scan caches all upcoming/recent earnings dates
- daily refresh re-fetches only tickers reporting within +/- 8 days

Output: site/data/earnings.json  {days: {date: [rows]}}
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from .config import CACHE_DIR, DATA_DIR

EARN_CACHE = os.path.join(CACHE_DIR, "earnings_cache.json")


def fetch_one(t):
    try:
        df = yf.Ticker(t).get_earnings_dates(limit=8)
        if df is None or df.empty:
            return t, []
        rows = []
        for ts, r in df.iterrows():
            def num(key):
                v = r.get(key)
                return None if v is None or pd.isna(v) else round(float(v), 4)
            rows.append({
                "date": ts.strftime("%Y-%m-%d"),
                "est": num("EPS Estimate"),
                "act": num("Reported EPS"),
                "surp": num("Surprise(%)"),
            })
        return t, rows
    except Exception:  # noqa: BLE001
        return t, None


def main(mode="daily", max_workers=4):
    with open(os.path.join(CACHE_DIR, "universe.json")) as f:
        universe = json.load(f)
    info = {u["t"]: u for u in universe}

    cache = {}
    if os.path.exists(EARN_CACHE):
        with open(EARN_CACHE) as f:
            cache = json.load(f)

    today = datetime.utcnow().date()
    if mode == "weekly" or not cache:
        targets = list(info)
    else:
        lo, hi = today - timedelta(days=8), today + timedelta(days=8)
        targets = []
        for t, rows in cache.items():
            for r in rows or []:
                d = datetime.strptime(r["date"], "%Y-%m-%d").date()
                if lo <= d <= hi:
                    targets.append(t)
                    break
        targets += [t for t in info if t not in cache]

    print(f"earnings fetch ({mode}): {len(targets)} tickers")
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(fetch_one, t) for t in targets]
        for fut in as_completed(futs):
            t, rows = fut.result()
            if rows is not None:
                cache[t] = rows
            done += 1
            if done % 250 == 0:
                print(f"  {done}/{len(targets)}", flush=True)
                with open(EARN_CACHE, "w") as f:
                    json.dump(cache, f, separators=(",", ":"))
    with open(EARN_CACHE, "w") as f:
        json.dump(cache, f, separators=(",", ":"))

    # build calendar: past 21 days .. next 30 days
    lo = today - timedelta(days=21)
    hi = today + timedelta(days=30)
    days = {}
    for t, rows in cache.items():
        u = info.get(t)
        if not u:
            continue
        for r in rows or []:
            d = datetime.strptime(r["date"], "%Y-%m-%d").date()
            if not (lo <= d <= hi):
                continue
            days.setdefault(r["date"], []).append({
                "t": t, "name": u["name"][:36], "ind": u.get("industry", ""),
                "mcap": u.get("mcap") or 0,
                "est": r["est"], "act": r["act"], "surp": r["surp"],
            })
    for d in days:
        days[d].sort(key=lambda r: -(r["mcap"] or 0))

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "earnings.json"), "w") as f:
        json.dump({"days": days}, f, separators=(",", ":"))
    print(f"earnings calendar: {len(days)} days, {sum(len(v) for v in days.values())} reports")


if __name__ == "__main__":
    main(mode=sys.argv[1] if len(sys.argv) > 1 else "daily")
