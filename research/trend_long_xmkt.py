"""The long-only 200 EMA + ADX + pullback battery, run on NQ and US100 together.

One command, both instruments, the same rules and geometry on each. It exists ready-to-run
because the US100 upload was cleared mid-study; `us100.find_raw` will locate the file as soon as
it is re-attached (durably, at `data/US100_15m.csv`).

The design point is which block counts as out-of-sample on each instrument:

  NQ     research = first 65% of sessions, holdout = the rest, as everywhere else here.
  US100  research = before 2022-12-26, which is SIX YEARS NOTHING ON THIS BRANCH HAS SEEN,
         holdout = 2022-12-26 onward.

So US100's "research" block is itself a genuine out-of-sample test of anything selected on NQ,
and its holdout is a second one. Both are scored against a minute-of-day matched control, because
a long-only rule in a rising market beats zero without beating random.

Usage: python3 research/trend_long_xmkt.py
"""
from __future__ import annotations

import sys

import numpy as np

sys.path.insert(0, "research")
import trend_long as T
import us100
from oner_union import _cut, bars
from scipy.stats import binomtest

TF = 15                    # the coarsest common timeframe: US100's source is 15-minute
STOP, TARGET, FLAT = 2.0, 1.0, 960


def _panel(d, blk, label, mask, am=STOP, tp=TARGET, flat=FLAT):
    m = mask.copy(); m[:300] = False
    trig = np.flatnonzero(m).astype(np.int64)
    if len(trig) < 40:
        print(f"  {label:<38}{'too few triggers':>30}")
        return
    p, e, _x, _w, _g = T.sim(d, trig, am, tp, flat)
    for tag, k, b in (("in-sample", blk[e], blk), ("OUT-OF-SAMPLE", ~blk[e], ~blk)):
        if k.sum() < 20:
            continue
        ctl = T.control(d, trig, am, tp, flat, b, draws=400)
        wr = 100.0 * float((p[k] > 0).mean()); n = int(k.sum())
        pv = binomtest(int((p[k] > 0).sum()), n,
                       min(max(ctl / 100.0, 1e-6), 1 - 1e-6), alternative="greater").pvalue
        print(f"  {label:<38}{tag:<15}{n:>5}{wr:>7.1f}%{ctl:>7.1f}{wr-ctl:>+8.1f}"
              f"{p[k].mean():>9.1f}{pv:>9.4f}")


def variants(d):
    F = T.features(d)
    mod = d["mod"]
    W = (mod >= T.WIN_EARLY[0]) & (mod < T.WIN_EARLY[1])
    PB = T.recent(T.PULLBACKS["below EMA20"](F, d), 6)
    R = T.regime(F, d, adx_min=25.0, slope_min=0.0)
    out = {
        "full regime + break pullback high": R & PB & T.TRIGGERS["break pullback high"](F, d) & W,
        "full regime + reclaim EMA20": R & PB & T.TRIGGERS["reclaim EMA20"](F, d) & W,
        "NO regime + reclaim EMA20": PB & T.TRIGGERS["reclaim EMA20"](F, d) & W,
        "drop the 200 EMA": T.regime(F, d, use_200=False, adx_min=25.0, slope_min=0.0) & PB
                            & T.TRIGGERS["reclaim EMA20"](F, d) & W,
        "drop ADX": T.regime(F, d, use_adx=False, adx_min=25.0, slope_min=0.0) & PB
                    & T.TRIGGERS["reclaim EMA20"](F, d) & W,
    }
    return out


def run():
    hdr = (f"  {'':<38}{'block':<15}{'n':>5}{'win%':>8}{'ctrl':>7}{'excess':>8}"
           f"{'$/trade':>9}{'p':>9}")
    print(f"{TF}-minute, 07:00-11:00 New York, {STOP}xATR / {TARGET}R, flat 16:00\n")
    d = bars(TF); si, cut, _ = _cut(d)
    print("NQ  (in-sample = first 65% of sessions)"); print(hdr)
    for k, m in variants(d).items():
        _panel(d, si < cut, k, m)
    print()
    try:
        b = us100.to_bars(TF)
    except FileNotFoundError as e:
        print("US100 SKIPPED --", str(e).split(". ")[0] + ".")
        print("  Re-attach the file, ideally at data/US100_15m.csv, and re-run this module.")
        return
    unseen = np.asarray(b["df"].index < np.datetime64("2022-12-26"))
    print("US100  (in-sample = 2016-2022, six years nothing here has seen)"); print(hdr)
    for k, m in variants(b).items():
        _panel(b, unseen, k, m)


if __name__ == "__main__":
    run()
