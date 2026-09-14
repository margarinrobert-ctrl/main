"""The best Donchian breakout, 07:00-11:00 New York, BOTH SIDES, direction set by the HMM regime.

WHY THE REGIME SETS THE DIRECTION RATHER THAN THE OPTIMISER. This branch has learned eleven times
that a search allowed to pick a side picks LONG, because every sample here rose. Letting the HMM's
causal state decide -- long in Bull, short in Bear -- spends no degrees of freedom on direction:
the rule is symmetric and the data chooses.

WHAT IS ALREADY KNOWN ABOUT THIS WINDOW, so the result is read against it rather than in a vacuum:
  * 07:00-09:00 is the WORST part of the day on all three indices (-0.18 to -0.43 R/trade), and
    10:00-11:00 is the only positive hour (`STUDY_TREND_PULLBACK`).
  * "If trading 07:00-11:00 New York, trade 09:30-11:00" -- same rule, 4x the per-trade result on
    44% fewer trades. So 07:00-11:00 is tested here BECAUSE IT WAS ASKED FOR, with 09:30-11:00
    printed beside it as the comparison that matters.
  * The cost model does not widen the pre-RTH spread, so the real penalty on the early block is
    LARGER than anything measured below.
  * The short side has lost on every block tested as-specified (p 0.65-0.96) on rising samples.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v21")
sys.path.insert(0, "research/v24")
sys.path.insert(0, "research/v27")
import v16core as C           # noqa: E402
import v21regime as RG        # noqa: E402
import v24ma as V             # noqa: E402
import v27run as R            # noqa: E402

WINDOWS = (("07:00-11:00 (as asked)", 420, 660), ("09:30-11:00 (the comparison)", 570, 660),
           ("all hours", 0, 1440))


def control(P, O, pool, k, draws=300, seed=31):
    rng = np.random.default_rng(seed)
    n = len(O["sig"])
    out = np.empty(draws)
    for d in range(draws):
        m = np.zeros(n, bool)
        m[rng.choice(pool, size=k, replace=False)] = True
        st = V.stat(P, O, m)
        out[d] = st["pf"] if st else np.nan
    return out[np.isfinite(out)]


def prep_market(name):
    if name == "NQ":
        P = C.prep(30, entry_n=30, exit_n=20, cost_mult=1.44)
        b = dict(ts=P["ts"], o=P["o"], h=P["h"], l=P["l"], c=P["c"], sess=P["sess"], mod=P["mod"])
        return P, b
    b15 = R.load_us30()
    df = pd.DataFrame(b15)
    df["blk"] = np.arange(len(df)) // 2
    g = df.groupby("blk")
    b = dict(ts=g.ts.first().to_numpy(), o=g.o.first().to_numpy(), h=g.h.max().to_numpy(),
             l=g.l.min().to_numpy(), c=g.c.last().to_numpy(), sess=g.sess.first().to_numpy(),
             mod=g["mod"].first().to_numpy())
    P = C.prep_from_bars(b, entry_n=30, exit_n=20, cost_mult=1.44) if hasattr(C, "prep_from_bars") else None
    return P, b


if __name__ == "__main__":
    for mkt in ("NQ",):
        P, b = prep_market(mkt)
        u = np.unique(P["sess"])
        cut = u[int(len(u) * 0.65)]
        s, _, _, _, _ = R.hmm_states(b, cut, seed=3)          # CAUSAL
        sL, _, _, _, _ = R.hmm_states(b, cut, seed=3, leaky=True)
        ch = RG.chop(P["h"], P["l"], P["c"], 14)
        res_a, lk_a = V.blocks(P["sess"])

        V.hdr(f"{mkt} 30m -- Donchian 30/20 + CHOP<=40, 2.0N stop, no target, BOTH SIDES,"
              f" direction set by the CAUSAL HMM regime")
        print(f"   {'window':<30}{'side / regime':<22}{'RESEARCH':>24}{'|':>3}{'LOCKED':>24}")
        print(f"   {'':<30}{'':<22}{'n':>6}{'PF':>8}{'Shp':>5}{'ctlp':>5}{'|':>3}"
              f"{'n':>6}{'PF':>8}{'Shp':>5}{'ctlp':>5}")
        for wlab, w0, w1 in WINDOWS:
            for side, regime in ((1, "Bull"), (-1, "Bear"), (1, "any"), (-1, "any")):
                sig = C.signals(P, side)
                O = C.outcomes(P, side, sig, stop_mult=2.0, tp_r=0.0)
                inw = (P["mod"][sig] >= w0) & (P["mod"][sig] < w1)
                cm = np.isfinite(ch[sig]) & (ch[sig] <= 40)
                rm = np.ones(len(sig), bool) if regime == "any" else (s[sig] == regime)
                ok = O["xb"] >= 0
                lab = ("LONG " if side > 0 else "SHORT") + ("  regime " + regime if regime != "any"
                                                            else "  no regime")
                line = f"   {wlab:<30}{lab:<22}"
                for blk in (res_a[sig], lk_a[sig]):
                    keep = ok & inw & cm & rm & blk
                    st = V.stat(P, O, keep)
                    if st is None:
                        line += f"{'--':>6}{'':>8}{'':>5}{'':>5}"
                    else:
                        pool = np.flatnonzero(ok & inw & cm & blk)
                        cp = control(P, O, pool, int(keep.sum()))
                        pv = float((cp >= st["pf"]).mean()) if len(cp) else np.nan
                        line += f"{st['n']:>6}{st['pf']:>8.3f}{st['sharpe']:>5.2f}{pv:>5.2f}"
                    if blk is res_a[sig]:
                        line += f"{'|':>3}"
                print(line)
            print()
