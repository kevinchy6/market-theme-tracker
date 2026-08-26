"""Build the stock universe: S&P 500 + 400 + 600 constituents from Wikipedia,
enriched with Yahoo Finance sector/industry classification (cached).

Output: data_cache/universe.json  [{t, name, sector, industry, cap_bucket}]
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "data_cache")
UNIVERSE_PATH = os.path.join(CACHE_DIR, "universe.json")
YMAP_PATH = os.path.join(CACHE_DIR, "yahoo_industry_map.json")

WIKI = {
    "sp500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "sp600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
}

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_wiki_members():
    import requests

    rows = []
    for bucket, url in WIKI.items():
        from io import StringIO

        html = requests.get(url, headers=UA, timeout=30).text
        tables = pd.read_html(StringIO(html))
        df = None
        for t in tables:
            cols = [str(c).lower() for c in t.columns]
            if any("symbol" in c for c in cols) and any("security" in c or "company" in c for c in cols):
                df = t
                break
        if df is None:
            raise RuntimeError(f"constituents table not found for {bucket}")
        sym_col = [c for c in df.columns if "symbol" in str(c).lower()][0]
        name_col = [c for c in df.columns if "security" in str(c).lower() or "company" in str(c).lower()][0]
        gics_sub = [c for c in df.columns if "sub-industry" in str(c).lower()]
        gics_sec = [c for c in df.columns if str(c).lower().startswith("gics sector")]
        for _, r in df.iterrows():
            sym = str(r[sym_col]).strip()
            if not sym or sym == "nan":
                continue
            rows.append(
                {
                    "t": sym.replace(".", "-"),  # BRK.B -> BRK-B for Yahoo
                    "name": str(r[name_col]).strip(),
                    "gics_sector": str(r[gics_sec[0]]).strip() if gics_sec else "",
                    "gics_sub": str(r[gics_sub[0]]).strip() if gics_sub else "",
                    "cap_bucket": {"sp500": "Large", "sp400": "Mid", "sp600": "Small"}[bucket],
                }
            )
        time.sleep(1)
    # dedupe (some tickers appear in multiple indices transiently)
    seen, out = set(), []
    for r in rows:
        if r["t"] in seen:
            continue
        seen.add(r["t"])
        out.append(r)
    return out


def load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def fetch_yahoo_classification(tickers, ymap, max_workers=8, limit=None):
    """Fetch sector/industry from Yahoo for tickers missing from cache."""
    missing = [t for t in tickers if t not in ymap]
    if limit:
        missing = missing[:limit]
    if not missing:
        return ymap, 0

    def one(t):
        try:
            info = yf.Ticker(t).info
            return t, {
                "sector": info.get("sector") or "",
                "industry": info.get("industry") or "",
                "name": info.get("shortName") or info.get("longName") or "",
                "mcap": info.get("marketCap") or 0,
            }
        except Exception as e:  # noqa: BLE001
            return t, {"error": str(e)[:120]}

    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(one, t): t for t in missing}
        for fut in as_completed(futs):
            t, res = fut.result()
            if "error" not in res and res.get("industry"):
                ymap[t] = res
            done += 1
            if done % 100 == 0:
                print(f"  yahoo classification {done}/{len(missing)}", flush=True)
                save_json(YMAP_PATH, ymap)
    return ymap, len(missing)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    members = fetch_wiki_members()
    print(f"wikipedia members: {len(members)}")

    ymap = load_json(YMAP_PATH, {})
    ymap, n_fetched = fetch_yahoo_classification([m["t"] for m in members], ymap)
    save_json(YMAP_PATH, ymap)
    print(f"yahoo map size: {len(ymap)} (fetched {n_fetched})")

    universe = []
    for m in members:
        y = ymap.get(m["t"], {})
        universe.append(
            {
                "t": m["t"],
                "name": y.get("name") or m["name"],
                "sector": y.get("sector") or m["gics_sector"],
                "industry": y.get("industry") or m["gics_sub"],
                "mcap": y.get("mcap", 0),
                "cap_bucket": m["cap_bucket"],
            }
        )
    save_json(UNIVERSE_PATH, universe)
    inds = {u["industry"] for u in universe if u["industry"]}
    print(f"universe: {len(universe)} tickers, {len(inds)} industries")


if __name__ == "__main__":
    sys.exit(main())
