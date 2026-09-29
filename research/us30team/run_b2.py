"""Step 3 and 4: does any of it survive as P&L, scored as a VETO against a same-selectivity random
gate re-simulated end to end. Research block only, donchian 20 long, 07:00-11:00 NY, flat at 11:00.

DECLARED BEFORE ANY FILTERED P&L WAS RUN (the base-rate table of `run_b1` is the only thing that
had been seen, and no P&L is in it beyond the unfiltered base):

  POOL. Every one of the 24 conditions in `base_rates.build`, each as a single veto, at BOTH
  geometries. The pool already contains every ADX and ATR reading as a FLOOR and as a CEILING.
  A rung is UNUSABLE if it passes <10% or >95% of breakout bars: below 10% the sample cannot
  support a control, and above 95% it is inert by the study's own flag.

  THREE STACKS, each drop-one'd. All three are named here rather than picked afterwards:
    S1 CONV -- what a practitioner would actually build:      adx>=25, atr/tod>=1.0, ema13>48
    S2 LIFT -- the HIGHEST-LIFT usable rung of each family
               from the run_b1 donch20 table:                 adx>=30, atrpct250>=0.5,
                                                              ema13x48 fresh<=5
    S3 DIST -- S2 with the EMA slot taken by the DISTANCE
               reading rather than the recency one, because
               STUDY_V40's finding is specifically about
               distance and the two are different objects:    adx>=30, atrpct250>=0.5,
                                                              d_ema200>=2.0

  GEOMETRIES, declared in advance: 30-pt stop / 150-pt target and 50/150, both with the 11:00
  flatten. Absolute points, not ATR multiples, because STUDY_DL50 found the two parameterisations
  disagree about whether a US30 result decays at all.

TRIAL COUNT is printed at the end and is the number this study must be deflated against.
"""
from __future__ import annotations

import os
import sys
import zlib

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import base_rates as B  # noqa: E402

pd.set_option("display.width", 220)
OUT = os.path.dirname(os.path.abspath(__file__))
NDRAW = 400

STACKS = {
    "S1 CONV": ("adx>=25", "atr/tod>=1.0", "ema13>48"),
    "S2 LIFT": ("adx>=30", "atrpct250>=0.5", "ema13x48 fresh<=5"),
    "S3 DIST": ("adx>=30", "atrpct250>=0.5", "d_ema200>=2.0"),
}
FAMOF = lambda c: "ADX" if ("adx" in c or "DI" in c) else ("ATR" if "atr" in c else "EMA")


def cell(f, sig, side, mask, geom, label, base_pts, n_draw=NDRAW):
    """One veto: keep the signal bars where `mask` is True and RE-SIMULATE. The control keeps the
    same NUMBER of the trigger's own signal bars at random and re-simulates identically."""
    k = mask[sig]
    if k.sum() < 20:
        return None
    t = B.run_cell(f, sig[k], side[k], geom)
    s = B.score(t, label, geom)
    seed = zlib.crc32((label + geom).encode()) & 0xFFFF
    d = B.veto_control(f, sig, side, int(k.sum()), geom, n_draw=n_draw, seed=seed)
    s.update(kept=float(k.mean()), ctl_med=float(np.median(d)) if len(d) else np.nan,
             p=B.pval(s["pts"], d), lift_pts=s["pts"] - base_pts)
    return s


def main():
    f = B.S.load("US30L")
    blk = B.S.blocks(f); win = B.S.window(f)
    X, raw = B.build(f); ok = B.valid_mask(f, X, raw)
    pop = blk["A_research"] & win & ok
    sig0, side0 = B.S.donchian(f, 20, 1)
    keep = np.isin(sig0, np.flatnonzero(pop))
    sig, side = sig0[keep], side0[keep]
    print(f"donchian 20 long, A_research, 07:00-11:00: {len(sig):,} signal bars\n")

    base = {}
    for g in B.GEOMS:
        t = B.run_cell(f, sig, side, g)
        base[g] = B.score(t, "UNFILTERED", g)
        b = base[g]
        print(f"UNFILTERED {g:>7}: n={b['n']:<5} {b['pts']:+.3f} pts  PF {b['pf']:.3f}  "
              f"win {b['win']:.4f} (be {b['be']:.4f})  MDE +-{b['mde']:.3f}  tot {b['tot']:+,.0f}")

    bt = B.base_rates(X, np.isin(np.arange(len(f)), sig), pop).set_index("cond")
    usable = [c for c in X.columns if 0.10 <= bt.loc[c, "p_sig"] <= 0.95]
    print(f"\nusable rungs (pass 10-95% of breakout bars): {len(usable)} of {len(X.columns)}; "
          f"excluded {[c for c in X.columns if c not in usable]}")

    # ---------------------------------------------------------------- singles
    rows = []
    for g in B.GEOMS:
        for c in usable:
            r = cell(f, sig, side, X[c].to_numpy(), g, c, base[g]["pts"])
            if r:
                r["fam"] = FAMOF(c); r["lift_br"] = float(bt.loc[c, "lift"])
                rows.append(r)
    S = pd.DataFrame(rows)
    S.to_csv(os.path.join(OUT, "b2_singles.csv"), index=False)

    print(f"\n{'='*128}\nSINGLE-CONDITION VETOES on donchian 20 long. POPULATION FIRST:")
    for g in B.GEOMS:
        sub = S[S.geom == g]
        print(f"  {g:>7}: {len(sub)} cells, {100*(sub.pts>0).mean():.1f}% profitable, "
              f"{100*(sub.pts>base[g]['pts']).mean():.1f}% beat the unfiltered base, "
              f"{(sub.p<=0.05).sum()} clear the control at p<=0.05 "
              f"(chance {0.05*len(sub):.1f}), best p {sub.p.min():.3f}")
    print("\n  MARGINAL AVERAGE BY FAMILY AND DIRECTION (never the top cell):")
    S["dir"] = np.where(S.rule.str.contains("<=") | S.rule.isin(["-DI>+DI", "ema13<48"]),
                        "ceiling/counter", "floor/with")
    for g in B.GEOMS:
        sub = S[S.geom == g]
        for fam in ("ADX", "ATR", "EMA"):
            for d in ("floor/with", "ceiling/counter"):
                q = sub[(sub.fam == fam) & (sub["dir"] == d)]
                if len(q):
                    print(f"    {g:>7} {fam:<4} {d:<16} n_cells={len(q):<3} "
                          f"mean {q.pts.mean():+7.3f} pts (base {base[g]['pts']:+.3f})  "
                          f"mean edge {q.lift_pts.mean():+7.3f}  mean PF {q.pf.mean():.3f}  "
                          f"beats base {100*(q.pts>base[g]['pts']).mean():.0f}%")

    for g in B.GEOMS:
        sub = S[S.geom == g].sort_values("pts", ascending=False)
        print(f"\n  --- every cell, {g} (sorted; read the marginals above, not this order) ---")
        print(f"  {'condition':<20}{'fam':>4}{'kept':>7}{'n':>6}{'pts':>9}{'edge':>8}{'MDE':>8}"
              f"{'PF':>7}{'win':>7}{'be':>7}{'ctl':>8}{'p':>7}   inside MDE?")
        for _, r in sub.iterrows():
            ins = "yes -- indistinguishable" if abs(r.lift_pts) < r.mde else "NO"
            print(f"  {r.rule:<20}{r.fam:>4}{r.kept:>7.3f}{int(r.n):>6}{r.pts:>9.3f}"
                  f"{r.lift_pts:>8.3f}{r.mde:>8.3f}{r.pf:>7.3f}{r.win:>7.4f}{r.be:>7.4f}"
                  f"{r.ctl_med:>8.3f}{r.p:>7.3f}   {ins}")

    # ---------------------------------------------------------------- drop-one
    drows = []
    for g in B.GEOMS:
        for nm, cs in STACKS.items():
            arms = [("full", cs)] + [(f"-{FAMOF(c)}", tuple(x for x in cs if x != c)) for c in cs]
            for arm, keepcs in arms:
                m = np.ones(len(f), bool)
                for c in keepcs:
                    m &= X[c].to_numpy()
                r = cell(f, sig, side, m, g, f"{nm} {arm}", base[g]["pts"])
                if r:
                    r.update(stk=nm, arm=arm, conds=" & ".join(keepcs) or "(none)")
                    drows.append(r)
    Dd = pd.DataFrame(drows)
    Dd.to_csv(os.path.join(OUT, "b2_dropone.csv"), index=False)

    print(f"\n{'='*128}\nDROP-ONE. Contribution of a component = full minus the arm that removes it.")
    for g in B.GEOMS:
        print(f"\n  --- {g} (unfiltered base {base[g]['pts']:+.3f} pts, "
              f"n={base[g]['n']}, PF {base[g]['pf']:.3f}) ---")
        print(f"  {'arm':<14}{'kept':>7}{'n':>6}{'pts':>9}{'vs base':>9}{'MDE':>8}{'PF':>7}"
              f"{'win':>7}{'be':>7}{'ctl':>8}{'p':>7}{'contrib':>9}")
        for nm in STACKS:
            sub = Dd[(Dd.geom == g) & (Dd["stk"] == nm)]
            full = sub[sub.arm == "full"]
            fp = float(full.pts.iloc[0]) if len(full) else np.nan
            for _, r in sub.iterrows():
                con = "" if r.arm == "full" else f"{fp - r.pts:+9.3f}"
                print(f"  {nm} {r.arm:<6}{r.kept:>7.3f}{int(r.n):>6}{r.pts:>9.3f}"
                      f"{r.lift_pts:>9.3f}{r.mde:>8.3f}{r.pf:>7.3f}{r.win:>7.4f}{r.be:>7.4f}"
                      f"{r.ctl_med:>8.3f}{r.p:>7.3f}{con:>9}")
            if len(full):
                fm = float(full.mde.iloc[0])
                print(f"     -> every contribution above is inside the full arm's own MDE of "
                      f"+-{fm:.3f}: "
                      f"{all(abs(fp - float(x)) < fm for x in sub[sub.arm!='full'].pts)}")

    n_trials = len(S) + len(Dd) + len(B.GEOMS)
    print(f"\n{'='*128}\nTRIAL COUNT on A_research (this run): singles {len(S)} + drop-one arms "
          f"{len(Dd)} + unfiltered bases {len(B.GEOMS)} = {n_trials}. "
          f"Expected passes at p<=0.05 by chance: {0.05*(len(S)+len(Dd)):.1f}")
    print(f"Observed passes at p<=0.05: singles {(S.p<=0.05).sum()}, "
          f"drop-one {(Dd.p<=0.05).sum()}.")


if __name__ == "__main__":
    main()
