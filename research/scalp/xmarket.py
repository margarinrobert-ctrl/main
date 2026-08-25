"""Cross-market analysis: US30 against NQ and US100 (brief stage CROSS-MARKET ANALYSIS).

WHY THIS STAGE IS THE IMPORTANT ONE. Every study on this branch has ended with the same
limitation: NQ and US100 track the SAME underlying index, and `STUDY_TREND_LONG.md` measured what
that costs -- 68% of signals fire on the identical 15-minute bar, so one cannot replicate the
other. US30 is the Dow, a different index with different composition and weighting. It is the
first genuinely separate market on this branch, and the first honest replication target.

What this module measures, all on RETURNS rather than levels (the NQ series' levels are synthetic):

  * contemporaneous correlation, whole-sample and by session
  * lead-lag at +/- k bars -- does one market inform the next bar of another, or is the transfer
    complete inside the bar as it was for NQ/US100
  * whether the correlation is stable across the sample or a regime artifact
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from edgelab import feeds


def aligned(insts=("US30", "US100", "NQ"), tf=15):
    """Log returns on a common New York index, inner-joined so every row exists everywhere."""
    cols = {}
    for i in insts:
        d = feeds.bars(i, tf)
        ix = pd.DatetimeIndex(d["idx"])
        if ix.tz is not None:
            ix = ix.tz_localize(None)
        s = pd.Series(d["c"], index=ix)
        cols[i] = np.log(s).diff()
    df = pd.DataFrame(cols).dropna()
    return df


def report(insts=("US30", "US100", "NQ"), tf=15, max_lag=4):
    df = aligned(insts, tf)
    print(f"CROSS-MARKET, {tf}-minute log returns, {len(df):,} common bars "
          f"{df.index[0].date()} -> {df.index[-1].date()}\n")
    print("  contemporaneous correlation")
    print(df.corr().to_string(float_format=lambda x: f"{x:.4f}"))

    print("\n  lead-lag: corr(X at t-k, Y at t). A spike only at k=0 means the transfer is")
    print("  complete inside the bar and there is nothing tradable between them.")
    names = list(df.columns)
    for a in names:
        for b in names:
            if a >= b:
                continue
            row = []
            for k in range(-max_lag, max_lag + 1):
                row.append(df[a].shift(k).corr(df[b]))
            best = int(np.argmax(np.abs(row))) - max_lag
            print(f"    {a:<6} vs {b:<6} " + " ".join(f"{v:+.3f}" for v in row) +
                  f"   peak at k={best:+d}")

    print("\n  correlation by year -- is it stable or a regime artifact?")
    yr = df.groupby(df.index.year).apply(
        lambda g: pd.Series({f"{a}/{b}": g[a].corr(g[b])
                             for a in names for b in names if a < b}))
    print(yr.to_string(float_format=lambda x: f"{x:.3f}"))

    print("\n  correlation by session (New York)")
    mod = df.index.hour * 60 + df.index.minute
    for tag, sel in (("pre 04:00-09:30", (mod >= 240) & (mod < 570)),
                     ("RTH 09:30-16:00", (mod >= 570) & (mod < 960)),
                     ("post 16:00-20:00", (mod >= 960) & (mod < 1200))):
        g = df[sel]
        if len(g) < 500:
            continue
        pairs = "  ".join(f"{a}/{b} {g[a].corr(g[b]):.3f}"
                          for a in names for b in names if a < b)
        print(f"    {tag:<18} n={len(g):>7,}   {pairs}")
    return df
