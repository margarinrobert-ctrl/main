"""V44 step 2 -- build the scalping strategy, on the TRUE 1-MINUTE PATH, and time the barriers.

WHY 1-MINUTE. A 5- or 15-minute bar whose range contains BOTH the target and the stop cannot say
which came first; resolving by rule sets the answer rather than measuring it, and this branch has
recorded the ambiguous share at 47.4% for a 0.25xATR stop. Every trade here is walked on the
1-minute series, so the barrier that fired is the one price reached first, and TIME-TO-TARGET and
TIME-TO-STOP are read to the minute rather than inferred from a bar count.

SELECTION IS ON RESEARCH ONLY. Features, directions, thresholds, the count rung and the barrier
pair are all chosen on the first 65% of sessions. The locked block is read ONCE, at the end.

FEATURES ARE PICKED ON THE RATIO MFE/MAE, NOT ON EITHER ONE ALONE. `v44run.py` shows why: both
excursions are divided by ATR at the signal bar, so a compressed ATR inflates both and an expanded
ATR deflates both. Ranking on MFE alone selects low current volatility and ranking on low MAE
selects high current volatility -- the SAME features with OPPOSITE signs. The ratio is the only one
of the three where that denominator cancels.

FAMILY BEFORE RHO. Picks are made one per concept family first, then filtered on signal-bar
correlation. Five of six "independent" picks were all volatility level once on this branch, because
a |rho| ceiling does not catch conceptual redundancy.

Usage: python research/v44/v44build.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v44")
import data as TD           # noqa: E402
import v44feat as F         # noqa: E402
import v44run as R          # noqa: E402

SPLIT = 0.65
WIN = (420, 660)
FLAT_MIN = 660              # 11:00 New York, hard flatten
N_PICKS = 4
STOPS = (0.75, 1.0, 1.5)    # ATR
TPS = (1.0, 1.5, 2.0)       # R


@njit(cache=True)
def walk(o1, h1, l1, c1, mod1, e_idx, stop_px, tp_px, flat_min, cost, slip):
    """One live position at a time is guaranteed by the caller; this walks minutes.

    Returns per trade: pnl in points, exit reason (1 stop, 2 target, 3 flatten, 0 ran out),
    minutes held, and the minute index it closed on."""
    n = len(e_idx)
    pnl = np.zeros(n); why = np.zeros(n, np.int64)
    mins = np.zeros(n, np.int64); xi = np.zeros(n, np.int64)
    m = len(c1)
    for k in range(n):
        a = e_idx[k]
        px = o1[a] + slip
        s = stop_px[k]; t = tp_px[k]
        j = a
        r = 0; out = 0.0
        while j < m:
            if l1[j] <= s:
                r = 1; out = s - slip
                break
            if h1[j] >= t:
                r = 2; out = t - slip
                break
            if mod1[j] >= flat_min:
                r = 3; out = c1[j] - slip
                break
            j += 1
        if r == 0:
            j = m - 1; out = c1[j] - slip
        pnl[k] = out - px - cost
        why[k] = r; mins[k] = j - a; xi[k] = j
    return pnl, why, mins, xi


def align(tf):
    """Map each tf-bar to the 1-minute bar that opens it. Entry is the NEXT tf bar's open, which
    is a real 1-minute bar, so no synthetic price is ever used."""
    d = TD.bars("NQ", tf)
    d1 = TD.bars("NQ", 1)
    t = pd.to_datetime(pd.Series(d["idx"]))
    t1 = pd.to_datetime(pd.Series(d1["idx"]))
    pos = pd.Series(np.arange(len(t1)), index=t1.values)
    m = pos.reindex(t.values).to_numpy()
    return d, d1, m


def pick_features(tf, win, hz=30):
    """Top cells by RATIO on research, one per family, then a signal-bar correlation screen."""
    P = R.prep(tf, win, hz)
    mfe, mae = R.excursions(P)
    df = R.score(P, mfe, mae)
    df = df[df.n >= 400].sort_values("ratio", ascending=False)
    picks, seen_fam = [], set()
    for _, r in df.iterrows():
        if r.fam in seen_fam:
            continue
        picks.append(r); seen_fam.add(r.fam)
        if len(picks) >= N_PICKS:
            break
    return P, picks, df


def condition(P, r):
    a = np.asarray(P["feats"][r.feat], float)
    return (a >= r.thr) if r["dir"] == "high" else (a <= r.thr)


def main():
    rows, detail = [], []
    for tf in (5, 15):
        P, picks, df = pick_features(tf, WIN)
        d, d1, m1 = align(tf)
        o1, h1, l1, c1 = d1["o"], d1["h"], d1["l"], d1["c"]
        mod1 = np.asarray(d1["mod"], int)
        cost = TD.COSTS["NQ"]["cost_pts"]; slip = TD.COSTS["NQ"]["slip_pts"]
        atr = P["atr"]; n = P["n"]
        res = P["res"]

        conds = np.vstack([condition(P, r) for r in picks])
        cscore = conds.sum(axis=0)
        C = np.corrcoef(conds.astype(float))

        print("\n" + "=" * 106)
        print(f"  NQ {tf}m -- features picked on RESEARCH by MFE/MAE ratio, one per family")
        print("=" * 106)
        for r in picks:
            print(f"    {r.feat:<18} {r['dir']:<5} thr {r.thr:+9.4f}   research ratio {r.ratio:.3f}"
                  f"  (MFE {r.mfe:.3f} MAE {r.mae:.3f}, n={int(r.n)})")
        print(f"    max |rho| between the picks on eligible bars: {np.abs(C - np.eye(len(C))).max():.3f}")

        # k=0 is the ABLATION: the window and the barriers with NO feature filter at all. Without
        # it the grid cannot say whether the features contributed anything or the session did.
        for k in range(0, len(picks) + 1):
            sig = P["elig"] & (cscore >= k) & np.isfinite(atr) & (atr > 0)
            sig[n - 2:] = False
            for sN in STOPS:
                for tpR in TPS:
                    idx = np.flatnonzero(sig)
                    if len(idx) < 60:
                        continue
                    # one position at a time: entry at the next tf bar's open
                    ent = m1[idx + 1]
                    keep = np.isfinite(ent)
                    idx, ent = idx[keep], ent[keep].astype(np.int64)
                    if len(idx) < 60:
                        continue
                    px0 = o1[ent]
                    risk = sN * atr[idx]
                    stop_px = px0 - risk
                    tp_px = px0 + tpR * risk
                    pnl, why, mins, xi = walk(o1, h1, l1, c1, mod1, ent, stop_px, tp_px,
                                              FLAT_MIN, cost, slip)
                    # enforce one live position: drop any entry inside a previous trade
                    keep2 = np.ones(len(ent), bool)
                    last = -1
                    for z in range(len(ent)):
                        if ent[z] <= last:
                            keep2[z] = False
                        else:
                            last = xi[z]
                    idx, pnl, why, mins = idx[keep2], pnl[keep2], why[keep2], mins[keep2]
                    rk = pnl / (sN * atr[idx])
                    for bname, blk in (("research", res), ("locked", ~res)):
                        s = blk[idx]
                        if s.sum() < 40:
                            continue
                        p, w, mi, r_ = pnl[s], why[s], mins[s], rk[s]
                        win_ = p > 0
                        gp = p[p > 0].sum(); gl = -p[p < 0].sum()
                        rows.append(dict(
                            tf=tf, k=k, stop_atr=sN, tp_r=tpR, block=bname, n=int(s.sum()),
                            pf=float(gp / gl) if gl > 0 else np.nan,
                            pts=float(p.mean()), R=float(r_.mean()), win=float(win_.mean()),
                            hit_tp=float((w == 2).mean()), hit_sl=float((w == 1).mean()),
                            flat=float((w == 3).mean()),
                            t_tp=float(np.mean(mi[w == 2])) if (w == 2).any() else np.nan,
                            t_sl=float(np.mean(mi[w == 1])) if (w == 1).any() else np.nan,
                            t_tp_med=float(np.median(mi[w == 2])) if (w == 2).any() else np.nan,
                            t_sl_med=float(np.median(mi[w == 1])) if (w == 1).any() else np.nan,
                            t_flat=float(np.mean(mi[w == 3])) if (w == 3).any() else np.nan))
                        if bname == "research":
                            detail.append(dict(tf=tf, k=k, stop_atr=sN, tp_r=tpR,
                                               mins=mi, why=w))
    out = pd.DataFrame(rows)
    out.to_csv("results/v44/v44_strategy_grid.csv", index=False)
    return out


if __name__ == "__main__":
    main()
