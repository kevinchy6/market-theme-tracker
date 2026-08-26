"""Commitment of Traders (CFTC legacy futures-only) via the free public
Socrata API at publicreporting.cftc.gov — no API key required.

Output: site/data/cot.json  {markets: {code: {name, rows: [...]}}}
"""

import json
import os
import time

import requests

from .config import COT_MARKETS, DATA_DIR

API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
FIELDS = ",".join([
    "report_date_as_yyyy_mm_dd",
    "open_interest_all",
    "noncomm_positions_long_all",
    "noncomm_positions_short_all",
    "comm_positions_long_all",
    "comm_positions_short_all",
    "nonrept_positions_long_all",
    "nonrept_positions_short_all",
])


def fetch_market(code, limit=156):
    params = {
        "$select": FIELDS,
        "$where": f"cftc_contract_market_code='{code}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": limit,
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    rows = []
    for rec in r.json():
        try:
            oi = int(rec.get("open_interest_all") or 0)
            ncl = int(rec.get("noncomm_positions_long_all") or 0)
            ncs = int(rec.get("noncomm_positions_short_all") or 0)
            cl = int(rec.get("comm_positions_long_all") or 0)
            cs = int(rec.get("comm_positions_short_all") or 0)
            nrl = int(rec.get("nonrept_positions_long_all") or 0)
            nrs = int(rec.get("nonrept_positions_short_all") or 0)
            rows.append({
                "date": rec["report_date_as_yyyy_mm_dd"][:10],
                "oi": oi,
                "spec": ncl - ncs,      # large speculators net
                "comm": cl - cs,        # commercials net
                "small": nrl - nrs,     # small traders net
            })
        except (ValueError, KeyError):
            continue
    rows.sort(key=lambda x: x["date"])
    return rows


def main():
    out = {}
    for code, name in COT_MARKETS.items():
        try:
            rows = fetch_market(code)
            if rows:
                out[code] = {"name": name, "rows": rows}
                print(f"  {name}: {len(rows)} weeks")
        except Exception as e:  # noqa: BLE001
            print(f"  {name} failed: {e}")
        time.sleep(1)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "cot.json"), "w") as f:
        json.dump({"markets": out}, f, separators=(",", ":"))
    print(f"cot: {len(out)} markets")


if __name__ == "__main__":
    main()
