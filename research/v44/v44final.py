"""V44 step 3 -- the frozen rule read ONCE on locked, against a matched control, with the barriers timed.

FROZEN ON RESEARCH BY MARGINAL AVERAGE, NOT BY TOP CELL. The top row of a 72-cell grid is the max
of 72 draws. Each axis was read by its mean across the others: the stop axis runs 0.910 / 0.973 /
1.057 on 5m and 0.923 / 0.961 / 1.007 on 15m, and the target axis 0.916 / 0.989 / 1.035 and 0.948 /
0.956 / 0.987 -- both MONOTONE TOWARD WIDER on both timeframes, with the best setting at the EDGE
of the declared grid. That is recorded as a limitation, not resolved by extending the grid, because
extending it after seeing the result is how a boundary becomes an optimum.

  5m : 4 of 4 conditions, stop 1.5 ATR, target 2.0 R
  15m: 3 of 4 conditions, stop 1.5 ATR, target 2.0 R

THE CONTROL is a random entry inside the same window on the same day, with the identical stop,
target, flatten, 1-minute walk and costs, matched on trade count, 200 draws. It prices the session,
the barrier geometry, the drift and the cost floor at once, so what is left is the features.

Usage: python research/v44/v44final.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v44")
import data as TD           # noqa: E402
import v44run as R          # noqa: E402
import v44build as B        # noqa: E402

FROZEN = {5: dict(k=4, stop=1.5, tp=2.0), 15: dict(k=3, stop=1.5, tp=2.0)}


_CACHE = {}


def context(tf, win):
    """Build the 36 features and the 1-minute alignment ONCE per (tf, window).

    Without this the control rebuilds every feature over 210,516 bars inside each of its draws.
    The control is only useful as a GATE if it is affordable to run, which is the whole reason
    `research/tune.py` exists."""
    key = (tf, tuple(win))
    if key not in _CACHE:
        P, picks, _ = B.pick_features(tf, win)
        _d, d1, m1 = B.align(tf)
        _CACHE[key] = (P, picks, d1, m1)
    return _CACHE[key]


def one(tf, win, k, sN, tpR, entry_idx=None):
    P, picks, d1, m1 = context(tf, win)
    o1, h1, l1, c1 = d1["o"], d1["h"], d1["l"], d1["c"]
    mod1 = np.asarray(d1["mod"], int)
    cost = TD.COSTS["NQ"]["cost_pts"]; slip = TD.COSTS["NQ"]["slip_pts"]
    atr, n = P["atr"], P["n"]
    if entry_idx is None:
        conds = np.vstack([B.condition(P, r) for r in picks])
        sig = P["elig"] & (conds.sum(axis=0) >= k) & np.isfinite(atr) & (atr > 0)
        sig[n - 2:] = False
        idx = np.flatnonzero(sig)
    else:
        idx = entry_idx
    ent = m1[idx + 1]
    keep = np.isfinite(ent)
    idx, ent = idx[keep], ent[keep].astype(np.int64)
    px0 = o1[ent]; risk = sN * atr[idx]
    pnl, why, mins, xi = B.walk(o1, h1, l1, c1, mod1, ent, px0 - risk, px0 + tpR * risk,
                                B.FLAT_MIN, cost, slip)
    keep2 = np.ones(len(ent), bool); last = -1
    for z in range(len(ent)):
        if ent[z] <= last:
            keep2[z] = False
        else:
            last = xi[z]
    return P, picks, idx[keep2], pnl[keep2], why[keep2], mins[keep2], risk[keep2]


def summarise(tag, pnl, why, mins, risk):
    if len(pnl) < 20:
        return None
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    r = pnl / risk
    d = dict(tag=tag, n=len(pnl), pf=float(gp / gl) if gl > 0 else np.nan,
             pts=float(pnl.mean()), R=float(r.mean()), win=float((pnl > 0).mean()),
             hit_tp=float((why == 2).mean()), hit_sl=float((why == 1).mean()),
             flat=float((why == 3).mean()))
    for code, nm in ((2, "tp"), (1, "sl"), (3, "flat")):
        m = mins[why == code]
        if len(m):
            d[f"t_{nm}_mean"] = float(m.mean()); d[f"t_{nm}_med"] = float(np.median(m))
            d[f"t_{nm}_p25"] = float(np.percentile(m, 25))
            d[f"t_{nm}_p75"] = float(np.percentile(m, 75))
    return d


def control(tf, win, k, sN, tpR, P, n_target, blk, draws=120, seed=5):
    """Random entries from the same eligible window, matched on count."""
    elig = np.flatnonzero(P["elig"] & blk)
    if len(elig) < n_target * 3:
        return None
    rng = np.random.default_rng(seed)
    pfs, ptss = [], []
    for _ in range(draws):
        pick = np.sort(rng.choice(elig, size=n_target, replace=False))
        _P, _pk, idx, pnl, why, mins, risk = one(tf, win, k, sN, tpR, entry_idx=pick)
        if len(pnl) < 20:
            continue
        gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
        pfs.append(gp / gl if gl > 0 else np.nan); ptss.append(pnl.mean())
    return np.asarray(pfs, float), np.asarray(ptss, float)


def main():
    rows = []
    for tf, cfg in FROZEN.items():
        for wname, win in (("07:00-11:00", B.WIN), ("09:30-11:00", (570, 660))):
            P, picks, idx, pnl, why, mins, risk = one(tf, win, cfg["k"], cfg["stop"], cfg["tp"])
            res = P["res"]
            print("\n" + "=" * 104)
            print(f"  NQ {tf}m   {wname} NY   {cfg['k']} of 4 conditions   "
                  f"stop {cfg['stop']} ATR   target {cfg['tp']} R   1-minute path")
            print("=" * 104)
            for bname, blk in (("research", res), ("locked", ~res)):
                s = blk[idx]
                d = summarise(f"{tf}m {wname} {bname}", pnl[s], why[s], mins[s], risk[s])
                if d is None:
                    print(f"    {bname}: fewer than 20 trades"); continue
                ctl = control(tf, win, cfg["k"], cfg["stop"], cfg["tp"], P, int(s.sum()), blk)
                if ctl is not None and len(ctl[0]):
                    cpf, cpt = ctl
                    d["c_pf"] = float(np.nanmean(cpf)); d["c_pts"] = float(np.nanmean(cpt))
                    d["p_pts"] = float(np.mean(cpt >= d["pts"]))
                print(f"    {bname:<9} n {d['n']:>5}  PF {d['pf']:.3f}  pts {d['pts']:+.3f}  "
                      f"R {d['R']:+.4f}  win {d['win']:.1%}", end="")
                if "c_pf" in d:
                    print(f"   | control PF {d['c_pf']:.3f} pts {d['c_pts']:+.3f}  p {d['p_pts']:.3f}")
                else:
                    print()
                print(f"              outcome mix: target {d['hit_tp']:.1%}  stop {d['hit_sl']:.1%}"
                      f"  11:00 flatten {d['flat']:.1%}")
                for nm, lbl in (("tp", "TIME TO TARGET"), ("sl", "TIME TO STOP"),
                                ("flat", "time to flatten")):
                    if f"t_{nm}_med" in d:
                        print(f"              {lbl:<16} median {d[f't_{nm}_med']:>5.0f} min   "
                              f"mean {d[f't_{nm}_mean']:>5.0f}   "
                              f"IQR {d[f't_{nm}_p25']:.0f}-{d[f't_{nm}_p75']:.0f}")
                d["tf"] = tf; d["win"] = wname; d["block"] = bname
                rows.append(d)
    out = pd.DataFrame(rows)
    out.to_csv("results/v44/v44_frozen.csv", index=False)
    return out


if __name__ == "__main__":
    main()
