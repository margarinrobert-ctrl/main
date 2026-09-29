"""Diagnose the null before believing any p-value it produces. Research block only, no new cells.

CLAUDE.md: "DIAGNOSE A NULL BY ITS SPREAD, NOT ONLY ITS MEDIAN -- a control whose median is far
below the rule and which still cannot reject anything is broken." The converse is the risk here:
the same-selectivity random gate draws SUBSETS OF THE SAME SIGNAL SET, so its draws are correlated
with each other and with the unfiltered base, and its spread is narrowed by a finite-population
factor sqrt(1 - K/N). A null that tight can reject an effect that a per-trade MDE says is
indistinguishable -- which is exactly what happened to `atrpct250<=0.5` (control p 0.000, effect
inside its own MDE). Both are correct answers to DIFFERENT questions and both are reported:

  control p   : is this subset better than a RANDOM subset OF THE SAME SIZE drawn from the same
                signal set? (a within-sample ranking question, correlated draws, tight null)
  MDE         : could an effect this size be told from zero given the per-trade dispersion and
                this many trades? (an out-of-sample detectability question, the honest bar)
  day-block   : does the kept set's mean differ from the dropped set's, resampling whole DAYS with
                their trades attached, since trades cluster inside a session?

If a cell clears the control and fails the other two, what has been shown is that the subset ranks
well inside this sample -- not that the effect is measurable.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import base_rates as B  # noqa: E402

CELLS = ["atrpct250<=0.5", "adx<=20", "ema13>34>89", "ema13>48", "adx>=25", "atrpct250>=0.8"]


def dayboot(a_pts, a_day, b_pts, b_day, n=2000, seed=7):
    """Difference of means, resampling whole DAYS with their trades attached, independently in the
    kept and dropped sets."""
    rng = np.random.default_rng(seed)
    da, db = np.unique(a_day), np.unique(b_day)
    ga = {d: a_pts[a_day == d] for d in da}
    gb = {d: b_pts[b_day == d] for d in db}
    out = np.empty(n)
    for i in range(n):
        xa = np.concatenate([ga[d] for d in rng.choice(da, len(da))])
        xb = np.concatenate([gb[d] for d in rng.choice(db, len(db))])
        out[i] = xa.mean() - xb.mean()
    return out


def main():
    f = B.S.load("US30L")
    blk = B.S.blocks(f); win = B.S.window(f)
    X, raw = B.build(f); ok = B.valid_mask(f, X, raw)
    pop = blk["A_research"] & win & ok
    sig0, side0 = B.S.donchian(f, 20, 1)
    k = np.isin(sig0, np.flatnonzero(pop)); sig, side = sig0[k], side0[k]
    print(f"column-name shadow check: {B.shadow_check(['stk','geom','rule','fam','dir','arm'])}"
          f"  (empty = no pandas method is being shadowed)\n")

    for g in B.GEOMS:
        tb = B.run_cell(f, sig, side, g)
        base = B.score(tb, "base", g)
        print(f"{'='*112}\n{g}  unfiltered base {base['pts']:+.3f} pts on n={base['n']}")
        print(f"  {'cell':<18}{'n':>6}{'edge':>8}{'MDE':>8}  | control: {'med':>7}{'p5':>7}"
              f"{'p95':>7}{'sd':>7}{'p':>7}  | dayblock: {'mean':>8}{'p5':>8}{'p95':>8}{'P<=0':>7}")
        for c in CELLS:
            m = X[c].to_numpy()
            t = B.run_cell(f, sig[m[sig]], side[m[sig]], g)
            s = B.score(t, c, g)
            d = B.veto_control(f, sig, side, int(m[sig].sum()), g, n_draw=400, seed=11)
            # kept vs dropped, day-blocked
            nm = ~m
            t2 = B.run_cell(f, sig[nm[sig]], side[nm[sig]], g)
            da = t["ts"].dt.normalize().to_numpy(); db = t2["ts"].dt.normalize().to_numpy()
            bo = dayboot(t["pts"].to_numpy(), da, t2["pts"].to_numpy(), db)
            print(f"  {c:<18}{s['n']:>6}{s['pts']-base['pts']:>8.3f}{s['mde']:>8.3f}  |"
                  f"{np.median(d):>15.3f}{np.percentile(d,5):>7.3f}{np.percentile(d,95):>7.3f}"
                  f"{d.std():>7.3f}{B.pval(s['pts'],d):>7.3f}  |"
                  f"{bo.mean():>16.3f}{np.percentile(bo,5):>8.3f}{np.percentile(bo,95):>8.3f}"
                  f"{(bo<=0).mean():>7.3f}")
        print(f"  control null spread as a fraction of the per-trade MDE tells you which question "
              f"a p-value answered.")


if __name__ == "__main__":
    main()
