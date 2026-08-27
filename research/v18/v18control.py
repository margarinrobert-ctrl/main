"""The matched control, run as the GATE it should be rather than a final flourish.

Random entries with the SAME side, the SAME geometry and the SAME minute-of-day distribution price
in drift, costs, barrier width and session timing at once. A breakout that cannot beat that is not
a breakout edge; it is exposure to being in the market at those times with those barriers.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v18")
import v16core as C          # noqa: E402
import v18multi as M         # noqa: E402

RNG = np.random.default_rng(20260827)


def control(P, block, O, idx, stop, tp_r, draws=1500, side=1):
    if len(idx) < 15:
        return np.array([]), np.nan
    mod = P["mod"]
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero(block & np.isfinite(P["atr"]) & (P["atr"] > 0))
    elig = elig[elig < len(P["c"]) - 2]
    by = {m: elig[mod[elig] == m] for m in want.index}
    Oa = C.outcomes(P, side, elig.astype(np.int64), stop_mult=stop, tp_r=tp_r)
    pos = {v: i for i, v in enumerate(elig)}
    real = float(O["R"][idx].sum())
    tot = np.empty(draws)
    for d in range(draws):
        pick = np.concatenate([RNG.choice(by[m], size=min(k, len(by[m])), replace=False)
                               for m, k in want.items() if len(by[m])])
        keep = np.zeros(len(elig), bool)
        keep[[pos[v] for v in np.sort(pick)]] = True
        tot[d] = Oa["R"][C.take(Oa, keep)].sum()
    return tot, float((tot >= real).mean())


if __name__ == "__main__":
    print("=" * 112)
    print("THE MATCHED CONTROL -- every cell that looked positive, plus the spec for reference")
    print("=" * 112)
    print(f"   {'instrument':<9}{'config':<24}{'block':<10}{'n':>6}{'rule R':>9}"
          f"{'control med':>13}{'control p95':>13}{'p':>8}   verdict")
    CASES = [("US100", 1.5, 2.0), ("US100", 3.0, 0.0), ("NQ", 1.5, 2.0), ("NQ", 3.0, 0.0),
             ("XAU", 3.0, 0.0), ("US30L", 3.0, 0.0)]
    for name, st, tp in CASES:
        P = M.ctx(name)
        res, lock = M.blocks(P)
        lab = f"{st:g}N, {'no TP' if tp == 0 else f'{tp:g}R'}"
        for bn, bb in (("research", res), ("LOCKED", lock)):
            O, i = M.run(P, 1, block=bb, gate=True, stop=st, tp_r=tp)
            ctl, p = control(P, bb, O, i, st, tp)
            if not np.isfinite(p):
                continue
            r = float(O["R"][i].sum())
            v = "beats control" if p <= 0.05 else ("marginal" if p <= 0.15 else "NOT distinguishable")
            print(f"   {name:<9}{lab:<24}{bn:<10}{len(i):>6}{r:>+9.1f}"
                  f"{np.median(ctl):>+13.1f}{np.percentile(ctl, 95):>+13.1f}{p:>8.3f}   {v}")
        print()
