"""How many of the 777,600 configurations are profitable on BOTH markets in BOTH blocks -- and
of those, how many beat their own risk-matched control out of sample.

This is the headline number. A per-market or per-block count can always be met by drift; four
independent sign requirements plus a control cannot.
"""
from __future__ import annotations

import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from research.v58 import v58ib as V                                     # noqa: E402
from research.v58.run_v58 import MK, aggregate, MIN_N                   # noqa: E402
from research.v58.v58judge import load, control_p, label                # noqa: E402


def main():
    data = {mk: load(mk) for mk in MK}
    F = {mk: V.build(mk) for mk in MK}
    lockm = {mk: aggregate(data[mk][1], data[mk][2], data[mk][3], data[mk][4],
                           data[mk][6]) for mk in MK}
    tot = 0
    keep = []
    for side in ("long", "short", "both"):
        ok = np.ones((V.NF, V.NG), bool)
        pos = np.ones((V.NF, V.NG), bool)
        for mk in MK:
            ok &= (data[mk][0][side]["n"] >= MIN_N) & (lockm[mk][side]["n"] >= 30)
            pos &= (data[mk][0][side]["perTrade"] > 0) & (lockm[mk][side]["perTrade"] > 0)
        tot += int(ok.sum())
        f, g = np.where(ok & pos)
        for a, b in zip(f, g):
            keep.append((side, int(a), int(b)))
    print(f"scorable on both markets in both blocks : {tot:,}")
    print(f"profitable in ALL FOUR                  : {len(keep):,} "
          f"({len(keep)/max(tot,1)*100:.2f}%)")

    # the wrong-shape check and the control, on whatever survived
    surv = []
    for side, f, g in keep:
        r = min(data[mk][0][side]["perTrade"][f, g] for mk in MK)
        l = min(lockm[mk][side]["perTrade"][f, g] for mk in MK)
        surv.append((r, l, side, f, g))
    if surv:
        wrong = sum(1 for r, l, *_ in surv if l > r)
        print(f"  of those, LOCKED BETTER THAN RESEARCH  : {wrong:,} "
              f"({wrong/len(surv)*100:.0f}%) -- the wrong shape; a rule chosen on research "
              f"should look better there")
        surv.sort(key=lambda x: -min(x[0], x[1]))
        print(f"\n  the {min(20,len(surv))} strongest, read against their control ON LOCKED:")
        nclear = 0
        for r, l, side, f, g in surv[:20]:
            li = g // 450
            ps = []
            for mk in MK:
                m, A, P, mL, mS, res, lock = data[mk]
                act = lockm[mk][side]["perTrade"][f, g]
                pp = []
                for s2 in (["long", "short"] if side == "both" else [side]):
                    si = 0 if s2 == "long" else 1
                    msk = (mL if si == 0 else mS)[:, f, li]
                    d = lock[np.isfinite(A[si][lock, g]) & msk[lock]]
                    if len(d) >= 15:
                        p, _, _ = control_p(F[mk], g, si, d, V.COST_PTS[mk], act)
                        pp.append(p)
                ps.append(max(pp) if pp else 1.0)
            p = max(ps)
            nclear += int(p <= 0.05)
            print(f"    res {r:+.4f}  lock {l:+.4f}  lock ctrl p {p:.3f}  {label(g, f, side)}")
        print(f"\n  {nclear}/{min(20,len(surv))} beat the risk-matched control on locked at p <= 0.05")


if __name__ == "__main__":
    main()
