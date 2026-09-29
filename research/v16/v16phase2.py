"""Phases 2-5: is a survivor a mechanism, does the geometry matter, and what does locked say.

Run only after `v16run.py`. It reads that sweep's research-block table and asks the four questions
that separate a rule from an artefact of a 2,196-cell search:

  2. NEIGHBOURHOOD COHERENCE. A win rate that exists at one threshold and nowhere near it is not a
     mechanism. Every survivor's whole rung ladder is printed -- a real edge decays smoothly and a
     fitted one falls off a cliff. Corollary learned the hard way on this branch: over a monotone
     grid a union IS its loosest member, so the ladder is read for the SIZE of the excess, never
     its sign.
  3. GEOMETRY. Stop multiple, exit channel and target are swept AFTER the condition is fixed, not
     jointly with it -- searching them together multiplies the multiplicity by twelve for axes the
     request already pinned. Read by marginal average per axis, never by the top cell.
  4. THE MINUTE-OF-DAY MATCHED CONTROL, as a gate rather than a final check. Random entries with
     the same side, geometry and time-of-day distribution price in drift, costs, barrier width and
     session timing at once. Running this only at the end let four rules reach a holdout they then
     "passed" while failing research.
  5. THE LOCKED BLOCK, READ ONCE, with the multiplicity stated first. Passing on locked while
     FAILING on research is the wrong shape and is treated as a defect, not a result.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
import v16core as C     # noqa: E402
import v16mom as M      # noqa: E402
from v16run import block_masks, _control, fam   # noqa: E402

RNG = np.random.default_rng(20260827)


def ctx(tf, entry_n=30, exit_n=20):
    P = C.prep(tf, entry_n=entry_n, exit_n=exit_n)
    pool = M.build(P["b"])
    res, lock, _ = block_masks(P)
    return P, pool, res, lock


def leg(P, pool, side, blockbar, feat, off, stop_mult=2.0, tp_r=0.0, win=None, flat_mod=0):
    sig_all = C.signals(P, side)
    m = blockbar[sig_all]
    if win is not None:
        lo, hi = win
        md = P["mod"][sig_all]
        m = m & ((md >= lo) & (md < hi) if lo <= hi else ((md >= lo) | (md < hi)))
    sig = sig_all[m]
    O = C.outcomes(P, side, sig, stop_mult=stop_mult, tp_r=tp_r, flat_mod=flat_mod)
    if feat is None:
        keep = np.ones(len(sig), bool)
    else:
        score, center, _offs = pool[feat]
        keep = M.mask_for(score[sig], center, off, side)
    idx = C.take(O, keep)
    return O, idx, C.stats(O, idx, P["sess"]), int(keep.sum())


def mod_control(P, pool, side, blockbar, feat, off, draws=2000, stop_mult=2.0, tp_r=0.0):
    """Random entries matched on MINUTE OF DAY, same side and geometry -- not random signals.

    This is a different null from the sweep's. The sweep asked whether the condition beats a random
    subset of the SAME BREAKOUTS; this asks whether the whole rule beats being in the market at the
    same times of day with the same barriers. A rule can pass one and fail the other, and the
    second is the one that prices in drift."""
    O, idx, s, _k = leg(P, pool, side, blockbar, feat, off, stop_mult, tp_r)
    if s["n"] < 20:
        return s, np.array([]), np.nan
    mod = P["mod"]
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero(blockbar & np.isfinite(P["atr"]) & (P["atr"] > 0))
    elig = elig[elig < len(P["c"]) - 2]
    pool_by = {m: elig[mod[elig] == m] for m in want.index}
    Oa = C.outcomes(P, side, elig.astype(np.int64), stop_mult=stop_mult, tp_r=tp_r)
    pos = {v: i for i, v in enumerate(elig)}
    tot = np.empty(draws)
    for d in range(draws):
        pick = []
        for m, k in want.items():
            p = pool_by[m]
            if len(p):
                pick.append(RNG.choice(p, size=min(k, len(p)), replace=False))
        pick = np.sort(np.concatenate(pick)) if pick else np.array([], int)
        keep = np.zeros(len(elig), bool)
        keep[[pos[v] for v in pick]] = True
        tot[d] = Oa["R"][C.take(Oa, keep)].sum()
    return s, tot, float((tot >= s["R"]).mean())


def geometry(tf, side, feat, off, blockbar_name="res"):
    """Sweep the exit geometry AFTER the condition is fixed. Marginal averages, never the top cell."""
    rows = []
    for exit_n in (10, 15, 20, 25, 30):
        P, pool, res, lock = ctx(tf, exit_n=exit_n)
        bb = res if blockbar_name == "res" else lock
        for sm in (1.5, 2.0, 2.5, 3.0):
            for tp in (0.0, 1.5, 2.0, 3.0):
                _O, _idx, s, _k = leg(P, pool, side, bb, feat, off, stop_mult=sm, tp_r=tp)
                rows.append(dict(exit_n=exit_n, stop=sm, tp=tp, **{k: s.get(k) for k in
                                 ("n", "R", "perR", "pf", "win", "sharpe", "retdd")}))
    return pd.DataFrame(rows)


def marginal(df, axis, label):
    g = df.groupby(axis).agg(cells=("R", "size"), med_R=("R", "median"),
                             med_per=("perR", "median"), med_sharpe=("sharpe", "median"),
                             prof=("R", lambda x: float((x > 0).mean())))
    print(f"\n   {label}")
    print(f"   {'rung':>8}{'cells':>7}{'median R':>11}{'median R/trade':>16}"
          f"{'median Sharpe':>15}{'share profitable':>18}")
    for k, r in g.iterrows():
        print(f"   {k:>8g}{int(r.cells):>7}{r.med_R:>+11.1f}{r.med_per:>+16.4f}"
              f"{r.med_sharpe:>15.2f}{r.prof:>17.0%}")
