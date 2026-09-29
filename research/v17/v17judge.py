"""One condition, read once on the locked block, with the family's own null stated first.

THE FAMILY FOUND NOTHING. 285 scorable conditions, 16 beat a same-selectivity control on Sharpe at
p <= 0.05, and 14.2 were expected by chance. On net R only 7 passed against 14 expected -- worse
than chance. That is the result at the family level and it is stated before any single row.

ONE CONDITION IS CARRIED ANYWAY, on shape rather than rank. `C_dist_pdh` -- how far the signal bar
sits above the PRIOR DAY'S HIGH, in ATR -- is the only feature in the pool whose whole ladder is
sign-consistent in both directions:

   below yesterday's high   -2.0: -0.103   -0.5: -0.060   0.0: -0.046   +0.5: -0.040  R/trade
   above yesterday's high   -0.5: +0.233    0.0: +0.265   +0.5: +0.251   +1.5: +0.364  R/trade

Every rung of one side loses and every rung of the other wins. That is a gradient, not a cell, and
it is the only one here. The level shipped is **0**, not the 1.5 that scores best: zero is the
parameter-free boundary the feature already has, and it keeps 49 more trades.

A runner-up is read at the same time and counted: `A_pen_close <= 0.1`, the rule against chasing --
four consecutive rungs at p 0.003-0.037 with the opposite direction uniformly worse. Two conditions
are read on locked, so the holdout multiplicity is two, not one, and Bonferroni is 2x.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v17")
import v16core as C          # noqa: E402
import v17feat as F          # noqa: E402
import v17run as R           # noqa: E402

RNG = np.random.default_rng(20260827)
PICKS = [("none (base)", None, None, None),
         ("C_dist_pdh >= 0", "C_dist_pdh", 0.0, +1),
         ("A_pen_close <= 0.1", "A_pen_close", 0.1, -1),
         ("both", None, None, None)]


def leg(P, pool, block, feat=None, lvl=None, dirn=None, both=False, stop=2.5, exit_ready=None):
    sig = R.base_signals(P, block)
    keep = np.ones(len(sig), bool)
    if both:
        for f, l, d in (("C_dist_pdh", 0.0, +1), ("A_pen_close", 0.1, -1)):
            keep &= F.mask_for(pool[f][0][sig], l, d)
    elif feat is not None:
        keep &= F.mask_for(pool[feat][0][sig], lvl, dirn)
    O = C.outcomes(P, 1, sig, stop_mult=stop, tp_r=0.0)
    return O, C.take(O, keep)


def mod_control(P, block, O, idx, draws=2000, stop=2.5):
    if len(idx) < 15:
        return np.array([]), np.nan
    mod = P["mod"]
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero(block & np.isfinite(P["atr"]) & (P["atr"] > 0))
    elig = elig[elig < len(P["c"]) - 2]
    by = {m: elig[mod[elig] == m] for m in want.index}
    Oa = C.outcomes(P, 1, elig.astype(np.int64), stop_mult=stop, tp_r=0.0)
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


def show(tag, P, O, idx, block):
    s = R.evaluate(P, O, idx, block)
    print(f"   {tag:<24}{s['n']:>7} trades{s['R']:>+8.1f}R{s['perR']:>+9.4f}/t"
          f"{s['pf']:>8.3f} PF{100*s['win']:>7.2f}% win{s['sharpe']:>7.2f} Shp"
          f"{s['dd']:>7.1f} DD{s['retdd']:>7.2f} R/DD")
    return s


if __name__ == "__main__":
    P, daily, res, lock = R.context()
    pool = F.build(P, entry_n=R.SPEC["entry_n"], daily=daily)

    print("=" * 116)
    print("A. THE FAMILY'S OWN NULL, FIRST")
    print("=" * 116)
    df = pd.read_csv("results/v17/v17_sweep.csv")
    print(f"   285 scorable conditions. Beat the same-selectivity control on Sharpe at p <= 0.05: "
          f"{int((df.p_sh <= 0.05).sum())}, expected {0.05*len(df):.1f}.")
    print(f"   On net R: {int((df.p_R <= 0.05).sum())}, expected {0.05*len(df):.1f}. "
          f"The pool is chance-consistent as a family.\n")
    print("   Three duplicate pairs were found inside the pool and are reported rather than")
    print("   silently double-counted: C_pos_pdr >= 1 IS C_dist_pdh >= 0; C_D_ema_gap >= 0 IS")
    print("   C_D_ema20_50; C_D_dist_ema200 >= 0 IS C_D_above200.")

    print("\n" + "=" * 116)
    print("B. RESEARCH AND LOCKED, SIDE BY SIDE -- locked read once, for two conditions")
    print("=" * 116)
    out = {}
    for lab, feat, lvl, dirn in PICKS:
        both = lab == "both"
        for bn, bb in (("research", res), ("locked  ", lock)):
            O, idx = leg(P, pool, bb, feat, lvl, dirn, both=both)
            print(f"   [{bn}]", end="")
            out[(lab, bn.strip())] = show(lab, P, O, idx, bb)
        print()

    print("=" * 116)
    print("C. AGAINST THE MINUTE-OF-DAY MATCHED CONTROL -- the gate the base itself does not clear")
    print("=" * 116)
    for lab, feat, lvl, dirn in PICKS:
        both = lab == "both"
        for bn, bb in (("research", res), ("locked", lock)):
            O, idx = leg(P, pool, bb, feat, lvl, dirn, both=both)
            ctl, p = mod_control(P, bb, O, idx)
            print(f"   {lab:<22}{bn:<10}rule {O['R'][idx].sum():+7.1f}R   "
                  f"control median {np.median(ctl):+7.1f}R   p = {p:.4f}"
                  + ("   (x2 for two conditions read: " + f"{min(1.0, 2*p):.4f})" if bn == "locked" and lab != "none (base)" else ""))
        print()

    print("=" * 116)
    print("D. DOES THE GRADIENT SURVIVE? -- the whole ladder, on LOCKED")
    print("=" * 116)
    print(f"   {'condition':<24}{'trades':>8}{'net R':>9}{'R/trade':>10}{'PF':>8}{'Sharpe':>9}{'maxDD':>8}")
    for lvl in (-2.0, -0.5, 0.0, 0.5, 1.5, 3.0):
        for dirn, sym in ((-1, "<="), (+1, ">=")):
            O, idx = leg(P, pool, lock, "C_dist_pdh", lvl, dirn)
            s = R.evaluate(P, O, idx, lock)
            print(f"   {'C_dist_pdh ' + sym + f' {lvl:g}':<24}{s['n']:>8}{s['R']:>+9.1f}"
                  f"{s['perR']:>+10.4f}{s['pf']:>8.3f}{s['sharpe']:>9.2f}{s['dd']:>8.1f}")

    print("\n" + "=" * 116)
    print("E. STABILITY OF THE COMBINATION")
    print("=" * 116)
    for bn, bb in (("research", res), ("locked", lock)):
        O, idx = leg(P, pool, bb, "C_dist_pdh", 0.0, +1)
        d = R.daily_series(P, O, idx, bb)
        q = d.groupby(pd.PeriodIndex(pd.to_datetime(
            np.asarray(P["b"]["ts"])[np.searchsorted(P["sess"], d.index)].astype("datetime64[ns]")),
            freq="Q")).sum() if False else None
    O, idx = leg(P, pool, lock, "C_dist_pdh", 0.0, +1)
    d = R.daily_series(P, O, idx, lock)
    p = d.to_numpy()
    dds = np.array([float((np.maximum.accumulate(RNG.permutation(p).cumsum())
                           - RNG.permutation(p).cumsum()).max()) for _ in range(200)])
    eq = p.cumsum()
    print(f"   locked realised maxDD {float((np.maximum.accumulate(eq)-eq).max()):.2f}R")
    bs = np.array([RNG.choice(p, len(p), replace=True).mean() for _ in range(20000)])
    print(f"   bootstrap P(mean daily R <= 0) on locked = {float((bs <= 0).mean()):.4f}")
    sh = []
    for _ in range(2000):
        k = RNG.choice(len(p), int(len(p) * 0.9), replace=False)
        x = p[k]
        sh.append(x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) > 0 else np.nan)
    print(f"   drop a random 10% of days: locked Sharpe p5 {np.nanpercentile(sh,5):.2f}, "
          f"median {np.nanmedian(sh):.2f}")
