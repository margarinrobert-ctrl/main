"""x_run7 -- does the EXIT marginal invert in ATR units, as the ARM comparison does?

`STUDY_US30_SCALP_0711` section 18 found that `+adx<=20` beats its base by +5.304 POINTS and by
-0.0134 ATR, because the ceiling selects calmer bars and its point advantage is carried by the
high-ATR minority it keeps. Everything in this study is in POINTS, so the same question has to be
put to the EXIT axis before any of it is believed.

The exposure is NOT the same. Section 18 compares two different ENTRY populations; every comparison
here holds the entry fixed and varies only what happens after the fill. But the policies do admit
slightly different trade counts (the trail frees the position lock earlier), so the ATR mix can
still move. Measured rather than argued: each policy in POINTS and in ATR AT THE SIGNAL BAR, beside
its own matched twin, on all three arms.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x_lib as X  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 260)
ARMS = ["+adx<=20", "+ema align", "ema34>89"]
COND = {"+adx<=20": ["adx<=20"], "+ema align": ["ema align"], "ema34>89": ["ema34>89"]}


def masks(f):
    M = X.L.build_masks(f["high"].to_numpy(), f["low"].to_numpy(), f["close"].to_numpy())
    c = f["close"].to_numpy()
    M["ema34>89"] = X.L.ema(c, 34) > X.L.ema(c, 89)
    return M


def sigs(f, arm, bm, M):
    s2, d2 = S.donchian(f, 20, 1)
    keep = np.isin(s2, np.flatnonzero(bm))
    for c in COND[arm]:
        keep &= M[c][s2]
    return s2[keep], d2[keep]


def both_units(f, t):
    """Points, and points divided by the ATR at the SIGNAL bar (the bar before the fill)."""
    atr = f["atr"].to_numpy()[t.e_bar.to_numpy() - 1]
    ok = np.isfinite(atr) & (atr > 0)
    return float(t.pts.to_numpy()[ok].mean()), float((t.pts.to_numpy()[ok] / atr[ok]).mean()), \
        float(np.median(atr[ok]))


def ctl_units(f, t, elig, n_draw, seed, **kw):
    rng = np.random.default_rng(seed)
    pool = np.flatnonzero(elig)
    o = np.full((n_draw, 2), np.nan)
    for i in range(n_draw):
        pick = np.sort(rng.choice(pool, size=len(t), replace=False))
        sd = rng.permutation(t["side"].to_numpy())[:len(pick)]
        tt = X.xwalk(f, pick, sd, **kw)
        if len(tt) < 5:
            continue
        o[i] = both_units(f, tt)[:2]
    return o[np.isfinite(o[:, 0])]


def main():
    f = S.load("US30L")
    res = S.blocks(f, "US30L")["A_research"]
    M = masks(f)
    chlo = X.chan_low(f, 10, 1)
    elig = S.window(f) & res

    print("=== the EXIT policy marginal in POINTS and in ATR, stop 100 / target 150 ===")
    print("    `d_pts` / `d_atr` are the rule minus its own matched twin in each unit.\n")
    rows = []
    for arm in ARMS:
        sig, sd = sigs(f, arm, res, M)
        for pol in X.POLICIES:
            kw = dict(stop=100, tgt=150, policy=pol, chlo=chlo)
            t = X.xwalk(f, sig, sd, **kw)
            p, a, med_atr = both_units(f, t)
            c = ctl_units(f, t, elig, 200, seed=101, **kw)
            rows.append(dict(arm=arm, policy=pol, n=len(t), pts=p, atr_u=a,
                             med_sig_atr=med_atr,
                             ctl_pts=float(np.median(c[:, 0])),
                             ctl_atr=float(np.median(c[:, 1])),
                             d_pts=p - float(np.median(c[:, 0])),
                             d_atr=a - float(np.median(c[:, 1]))))
    R = pd.DataFrame(rows)
    for arm in ARMS:
        print(f"\n  --- {arm} ---")
        print(R[R.arm == arm].drop(columns=["arm"]).round(4).to_string(index=False))

    print("\n=== do the two units RANK the four policies the same way? ===")
    for arm in ARMS:
        g = R[R.arm == arm].set_index("policy")
        rp = g["d_pts"].rank(ascending=False)
        ra = g["d_atr"].rank(ascending=False)
        print(f"  {arm:12s} by d_pts {list(rp.sort_values().index)}")
        print(f"  {'':12s} by d_atr {list(ra.sort_values().index)}   "
              f"Spearman {rp.corr(ra, method='spearman'):+.3f}")

    print("\n=== does the trail keep a different ATR mix? (section 18's mechanism) ===")
    base = R[R.policy == "flatten"].set_index("arm")["med_sig_atr"]
    for arm in ARMS:
        g = R[R.arm == arm].set_index("policy")
        print(f"  {arm:12s} median signal-bar ATR by policy: " +
              "  ".join(f"{p} {g.loc[p,'med_sig_atr']:.3f}" for p in X.POLICIES) +
              f"   trail/flatten {g.loc['+trail1atr','med_sig_atr']/base[arm]:.4f}")

    print("\n=== the headline comparison in BOTH units: trail vs no trail, and vs its twin ===")
    for arm in ARMS:
        g = R[R.arm == arm].set_index("policy")
        print(f"  {arm:12s} trail-minus-flatten  pts {g.loc['+trail1atr','pts']-g.loc['flatten','pts']:+7.3f}"
              f"   ATR {g.loc['+trail1atr','atr_u']-g.loc['flatten','atr_u']:+7.4f}")
        print(f"  {'':12s} EXCESS over own twin  pts {g.loc['+trail1atr','d_pts']:+7.3f} (trail) vs "
              f"{g.loc['flatten','d_pts']:+7.3f} (flatten)"
              f"   ATR {g.loc['+trail1atr','d_atr']:+7.4f} vs {g.loc['flatten','d_atr']:+7.4f}")


if __name__ == "__main__":
    main()
