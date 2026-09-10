"""ONE read of B_holdout and ONE of C_forward, on cells named before either block was opened.

DECLARED FROM `run_b1`/`run_b2`, RESEARCH BLOCK ONLY. Nothing here was chosen after a holdout
number was seen, and nothing else will be read on B or C in this study.

  1. The UNFILTERED base at both geometries -- the thing a filter has to improve on.
  2. THE STRUCTURAL CLAIM, which is the one worth testing because it is a DIRECTION and not a
     threshold: on research the marginal average over every usable rung says ADX and ATR both
     prefer the CEILING and EMA prefers the WITH-TREND side, on both geometries, 0%/100% and
     100%/0% of cells beating the base. If that is real it must survive as a marginal, not as a
     cell. Reported as the family x direction marginal on each block.
  3. The three research survivors as individual cells, EACH WITH ITS MIRROR so the direction is
     read and not just the level: atrpct250<=0.5, adx<=20, ema13>34>89.
  4. adx>=25 and the S1 CONV stack, carried as FALSIFIERS: the conventional readings, which
     research says are negative. If they come back positive out of sample the research picture is
     noise in both directions.

WHAT THE READ CANNOT DO. Every research edge measured here is INSIDE its own minimum detectable
effect, and B and C are smaller than A. So this read can only ever say `consistent` or
`inconsistent`; it cannot certify anything, and the MDE is printed beside every row so that is
visible rather than asserted. B is also a heavily spent block -- six studies have read it -- so C
is the only genuinely unread one. `atrpct250<=0.5` in particular is a THIRD read of an ATR-
percentile ceiling on this market (STUDY_V28 found `atr_pct 500<=0.2` at p 0.003/0.003; STUDY_MR30
re-tested it and got research 0.021 -> holdout 0.888 -> forward 0.746, with the MIRROR clearing the
holdout at 0.005). It is a replication attempt, not a discovery.
"""
from __future__ import annotations

import os
import sys
import zlib

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import base_rates as B  # noqa: E402
import run_b2 as R2     # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
CELLS = ["atrpct250<=0.5", "atrpct250>=0.5", "adx<=20", "adx>=20",
         "ema13>34>89", "adx>=25", "ema13>48", "ema13<48"]
FAMOF = R2.FAMOF


def prep(name):
    f = B.S.load(name)
    blk = B.S.blocks(f, name)
    win = B.S.window(f)
    X, raw = B.build(f)
    ok = B.valid_mask(f, X, raw)
    return f, blk, win, X, ok


def read_block(f, mask, X, name, tag, usable):
    pop = mask
    sig0, side0 = B.S.donchian(f, 20, 1)
    keep = np.isin(sig0, np.flatnonzero(pop))
    sig, side = sig0[keep], side0[keep]
    print(f"\n{'='*118}\n{tag}  ({f.index[np.flatnonzero(pop)[0]].date()} .. "
          f"{f.index[np.flatnonzero(pop)[-1]].date()})   "
          f"{len(sig):,} donchian-20 long breakout bars in 07:00-11:00")
    bt = B.base_rates(X, np.isin(np.arange(len(f)), sig), pop).set_index("cond")
    base = {}
    for g in B.GEOMS:
        t = B.run_cell(f, sig, side, g)
        base[g] = B.score(t, "UNFILTERED", g)
        b = base[g]
        print(f"  UNFILTERED {g:>7}: n={b['n']:<5} {b['pts']:+.3f} pts  PF {b['pf']:.3f}  "
              f"win {b['win']:.4f} (be {b['be']:.4f})  MDE +-{b['mde']:.3f}")

    rows = []
    for g in B.GEOMS:
        for c in usable:
            r = R2.cell(f, sig, side, X[c].to_numpy(), g, c, base[g]["pts"], n_draw=400)
            if r:
                r["fam"] = FAMOF(c); r["blk"] = tag
                r["dir"] = "ceiling/counter" if ("<=" in c or c in ("-DI>+DI", "ema13<48")) \
                    else "floor/with"
                r["lift_br"] = float(bt.loc[c, "lift"])
                rows.append(r)
    # the S1 CONV stack, declared as a falsifier
    for g in B.GEOMS:
        m = np.ones(len(f), bool)
        for c in R2.STACKS["S1 CONV"]:
            m &= X[c].to_numpy()
        r = R2.cell(f, sig, side, m, g, "S1 CONV stack", base[g]["pts"], n_draw=400)
        if r:
            r["fam"] = "STACK"; r["blk"] = tag; r["dir"] = "floor/with"
            r["lift_br"] = np.nan
            rows.append(r)
    D = pd.DataFrame(rows)

    print(f"\n  --- 2. THE STRUCTURAL CLAIM: family x direction marginal over all usable rungs ---")
    for g in B.GEOMS:
        sub = D[(D.geom == g) & (D.fam != "STACK")]
        for fam in ("ADX", "ATR", "EMA"):
            for d in ("floor/with", "ceiling/counter"):
                q = sub[(sub.fam == fam) & (sub["dir"] == d)]
                if len(q):
                    print(f"    {g:>7} {fam:<4} {d:<16} n_cells={len(q):<2} "
                          f"mean {q.pts.mean():+7.3f} pts   mean edge {q.lift_pts.mean():+7.3f}   "
                          f"beats base {100*(q.pts>base[g]['pts']).mean():>3.0f}%")

    print(f"\n  --- 3/4. THE DECLARED CELLS AND THEIR MIRRORS ---")
    print(f"  {'cell':<20}{'geom':>8}{'base rate':>11}{'lift':>7}{'kept':>7}{'n':>6}{'pts':>9}"
          f"{'edge':>8}{'MDE':>8}{'PF':>7}{'win':>7}{'be':>7}{'p':>7}   verdict")
    for g in B.GEOMS:
        for c in CELLS + ["S1 CONV stack"]:
            q = D[(D.geom == g) & (D.rule == c)]
            if not len(q):
                print(f"  {c:<20}{g:>8}   -- not usable on this block (base rate outside 10-95%)")
                continue
            r = q.iloc[0]
            v = "inside MDE -- indistinguishable" if abs(r.lift_pts) < r.mde else "OUTSIDE MDE"
            br = bt.loc[c, "p_sig"] if c in bt.index else np.nan
            print(f"  {c:<20}{g:>8}{br:>11.4f}{r.lift_br:>7.3f}{r.kept:>7.3f}{int(r.n):>6}"
                  f"{r.pts:>9.3f}{r.lift_pts:>8.3f}{r.mde:>8.3f}{r.pf:>7.3f}{r.win:>7.4f}"
                  f"{r.be:>7.4f}{r.p:>7.3f}   {v}")
    return D


def main():
    out = []
    f, blk, win, X, ok = prep("US30L")
    # The usable set is FROZEN from A_research. Recomputing it per block would let the holdout
    # decide which rungs are tested, which is selection inside the read.
    sigA, _ = B.S.donchian(f, 20, 1)
    popA = blk["A_research"] & win & ok
    kA = np.isin(sigA, np.flatnonzero(popA))
    btA = B.base_rates(X, np.isin(np.arange(len(f)), sigA[kA]), popA).set_index("cond")
    usable = [c for c in X.columns if 0.10 <= btA.loc[c, "p_sig"] <= 0.95]
    print(f"usable rungs FROZEN from A_research: {len(usable)} of {len(X.columns)}")
    out.append(read_block(f, blk["B_holdout"] & win & ok, X, "US30L",
                          "B_holdout (US30L, one read)", usable))
    g, blkI, winI, XI, okI = prep("US30I")
    out.append(read_block(g, blkI["C_forward"] & winI & okI, XI,
                          "C_forward (US30_ISO, DIFFERENT PROVIDER, one read)", usable))
    D = pd.concat(out, ignore_index=True)
    D.to_csv(os.path.join(OUT, "b3_holdout.csv"), index=False)
    print(f"\n{'='*118}\nwrote b3_holdout.csv -- {len(D)} rows. "
          f"Cells clearing p<=0.05: {(D.p<=0.05).sum()} of {len(D)} "
          f"(chance {0.05*len(D):.1f}). No further read of B or C in this study.")


if __name__ == "__main__":
    main()
