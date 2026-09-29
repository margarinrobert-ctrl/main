"""GATE 2 -- the six mathematical states as the META layer on the Donchian+EMA primary, US30.

GATE 1 WAS NOT CLEARED: the primary reads +0.0429 %/trade at PF 1.122 on research and its matched
random entry gives p 0.167. Under the mechanism-first architecture that normally ends it. The one
declared exception applies here and is stated rather than assumed: a primary with no UNCONDITIONAL
edge can still carry a CONDITIONAL one, and it may be tested when the conditioning variables were
written down before the search. These six were -- they were implemented and validated against
simulated processes with known parameters before any strategy was touched. Anything found is
therefore a conditional-edge claim carrying that caveat, not a Gate 1 pass.

Objective is the PERCENT ACTUALLY EARNED, not win/lose -- a win/lose model is a win-rate optimiser
and this branch has measured it trimming the tail four times. Every model runs beside a
SHUFFLED-LABEL TWIN, and the gate is scored as a VETO, re-simulated end to end, against a random
gate of the same selectivity.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mathmodels import mmcore as M  # noqa: E402
from mathmodels.run_m2 import walk, walk_at, chan, COST  # noqa: E402

RNG = np.random.default_rng(99)
TF, ENT, EMA, STOP, W = 60, 30, 200, 2.0, 500
ND = 400


def purged(n, k=5, emb=30):
    edges = np.linspace(0, n, k + 1).astype(int)
    for i in range(k):
        te = np.arange(edges[i], edges[i + 1])
        tr = np.setdiff1d(np.arange(n), np.arange(max(0, te[0] - emb),
                                                  min(n, te[-1] + emb + 1)))
        yield tr, te


def oof(X, y, mk, shuffle=False, seed=0):
    p = np.full(len(y), np.nan)
    yy = np.random.default_rng(seed).permutation(y) if shuffle else y
    sc = StandardScaler()
    for tr, te in purged(len(y), 5, 30):
        m = mk()
        m.fit(sc.fit_transform(X[tr]), yy[tr])
        p[te] = m.predict(sc.transform(X[te]))
    return p


def ic(a, b):
    k = np.isfinite(a) & np.isfinite(b)
    return float(pd.Series(a[k]).corr(pd.Series(b[k]), method="spearman"))


def main():
    f = M.load("US30L", TF)
    s = np.unique(f.index.normalize())
    cut = pd.Timestamp(s[int(0.75 * len(s))])
    o, h, l, c = (f[k].to_numpy() for k in ("open", "high", "low", "close"))
    at = f["atr"].to_numpy()
    xh, xl = chan(h, l, 20)
    eh, el = chan(h, l, ENT)
    e = pd.Series(c).ewm(span=EMA, adjust=False).mean().to_numpy()
    ou = (c > e).astype(np.int64); od = (c < e).astype(np.int64)
    eb, r, sd, hl = walk(o, h, l, c, at, eh, el, xh, xl, ou, od, STOP, COST)
    sig = eb - 1                                     # the SIGNAL bar, never the fill bar
    ts = f.index[eb]
    res = np.asarray(ts < cut)

    S = M.states(f, W)
    cols = list(S.columns)
    E = S.iloc[sig][cols].reset_index(drop=True)
    print(f"primary {TF}m d{ENT}/20 ema{EMA} {STOP}N   events {len(r)}  "
          f"research {res.sum()}  holdout {(~res).sum()}  states {len(cols)}")

    print("\nSTATE BEHAVIOUR ON THE TRIGGER'S OWN BARS (lift = share above the all-bar median)")
    print(f"{'state':<14}{'lift':>8}{'|rho| to R':>12}{'research IC':>13}{'holdout IC':>12}")
    keep = []
    for cn in cols:
        v = S[cn].to_numpy()
        pop = v[np.isfinite(v)]
        if len(pop) < 1000:
            continue
        sv = E[cn].to_numpy()
        share = float(np.nanmean(sv > np.nanmedian(pop)))
        a = ic(sv[res], r[res]); b = ic(sv[~res], r[~res])
        flag = "  <- degenerate" if (share > 0.95 or share < 0.05) else ""
        print(f"{cn:<14}{share/0.5:>8.2f}{abs(a):>12.4f}{a:>13.4f}{b:>12.4f}{flag}")
        if not (share > 0.95 or share < 0.05):
            keep.append(cn)
    print(f"  pool {len(cols)} -> {len(keep)}")

    C = E[keep].corr().abs()
    np.fill_diagonal(C.values, 0.0)
    dup = [(a, b, C.loc[a, b]) for a in C.index for b in C.columns if a < b and C.loc[a, b] > 0.95]
    for a, b, rr in dup:
        print(f"  NEAR-DUPLICATE {a} == {b}  rho {rr:.4f}")
    keep = [x for x in keep if x not in {b for _, b, _ in dup}]

    X = E[keep].to_numpy(float)
    med = np.nanmedian(X[res], axis=0)
    X = np.where(np.isfinite(X), X, med)
    Xr, yr = X[res], r[res]

    print("\nMODEL LADDER -- OOF IC on research, real vs its shuffled twin")
    mks = {"ridge": lambda: Ridge(alpha=10.0),
           "rf": lambda: RandomForestRegressor(n_estimators=300, max_depth=4, min_samples_leaf=30,
                                               max_features=0.6, random_state=0, n_jobs=4),
           "lgbm": lambda: lgb.LGBMRegressor(n_estimators=250, num_leaves=7, learning_rate=0.03,
                                             min_child_samples=30, subsample=0.8,
                                             colsample_bytree=0.7, verbose=-1, n_jobs=4)}
    preds, twins = {}, 0
    print(f"{'model':<8}{'IC':>9}{'twin':>9}{'winner':>9}")
    for nm, mk in mks.items():
        p = oof(Xr, yr, mk); q = oof(Xr, yr, mk, True, 7)
        a, b = ic(p, yr), ic(q, yr)
        preds[nm] = p
        twins += int(b > a)
        print(f"{nm:<8}{a:>9.4f}{b:>9.4f}{('TWIN' if b > a else 'real'):>9}")
    print(f"  twin wins {twins}/{len(mks)} = {twins/len(mks):.0%}  (above 50% = noise floor)")

    print("\nGATE 2 -- veto, re-simulated, against a random gate of the same size")
    sr, dr = sig[res], sd[res]
    base = walk_at(o, h, l, c, at, xh, xl, sr.astype(np.int64), dr.astype(np.int64), STOP, COST)
    print(f"  base: n {np.isfinite(base).sum()}  %/trade {np.nanmean(base):.4f}  PF {M.pf(base):.3f}")

    def rgate(k):
        out = np.empty(ND)
        for i in range(ND):
            pick = np.sort(RNG.choice(len(sr), size=k, replace=False))
            out[i] = np.nanmean(walk_at(o, h, l, c, at, xh, xl, sr[pick].astype(np.int64),
                                        dr[pick].astype(np.int64), STOP, COST))
        return out

    print(f"{'model':<8}{'keep':>6}{'n':>6}{'%/trade':>9}{'PF':>7}{'uplift':>9}{'ctl':>9}{'p':>7}")
    best = None
    for nm, p in preds.items():
        for kf in (0.7, 0.5, 0.3):
            thr = np.nanquantile(p, 1 - kf)
            m = p >= thr
            q = walk_at(o, h, l, c, at, xh, xl, sr[m].astype(np.int64),
                        dr[m].astype(np.int64), STOP, COST)
            mu = float(np.nanmean(q))
            ctl = rgate(int(m.sum()))
            pv = float(np.mean(ctl >= mu))
            up = mu - float(np.nanmean(base))
            print(f"{nm:<8}{kf:>6.1f}{int(np.isfinite(q).sum()):>6}{mu:>9.4f}{M.pf(q):>7.3f}"
                  f"{up:>9.4f}{np.nanmedian(ctl):>9.4f}{pv:>7.3f}")
            if best is None or (pv < best[0]):
                best = (pv, nm, kf, thr, up)
    print(f"\n  best research cell: {best[1]} keep {best[2]:.0%}  uplift {best[4]:+.4f}  p {best[0]:.3f}")
    np.save("research/mathmodels/keep.npy", np.array(keep, object))


if __name__ == "__main__":
    main()
