"""V52 -- does each gate earn its place ON THIS SCRIPT'S OWN GEOMETRY? Every condition against a
RANDOM FILTER KEEPING THE SAME SHARE OF THE SAME SIGNALS, 2,000 draws, on three blocks.

Base: the pasted script's System 1, reduced to one entry and one exit -- 240m, 20-bar entry,
10-bar exit, 2.0N ATR stop, ONE unit, no gate at all."""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

sys.path.insert(0, "research"); sys.path.insert(0, "research/v38")
sys.path.insert(0, "research/v51"); sys.path.insert(0, "research/v52")
import v51tensor as T51     # noqa: E402
import v52feat as V         # noqa: E402
import run_v52 as RUN       # noqa: E402

TF, ENT, EXIT, STOP = 240, 20, 10, 2.0
N_DRAW = 2000
AB_LBL = [f"v{m}.{a}" for m in V.VOL_MULT for a in V.ABS_MODES]
# (label, ma, cx, ab, adx, ext, ss)
TESTS = [("base -- one entry, one exit, no gate", 0, 0, 0, 0, 0, 0),
         ("ADX < 22            (the script)", 0, 0, 0, 1, 0, 0),
         ("ADX >= 22           (inverted)", 0, 0, 0, 2, 0, 0),
         ("ADX >= 25           (inverted)", 0, 0, 0, 3, 0, 0),
         ("EMA100 dist < 3.964 (the script)", 0, 0, 0, 0, 1, 0),
         ("EMA100 dist >= 1.5  (inverted)", 0, 0, 0, 0, 2, 0),
         ("EMA100 dist >= 3.0  (inverted)", 0, 0, 0, 0, 3, 0),
         ("BOTH the script's gates", 0, 0, 0, 1, 1, 0),
         ("BOTH inverted (ADX>=22, dist>=1.5)", 0, 0, 0, 2, 2, 0),
         ("MA200 >= 1.5 ATR above (V51's)", 4, 0, 0, 0, 0, 0),
         ("MA200 above & within 3.0 ATR", 3, 0, 0, 0, 0, 0),
         ("EMA13 > EMA48 (state)", 0, 1, 0, 0, 0, 0),
         ("EMA13 x 48 cross <= 20 bars", 0, 3, 0, 0, 0, 0),
         ("avoid SELLER absorption <= 20", 0, 0, 4, 0, 0, 0),
         ("require SELLER absorption <= 20", 0, 0, 6, 0, 0, 0),
         ("session 08:00-12:00", 0, 0, 0, 0, 0, 3),
         ("session 08:00-12:00 + FLATTEN", 0, 0, 0, 0, 0, 4),
         ("session 09:30-16:00 + FLATTEN", 0, 0, 0, 0, 0, 8)]


def lock(sel, xb, R):
    take, free = [], -1
    for k, i in enumerate(sel):
        if i < free or xb[k] < 0 or not np.isfinite(R[k]):
            continue
        free = xb[k]
        take.append(k)
    return np.array(take, np.int64)


def run(P, cost, slip, ma, cx, ab, adx, ext, ss, blk):
    bars = np.flatnonzero(V.entry_mask(P, ENT))
    MA, CX, AB, SS, AD, EX = V.filter_masks(P, bars)
    keep = MA[ma] & CX[cx] & AB[ab] & AD[adx] & EX[ext] & SS[ss]
    w, f = V.SESS[ss]
    fm = V.WINDOWS[w][1] if f == 1 else -1
    sel = bars[keep]
    xb, R = T51.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], sel, P["exit_lo"][EXIT],
                     float(STOP), fm, P["mod"], cost, slip, V.MAX_HOLD)
    t = lock(sel, xb, R)
    b = np.ones(len(t), bool) if blk is None else blk[sel[t]]
    return sel[t][b], R[t][b], keep.mean()


def ctrl(P, cost, slip, keep_rate, ss, blk, seed=13):
    bars = np.flatnonzero(V.entry_mask(P, ENT))
    w, f = V.SESS[ss]
    fm = V.WINDOWS[w][1] if f == 1 else -1
    xb, R = T51.walk(P["o"], P["h"], P["l"], P["c"], P["atr"], bars, P["exit_lo"][EXIT],
                     float(STOP), fm, P["mod"], cost, slip, V.MAX_HOLD)
    rng = np.random.default_rng(seed)
    out = np.empty(N_DRAW)
    m = len(bars)
    for d in range(N_DRAW):
        idx = np.flatnonzero(rng.random(m) < keep_rate)
        t = lock(bars[idx], xb[idx], R[idx])
        if len(t) == 0:
            out[d] = np.nan
            continue
        sb, sr = bars[idx][t], R[idx][t]
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
            print(f"  {market}  {bn}   base = {TF}m Turtle System 1 alone: {ENT} in / {EXIT} out /"
                  f" {STOP}N stop, ONE unit, long")
            print("=" * 100)
            print(f"  {'condition':<38} {'n':>5} {'keep':>6} {'R':>9} {'PF':>6}"
                  f"  {'same-selectivity control':>26} {'p':>7}")
            for label, ma, cx, ab, adx, ext, ss in TESTS:
                bb, rr, kr = run(P, cost, slip, ma, cx, ab, adx, ext, ss, blk)
                if len(rr) < 15:
                    print(f"  {label:<38} {len(rr):>5}  too few trades to score")
                    continue
                wins, losses = rr[rr > 0], rr[rr <= 0]
                pf = wins.sum() / -losses.sum() if len(losses) and losses.sum() < 0 else np.inf
                if kr >= 0.999 and ss == 0:
                    print(f"  {label:<38} {len(rr):>5} {100*kr:5.1f}% {rr.mean():+9.4f} {pf:6.3f}"
                          f" {'--':>26} {'--':>7}")
                    continue
                cc = ctrl(P, cost, slip, kr, ss, blk)
                p = float(np.nanmean(cc >= rr.mean()))
                print(f"  {label:<38} {len(rr):>5} {100*kr:5.1f}% {rr.mean():+9.4f} {pf:6.3f}"
                      f" {np.nanmedian(cc):+26.4f} {p:7.3f}")


if __name__ == "__main__":
    main()
