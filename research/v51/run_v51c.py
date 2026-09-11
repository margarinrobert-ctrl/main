"""V51 -- does each requested feature EARN ITS PLACE? Every filter is scored against a RANDOM
FILTER OF THE SAME SELECTIVITY, not against total dollars (which fails every restrictive condition)
and not against per-trade edge (which passes every one). `research/dropone.py`'s rule.

The base is the top-1000 consensus GEOMETRY with every filter off and no session restriction, so
each row below is one feature added to the same starting point.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v38"); sys.path.insert(0, "research/v51")
import v51feat as V     # noqa: E402
import v51tensor as T   # noqa: E402
import run_v51 as RUN   # noqa: E402

TF, ENT, EXIT, STOP = 60, 20, 30, 1.5
N_DRAW = 2000
AB_LBL = [f"v{m}.{a}" for m in V.VOL_MULT for a in V.ABS_MODES]
TESTS = [("base (no filter)", 0, 0, 0, 0),
         ("MA200 above", 1, 0, 0, 0),
         ("MA200 above & within 1.5 ATR", 2, 0, 0, 0),
         ("MA200 above & within 3.0 ATR", 3, 0, 0, 0),
         ("MA200 >= 1.5 ATR above", 4, 0, 0, 0),
         ("MA200 >= 3.0 ATR above", 5, 0, 0, 0),
         ("EMA13 > EMA48 (state)", 0, 1, 0, 0),
         ("EMA13 x 48 cross in 5 bars", 0, 2, 0, 0),
         ("EMA13 x 48 cross in 20 bars", 0, 3, 0, 0),
         ("require BUYER absorption <=5", 0, 0, 1, 0),
         ("require BUYER absorption <=20", 0, 0, 2, 0),
         ("avoid SELLER absorption <=5", 0, 0, 3, 0),
         ("avoid SELLER absorption <=20", 0, 0, 4, 0),
         ("require SELLER absorption <=5", 0, 0, 5, 0),
         ("require SELLER absorption <=20", 0, 0, 6, 0),
         ("session 08:00-12:00", 0, 0, 0, 3),
         ("session 08:00-12:00 + FLATTEN", 0, 0, 0, 4),
         ("session 09:30-16:00", 0, 0, 0, 7),
         ("session 09:30-16:00 + FLATTEN", 0, 0, 0, 8)]


def lock(sel, xb, R):
    take, free = [], -1
    for k, i in enumerate(sel):
        if i < free or xb[k] < 0 or not np.isfinite(R[k]):
            continue
        free = xb[k]
        take.append(k)
    return np.array(take, np.int64)


def run(P, cost, slip, ma, cx, ab, ss, blk):
    bars = np.flatnonzero(V.entry_mask(P, ENT))
    MA, CX, AB, SS = V.filter_masks(P, bars)
    keep = MA[ma] & CX[cx] & AB[ab] & SS[ss]
    w, f = V.SESS[ss]
    fm = V.WINDOWS[w][1] if f == 1 else -1
    sel = bars[keep]
    xb, R = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sel, P["exit_lo"][EXIT],
                   float(STOP), fm, P["mod"], cost, slip, V.MAX_HOLD)
    t = lock(sel, xb, R)
    b = np.ones(len(t), bool) if blk is None else blk[sel[t]]
    return sel[t][b], R[t][b], bars, keep, fm


def selectivity_control(P, cost, slip, keep_rate, ss, blk, n_target, seed=11):
    """A RANDOM filter keeping the same share of the SAME base signals, same geometry, same exits."""
    bars = np.flatnonzero(V.entry_mask(P, ENT))
    _MA, _CX, _AB, SS = V.filter_masks(P, bars)
    w, f = V.SESS[ss]
    fm = V.WINDOWS[w][1] if f == 1 else -1
    base = bars[SS[0]] if ss == 0 else bars
    xb, R = T.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], base, P["exit_lo"][EXIT],
                   float(STOP), fm, P["mod"], cost, slip, V.MAX_HOLD)
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    m = len(base)
    for d in range(N_DRAW):
        k = rng.random(m) < keep_rate
        idx = np.flatnonzero(k)
        t = lock(base[idx], xb[idx], R[idx])
        if len(t) == 0:
            out[d] = np.nan
            continue
        sb, sr = base[idx][t], R[idx][t]
        if blk is not None:
            b = blk[sb]
            sb, sr = sb[b], sr[b]
        out[d] = sr.mean() if len(sr) else np.nan
    return out


def main():
    for market in ("US100L", "US30L"):
        P = V.build(market, TF)
        ck = V.COSTS[market]
        cost, slip = ck["cost"], ck["slip"]
        cut = int(P["n"] * RUN.SPLIT)
        blocks = ([("research", np.arange(P["n"]) < cut), ("LOCKED", np.arange(P["n"]) >= cut)]
                  if market == "US100L" else [("held back", None)])
        for bn, blk in blocks:
            print("\n" + "=" * 100)
            print(f"  {market}  {bn}   base = {TF}m Donchian {ENT} in / {EXIT} out / {STOP}N stop,"
                  f" long, no target, max hold {V.MAX_HOLD} bars")
            print("=" * 100)
            print(f"  {'feature':<34} {'n':>5} {'keep':>6} {'R':>9} {'PF':>6} {'win':>6}"
                  f"  {'same-selectivity control':>26} {'p':>7}")
            b0, r0, bars, keep0, _ = run(P, cost, slip, 0, 0, 0, 0, blk)
            for label, ma, cx, ab, ss in TESTS:
                bb, rr, _bars, keep, _fm = run(P, cost, slip, ma, cx, ab, ss, blk)
                if len(rr) < 15:
                    print(f"  {label:<34} {len(rr):>5}  too few trades to score")
                    continue
                wins, losses = rr[rr > 0], rr[rr <= 0]
                pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf
                kr = keep.mean()
                if ma == 0 and cx == 0 and ab == 0 and ss == 0:
                    print(f"  {label:<34} {len(rr):>5} {100*kr:5.1f}% {rr.mean():+9.4f} {pf:6.3f}"
                          f" {100*(rr>0).mean():5.1f}% {'--':>26} {'--':>7}")
                    continue
                ctrl = selectivity_control(P, cost, slip, kr, ss, blk, len(rr))
                p = float(np.nanmean(ctrl >= rr.mean()))
                print(f"  {label:<34} {len(rr):>5} {100*kr:5.1f}% {rr.mean():+9.4f} {pf:6.3f}"
                      f" {100*(rr>0).mean():5.1f}% {np.nanmedian(ctrl):+26.4f} {p:7.3f}")


if __name__ == "__main__":
    main()
