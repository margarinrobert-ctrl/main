"""S9 -- build the rule the TEAM'S EVIDENCE implies, rather than searching for one that is positive.

Three agents produced two findings that reproduced across three blocks and two providers:
  ADX IS INVERTED -- ceilings beat their block's base in 12 of 12 cells (mean +3.37 pts) against
    floors' 6 of 24 (-0.97); `adx>=25` is negative 6/6 and removing it moved a stack's control
    p from 0.237 to 0.040, the only p-value the team moved across 0.05 anywhere.
  THE EMA ALIGNMENT CARRIES, THE STATE DOES NOT -- `ema13>34>89` positive 6/6 with the most stable
    lift in the pool (1.569/1.583/1.590), while `ema13>48` passes 84.2% of breakout bars and is
    the trigger restated.
  AND ATR IS AT CHANCE in both directions (58%/44%), with `atrpct250<=0.5` drifting its kept share
    0.318 -> 0.212 -> 0.142, i.e. not the same filter on each block.

Nobody built the rule those three statements imply: Donchian + an ADX CEILING + the EMA ALIGNMENT
and NO ATR condition. This is a pre-declared hypothesis derived from measured component behaviour,
not a cell chosen for being positive -- and it is falsifiable in advance, because
`STUDY_US30_SCALP_0711` §9 fixes the bar: a PF of 1.2 requires +10.61 points a trade and IS
detectable at this sample size, so if the implied rule is worth trading it must show up here.

DECLARED IN FULL BEFORE RUNNING, and this is the entire grid:
  trigger   Donchian 20 long
  window    07:00-11:00 New York, FLATTEN at the 11:00 open
  geometry  30/150 and 50/150 points  (the two the team already used)
  arms      base | +adx<=20 | +ema align | +both | +both+adx>=25 (the conventional stack, as the
            arm that must LOSE if the inversion is real)
  = 2 geometries x 5 arms = 10 research cells. Nothing else is tried.
Then ONE read of B_holdout and ONE of C_forward on the arms declared here.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s30core as S  # noqa: E402

pd.set_option("display.width", 240)
Z80 = 2.802
GEOS = [(30, 150), (50, 150)]


def adx_wilder(f, n=14):
    h, l, c = f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy()
    up, dn = h[1:] - h[:-1], l[:-1] - l[1:]
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    def rma(x):
        out = np.empty(len(x)); out[:] = np.nan
        if len(x) < n:
            return out
        out[n - 1] = x[:n].mean()
        for i in range(n, len(x)):
            out[i] = (out[i - 1] * (n - 1) + x[i]) / n
        return out
    atr, pv, nv = rma(tr), rma(pdm), rma(ndm)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi, ndi = 100 * pv / atr, 100 * nv / atr
        dx = 100 * np.abs(pdi - ndi) / (pdi + ndi)
    adx = rma(np.nan_to_num(dx, nan=0.0))
    return np.r_[np.nan, adx], np.r_[np.nan, pdi], np.r_[np.nan, ndi]


def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def masks(f):
    a, _, _ = adx_wilder(f)
    c = f["close"].to_numpy()
    e13, e34, e89 = ema(c, 13), ema(c, 34), ema(c, 89)
    return {
        "adx<=20": np.nan_to_num(a, nan=999) <= 20,
        "adx>=25": np.nan_to_num(a, nan=0) >= 25,
        "ema align": (e13 > e34) & (e34 > e89),
    }


ARMS = [("base", []), ("+adx<=20", ["adx<=20"]), ("+ema align", ["ema align"]),
        ("+both", ["adx<=20", "ema align"]),
        ("+both +adx>=25", ["ema align", "adx>=25"])]


def score(f, bm, arm_conds, st, tg, nsess, seed=21, draws=400):
    s2, d2 = S.donchian(f, 20, 1)
    M = masks(f)
    keep = np.isin(s2, np.flatnonzero(bm))
    for cnd in arm_conds:
        keep &= M[cnd][s2]
    sig, sd = s2[keep], d2[keep]
    if len(sig) < 25:
        return None
    kw = dict(stop_a=st, tgt_a=tg, hold=0, flat=S.FLAT, use_pts=1)
    t = S.walk(f, sig, sd, **kw)
    if len(t) < 25:
        return None
    p = t["pts"].to_numpy()
    se = p.std(ddof=1) / np.sqrt(len(p))
    ctl = S.control(f, len(t), t["side"].to_numpy(), S.window(f) & bm, n_draw=draws,
                    seed=seed, **kw)
    d = t.groupby(t.ts.dt.normalize())["pts"].sum()
    dd = np.zeros(max(nsess, len(d))); dd[:len(d)] = d.to_numpy()
    rng = np.random.default_rng(5)
    bs = np.array([rng.choice(d.to_numpy(), len(d), replace=True).mean() for _ in range(2000)])
    return dict(n=len(t), pts=p.mean(), sd=p.std(ddof=1), t=p.mean() / se,
                mde=Z80 * se, inside_mde=abs(p.mean()) < Z80 * se,
                pf=S.pf(p), win=float((p > 0).mean()),
                be=S.breakeven(st / np.nanmedian(t["risk"] / st), tg / st * 1.0, 0, 1) if False else
                   (st + S.COST) / (st + tg),
                sharpe=dd.mean() / dd.std(ddof=1) * np.sqrt(252) if dd.std() > 0 else np.nan,
                ctl=float(np.median(ctl)), p=float(np.mean(ctl >= p.mean())),
                boot_p=float(np.mean(bs <= 0)), med_min=float(t["mins"].median()))


def main():
    f = S.load("US30L")
    bl = S.blocks(f, "US30L")
    res = bl["A_research"]
    ns = f.index[res & S.window(f)].normalize().nunique()

    print("=== 1. the ten declared research cells ===")
    rows = []
    for st, tg in GEOS:
        for nm, cond in ARMS:
            r = score(f, res, cond, st, tg, ns)
            if r:
                r.update(geo=f"{st}/{tg}", arm=nm)
                rows.append(r)
    R = pd.DataFrame(rows)
    print(R[["geo", "arm", "n", "pts", "sd", "t", "mde", "inside_mde", "pf", "win", "be",
             "sharpe", "ctl", "p", "boot_p", "med_min"]].round(4).to_string(index=False))

    print("\n=== 2. does the inversion hold? the conventional stack must LOSE ===")
    for st, tg in GEOS:
        g = R[R.geo == f"{st}/{tg}"].set_index("arm")
        print(f"  {st}/{tg}:  base {g.loc['base','pts']:+7.3f}   "
              f"+adx<=20 {g.loc['+adx<=20','pts']:+7.3f}   "
              f"+ema {g.loc['+ema align','pts']:+7.3f}   "
              f"+both {g.loc['+both','pts']:+7.3f}   "
              f"CONVENTIONAL {g.loc['+both +adx>=25','pts']:+7.3f}")

    print("\n=== 3. what PF 1.2 would require here, against what each arm delivers ===")
    for _, r in R.iterrows():
        need = 10.61
        print(f"  {r.geo:8s} {r.arm:15s} delivers {r.pts:+7.3f}  needs {need:+6.2f} for PF 1.2  "
              f"MDE {r.mde:5.2f}  -> {'DETECTABLE' if abs(r.pts) > r.mde else 'inside the MDE'}")

    # ---- ONE READ ---------------------------------------------------------------------------
    print("\n=== 4. ONE READ of all five arms on B_holdout and on C_forward ===")
    out = []
    for feed, fname in ((f, "US30L"), (S.load("US30I"), "US30I")):
        for bn, bm in S.blocks(feed, fname).items():
            if bn == "A_research":
                continue
            nsb = feed.index[bm & S.window(feed)].normalize().nunique()
            for st, tg in GEOS:
                for nm, cond in ARMS:
                    r = score(feed, bm, cond, st, tg, nsb, seed=31)
                    if r:
                        r.update(feed=fname, block=bn, geo=f"{st}/{tg}", arm=nm)
                        out.append(r)
    O = pd.DataFrame(out)
    print(O[["feed", "block", "geo", "arm", "n", "pts", "t", "mde", "inside_mde", "pf", "win",
             "sharpe", "p", "boot_p"]].round(4).to_string(index=False))

    print("\n=== 5. the arm-by-arm verdict across all three blocks ===")
    allr = pd.concat([R.assign(feed="US30L", block="A_research"), O], ignore_index=True)
    piv = allr.pivot_table(index="arm", columns="block", values="pts", aggfunc="mean").round(3)
    print(piv.to_string())
    print("\nshare of the 3 blocks positive, per arm:")
    for nm, _ in ARMS:
        sub = allr[allr.arm == nm]
        print(f"  {nm:16s} {int((sub.pts > 0).sum())}/{len(sub)} cells positive   "
              f"mean {sub.pts.mean():+7.3f}   cells clearing control "
              f"{int((sub.p <= 0.05).sum())}/{len(sub)}   "
              f"cells outside their MDE {int((~sub.inside_mde).sum())}/{len(sub)}")


if __name__ == "__main__":
    main()
