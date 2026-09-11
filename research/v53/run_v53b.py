"""V53 controls. The base is chosen for AGREEMENT BETWEEN BLOCKS, not for research score: 30m is
the timeframe whose research and locked marginals are closest (+0.1192 / +0.0896), where 60m has
the best research (+0.1965) and the WORST locked (+0.0304) -- the overfit end of that axis.

Two nulls, both required:
  * a RANDOM ENTRY with identical exits, stop, max hold and costs, matched on trade count
  * for each condition, a RANDOM FILTER keeping the same share of the same signals
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v51"); sys.path.insert(0, "research/v53")
import v51tensor as T   # noqa: E402
import v53abs as A      # noqa: E402
import run_v53 as R     # noqa: E402

TF, ENT, EXIT, STOP = 30, 20, 20, 2.0
N_DRAW = 2000
TESTS = [("base -- no condition at all", 0, 0, 0),
         ("MA200 above", 1, 0, 0),
         ("MA200 >= 1.5 ATR above", 3, 0, 0),
         ("EMA13 > EMA48", 0, 1, 0),
         ("EMA13 x 48 cross <= 20 bars", 0, 2, 0)]


def lock(sel, xb, R_):
    take, free = [], -1
    for k, i in enumerate(sel):
        if i < free or xb[k] < 0 or not np.isfinite(R_[k]):
            continue
        free = xb[k]
        take.append(k)
    return np.array(take, np.int64)


def trades(P, ma, cx, ab, blk, tf):
    bars = np.flatnonzero(R.entry_mask(P, ENT))
    MA, CX, AB, _ = R.masks(P, bars, tf)
    keep = MA[ma] & CX[cx] & AB[ab]
    sel = bars[keep]
    xb, rr = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sel, P["exit_lo"][EXIT],
                    float(STOP), -1, np.zeros(P["n"], np.int64), R.COST, R.SLIP, R.MAX_HOLD)
    t = lock(sel, xb, rr)
    b = np.ones(len(t), bool) if blk is None else blk[sel[t]]
    return sel[t][b], rr[t][b], keep.mean()


def sel_control(P, keep_rate, blk, seed=17):
    bars = np.flatnonzero(R.entry_mask(P, ENT))
    xb, rr = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], bars, P["exit_lo"][EXIT],
                    float(STOP), -1, np.zeros(P["n"], np.int64), R.COST, R.SLIP, R.MAX_HOLD)
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    m = len(bars)
    for d in range(N_DRAW):
        idx = np.flatnonzero(rng.random(m) < keep_rate)
        t = lock(bars[idx], xb[idx], rr[idx])
        sb, sr = bars[idx][t], rr[idx][t]
        if blk is not None:
            b = blk[sb]
            sb, sr = sb[b], sr[b]
        out[d] = sr.mean() if len(sr) else np.nan
    return out


def entry_control(P, n_target, blk, seed=23):
    ok = np.isfinite(P["atr"]) & (P["atr"] > 0) & np.isfinite(P["ma_dist"])
    ok[:1000] = False
    ok[-(R.MAX_HOLD + 5):] = False
    el = np.flatnonzero(ok)
    xb, rr = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], el, P["exit_lo"][EXIT],
                    float(STOP), -1, np.zeros(P["n"], np.int64), R.COST, R.SLIP, R.MAX_HOLD)
    good = (xb >= 0) & np.isfinite(rr)
    el, xb, rr = el[good], xb[good], rr[good]
    if blk is not None:
        b = blk[el]
        el, xb, rr = el[b], xb[b], rr[b]
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    for d in range(N_DRAW):
        cand = np.sort(rng.choice(len(el), size=min(len(el), n_target * 6), replace=False))
        tot, free, took = 0.0, -1, 0
        for k in cand:
            if el[k] < free:
                continue
            free = xb[k]
            tot += rr[k]
            took += 1
            if took >= n_target:
                break
        out[d] = tot / took if took else np.nan
    return out


def main():
    f1 = A.load_1m()
    P = R.build(f1, TF)
    cut = int(P["n"] * R.SPLIT)
    for bn, blk in (("research", np.arange(P["n"]) < cut), ("LOCKED", np.arange(P["n"]) >= cut)):
        print("\n" + "=" * 100)
        print(f"  NQ {TF}m  {bn}   base = Donchian {ENT} in / {EXIT} out / {STOP}N stop, long, "
              f"no target, max hold {R.MAX_HOLD}")
        print("=" * 100)
        print(f"  {'condition':<34} {'n':>5} {'keep':>6} {'R':>9} {'PF':>6}"
              f"  {'control':>9} {'p':>7}  null")
        for label, ma, cx, ab in TESTS:
            bb, rr, kr = trades(P, ma, cx, ab, blk, TF)
            if len(rr) < 20:
                print(f"  {label:<34} {len(rr):>5}  too few")
                continue
            wins, losses = rr[rr > 0], rr[rr <= 0]
            pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf
            if ma == 0 and cx == 0 and ab == 0:
                cc = entry_control(P, len(rr), blk)
                nm = "random ENTRY"
            else:
                cc = sel_control(P, kr, blk)
                nm = "random FILTER"
            p = float(np.nanmean(cc >= rr.mean()))
            print(f"  {label:<34} {len(rr):>5} {100*kr:5.1f}% {rr.mean():+9.4f} {pf:6.3f}"
                  f" {np.nanmedian(cc):+9.4f} {p:7.3f}  {nm}")
        # every absorption reading, both sides, all lower timeframes, at the fixed window 200 / k 5
        print(f"\n  {'absorption (window 200, within 5 bars)':<34} {'n':>5} {'keep':>6} {'R':>9}"
              f" {'PF':>6}  {'control':>9} {'p':>7}")
        for i, (labl, side, ltf, kw) in enumerate(R.ABS_MODES):
            if side is None or kw != (5, 200):
                continue
            bb, rr, kr = trades(P, 0, 0, i, blk, TF)
            if len(rr) < 20:
                print(f"  {labl:<34} {len(rr):>5}  too few")
                continue
            wins, losses = rr[rr > 0], rr[rr <= 0]
            pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf
            cc = sel_control(P, kr, blk)
            p = float(np.nanmean(cc >= rr.mean()))
            print(f"  {labl:<34} {len(rr):>5} {100*kr:5.1f}% {rr.mean():+9.4f} {pf:6.3f}"
                  f" {np.nanmedian(cc):+9.4f} {p:7.3f}")


if __name__ == "__main__":
    main()
