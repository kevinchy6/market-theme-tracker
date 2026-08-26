"""Fetch per-ticker fundamentals from Yahoo Finance (weekly refresh).

Output: data_cache/fundamentals.json  {ticker: {...compact stats...}}
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

from .config import CACHE_DIR

FUND_PATH = os.path.join(CACHE_DIR, "fundamentals.json")
YMAP_PATH = os.path.join(CACHE_DIR, "yahoo_industry_map.json")

FIELDS = {
    "trailingPE": "pe",
    "forwardPE": "fpe",
    "priceToSalesTrailing12Months": "ps",
    "priceToBook": "pb",
    "profitMargins": "margin",
    "revenueGrowth": "revg",
    "earningsGrowth": "epsg",
    "beta": "beta",
    "dividendYield": "divy",
    "shortPercentOfFloat": "short",
    "heldPercentInstitutions": "inst",
    "totalRevenue": "rev",
    "trailingEps": "eps",
    "fullTimeEmployees": "emp",
}


def fetch_one(t):
    try:
        info = yf.Ticker(t).info
        out = {}
        for src, dst in FIELDS.items():
            v = info.get(src)
            if isinstance(v, (int, float)):
                out[dst] = round(v, 4) if isinstance(v, float) else v
        summary = info.get("longBusinessSummary") or ""
        if summary:
            out["desc"] = summary[:420]
        if info.get("website"):
            out["web"] = info["website"]
        cls = None
        if info.get("industry"):
            cls = {
                "sector": info.get("sector") or "",
                "industry": info.get("industry") or "",
                "name": info.get("shortName") or info.get("longName") or "",
                "mcap": info.get("marketCap") or 0,
            }
        return t, out, cls
    except Exception:  # noqa: BLE001
        return t, None, None


def main(max_workers=4, rounds=4):
    with open(os.path.join(CACHE_DIR, "universe.json")) as f:
        universe = json.load(f)
    tickers = [u["t"] for u in universe]
    fund = {}
    if os.path.exists(FUND_PATH):
        with open(FUND_PATH) as f:
            fund = json.load(f)
    ymap = {}
    if os.path.exists(YMAP_PATH):
        with open(YMAP_PATH) as f:
            ymap = json.load(f)

    def flush():
        with open(FUND_PATH, "w") as f:
            json.dump(fund, f, separators=(",", ":"))
        with open(YMAP_PATH, "w") as f:
            json.dump(ymap, f, separators=(",", ":"))

    for r in range(rounds):
        missing = [t for t in tickers if t not in fund]
        if not missing:
            break
        print(f"round {r}: fetching {len(missing)} fundamentals")
        done = 0
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = [ex.submit(fetch_one, t) for t in missing]
            for fut in as_completed(futs):
                t, res, cls = fut.result()
                if res is not None:
                    fund[t] = res
                if cls is not None:
                    ymap[t] = cls
                done += 1
                if done % 200 == 0:
                    print(f"  {done}/{len(missing)}", flush=True)
                    flush()
        flush()
        time.sleep(20)
    flush()
    # rebuild universe.json with the enriched classification
    upath = os.path.join(CACHE_DIR, "universe.json")
    if os.path.exists(upath):
        with open(upath) as f:
            universe = json.load(f)
        for u in universe:
            y = ymap.get(u["t"])
            if y:
                u["sector"] = y["sector"] or u["sector"]
                u["industry"] = y["industry"] or u["industry"]
                u["name"] = y["name"] or u["name"]
                u["mcap"] = y["mcap"] or u.get("mcap", 0)
        with open(upath, "w") as f:
            json.dump(universe, f, separators=(",", ":"))
        inds = {u["industry"] for u in universe if u["industry"]}
        print(f"universe refreshed: {len(inds)} industries")
    print(f"fundamentals: {len(fund)}/{len(tickers)}")


if __name__ == "__main__":
    main()
