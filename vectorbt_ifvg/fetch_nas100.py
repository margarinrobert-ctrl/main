"""
Fetch REAL Nasdaq-100 1-minute data and build a clean CSV for the backtest.

Source: FutureSharks/financial-data on GitHub (OANDA NAS100_USD, the Nasdaq-100
index CFD - the same underlying the NQ future tracks). This works in this sandbox
because raw.githubusercontent.com is reachable even though market-data APIs are not.

NAS100_USD is the INDEX, not the NQ future, so treat the dollar figures as an NQ
proxy (the backtest still applies NQ economics: $20/pt, 0.25 tick). The price action,
win rate, profit factor and % return are the meaningful, real-market numbers.

Usage:
    python -m vectorbt_ifvg.fetch_nas100 --years 2019
    python -m vectorbt_ifvg.fetch_nas100 --years 2017 2018 2019 --out data/nas100.csv
    python -m vectorbt_ifvg.main --optimize        # picks up the CSV in data/
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import urllib.request

import pandas as pd

from .data import DATA_DIR

RAW = ("https://raw.githubusercontent.com/FutureSharks/financial-data/master/"
       "pyfinancialdata/data/currencies/oanda/NAS100_USD/{yr}/oanda-NAS100_USD-{yr}-{mo}.csv")


def _get(url: str) -> pd.DataFrame | None:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return pd.read_csv(io.BytesIO(r.read()))
    except Exception:
        return None


def fetch(years: list[int], out: str | None = None) -> str:
    frames = []
    for yr in years:
        got = 0
        for mo in range(1, 13):
            df = _get(RAW.format(yr=yr, mo=mo))
            if df is not None and len(df):
                frames.append(df)
                got += 1
        print(f"{yr}: {got}/12 months", file=sys.stderr)
    if not frames:
        sys.exit("No data fetched (network/allowlist?). raw.githubusercontent.com must "
                 "be reachable.")
    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time").sort_index()[["open", "high", "low", "close", "volume"]]
    # Clean: drop glitch bars (NDX never < 1000 in this era) and inverted bars/dupes.
    n0 = len(df)
    df = df[(df[["open", "high", "low", "close"]] > 1000).all(axis=1)]
    df = df[df["high"] >= df["low"]]
    df = df[~df.index.duplicated(keep="first")]

    os.makedirs(DATA_DIR, exist_ok=True)
    out = out or os.path.join(DATA_DIR, f"nas100_{years[0]}_{years[-1]}.csv")
    df.to_csv(out)
    print(f"Wrote {len(df):,} clean 1-min bars (dropped {n0 - len(df)}) -> {out}")
    print(f"Span {df.index[0]} .. {df.index[-1]} (UTC; loader converts to New York)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch real Nasdaq-100 1-min data (OANDA)")
    ap.add_argument("--years", type=int, nargs="+", default=[2019],
                    help="years to fetch (2005-2020 available)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    fetch(sorted(args.years), args.out)


if __name__ == "__main__":
    main()
