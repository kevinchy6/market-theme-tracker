"""Fetch Yahoo Finance news for spotlight tickers (top movers, new highs/lows,
gappers) — a bounded set so we stay friendly with rate limits.

Output: data_cache/news.json {ticker: [{title, url, pub, src}]}
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

from .config import CACHE_DIR, DATA_DIR


def targets(limit=120):
    tick = set()
    for fname, keys in [
        ("spotlight.json", ("gainers", "losers", "highs", "lows")),
        ("scanner.json", ("rows",)),
    ]:
        path = os.path.join(DATA_DIR, fname)
        if not os.path.exists(path):
            continue
        with open(path) as f:
            data = json.load(f)
        for k in keys:
            for r in data.get(k, [])[:40]:
                tick.add(r["t"])
    return list(tick)[:limit]


def fetch_one(t):
    try:
        items = yf.Ticker(t).news or []
        out = []
        for it in items[:6]:
            c = it.get("content") or it
            title = c.get("title")
            url = ((c.get("clickThroughUrl") or {}).get("url")
                   or (c.get("canonicalUrl") or {}).get("url") or it.get("link"))
            if not title or not url:
                continue
            out.append({
                "title": title[:140],
                "url": url,
                "pub": (c.get("pubDate") or "")[:10],
                "src": (c.get("provider") or {}).get("displayName", "")[:30],
            })
        return t, out
    except Exception:  # noqa: BLE001
        return t, []


def main():
    tick = targets()
    print(f"news for {len(tick)} tickers")
    news = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(fetch_one, t) for t in tick]
        for fut in as_completed(futs):
            t, items = fut.result()
            if items:
                news[t] = items
    with open(os.path.join(CACHE_DIR, "news.json"), "w") as f:
        json.dump(news, f, separators=(",", ":"))
    print(f"news saved for {len(news)} tickers")


if __name__ == "__main__":
    main()
