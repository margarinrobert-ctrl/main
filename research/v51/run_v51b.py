"""V51 gates 2, 4, 5 and 6: the MATCHED CONTROL as a gate, the cost stress, one locked read and one
held-back-market read, for the TOP-1000 CONSENSUS configuration and for the argmax row.

THE CONTROL. Random entry, same side, same geometry, same exits, same costs, matched on TRADE COUNT
with the rate computed against ELIGIBLE bars, and matched on MINUTE-OF-DAY so the clock cannot do
the work. The R denominator is an ATR stop, not a channel stop, so it cannot collapse the way
`STUDY_TURTLE_YOUTUBE`'s first control did -- that is why an ATR stop is used here.

SHARPE IS COMPUTED OVER EVERY TRADING DAY IN THE BLOCK, zero-filled on days that did not trade.
Over traded days only, a filter is PAID for trading less.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v38"); sys.path.insert(0, "research/v51")
import v51feat as V     # noqa: E402
import v51tensor as T   # noqa: E402
import run_v51 as RUN   # noqa: E402

N_DRAW = 2000

# The two configurations, both declared from the sweep's own output and frozen before this file ran.
CONSENSUS = dict(tf=60, entN=20, exitN=30, stopN=1.5, ma=3, cx=3, ab=0, ss=3)   # near3.0/recent20/off/08-12
# The only reading that cleared a same-selectivity control on ALL THREE blocks with the right shape.
FLOOR = dict(tf=60, entN=20, exitN=30, stopN=1.5, ma=4, cx=0, ab=0, ss=0)      # MA200 >= 1.5 ATR above
BASE = dict(tf=60, entN=20, exitN=30, stopN=1.5, ma=0, cx=0, ab=0, ss=0)


def cfg_trades(P, cost, slip, cfg, block):
    bars = np.flatnonzero(V.entry_mask(P, cfg["entN"]))
    MA, CX, AB, SS = V.filter_masks(P, bars)
    keep = MA[cfg["ma"]] & CX[cfg["cx"]] & AB[cfg["ab"]] & SS[cfg["ss"]]
    sel = bars[keep]
    w, f = V.SESS[cfg["ss"]]
    fm = V.WINDOWS[w][1] if f == 1 else -1
    xb, R = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sel, P["exit_lo"][cfg["exitN"]],
                   float(cfg["stopN"]), fm, P["mod"], cost, slip, V.MAX_HOLD)
    take, free = [], -1
    for k, i in enumerate(sel):
        if i < free or xb[k] < 0 or not np.isfinite(R[k]):
            continue
        free = xb[k]
        take.append(k)
    take = np.array(take, np.int64)
    b = np.ones(len(take), bool) if block is None else block[sel[take]]
    return sel[take][b], R[take][b], xb[take][b]


def eligible(P, cfg):
    ok = np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["ma_dist"])
    ok[:300] = False
    ok[-(V.MAX_HOLD + 5):] = False
    w, _f = V.SESS[cfg["ss"]]
    a, b = V.WINDOWS[w]
    if w != 0:
        ok &= (P["mod"] >= a) & (P["mod"] < b)
    return np.flatnonzero(ok)


def control(P, cost, slip, cfg, sig_bars, block, seed=7):
    """Matched on trade count and on minute-of-day, drawn from eligible bars."""
    el = eligible(P, cfg)
    if block is not None:
        el = el[block[el]]
    w, f = V.SESS[cfg["ss"]]
    fm = V.WINDOWS[w][1] if f == 1 else -1
    xb, R = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], el, P["exit_lo"][cfg["exitN"]],
                   float(cfg["stopN"]), fm, P["mod"], cost, slip, V.MAX_HOLD)
    good = (xb >= 0) & np.isfinite(R)
    el, xb, R = el[good], xb[good], R[good]
    mod_el = P["mod"][el]
    buckets = {}
    for m in np.unique(mod_el):
        buckets[m] = np.flatnonzero(mod_el == m)
    want = pd.Series(P["mod"][sig_bars]).value_counts().to_dict()
    n_target = len(sig_bars)
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    for d in range(N_DRAW):
        pick = []
        for m, cnt in want.items():
            pool = buckets.get(m)
            if pool is None or len(pool) == 0:
                continue
            pick.append(rng.choice(pool, size=min(cnt * 3, len(pool)), replace=False))
        if not pick:
            out[d] = np.nan
            continue
        cand = np.sort(np.concatenate(pick))
        tot, free, took = 0.0, -1, 0
        for k in cand:
            if el[k] < free:
                continue
            free = xb[k]
            tot += R[k]
            took += 1
            if took >= n_target:
                break
        out[d] = tot / took if took else np.nan
    return out


def daily_sharpe(P, bars, R):
    """Every trading day in the block, zero-filled where the rule did not trade."""
    day = P["day"]
    days = np.unique(day)
    s = pd.Series(R, index=day[bars]).groupby(level=0).sum()
    v = pd.Series(0.0, index=days)
    v.loc[s.index] = s.to_numpy()
    return float(v.mean() / v.std() * np.sqrt(252)) if v.std() > 0 else np.nan


def report(name, cfg, cost_mult=1.0):
    print("\n" + "=" * 100)
    print(f"  {name}  --  tf {cfg['tf']}m  entry {cfg['entN']}  exit {cfg['exitN']}  "
          f"stop {cfg['stopN']}N  MA200 {V.MA200_MODES[cfg['ma']]}  cross "
          f"{V.CROSS_MODES[cfg['cx']]}  absorption "
          f"{[f'v{m}.{a}' for m in V.VOL_MULT for a in V.ABS_MODES][cfg['ab']]}  "
          f"session {V.SESS[cfg['ss']]}   [cost x{cost_mult}]")
    print("=" * 100)
    for market in ("US100L", "US30L"):
        P = V.build(market, cfg["tf"])
        ck = V.COSTS[market]
        cost, slip = ck["cost"] * cost_mult, ck["slip"] * cost_mult
        cut = int(P["n"] * RUN.SPLIT)
        blocks = ([("research", np.arange(P["n"]) < cut), ("LOCKED", np.arange(P["n"]) >= cut)]
                  if market == "US100L" else [("held back, whole file", None)])
        for bn, blk in blocks:
            bars, R, xb = cfg_trades(P, cost, slip, cfg, blk)
            if len(R) < 20:
                print(f"  {market:<7} {bn:<22} n {len(R)} -- too few to score")
                continue
            wins, losses = R[R > 0], R[R <= 0]
            pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf
            ctrl = control(P, cost, slip, cfg, bars, blk)
            p = float(np.nanmean(ctrl >= R.mean()))
            print(f"  {market:<7} {bn:<22} n {len(R):>5}  R {R.mean():+.4f}  PF {pf:5.3f}  "
                  f"win {100*(R>0).mean():4.1f}%  Sharpe {daily_sharpe(P, bars, R):5.2f}  "
                  f"| control {np.nanmedian(ctrl):+.4f}  p {p:.3f}")


if __name__ == "__main__":
    report("BASE -- no filter at all", BASE, 1.0)
    for cm in (1.0, 1.5, 2.0):
        report("MA200 EXTENSION FLOOR (>= 1.5 ATR above), nothing else", FLOOR, cm)
