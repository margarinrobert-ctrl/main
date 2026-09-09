"""The whole battery again, held to 07:00-11:00 New York with a hard flatten at 11:00.

TWO THINGS TO WATCH, both of which this branch has measured many times and neither of which is
assumed here:
  1. A hard flatten has cost 55-86% of the per-trade result on every TREND family measured on this
     branch -- fifteen confirmations. But those systems held for hours to days. THIS one has a
     median hold of 30-75 minutes inside a four-hour box, so the flatten may barely bind. The share
     of trades it actually closes is reported first, because that is what decides whether the
     finding transfers.
  2. 07:00-09:00 is the worst part of the day on all three indices (STUDY_TREND_PULLBACK,
     STUDY_INTRADAY_SESSION, STUDY_SCALP_FILTERS, STUDY_V60). The window asked for starts there.

`US30_LONG_15m` is already New York time -- the 09:30 mean-bar-range step was re-derived on this
feed -- so the window is minutes 420 to 660 and the flatten fires at the 660 open.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dl50 import d50core as D  # noqa: E402

RNG = np.random.default_rng(700)
ND = 400
M0, M1, FLAT = 420, 660, 660
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

    print("ALL HOURS vs 07:00-11:00 + FLATTEN, same rule, same barriers")
    print(f"{'target':>7} {'arm':<26}{'blk':<10}{'n':>6}{'win%':>8}{'need':>8}{'gap':>7}"
          f"{'pts':>9}{'PF':>7}{'hold':>7}{'flat%':>7}")
    for tgt in D.TARGETS:
        _, be = D.breakeven(tgt)
        for nm, m0, m1, fl in (("all hours", -1, -1, -1),
                               ("07:00-11:00 entries", M0, M1, -1),
                               ("07:00-11:00 + flatten", M0, M1, FLAT)):
            eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, tgt, HOLD,
                                             D.COST, m0, m1, mod, fl)
            ts = f.index[eb]
            for bl, sel in (("research", np.asarray(ts < cut)),
                            ("HOLDOUT", np.asarray(ts >= cut))):
                rr = r[sel]
                if len(rr) < 30:
                    continue
                w = float((rr > 0).mean())
                print(f"{tgt:>7.0f} {nm:<26}{bl:<10}{len(rr):>6}{w*100:>7.2f}%{be*100:>7.2f}%"
                      f"{(w-be)*100:>+7.2f}{rr.mean():>9.3f}{D.pf(rr):>7.3f}"
                      f"{np.median(hl[sel])*15:>6.0f}m{float((why[sel]==3).mean())*100:>6.1f}%")
        print()

    # ---- the ADX gate inside the window
    print("ADX AS A VETO INSIDE 07:00-11:00 + FLATTEN, re-simulated vs a random gate")
    reads = {"ADX(14) >= 20": a14 >= 20, "ADX(14) >= 25": a14 >= 25,
             "ADX(14) <= 20": a14 <= 20, "ADX(14) <= 25": a14 <= 25,
             "ADX(28) <= 20": a28 <= 20}
    print(f"{'target':>7} {'reading':<22}{'blk':<10}{'n':>6}{'win%':>8}{'need':>8}"
          f"{'pts':>9}{'PF':>7}{'kept':>7}{'ctl':>9}{'p':>7}")
    for tgt in D.TARGETS:
        _, be = D.breakeven(tgt)
        eb, r, sd, hl, why, amb = D.walk(o, h, l, c, eh, el, ou, od, D.STOP_PTS, tgt, HOLD,
                                         D.COST, M0, M1, mod, FLAT)
        sig = eb - 1
        ts = f.index[eb]
        for bl, sel in (("research", np.asarray(ts < cut)), ("HOLDOUT", np.asarray(ts >= cut))):
            s_all, d_all = sig[sel], sd[sel]
            base = D.walk_at(o, h, l, c, s_all.astype(np.int64), d_all.astype(np.int64),
                             D.STOP_PTS, tgt, HOLD, D.COST, mod, FLAT)
            print(f"{tgt:>7.0f} {'(no gate)':<22}{bl:<10}{len(base):>6}"
                  f"{float((base>0).mean())*100:>7.2f}%{be*100:>7.2f}%"
                  f"{np.nanmean(base):>9.3f}{D.pf(base):>7.3f}{1.0:>7.2f}{'':>9}{'':>7}")
            for nm, m_all in reads.items():
                keep = m_all[s_all]
                if keep.sum() < 30:
                    continue
                q = D.walk_at(o, h, l, c, s_all[keep].astype(np.int64),
                              d_all[keep].astype(np.int64), D.STOP_PTS, tgt, HOLD, D.COST,
                              mod, FLAT)
                k = int(keep.sum())
                ctl = np.empty(ND)
                for i in range(ND):
                    pick = np.sort(RNG.choice(len(s_all), size=k, replace=False))
                    ctl[i] = np.nanmean(D.walk_at(o, h, l, c, s_all[pick].astype(np.int64),
                                                  d_all[pick].astype(np.int64), D.STOP_PTS,
                                                  tgt, HOLD, D.COST, mod, FLAT))
                mu = float(np.nanmean(q))
                print(f"{'':7} {nm:<22}{bl:<10}{int(np.isfinite(q).sum()):>6}"
                      f"{float((q>0).mean())*100:>7.2f}%{be*100:>7.2f}%{mu:>9.3f}"
                      f"{D.pf(q):>7.3f}{keep.mean():>7.2f}{np.nanmedian(ctl):>9.3f}"
                      f"{float(np.mean(ctl >= mu)):>7.3f}")
        print()


if __name__ == "__main__":
    main()
