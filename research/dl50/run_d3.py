"""ADX on the fixed-point barrier system: base rate first, then as a GATE in BOTH directions.

WHY BOTH DIRECTIONS. This branch has moved ADX's sign five times -- it is the 2nd-best swing
condition in STUDY_SCALP_REQUIREMENTS and NEGATIVE at scalp geometry; it inverts out of sample in
V39/V52/V60; it fails all four rungs in V21 while CHOP clears; and STUDY_TURTLE_15M found the
Turtle's own ADX CEILING only works inverted, as a floor. The standing rule that follows is: run
both directions or run neither.

WHY THE BASE RATE COMES FIRST. A Donchian break filtered by an EMA200 state is already a trend
event. RSI>=55 passes 94.7% of breakout bars, Aroon 100.0%, MACD 99.8%, MFI 91.7% -- four
measurements of the same mechanism. If ADX>=25 passes ~95% of these signal bars it is the trigger
restated and no backtest is needed.

The gate is scored as a VETO and RE-SIMULATED: refusing a signal releases the position lock and
admits a later one, so splitting an existing trade list gives a different and flattering answer.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402

RNG = np.random.default_rng(1414)
ND = 400
HOLD = 96


def main():
    f = D.load(15)
    sess = np.unique(f.index.normalize())
    cut = pd.Timestamp(sess[int(0.75 * len(sess))])
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    mod = f["mod"].to_numpy().astype(np.int64)
    eh, el, ou, od, _ = D.signals(f, 20, 200)
    a14, pdi, ndi = D.adx(f, 14)
    a28, _, _ = D.adx(f, 28)

    # ---------------------------------------------------------------- base rates
    eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, 150.0, HOLD,
                                     D.COST, -1, -1, mod)
    sig = eb - 1
    ts = f.index[eb]
    res = np.asarray(ts < cut)
    print("BASE RATE ON THE TRIGGER'S OWN BARS -- share passing, and the lift over all bars")
    print(f"{'reading':<22}{'signal bars':>13}{'all bars':>11}{'lift':>8}")
    reads = {}
    for nm, v, thr, up in (("ADX(14) >= 20", a14, 20, True), ("ADX(14) >= 25", a14, 25, True),
                           ("ADX(14) >= 30", a14, 30, True), ("ADX(14) <= 20", a14, 20, False),
                           ("ADX(14) <= 25", a14, 25, False), ("ADX(28) >= 20", a28, 20, True),
                           ("ADX(28) <= 20", a28, 20, False)):
        m_all = (v >= thr) if up else (v <= thr)
        ok = np.isfinite(v)
        sa = float(np.nanmean(m_all[ok]))
        ss = float(np.nanmean(m_all[sig]))
        reads[nm] = m_all
        print(f"{nm:<22}{ss:>12.3f}{sa:>11.3f}{ss/max(sa,1e-9):>8.2f}")

    # ---------------------------------------------------------------- the gate, re-simulated
    print(f"\nADX AS A VETO, re-simulated, against a random gate keeping the same share")
    print(f"{'target':>7} {'reading':<22}{'blk':<10}{'n':>6}{'win%':>8}{'need':>8}"
          f"{'pts':>9}{'PF':>7}{'kept':>7}{'ctl':>9}{'p':>7}")
    for tgt in D.TARGETS:
        _, be = D.breakeven(tgt)
        eb0, r0, sd0, _, _, _ = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, tgt, HOLD,
                                       D.COST, -1, -1, mod)
        sig0 = eb0 - 1
        ts0 = f.index[eb0]
        for bl, sel in (("research", np.asarray(ts0 < cut)), ("HOLDOUT", np.asarray(ts0 >= cut))):
            s_all, d_all = sig0[sel], sd0[sel]
            base = D.walk_at(o, h, l, c, s_all.astype(np.int64), d_all.astype(np.int64),
                             D.STOP_PTS, tgt, HOLD, D.COST)
            bw = float((base > 0).mean())
            print(f"{tgt:>7.0f} {'(no gate)':<22}{bl:<10}{len(base):>6}{bw*100:>7.2f}%"
                  f"{be*100:>7.2f}%{np.nanmean(base):>9.3f}{D.pf(base):>7.3f}{1.0:>7.2f}"
                  f"{'':>9}{'':>7}")
            for nm, m_all in reads.items():
                keep = m_all[s_all]
                if keep.sum() < 40:
                    continue
                q = D.walk_at(o, h, l, c, s_all[keep].astype(np.int64),
                              d_all[keep].astype(np.int64), D.STOP_PTS, tgt, HOLD, D.COST)
                k = int(keep.sum())
                ctl = np.empty(ND)
                for i in range(ND):
                    pick = np.sort(RNG.choice(len(s_all), size=k, replace=False))
                    ctl[i] = np.nanmean(D.walk_at(o, h, l, c, s_all[pick].astype(np.int64),
                                                  d_all[pick].astype(np.int64),
                                                  D.STOP_PTS, tgt, HOLD, D.COST))
                mu = float(np.nanmean(q))
                print(f"{'':7} {nm:<22}{bl:<10}{int(np.isfinite(q).sum()):>6}"
                      f"{float((q>0).mean())*100:>7.2f}%{be*100:>7.2f}%{mu:>9.3f}"
                      f"{D.pf(q):>7.3f}{keep.mean():>7.2f}{np.nanmedian(ctl):>9.3f}"
                      f"{float(np.mean(ctl >= mu)):>7.3f}")
        print()


if __name__ == "__main__":
    main()
