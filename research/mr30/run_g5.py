"""THE ONE SURVIVOR, TESTED AS A REPLICATION RATHER THAN A DISCOVERY.

`run_g4` put 20 declared conditions x 3 holding lengths through a null that holds the exposure
fixed and preserves each condition's own clustering: **1 of 60 cells clears p<=0.05 where 3.0 are
expected by chance, and 0 survive BH**. Timing is worth nothing on US30 at 15 minutes -- which is
the cleanest statement of why eight Donchian breakouts, the Initial Balance, the VWAP-EMA spec,
the volume profile and three primaries in this study all failed the same way.

The top cell is `ATR percentile over its own last 250 bars <= 0.2` at a four-hour hold: +0.0214%
against a null of +0.0086%, a 2.5x lift, p 0.051. On its own that is chance. It is not on its own:
`STUDY_V28` swept 240 declared ATR-regime cells on US30 and found exactly two survivors, the same
condition and its near-duplicate, clearing **both** blocks at p 0.003. Two different constructions,
two different framings, the same variable. So this is a PRE-REGISTERED REPLICATION and is scored as
one -- a ladder, its mirror, three blocks including a reserved forward feed from another provider,
and the mechanism `STUDY_V22` already measured twice.

WHAT THE MECHANISM PREDICTS AND THIS TESTS. V22 established on NQ and SPX, value for value across
blocks, that ATR(14) is BACKWARD-looking while volatility MEAN-REVERTS, so when vol sits low in its
own distribution the trailing ATR has already contracted and forward vol EXCEEDS it. If that is why
this cell reads high, then on US30 too the ratio forward-realised / trailing-ATR must RISE as the
percentile falls, the effect must be MONOTONE in the percentile, and the mirror (high percentile)
must be the weak end. Three predictions, all falsifiable, none of them the p-value.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mr30 import mr30core as M  # noqa: E402
from mr30.run_g4 import fwd, shift_null  # noqa: E402

LS = (16, 64)
RUNGS = (0.1, 0.2, 0.3, 0.4, 0.5)


def pct250(f):
    return pd.Series(f["atr"].to_numpy()).rolling(250).rank(pct=True).shift(1).to_numpy()


def fwd_rv(f, h):
    """Forward realised volatility over h bars, in points, aligned to the signal bar."""
    c = f["close"].to_numpy()
    r = np.r_[np.nan, np.diff(c)]
    v = pd.Series(r).rolling(h).std().to_numpy()
    return np.r_[v[h:], np.full(h, np.nan)] * np.sqrt(h)


def main():
    print("REPLICATION: ATR percentile (own last 250 bars) as a TIMING condition, exposure fixed.\n")
    feeds = [("US30L", "A_research"), ("US30L", "B_holdout"), ("US30I", "C_forward")]
    cache = {}
    for feed in ("US30L", "US30I"):
        f = M.load(feed)
        cache[feed] = (f, pct250(f), M.blocks(f, feed))

    for L in LS:
        print(f"--- holding length L={L} bars ({L * 15 / 60:.0f} hours) ---")
        print(f"  {'rung':<18}{'block':<12}{'n':>8}{'mean %':>10}{'null %':>10}"
              f"{'excess':>10}{'lift':>7}{'sd':>8}{'Sharpe':>8}{'p':>8}")
        for lo in RUNGS:
            for feed, bn in feeds:
                f, pc, blk = cache[feed]
                r = fwd(f, L)
                m = np.nan_to_num(pc <= lo, nan=False).astype(bool)
                bm = blk[bn]
                sel = m & bm & np.isfinite(r)
                if sel.sum() < 150:
                    continue
                mu = float(r[sel].mean()); sd = float(r[sel].std(ddof=1))
                null = shift_null(m, bm, r)
                nm_ = float(np.median(null))
                p = float(np.mean(null >= mu))
                print(f"  {f'pct250<={lo}':<18}{bn:<12}{int(sel.sum()):>8}{mu:>10.4f}"
                      f"{nm_:>10.4f}{mu - nm_:>10.4f}{mu / max(nm_, 1e-9):>7.2f}"
                      f"{sd:>8.3f}{mu / sd:>8.4f}{p:>8.3f}")
            print()

    print("--- THE MIRROR (high percentile) at L=16, which must be the weak end ---")
    print(f"  {'rung':<18}{'block':<12}{'n':>8}{'mean %':>10}{'null %':>10}{'excess':>10}{'p':>8}")
    for hi in (0.5, 0.6, 0.7, 0.8, 0.9):
        for feed, bn in feeds:
            f, pc, blk = cache[feed]
            r = fwd(f, 16)
            m = np.nan_to_num(pc >= hi, nan=False).astype(bool)
            bm = blk[bn]
            sel = m & bm & np.isfinite(r)
            if sel.sum() < 150:
                continue
            mu = float(r[sel].mean())
            null = shift_null(m, bm, r)
            print(f"  {f'pct250>={hi}':<18}{bn:<12}{int(sel.sum()):>8}{mu:>10.4f}"
                  f"{float(np.median(null)):>10.4f}{mu - float(np.median(null)):>10.4f}"
                  f"{float(np.mean(null >= mu)):>8.3f}")
        print()

    print("--- V22'S MECHANISM ON US30: forward realised vol / trailing ATR, by percentile ---")
    print("    it must RISE as the percentile falls, or the reason given for the cell is wrong")
    for feed, bn in feeds:
        f, pc, blk = cache[feed]
        rv = fwd_rv(f, 16)
        at = f["atr"].to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = rv / np.where(at > 0, at, np.nan)
        bm = blk[bn] & np.isfinite(ratio) & np.isfinite(pc)
        cells = []
        for a, b in ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)):
            s = bm & (pc >= a) & (pc < b)
            cells.append(float(np.nanmedian(ratio[s])))
        print(f"  {feed} {bn:<12} " + " ".join(f"{v:>7.3f}" for v in cells) +
              f"   Q1-Q5 {cells[0] - cells[-1]:>+7.3f}  "
              f"{'RISES as vol falls' if cells[0] > cells[-1] else 'FALLS -- mechanism wrong'}")


if __name__ == "__main__":
    main()
