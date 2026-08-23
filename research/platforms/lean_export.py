"""QuantConnect LEAN: data export and algorithm, plus an honest note about running it.

LEAN CANNOT EXECUTE IN THIS CONTAINER. The `lean` CLI is pure Python and installs fine, but it runs
the engine inside a Docker image, and this container has the Docker *client* with no daemon
(`docker info` fails) and no `dotnet`/`mono` either. So nothing here claims a LEAN backtest result.
What this module does is produce the two artifacts a LEAN run needs -- correctly formatted data and
a complete algorithm -- so the run is one command on any machine with Docker:

    pip install lean
    lean init
    cp research/platforms/lean_algorithm.py <project>/main.py
    python3 research/platforms/lean_export.py --out <lean-data-dir>
    lean backtest <project>

LEAN's minute-resolution equity/future format is one zipped CSV per symbol per day, with the time
column in MILLISECONDS SINCE MIDNIGHT in the exchange's local time zone, and prices scaled by
10,000 for equities (futures use raw prices). Getting that wrong produces a silent no-trades run,
which is why the writer below is explicit about both.

Usage: python3 research/platforms/lean_export.py --out research/lean_data --days 60
"""
from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from nqdata import load_bars, session_index, session_slice

RTH_START, RTH_END = 570, 960


def write_lean_minute(df: pd.DataFrame, out_dir: Path, ticker: str = "nq") -> int:
    """Write LEAN minute bars: one zip per session, `<yyyyMMdd>_<ticker>_minute_trade.csv`.

    Columns are: milliseconds-since-midnight (exchange local), open, high, low, close, volume.
    Futures keep raw prices -- the 10,000x scaling LEAN applies to equities does NOT apply here.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for day, g in df.groupby(df.index.normalize()):
        ms = ((g.index.hour * 3600 + g.index.minute * 60 + g.index.second) * 1000).astype("int64")
        body = pd.DataFrame({
            "time": ms,
            "open": g.open.to_numpy(),
            "high": g.high.to_numpy(),
            "low": g.low.to_numpy(),
            "close": g.close.to_numpy(),
            "volume": g.volume.astype("int64").to_numpy(),
        })
        csv_name = f"{day.strftime('%Y%m%d')}_{ticker}_minute_trade.csv"
        zip_path = out_dir / f"{day.strftime('%Y%m%d')}_trade.zip"
        buf = io.StringIO()
        body.to_csv(buf, index=False, header=False)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(csv_name, buf.getvalue())
        written += 1
    return written


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="research/lean_data")
    ap.add_argument("--days", type=int, default=60)
    a = ap.parse_args()

    df = session_slice(load_bars("data/NQ_1m.csv"), RTH_START, RTH_END)
    sess = session_index(df.index, RTH_START)
    df = df[np.isin(sess, np.unique(sess)[:a.days])]

    out = Path(a.out) / "future" / "cme" / "minute" / "nq"
    n = write_lean_minute(df, out)
    print(f"  wrote {n} session archives to {out}")
    print(f"  {len(df):,} bars, {df.index[0]} -> {df.index[-1]}")
    print("\n  LEAN cannot run in this container: the Docker client is present with no daemon")
    print("  (`docker info` fails) and there is no dotnet/mono runtime. No LEAN backtest result")
    print("  is claimed anywhere in this repository. To run it on a machine with Docker:")
    print("    lean init")
    print("    cp research/platforms/lean_algorithm.py <project>/main.py")
    print(f"    python3 research/platforms/lean_export.py --out <lean-data-dir> --days {a.days}")
    print("    lean backtest <project>")


if __name__ == "__main__":
    main()
