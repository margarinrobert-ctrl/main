"""Run the ATME grid on every market, for the null signal and for the two gross-positive entries."""
from __future__ import annotations

import sys
import time

import pandas as pd

sys.path.insert(0, "research")
from atme import sweep

MARKETS = [("US30", 5), ("US100", 15), ("NQ", 5), ("XAUUSD", 5)]
SIGNALS = [("every bar", 4), ("H5 break and retest", 1), ("H6 MTF-aligned break", 1)]


def main(out="research/atme/_sweep.parquet"):
    n = sweep.n_configs()
    print(f"{n:,} configurations per market-signal; "
          f"{n * len(MARKETS) * len(SIGNALS):,} evaluations total", flush=True)
    frames = []
    t0 = time.time()
    for inst, tf in MARKETS:
        for sig, stride in SIGNALS:
            t = time.time()
            df = sweep.run(inst, tf, sig, stride=stride)
            if len(df):
                frames.append(df)
            print(f"  {inst:<7} {sig:<22} {len(df):>6} scored   "
                  f"{(time.time()-t)/60:.1f} min", flush=True)
    out_df = pd.concat(frames, ignore_index=True)
    out_df.to_parquet(out)
    print(f"\ntotal {len(out_df):,} scored rows in {(time.time()-t0)/60:.1f} min -> {out}")
    return out_df


if __name__ == "__main__":
    main()
