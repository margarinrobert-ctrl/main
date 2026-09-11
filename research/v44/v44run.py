"""V44 step 1 -- score every feature by the excursions it selects, and test whether the brief's
two criteria are the same axis or opposite ones.

SELECTION IS ON THE RESEARCH BLOCK ONLY. Thresholds, directions and the final feature set are all
chosen there; the locked block is read once, in v44build.py, after the rule is frozen.

HORIZON, AND THE TIMEOUT TRAP. Excursions are measured over a FIXED 90 minutes with no barriers,
in ATR at the signal bar. Bars with less than that left before the 11:00 flatten are DROPPED, not
truncated -- a bar near the bell cannot reach a target, so leaving them in makes any feature that
merely speeds resolution look predictive. That mistake made `min_to_close` separate 0.00% from
43.17% on this branch once.

LONG ONLY. NQ rose 89% over this sample; a search allowed to pick a side picks long and calls the
drift an edge. Fixing the side removes that degree of freedom rather than spending it.

Usage: python research/v44/v44run.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v44")
import data as TD           # noqa: E402
import v44feat as F         # noqa: E402

WIN = (420, 660)            # 07:00-11:00 New York, as briefed
ALT = (570, 660)            # 09:30-11:00, the branch's standing preference, printed beside it
HORIZONS_MIN = (30, 90)
SPLIT = 0.65


def prep(tf, win, horizon_min):
    """THE HORIZON IS NOT CLIPPED BY THE ENTRY WINDOW. Scoring a feature is a measurement of what
    follows a bar, so the excursion is allowed to run its full length past 11:00. Clipping it to
    the window makes the horizon a function of the clock -- an earlier version of this file
    required the whole horizon to fit inside 09:30-11:00 and left ONE eligible bar per day. The
    11:00 flatten is a constraint on the STRATEGY, and it binds in v44build.py where it belongs,
    with the share of trades it closes reported rather than hidden."""
    d = TD.bars("NQ", tf)
    o, h, l, c, v = d["o"], d["h"], d["l"], d["c"], d["v"]
    feats, atr = F.build(o, h, l, c, v)
    mod = np.asarray(d["mod"], int)
    H = max(1, horizon_min // tf)
    n = len(c)
    elig = (mod >= win[0]) & (mod < win[1]) & np.isfinite(atr) & (atr > 0)
    elig[n - H - 2:] = False
    res = np.arange(n) < int(n * SPLIT)
    return dict(o=o, h=h, l=l, c=c, atr=atr, feats=feats, elig=elig, res=res, H=H, tf=tf, n=n)


def excursions(P):
    """MFE and MAE in ATR at the signal bar, over exactly H bars from the NEXT open."""
    o, h, l, atr, H, n = P["o"], P["h"], P["l"], P["atr"], P["H"], P["n"]
    mfe = np.full(n, np.nan); mae = np.full(n, np.nan)
    idx = np.flatnonzero(P["elig"])
    for i in idx:
        a = i + 1
        b = min(a + H, n - 1)
        if b <= a:
            continue
        px = o[a]
        mfe[i] = (h[a:b + 1].max() - px) / atr[i]
        mae[i] = (px - l[a:b + 1].min()) / atr[i]
    return mfe, mae


def score(P, mfe, mae, q=0.2):
    """Per feature, both tails. Direction is part of the cell, so the pool is 2x its length."""
    rows = []
    m = P["elig"] & P["res"] & np.isfinite(mfe) & np.isfinite(mae)
    for k, arr in P["feats"].items():
        a = np.asarray(arr, float)
        ok = m & np.isfinite(a)
        if ok.sum() < 400:
            continue
        vals = a[ok]
        lo_t, hi_t = np.quantile(vals, q), np.quantile(vals, 1 - q)
        for side, sel in (("high", ok & (a >= hi_t)), ("low", ok & (a <= lo_t))):
            if sel.sum() < 150:
                continue
            # POINTS as well as ATR. Points are what is risked; ATR is what compares across
            # timeframes and blocks. They disagree because NQ's stored levels are synthetic and
            # inflated early in the sample (STUDY_US100), so a research points figure is not
            # comparable to a locked one -- read the ATR column for that.
            atr_sel = P["atr"][sel]
            rows.append(dict(feat=k, fam=k.split(".")[0], dir=side, n=int(sel.sum()),
                             thr=float(hi_t if side == "high" else lo_t),
                             mfe=float(np.mean(mfe[sel])), mae=float(np.mean(mae[sel])),
                             mfe_pts=float(np.mean(mfe[sel] * atr_sel)),
                             mae_pts=float(np.mean(mae[sel] * atr_sel)),
                             atr_pts=float(np.median(atr_sel)),
                             ratio=float(np.mean(mfe[sel]) / np.mean(mae[sel]))))
    return pd.DataFrame(rows)


def main():
    out = {}
    for tf in (5, 15):
        for wname, win in (("07:00-11:00", WIN), ("09:30-11:00", ALT)):
          for hz in HORIZONS_MIN:
            P = prep(tf, win, hz)
            mfe, mae = excursions(P)
            base_m = P["elig"] & P["res"] & np.isfinite(mfe)
            df = score(P, mfe, mae)
            df["tf"] = tf; df["win"] = wname; df["hz"] = hz
            df["base_mfe"] = float(np.mean(mfe[base_m]))
            df["base_mae"] = float(np.mean(mae[base_m]))
            df["base_n"] = int(base_m.sum())
            out[(tf, wname, hz)] = df
    all_df = pd.concat(out.values(), ignore_index=True)
    all_df.to_csv("results/v44/v44_feature_scores.csv", index=False)

    for (tf, wname, hz), df in out.items():
        b_mfe, b_mae, b_n = df.base_mfe.iloc[0], df.base_mae.iloc[0], int(df.base_n.iloc[0])
        print("\n" + "=" * 108)
        print(f"  NQ {tf}m   {wname} NY   horizon {hz}min   research block")
        print(f"  BASELINE over all {b_n:,} eligible bars: MFE {b_mfe:.3f}  MAE {b_mae:.3f} ATR"
              f"   ratio {b_mfe / b_mae:.3f}")
        print("=" * 108)
        r = df.sort_values("mfe", ascending=False).head(4)
        print("\n  TOP 4 BY MEAN MFE   (mfe/mae in ATR, *_pts in NQ POINTS)")
        cols = ["feat", "dir", "n", "mfe", "mae", "mfe_pts", "mae_pts", "atr_pts", "ratio"]
        print(r[cols].round(2).to_string(index=False))
        r = df.sort_values("mae").head(4)
        print("\n  TOP 4 BY LOWEST MEAN MAE   (mfe/mae in ATR, *_pts in NQ POINTS)")
        print(r[cols].round(2).to_string(index=False))
        rho = df[["mfe", "mae"]].corr(method="spearman").iloc[0, 1]
        pear = df[["mfe", "mae"]].corr().iloc[0, 1]
        top_mfe = set(df.sort_values("mfe", ascending=False).head(4).feat)
        top_mae = set(df.sort_values("mae").head(4).feat)
        print(f"\n  ARE THE TWO CRITERIA THE SAME AXIS?")
        print(f"     corr(mean MFE, mean MAE) across {len(df)} cells: "
              f"Spearman {rho:+.3f}   Pearson {pear:+.3f}")
        print(f"     features shared by the two top-4 lists: {len(top_mfe & top_mae)} "
              f"{sorted(top_mfe & top_mae) if top_mfe & top_mae else ''}")
        print(f"     best cell by RATIO: ", end="")
        rb = df.sort_values("ratio", ascending=False).iloc[0]
        print(f"{rb.feat} {rb.dir}  ratio {rb.ratio:.3f}  (MFE {rb.mfe:.3f} MAE {rb.mae:.3f}, "
              f"n={int(rb.n)})")
    return all_df


if __name__ == "__main__":
    main()
