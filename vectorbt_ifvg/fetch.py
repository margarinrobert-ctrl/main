"""
Fetch real data for the backtest.

IMPORTANT: this environment blocks all market-data hosts (only github.com is
reachable), so this script will fail here with a clear message. Run it in an
environment with network access, or use it as a reference.

Two things to know about Yahoo / yfinance for NQ futures:

  * ``yf.download("NQ=F", start="2000-01-01")`` returns DAILY bars. The IFVG +
    Liquidity Sweep model is a 1-MINUTE intraday strategy (killzones, session
    ranges, 1-3 min IFVGs); daily bars cannot drive it. Use ``interval="1m"``.
  * Yahoo only serves 1-minute history for roughly the last 7 days, and intraday
    intervals at all for ~60 days. For real intraday history you need a paid feed
    (Polygon, Databento, FirstRate) or a broker/TradingView CSV export.

Usage:
    python -m vectorbt_ifvg.fetch --ticker NQ=F --interval 1m --days 7
    # -> writes vectorbt_ifvg/data/NQ_1m.csv, then:
    python -m vectorbt_ifvg.main --optimize     # picks up the CSV automatically
"""

from __future__ import annotations

import argparse
import os
import sys

from .data import DATA_DIR


def fetch(ticker: str = "NQ=F", interval: str = "1m", days: int = 7,
          start: str | None = None, out: str | None = None) -> str:
    try:
        import yfinance as yf
    except ImportError:
        sys.exit("yfinance not installed: pip install yfinance")

    if interval.endswith("m") and start:
        print("WARN: Yahoo ignores 'start' for intraday intervals; using 'period' "
              "(max ~7d for 1m, ~60d for other intraday).", file=sys.stderr)

    kwargs = dict(interval=interval, progress=False, auto_adjust=False)
    if interval.endswith("m"):
        kwargs["period"] = f"{days}d"
    elif start:
        kwargs["start"] = start

    df = yf.download(ticker, **kwargs)
    if df is None or len(df) == 0:
        sys.exit(f"No data returned for {ticker} (likely network/allowlist or an "
                 f"unsupported interval/range). This sandbox blocks Yahoo.")

    # Flatten yfinance's possible MultiIndex columns and normalise names.
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df.index.name = "datetime"

    if not interval.endswith("m"):
        print("WARN: this is NOT intraday data. The 1-minute IFVG strategy needs "
              "1m bars; daily bars will produce meaningless results.", file=sys.stderr)

    os.makedirs(DATA_DIR, exist_ok=True)
    out = out or os.path.join(DATA_DIR, f"{ticker.replace('=','').replace('!','')}_{interval}.csv")
    df.to_csv(out)
    print(f"Wrote {len(df):,} {interval} bars -> {out}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fetch OHLCV via yfinance for the backtest")
    ap.add_argument("--ticker", default="NQ=F")
    ap.add_argument("--interval", default="1m", help="1m, 5m, 15m, 1h, 1d ...")
    ap.add_argument("--days", type=int, default=7, help="lookback for intraday intervals")
    ap.add_argument("--start", default=None, help="start date for daily+ intervals")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    fetch(args.ticker, args.interval, args.days, args.start, args.out)


if __name__ == "__main__":
    main()
