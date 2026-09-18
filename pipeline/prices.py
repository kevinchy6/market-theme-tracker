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
    out = sanitize_dates(out)
    print(f"  total tickers with data: {len(frames)}")
    return out


def sanitize_dates(df):
    """Fix Yahoo's phantom-date quirk: after the US close (~20:00-24:00 ET,
    i.e. 00:00-04:00 UTC next day) the live row for the just-finished session
    is sometimes stamped with the *current UTC date* (e.g. Friday's close
    arrives labelled Saturday 00:00). Any bar dated after 'today in
    America/New_York' is relabelled to the last US business day; duplicates keep
    the row with better coverage."""
    df = df.copy()
    df.index = pd.to_datetime(df.index).normalize()
    et_today = pd.Timestamp.now(tz="America/New_York").normalize().tz_localize(None)
    bad = df.index > et_today
    if bad.any():
        # last completed/ongoing US session = et_today rolled back to weekday
        expected = et_today
        while expected.weekday() >= 5:
            expected -= pd.Timedelta(days=1)
        print(f"  relabelling {int(bad.sum())} future-dated bar(s) -> {expected.date()}")
        idx = df.index.to_series()
        idx[bad] = expected
        df.index = pd.DatetimeIndex(idx)
    if df.index.duplicated().any():
        # Merge duplicate dates instead of picking one row: after relabelling,
        # some tickers may carry the session under the real date and others
        # under the phantom date. Taking the first non-NaN per cell keeps both.
        n_dup = int(df.index.duplicated().sum())
        df = df.groupby(level=0).first()
        print(f"  merged {n_dup} duplicate-date row(s)")
    return df.sort_index()


def coverage_of_last_bar(df):
    c = df["Close"]
    return float(c.iloc[-1].notna().mean()) if len(c) else 0.0


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
        df = old
        # Yahoo can lag after the close: the newest bar may arrive for only a
        # handful of tickers on the first pass. Retry a few times until the
        # newest bar covers most of the universe, otherwise keep what we have.
        for attempt in range(3):
            try:
                new = download_all(
                    tickers, period="7d", chunk=50, rounds=4, pause=1.0, min_rows=1
                )
            except RuntimeError as e:
                print(f"incremental failed ({e}); keeping existing prices unchanged")
                break
            new = sanitize_dates(new)
            cutoff = new.index.min()
            # Prefer fresh values, but never let an empty/partial Yahoo row wipe
            # values we already hold for the same date (e.g. closes collected by
            # the intraday runs when Yahoo's post-close daily bar is still NaN).
            overlap = old[old.index >= cutoff]
            merged = new.combine_first(overlap) if len(overlap) else new
            merged = sanitize_dates(pd.concat([old[old.index < cutoff], merged]))
            cov = coverage_of_last_bar(merged)
            print(f"  attempt {attempt + 1}: last bar {merged.index[-1].date()} coverage {cov:.0%}")
            if cov >= 0.85:
                df = merged
                break
            df = merged  # keep partial; compute filters thin rows itself
            if attempt < 2:
                print("  newest bar is thin; waiting 180s before retrying", flush=True)
                time.sleep(180)
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
