"""Batch-download daily OHLCV history from Yahoo Finance for the whole
universe + all ETFs. Saves a tidy parquet cache used by compute steps.
"""

import json
import os
import time

import pandas as pd
import yfinance as yf

from .config import ALL_ETFS, CACHE_DIR, HISTORY_PERIOD

PRICES_PATH = os.path.join(CACHE_DIR, "prices.parquet")


def load_universe():
    with open(os.path.join(CACHE_DIR, "universe.json")) as f:
        return json.load(f)


def download_all(tickers, period=HISTORY_PERIOD, chunk=50, rounds=5, pause=2.0, min_rows=20):
    """Rate-limit-friendly bulk download with resume: small sequential chunks,
    exponential backoff between rounds, retrying only missing tickers."""
    frames = {}
    remaining = list(tickers)
    for rnd_i in range(rounds):
        failed = []
        for i in range(0, len(remaining), chunk):
            batch = remaining[i : i + chunk]
            try:
                df = yf.download(
                    batch,
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    group_by="ticker",
                    threads=4,
                    progress=False,
                )
            except Exception as e:  # noqa: BLE001
                print(f"  chunk error: {str(e)[:80]}")
                df = None
            got = 0
            if df is not None and len(df) > 0:
                for t in batch:
                    try:
                        sub = df[t].dropna(how="all")
                    except KeyError:
                        sub = None
                    if sub is not None and len(sub) >= min_rows:
                        frames[t] = sub
                        got += 1
                    else:
                        failed.append(t)
            else:
                failed.extend(batch)
            print(f"  round {rnd_i}: {min(i + chunk, len(remaining))}/{len(remaining)} (+{got})", flush=True)
            time.sleep(pause)
        if not failed:
            break
        if len(failed) == len(remaining):
            # no progress this round: likely delisted symbols, stop retrying
            print(f"  round {rnd_i}: no progress, giving up on {len(failed)} symbols", flush=True)
            break
        wait_s = 90 * (rnd_i + 1)
        print(f"  round {rnd_i} done, {len(failed)} missing; sleeping {wait_s}s", flush=True)
        remaining = failed
        time.sleep(wait_s)
    if not frames:
        raise RuntimeError("no price data downloaded")
    out = pd.concat(frames, axis=1)  # columns: (ticker, field)
    out = out.swaplevel(axis=1).sort_index(axis=1)  # -> (field, ticker)
    print(f"  total tickers with data: {len(frames)}")
    return out


def main(mode="auto"):
    universe = load_universe()
    tickers = sorted({u["t"] for u in universe} | set(ALL_ETFS))

    old = None
    if mode != "full" and os.path.exists(PRICES_PATH):
        try:
            old = pd.read_parquet(PRICES_PATH)
            age_days = (pd.Timestamp.utcnow().tz_localize(None) - old.index[-1]).days
            if age_days > 6:
                old = None
        except Exception:  # noqa: BLE001
            old = None

    if old is not None:
        print(f"incremental update ({len(tickers)} tickers, 7d)")
        try:
            new = download_all(
                tickers, period="7d", chunk=50, rounds=4, pause=1.0, min_rows=1
            )
        except RuntimeError as e:
            print(f"incremental failed ({e}); keeping existing prices unchanged")
            df = old
        else:
            cutoff = new.index.min()
            merged = pd.concat([old[old.index < cutoff], new])
            df = merged.sort_index()
    else:
        print(f"full download ({len(tickers)} tickers, {HISTORY_PERIOD} daily)")
        df = download_all(tickers)

    df.to_parquet(PRICES_PATH)
    close = df["Close"]
    print(f"saved {PRICES_PATH}: {close.shape[0]} days x {close.shape[1]} tickers")
    print(f"last date: {close.index[-1]}")


if __name__ == "__main__":
    import sys

    main(mode=sys.argv[1] if len(sys.argv) > 1 else "auto")
