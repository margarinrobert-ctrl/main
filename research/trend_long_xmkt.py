"""The long-only 200 EMA + ADX + pullback battery, run on NQ and US100 together.

One command, both instruments, the same rules and geometry on each.

THE BLOCK THAT COUNTS, AND THE ONE THAT DOES NOT
------------------------------------------------
US100 splits at 2022-12-26, where NQ's file starts:

  US100 2016-2022   SIX YEARS NOTHING ON THIS BRANCH HAS SEEN. The only genuinely independent
                    test of a rule selected on NQ.
  US100 2023-2025   the same calendar as NQ's whole sample, on the same underlying index.
                    `overlap()` below measures what that is worth: 68% of NQ's triggers fire on
                    the EXACT SAME 15-minute bar on US100. It is the same trades on a second
                    data feed, not a second test, and it is reported here only so the dependence
                    is visible rather than mistaken for confirmation.

Everything is scored two ways, because they disagree and the disagreement is the finding:

  matched control   random long entries, same minute-of-day, same geometry. Matched on TIME but
                    NOT on volatility -- so it flatters any rule that concentrates in high-ATR
                    bars, which is exactly what an ADX filter does. Read it with `baseline`.
  regime baseline   enter EVERY eligible bar the regime admits, in the same window. This is the
                    null that isolates the PULLBACK AND TRIGGER from "be long in this regime",
                    and it is the harder and more honest of the two.

Usage: python3 research/trend_long_xmkt.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
import trend_long as T
import us100
from oner_union import _cut, bars
from scipy.stats import binomtest

TF = 15                    # the coarsest common timeframe: US100's source is 15-minute
STOP, TARGET, FLAT = 2.0, 1.0, 960
SPLIT = np.datetime64("2022-12-26")


def _sim(d, mask):
    m = mask.copy(); m[:300] = False
    trig = np.flatnonzero(m).astype(np.int64)
    return trig, T.sim(d, trig, STOP, TARGET, FLAT)


def _control(d, trig, block, draws=300, seed=7):
    """Minute-of-day matched random longs; returns (win% draws, $/trade draws)."""
    mod = d["mod"].astype(int)
    by: dict[int, list[int]] = {}
    for i in np.arange(300, len(d["c"]) - 1):
        by.setdefault(int(mod[i]), []).append(i)
    want: dict[int, int] = {}
    for i in trig:
        want[int(mod[i])] = want.get(int(mod[i]), 0) + 1
    rng = np.random.default_rng(seed); W: list[float] = []; D: list[float] = []
    for _ in range(draws):
        pick = [rng.choice(by[k], size=min(n, len(by[k])), replace=False)
                for k, n in want.items() if by.get(k)]
        if not pick:
            continue
        p, e, _x, _w, _g = T.sim(d, np.sort(np.concatenate(pick)), STOP, TARGET, FLAT)
        k = block[e]
        if k.sum() >= 10:
            W.append(100.0 * float((p[k] > 0).mean())); D.append(float(p[k].mean()))
    return np.array(W), np.array(D)


def _panel(d, blk, label, mask):
    trig, (p, e, _x, _w, _g) = _sim(d, mask)
    if len(trig) < 40:
        print(f"  {label:<38}{'too few triggers':>30}")
        return
    k = blk[e]
    if k.sum() < 20:
        print(f"  {label:<38}{'too few in block':>30}")
        return
    W, D = _control(d, trig, blk)
    wr = 100.0 * float((p[k] > 0).mean()); dl = float(p[k].mean()); n = int(k.sum())
    pw = binomtest(int((p[k] > 0).sum()), n,
                   min(max(W.mean() / 100.0, 1e-6), 1 - 1e-6), alternative="greater").pvalue
    pd_ = float((D >= dl).mean())
    print(f"  {label:<38}{n:>5}{wr:>7.1f}%{W.mean():>7.1f}{wr - W.mean():>+8.1f}"
          f"{dl:>9.1f}{dl - D.mean():>+8.1f}{pw:>8.4f}{pd_:>8.4f}")


def variants(d):
    F = T.features(d)
    mod = d["mod"]
    W = (mod >= T.WIN_EARLY[0]) & (mod < T.WIN_EARLY[1])
    PB = T.recent(T.PULLBACKS["below EMA20"](F, d), 6)
    R = T.regime(F, d, adx_min=25.0, slope_min=0.0)
    return {
        "full regime + break pullback high": R & PB & T.TRIGGERS["break pullback high"](F, d) & W,
        "full regime + reclaim EMA20": R & PB & T.TRIGGERS["reclaim EMA20"](F, d) & W,
        "NO regime + reclaim EMA20": PB & T.TRIGGERS["reclaim EMA20"](F, d) & W,
        "drop the 200 EMA": T.regime(F, d, use_200=False, adx_min=25.0, slope_min=0.0) & PB
                            & T.TRIGGERS["reclaim EMA20"](F, d) & W,
        "drop ADX": T.regime(F, d, use_adx=False, adx_min=25.0, slope_min=0.0) & PB
                    & T.TRIGGERS["reclaim EMA20"](F, d) & W,
    }


def _naive(ix):
    ix = pd.DatetimeIndex(ix)
    return ix.tz_localize(None) if ix.tz is not None else ix


def overlap(d, b):
    """How much of the US100 2023-2025 'test' is literally the NQ trades over again."""
    print("Trigger overlap, 2022-12-26 onward -- is US100 a second TEST or a second FEED?")
    print(f"  {'':<38}{'NQ':>6}{'US100':>7}{'same bar':>10}{'+-2 bars':>10}")
    for name in ("full regime + break pullback high", "full regime + reclaim EMA20"):
        tn = _naive(d["df"].index[variants(d)[name]]); tu = _naive(b["df"].index[variants(b)[name]])
        tn = tn[tn >= pd.Timestamp(SPLIT)]; tu = tu[tu >= pd.Timestamp(SPLIT)]
        su = set(tu)
        same = sum(1 for t in tn if t in su)
        near = sum(1 for t in tn if any(t + pd.Timedelta(minutes=15 * k) in su for k in (-2, -1, 0, 1, 2)))
        print(f"  {name:<38}{len(tn):>6}{len(tu):>7}"
              f"{same:>7} {100.0 * same / max(len(tn), 1):>2.0f}%{near:>7} {100.0 * near / max(len(tn), 1):>2.0f}%")


def baseline(d, blk, tag):
    """Regime-only vs rule, across ADX. Isolates the pullback+trigger from the trend filter."""
    F = T.features(d); mod = d["mod"]
    W = (mod >= T.WIN_EARLY[0]) & (mod < T.WIN_EARLY[1])
    PB = T.recent(T.PULLBACKS["below EMA20"](F, d), 6)
    TR = T.TRIGGERS["break pullback high"](F, d)
    print(f"\n{tag}")
    print(f"  {'':<12}{'REGIME ONLY':>24}{'':>6}{'+ PULLBACK AND TRIGGER':>30}")
    print(f"  {'':<12}{'n':>7}{'win%':>8}{'$/trade':>9}{'':>6}{'n':>7}{'win%':>8}{'$/trade':>9}{'rule adds':>11}")
    for a in (0, 20, 25, 28, 30, 35):
        R = T.regime(F, d, adx_min=float(a), slope_min=0.0, use_adx=(a > 0))
        got = []
        for m in (R & W, R & PB & TR & W):
            _t, (p, e, _x, _w, _g) = _sim(d, m)
            k = blk[e]
            got.append((int(k.sum()), 100.0 * float((p[k] > 0).mean()), float(p[k].mean()))
                       if k.sum() >= 20 else None)
        lbl = f"ADX>{a}" if a else "no ADX"
        if got[0] is None or got[1] is None:
            print(f"  {lbl:<12}{'--':>7}"); continue
        (n0, w0, d0), (n1, w1, d1) = got
        print(f"  {lbl:<12}{n0:>7}{w0:>8.1f}{d0:>9.2f}{'':>6}{n1:>7}{w1:>8.1f}{d1:>9.2f}{d1 - d0:>+11.2f}")


def windows(d, blk, tag):
    """The window split on the regime alone -- no rule, so it is a session effect or nothing."""
    F = T.features(d); mod = d["mod"]
    R = T.regime(F, d, adx_min=25.0, slope_min=0.0)
    print(f"\n{tag}   (regime only, no pullback or trigger)")
    print(f"  {'':<16}{'n':>7}{'win%':>8}{'$/trade':>10}")
    for name, (a, z) in (("07:00-09:30", (420, 570)), ("09:30-11:00", (570, 660)),
                         ("07:00-11:00", (420, 660))):
        _t, (p, e, _x, _w, _g) = _sim(d, R & (mod >= a) & (mod < z))
        k = blk[e]
        if k.sum() < 20:
            print(f"  {name:<16}{'--':>7}"); continue
        print(f"  {name:<16}{int(k.sum()):>7}{100.0 * float((p[k] > 0).mean()):>8.1f}"
              f"{float(p[k].mean()):>10.2f}")


def run():
    hdr = (f"  {'':<38}{'block':<0}{'n':>5}{'win%':>8}{'ctrl':>7}{'excess':>8}"
           f"{'$/trade':>9}{'$exc':>8}{'p(win)':>8}{'p($)':>8}")
    print(f"{TF}-minute, 07:00-11:00 New York, {STOP}xATR / {TARGET}R, flat 16:00")
    print("Scored against a MINUTE-OF-DAY matched control (not volatility-matched -- see below).\n")
    d = bars(TF); si, cut, _ = _cut(d)
    for tag, blk in (("NQ research block", si < cut), ("NQ holdout block", si >= cut)):
        print(tag); print(hdr)
        for k, m in variants(d).items():
            _panel(d, blk, k, m)
        print()
    try:
        b = us100.to_bars(TF)
    except FileNotFoundError as e:
        print("US100 SKIPPED --", str(e).split(". ")[0] + ".")
        print("  Re-attach the file, ideally at data/US100_15m.csv, and re-run this module.")
        return
    unseen = np.asarray(b["df"].index < SPLIT)
    for tag, blk in (("US100 2016-2022  -- SIX UNSEEN YEARS, the only independent test", unseen),
                     ("US100 2023-2025  -- same calendar as NQ; NOT independent, see below", ~unseen)):
        print(tag); print(hdr)
        for k, m in variants(b).items():
            _panel(b, blk, k, m)
        print()
    overlap(d, b)
    baseline(b, unseen, "US100 2016-2022 (unseen)")
    baseline(d, si >= cut, "NQ holdout block")
    baseline(d, si < cut, "NQ research block")
    windows(b, unseen, "US100 2016-2022 (unseen)")
    windows(d, si >= cut, "NQ holdout block")
    windows(d, si < cut, "NQ research block")


if __name__ == "__main__":
    run()
