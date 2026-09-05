"""Compute all dashboard datasets from the cached price panel:

- themes.json     industry / sector group performance across timeframes
- etfs.json       S&P sector, equal-weight, country, snapshot ETF tables
- breadth.json    daily breadth indicator history (backfilled from prices)
- scanner.json    gap scanner (today's gaps vs prior close)
- spotlight.json  new 52w highs/lows + top movers
- tape.json       ticker tape
- meta.json       last update timestamp / market session info
- tickers/<T>.json  per-ticker deep-dive payloads
"""

import json
import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .config import (
    CACHE_DIR,
    COUNTRY,
    DATA_DIR,
    EQWT,
    SNAPSHOT,
    SP_SECTORS,
    TAPE,
    TICKER_DIR,
)
from .prices import PRICES_PATH

# trading-day lookbacks
TIMEFRAMES = {"d1": 1, "w1": 5, "m1": 21, "m3": 63, "m6": 126}


def rnd(x, nd=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), nd)


def save(name, obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, name), "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def pct_returns(close: pd.DataFrame):
    """Return dict of {tf: Series of % return per ticker} + ytd."""
    out = {}
    last = close.ffill().iloc[-1]
    for tf, n in TIMEFRAMES.items():
        if len(close) > n:
            base = close.ffill().iloc[-1 - n]
            out[tf] = (last / base - 1) * 100
        else:
            out[tf] = last * np.nan
    # YTD: last close of previous calendar year
    year = close.index[-1].year
    prev = close[close.index.year < year]
    if len(prev):
        out["ytd"] = (last / prev.ffill().iloc[-1] - 1) * 100
    else:
        out["ytd"] = last * np.nan
    return out


def group_table(universe, rets, close, volume):
    """Aggregate per-ticker returns into industry & sector tables."""
    info = {u["t"]: u for u in universe}
    tickers = [t for t in close.columns if t in info]

    rows_by_key = {"industry": {}, "sector": {}}
    for t in tickers:
        u = info[t]
        for key in ("industry", "sector"):
            g = u.get(key) or "Other"
            rows_by_key[key].setdefault(g, []).append(t)

    def agg(members):
        d = {}
        for tf in list(TIMEFRAMES) + ["ytd"]:
            vals = rets[tf].reindex(members).dropna()
            d[tf] = rnd(vals.mean()) if len(vals) else None
        return d

    result = {}
    for key, groups in rows_by_key.items():
        table = []
        for g, members in groups.items():
            if key == "industry" and len(members) < 2:
                pass  # keep single-member industries too, matches "142 sub-industries"
            row = {"g": g, "n": len(members), **agg(members)}
            if key == "industry":
                row["sec"] = info[members[0]].get("sector", "")
            table.append(row)
        table.sort(key=lambda r: (r["d1"] is None, -(r["d1"] or 0)))
        result[key] = table

    # constituents payload for drill-down
    cons = {}
    for g, members in rows_by_key["industry"].items():
        cons[g] = sorted(members, key=lambda t: -(info[t].get("mcap") or 0))
    sec_cons = {}
    for g, members in rows_by_key["sector"].items():
        sec_cons[g] = sorted(members, key=lambda t: -(info[t].get("mcap") or 0))

    # per-ticker compact returns for drill-down tables
    stock_rows = {}
    last = close.ffill().iloc[-1]
    avg_vol = volume.tail(20).mean()
    for t in tickers:
        stock_rows[t] = {
            "name": info[t]["name"][:40],
            "px": rnd(last.get(t)),
            "mcap": info[t].get("mcap") or 0,
            "vol": int(avg_vol.get(t) or 0),
            **{tf: rnd(rets[tf].get(t)) for tf in list(TIMEFRAMES) + ["ytd"]},
        }
    return result, cons, sec_cons, stock_rows


def etf_tables(rets, close):
    def table(mapping):
        out = []
        last = close.ffill().iloc[-1]
        for sym, label in mapping.items():
            if sym not in close.columns or pd.isna(last.get(sym)):
                continue
            out.append(
                {
                    "g": label,
                    "t": sym,
                    "px": rnd(last[sym]),
                    **{tf: rnd(rets[tf].get(sym)) for tf in list(TIMEFRAMES) + ["ytd"]},
                }
            )
        out.sort(key=lambda r: -(r["d1"] or -999))
        return out

    return {
        "sp": table(SP_SECTORS),
        "eqwt": table(EQWT),
        "country": table(COUNTRY),
        "snapshot": table(SNAPSHOT),
    }


def breadth_history(universe, close, volume, days=252):
    """Daily breadth indicators computed over the trailing `days` sessions."""
    info = {u["t"]: u for u in universe}
    cols = [t for t in close.columns if t in info]
    c = close[cols].ffill()
    pct = c.pct_change() * 100

    ma20 = c.rolling(20).mean()
    ma50 = c.rolling(50).mean()
    ma200 = c.rolling(200).mean()
    hi52 = c.rolling(252, min_periods=60).max()
    lo52 = c.rolling(252, min_periods=60).min()
    r63 = (c / c.shift(63) - 1) * 100
    r21 = (c / c.shift(21) - 1) * 100
    r34 = (c / c.shift(34) - 1) * 100

    up4 = (pct >= 4).sum(axis=1)
    dn4 = (pct <= -4).sum(axis=1)
    adv = (pct > 0).sum(axis=1)
    dec = (pct < 0).sum(axis=1)
    nh = (c >= hi52).sum(axis=1)
    nl = (c <= lo52).sum(axis=1)
    above20 = (c > ma20).sum(axis=1) / len(cols) * 100
    above50 = (c > ma50).sum(axis=1) / len(cols) * 100
    above200 = (c > ma200).sum(axis=1) / len(cols) * 100
    up25q = (r63 >= 25).sum(axis=1)
    dn25q = (r63 <= -25).sum(axis=1)
    up25m = (r21 >= 25).sum(axis=1)
    dn25m = (r21 <= -25).sum(axis=1)
    up13_34 = (r34 >= 13).sum(axis=1)
    dn13_34 = (r34 <= -13).sum(axis=1)
    ratio5 = up4.rolling(5).sum() / dn4.rolling(5).sum().clip(lower=1)
    ratio10 = up4.rolling(10).sum() / dn4.rolling(10).sum().clip(lower=1)

    idx = c.index[-days:]
    rows = []
    for d in idx:
        rows.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "adv": int(adv[d]), "dec": int(dec[d]),
                "up4": int(up4[d]), "dn4": int(dn4[d]),
                "r5": rnd(ratio5[d]), "r10": rnd(ratio10[d]),
                "up25q": int(up25q[d]), "dn25q": int(dn25q[d]),
                "up25m": int(up25m[d]), "dn25m": int(dn25m[d]),
                "up13": int(up13_34[d]), "dn13": int(dn13_34[d]),
                "nh": int(nh[d]), "nl": int(nl[d]),
                "a20": rnd(above20[d], 1), "a50": rnd(above50[d], 1), "a200": rnd(above200[d], 1),
            }
        )
    rows.reverse()  # newest first
    return {"universe_size": len(cols), "rows": rows}


def gap_scanner(universe, opn, close, volume):
    """Today's gaps: open vs prior close, plus current change and RVOL."""
    info = {u["t"]: u for u in universe}
    cols = [t for t in close.columns if t in info]
    c = close[cols].ffill()
    if len(c) < 25:
        return {"rows": []}
    last, prev = c.iloc[-1], c.iloc[-2]
    o = opn[cols].iloc[-1]
    v = volume[cols].iloc[-1]
    av = volume[cols].iloc[-21:-1].mean()

    gap = (o / prev - 1) * 100
    chg = (last / prev - 1) * 100
    rvol = v / av.clip(lower=1)

    rows = []
    for t in cols:
        g, ch = gap.get(t), chg.get(t)
        if pd.isna(g) or pd.isna(ch):
            continue
        px = last[t]
        if px < 5 or (av.get(t) or 0) < 300_000:
            continue
        if abs(g) < 2 and abs(ch) < 5:
            continue
        rows.append(
            {
                "t": t, "name": info[t]["name"][:32], "px": rnd(px),
                "gap": rnd(g), "chg": rnd(ch),
                "vol": int(v.get(t) or 0), "rvol": rnd(rvol.get(t)),
                "ind": info[t].get("industry", ""),
            }
        )
    rows.sort(key=lambda r: -abs(r["gap"]))
    return {"rows": rows[:120]}


def spotlight(universe, close, volume):
    info = {u["t"]: u for u in universe}
    cols = [t for t in close.columns if t in info]
    c = close[cols].ffill()
    pct = (c.iloc[-1] / c.iloc[-2] - 1) * 100
    roll_hi = c.rolling(252, min_periods=60).max()
    roll_lo = c.rolling(252, min_periods=60).min()
    hi52 = roll_hi.iloc[-1]
    lo52 = roll_lo.iloc[-1]
    last = c.iloc[-1]

    # "Hit count" over the last 63 sessions (~3 months): how many days the
    # stock closed at a new 52w high / low within that window. Matches the
    # persistence metric on Market Pulse's Highs/Lows page.
    lookback = min(63, len(c))
    window = c.tail(lookback)
    hi_hits = (window >= roll_hi.tail(lookback)).sum(axis=0).astype(int)
    lo_hits = (window <= roll_lo.tail(lookback)).sum(axis=0).astype(int)

    def row(t, count=None):
        r = {
            "t": t, "name": info[t]["name"][:32], "px": rnd(last[t]),
            "chg": rnd(pct.get(t)), "ind": info[t].get("industry", ""),
            "mcap": info[t].get("mcap") or 0,
        }
        if count is not None:
            r["n"] = int(count)
        return r

    highs = [
        row(t, hi_hits.get(t, 0)) for t in cols
        if last[t] >= hi52[t] and not pd.isna(pct.get(t))
    ]
    lows = [
        row(t, lo_hits.get(t, 0)) for t in cols
        if last[t] <= lo52[t] and not pd.isna(pct.get(t))
    ]
    # Sort each list by hit count desc (most persistent first),
    # then by chg for tie-breaking.
    highs.sort(key=lambda r: (-r.get("n", 0), -(r["chg"] or 0)))
    lows.sort(key=lambda r: (-r.get("n", 0), r["chg"] or 0))

    def group_by_industry(items):
        """Return list of {industry, total_hits, items} sorted by total hits desc.
        Items missing an industry go into an 'Ungrouped' bucket."""
        buckets = {}
        for r in items:
            key = r.get("ind") or "Ungrouped"
            buckets.setdefault(key, []).append(r)
        groups = []
        for name, rows in buckets.items():
            total = sum(r.get("n", 0) for r in rows) or len(rows)
            groups.append({
                "industry": name,
                "hits": int(total),
                "count": len(rows),
                "items": rows,
            })
        groups.sort(key=lambda g: (-g["hits"], -g["count"]))
        return groups

    universe_size = len(cols)
    big = [t for t in cols if (info[t].get("mcap") or 0) > 10e9 and not pd.isna(pct.get(t))]
    gainers = sorted(big, key=lambda t: -pct[t])[:25]
    losers = sorted(big, key=lambda t: pct[t])[:25]
    return {
        "summary": {
            "universe": universe_size,
            "highs_count": len(highs),
            "lows_count": len(lows),
            "highs_pct": rnd(100 * len(highs) / universe_size) if universe_size else 0,
            "lows_pct": rnd(100 * len(lows) / universe_size) if universe_size else 0,
            "lookback_days": lookback,
        },
        "highs": highs[:150],
        "lows": lows[:150],
        "highs_grouped": group_by_industry(highs),
        "lows_grouped": group_by_industry(lows),
        "gainers": [row(t) for t in gainers],
        "losers": [row(t) for t in losers],
    }


def ticker_tape(close):
    c = close.ffill()
    rows = []
    for t in TAPE:
        if t not in c.columns or len(c[t].dropna()) < 2:
            continue
        s = c[t].dropna()
        rows.append({"t": t.replace("-USD", ""), "chg": rnd((s.iloc[-1] / s.iloc[-2] - 1) * 100)})
    return {"rows": rows}


def deepdive_files(universe, close, volume, fundamentals, news):
    os.makedirs(TICKER_DIR, exist_ok=True)
    info = {u["t"]: u for u in universe}
    c = close.ffill()
    year = c.tail(252)
    dates = [d.strftime("%Y-%m-%d") for d in year.index]
    vol20 = volume.tail(20).mean()
    n = 0
    for t in c.columns:
        if t not in info:
            continue
        s = year[t].dropna()
        if s.empty:
            continue
        closes = [rnd(x) for x in year[t].tolist()]
        f = fundamentals.get(t, {})
        payload = {
            "t": t,
            "name": info[t]["name"],
            "sector": info[t].get("sector", ""),
            "industry": info[t].get("industry", ""),
            "mcap": info[t].get("mcap") or 0,
            "px": rnd(s.iloc[-1]),
            "chg": rnd((s.iloc[-1] / s.iloc[-2] - 1) * 100) if len(s) > 1 else None,
            "hi52": rnd(s.max()),
            "lo52": rnd(s.min()),
            "avgvol": int(vol20.get(t) or 0),
            "dates": dates,
            "closes": closes,
            "f": f,
            "news": news.get(t, []),
        }
        with open(os.path.join(TICKER_DIR, f"{t}.json"), "w") as fp:
            json.dump(payload, fp, separators=(",", ":"))
        n += 1
    return n


def load_optional(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def main():
    with open(os.path.join(CACHE_DIR, "universe.json")) as f:
        universe = json.load(f)
    df = pd.read_parquet(PRICES_PATH)
    # drop bars with almost no coverage (e.g. Yahoo emits an empty "today"
    # row before the US session has any prints)
    coverage = df["Close"].notna().mean(axis=1)
    df = df[coverage > 0.1]
    close, opn, volume = df["Close"], df["Open"], df["Volume"]
    print(f"prices: {close.shape}")

    rets = pct_returns(close)
    groups, cons, sec_cons, stock_rows = group_table(universe, rets, close, volume)

    save("themes.json", {
        "industry": groups["industry"], "sector": groups["sector"],
        "cons": cons, "sec_cons": sec_cons, "stocks": stock_rows,
    })
    save("etfs.json", etf_tables(rets, close))
    save("breadth.json", breadth_history(universe, close, volume))
    save("scanner.json", gap_scanner(universe, opn, close, volume))
    save("spotlight.json", spotlight(universe, close, volume))
    save("tape.json", ticker_tape(close))

    fundamentals = load_optional(os.path.join(CACHE_DIR, "fundamentals.json"))
    news = load_optional(os.path.join(CACHE_DIR, "news.json"))
    n = deepdive_files(universe, close, volume, fundamentals, news)
    print(f"wrote {n} ticker files")

    last_bar = close.index[-1]
    # freshness check: what session should we have by now?
    now_et = pd.Timestamp.now(tz="America/New_York")
    expected = now_et.normalize().tz_localize(None)
    if now_et.hour < 10:  # before ~open, previous session is fine
        expected -= pd.Timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= pd.Timedelta(days=1)
    save("meta.json", {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "last_bar": last_bar.strftime("%Y-%m-%d"),
        "expected_bar": expected.strftime("%Y-%m-%d"),
        "stale": bool(last_bar.normalize() < expected),
        "universe": len(universe),
        "industries": len(groups["industry"]),
    })
    print("compute done")


if __name__ == "__main__":
    main()
