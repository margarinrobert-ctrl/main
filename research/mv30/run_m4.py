"""PART C ALONE: the adaptive hold cap, and what it is worth against its own shuffled twin.

Split out of `run_m3` after a kwarg fix so the expensive veto sweep is not re-run. Same forecast,
same base, same blocks. `STUDY_V67`'s rule is the point of the third arm: a forecast must beat its
own NOISE TWIN, not merely beat the baseline, because a policy that simply spreads the hold caps
out will look different from a constant whether or not the forecast carries information.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mv30 import mv30core as C  # noqa: E402
from mr30 import mr30core as M  # noqa: E402
from v67 import v67core as V67  # noqa: E402
from mv30.run_m2 import donchian_long, clean  # noqa: E402
from mv30.run_m3 import resim  # noqa: E402


def by_cap(f, sig, side, caps):
    parts = []
    for cap in np.unique(caps):
        q = caps == cap
        t = resim(f, sig[q], side[q], hold=int(cap))
        if len(t):
            parts.append(t)
    return pd.concat(parts) if parts else pd.DataFrame(dict(pct=[]))


def main():
    from sklearn.linear_model import Ridge
    fL = C.frame("US30L"); XL = C.features(fL); bL = M.blocks(fL)
    fI = C.frame("US30I"); XI = C.features(fI); bI = M.blocks(fI, "US30I")
    sigL, sdL = donchian_long(fL)
    sigI, sdI = donchian_long(fI)

    D = C.D_of(fL); T = V67.build_targets(D, 48); y = T["ttb"]
    A, med = clean(XL)
    res = bL["A_research"]
    tr = res & np.isfinite(y); tr[:800] = False
    mu_, sx = A[tr].mean(0), A[tr].std(0); sx[sx <= 0] = 1
    Z = np.clip((A - mu_) / sx, -8, 8)
    rg = Ridge(alpha=50.0).fit(Z[tr], y[tr])
    yhat = rg.predict(Z)
    AI, _ = clean(XI, med)
    yhatI = rg.predict(np.clip((AI - mu_) / sx, -8, 8))

    okA = np.isfinite(y) & res
    okB = np.isfinite(y) & bL["B_holdout"]
    print(f"ridge time-to-touch forecast: research IC {V67.ic(yhat[okA], y[okA]):+.4f}   "
          f"holdout IC {V67.ic(yhat[okB], y[okB]):+.4f}")
    print("(among the strongest out-of-sample ICs on this branch -- V67's was 0.7065 and it")
    print(" bought zero, so the only question that matters is the decision table below)\n")

    rngs = np.random.default_rng(3)

    def shuf(v):
        w = v.copy(); b = 500; nb = len(w) // b
        w[:nb * b] = np.roll(w[:nb * b].reshape(nb, b), int(rngs.integers(1, nb)), axis=0).ravel()
        return w

    print(f"{'block':<16}{'policy':<26}{'n':>6}{'mean %':>9}{'PF':>8}{'total %':>10}"
          f"{'med hold':>10}")
    for feed, fr, bb, sg, sd_, fc in (("US30L", fL, bL, sigL, sdL, yhat),
                                      ("US30I", fI, bI, sigI, sdI, yhatI)):
        fs = shuf(fc)
        for bn, mask in bb.items():
            sel = np.array([bool(mask[i]) for i in sg])
            s0, d0 = sg[sel], sd_[sel]
            if len(s0) < 150:
                continue
            for nm, hv in (("fixed 96", None), ("adaptive 2x ttb_hat", fc),
                           ("adaptive, SHUFFLED fc", fs)):
                if hv is None:
                    t = resim(fr, s0, d0, hold=96)
                else:
                    caps = np.clip(np.round(2.0 * hv[s0]), 8, 240).astype(int)
                    t = by_cap(fr, s0, d0, caps)
                print(f"{feed + ' ' + bn[0]:<16}{nm:<26}{len(t):>6}{t.pct.mean():>9.4f}"
                      f"{M.pf(t.pct):>8.3f}{t.pct.sum():>10.2f}"
                      f"{np.median(t.hold):>10.0f}")
            print()


if __name__ == "__main__":
    main()
