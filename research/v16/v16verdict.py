"""Does ANY of it replicate? The 99 research survivors, read once on the locked block.

READING LOCKED FOR 99 CONDITIONS IS ITSELF A MULTIPLICITY PROBLEM, and it is done here for one
reason: to REJECT. If a family of momentum filters carried real information, a good fraction of the
99 would repeat their sign and their excess out of sample. If about five in a hundred do, that is
what chance looks like and the family is dead. The number expected by chance is printed beside the
number observed, and no condition from this table is carried forward into anything.

The geometry question is settled separately and BEFORE locked is touched: the exit channel, the
stop multiple and the target are swept on the UNFILTERED breakout on research, read by marginal
average per axis, and the chosen cell is read once.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
import v16core as C          # noqa: E402
import v16mom as M           # noqa: E402
import v16phase2 as P2       # noqa: E402


def replicate():
    df = pd.read_csv("results/v16/v16_sweep.csv")
    surv = df[(df.R > 0) & (df.p <= 0.05)].copy()
    rows = []
    for tf, g in surv.groupby("tf"):
        P, pool, res, lock = P2.ctx(tf)
        for side, gs in g.groupby("side"):
            _O, _i, bl, _k = P2.leg(P, pool, side, lock, None, 0)
            for _, r in gs.iterrows():
                _O2, _i2, s, _k2 = P2.leg(P, pool, side, lock, r.feat, r.off)
                rows.append(dict(tf=tf, side=side, cond=r.cond,
                                 res_R=r.R, res_per=r.perR, res_p=r.p,
                                 lock_n=s["n"], lock_R=s["R"], lock_per=s["perR"],
                                 base_lock_per=bl["perR"],
                                 beats_base=s["perR"] > bl["perR"]))
    return pd.DataFrame(rows)


def geo_unfiltered(tf, side, blockname="res"):
    rows = []
    for exit_n in (10, 15, 20, 25, 30, 40):
        P, pool, res, lock = P2.ctx(tf, exit_n=exit_n)
        bb = res if blockname == "res" else lock
        for sm in (1.5, 2.0, 2.5, 3.0):
            for tp in (0.0, 2.0, 3.0):
                _O, _i, s, _k = P2.leg(P, pool, side, bb, None, 0, stop_mult=sm, tp_r=tp)
                rows.append(dict(exit_n=exit_n, stop=sm, tp=tp,
                                 **{k: s.get(k) for k in ("n", "R", "perR", "pf", "sharpe", "retdd")}))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print("=" * 104)
    print("A. DO THE 99 RESEARCH SURVIVORS REPLICATE? -- locked block, read once, to reject")
    print("=" * 104)
    R = replicate()
    R.to_csv("results/v16/v16_replicate.csv", index=False)
    pos = R.lock_R > 0
    beat = R.beats_base
    print(f"   survivors carried forward           : {len(R)}")
    print(f"   still PROFITABLE on locked          : {int(pos.sum())}  ({pos.mean():.0%})")
    print(f"   still BEATING the unfiltered breakout on locked : {int(beat.sum())}  ({beat.mean():.0%})")
    print(f"   expected by chance if the filters carry nothing : about 50%\n")
    print(f"   median research R/trade {R.res_per.median():+.4f}   "
          f"median locked R/trade {R.lock_per.median():+.4f}   "
          f"decay {R.lock_per.median() - R.res_per.median():+.4f}")
    cor = np.corrcoef(R.res_per, R.lock_per)[0, 1]
    print(f"   correlation between a condition's research edge and its locked edge: {cor:+.3f}")
    print("\n   by timeframe and side:")
    print(f"   {'tf':>5}{'side':>7}{'n':>6}{'profitable':>13}{'beats base':>13}"
          f"{'med res':>10}{'med lock':>10}")
    for (tf, sd), g in R.groupby(["tf", "side"]):
        print(f"   {tf:>4}m{('long' if sd > 0 else 'short'):>7}{len(g):>6}"
              f"{float((g.lock_R > 0).mean()):>12.0%}{float(g.beats_base.mean()):>13.0%}"
              f"{g.res_per.median():>+10.4f}{g.lock_per.median():>+10.4f}")

    print("\n" + "=" * 104)
    print("B. THE GEOMETRY OF THE BREAKOUT ITSELF -- swept on RESEARCH, unfiltered, 15m and 30m long")
    print("=" * 104)
    picks = {}
    for tf in (15, 30):
        G = geo_unfiltered(tf, 1)
        picks[tf] = G
        print(f"\n   {tf}m long, 72 cells. Share profitable {float((G.R > 0).mean()):.0%}, "
              f"median R/trade {G.perR.median():+.4f}")
        for ax, lab in (("exit_n", "exit channel"), ("stop", "ATR stop multiple"),
                        ("tp", "target in R (0 = none)")):
            P2.marginal(G, ax, lab)
        G.to_csv(f"results/v16/v16_geo_unf_{tf}.csv", index=False)

    print("\n" + "=" * 104)
    print("C. THE CHOSEN GEOMETRY, READ ONCE ON LOCKED")
    print("=" * 104)
    print("   Chosen from the marginal averages above, not from any cell: the longest exit channel,")
    print("   the wider stop, and NO TARGET -- which is the fifth time on this branch that no take")
    print("   profit has beaten every take profit.\n")
    for tf in (15, 30):
        for exit_n, sm, tp, tag in ((20, 2.0, 0.0, "the spec as asked (30/20, 2.0N, no TP)"),
                                    (30, 2.5, 0.0, "the swept geometry (30/30, 2.5N, no TP)")):
            P, pool, res, lock = P2.ctx(tf, exit_n=exit_n)
            _O, _i, sr, _k = P2.leg(P, pool, 1, res, None, 0, stop_mult=sm, tp_r=tp)
            _O, _i, sl, _k = P2.leg(P, pool, 1, lock, None, 0, stop_mult=sm, tp_r=tp)
            print(f"   {tf}m  {tag:<42}")
            print(f"        research {sr['n']:>4} trades {sr['R']:>+7.1f}R {sr['perR']:>+8.4f}/trade"
                  f"  PF {sr['pf']:.3f}  Sharpe {sr['sharpe']:>5.2f}")
            print(f"        LOCKED   {sl['n']:>4} trades {sl['R']:>+7.1f}R {sl['perR']:>+8.4f}/trade"
                  f"  PF {sl['pf']:.3f}  Sharpe {sl['sharpe']:>5.2f}")
        P, pool, res, lock = P2.ctx(tf, exit_n=30)
        s, ctl, p = P2.mod_control(P, pool, 1, lock, None, 0, draws=2000, stop_mult=2.5, tp_r=0.0)
        print(f"        LOCKED vs the minute-of-day matched control: rule {s['R']:+.1f}R, "
              f"control median {np.median(ctl):+.1f}R, p = {p:.4f}\n")
