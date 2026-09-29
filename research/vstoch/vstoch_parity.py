"""PARITY -- the shipped Pine's OWN order model in Python, diffed against the research engine.

`STUDY_PINE_PARITY` / `STUDY_V56`: a port cannot be asserted by reading it. The differences that
matter here are all in the order model, not the rules:

  * The bracket is FILL-RELATIVE (`loss`/`profit` in ticks) and goes out WITH the entry, so the fill
    bar is protected in both models -- that is the point of placing it at the signal bar.
  * Pine ROUNDS the bracket to whole ticks (`math.round(stopN * atr / mintick)`); the engine uses
    the exact level.
  * The HOLD CAP differs by construction. `bar_index - entryBar >= holdBars` fires on the bar
    signal+hold, and `strategy.close_all()` CANNOT sell the close of the bar that triggers it -- it
    fills at the NEXT bar's OPEN. The engine closes at the CLOSE of bar (fill + hold).

The test is run twice: with the hold cap far away, which is the TRANSCRIPTION check and must come
back near-exact, and as configured, which measures the order-model gap.
"""
import os, sys
import numpy as np, pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vstoch as V

TICK = 0.25


@njit(cache=True)
def _pine(o, h, l, c, atr, gate, side, stop_n, tp_n, hold, cost, slip, tick, first, last_bar):
    m = len(c); cap = 40000
    sig = np.zeros(cap, np.int64); xb = np.zeros(cap, np.int64)
    pts = np.full(cap, np.nan); pct = np.full(cap, np.nan)
    why = np.zeros(cap, np.int64)
    cnt = 0; busy = -1
    for i in range(first, last_bar):
        if i <= busy or not gate[i]:
            continue
        a = i + 1
        anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        s = side
        px = o[a] + s * slip
        # Pine rounds the bracket to whole ticks
        risk = np.round(stop_n * anchor / tick) * tick
        if risk <= 0.0:
            continue
        stp = px - s * risk
        tg_t = np.round(tp_n * anchor / tick) * tick
        tgt = px + s * tg_t if tp_n > 0.0 else (1e18 if s > 0 else -1e18)
        # close_all fires on bar i+hold and FILLS AT THE NEXT BAR'S OPEN
        cap_bar = i + hold + 1
        if cap_bar > m - 2:
            cap_bar = m - 2
        out = np.nan; j = a; w = 2
        while j <= cap_bar:
            if j < cap_bar:
                if s > 0:
                    if l[j] <= stp:
                        out = (stp if o[j] > stp else o[j]) - slip; w = 0; break
                    if h[j] >= tgt:
                        out = (tgt if o[j] < tgt else o[j]) - slip; w = 1; break
                else:
                    if h[j] >= stp:
                        out = (stp if o[j] < stp else o[j]) + slip; w = 0; break
                    if l[j] <= tgt:
                        out = (tgt if o[j] > tgt else o[j]) + slip; w = 1; break
            else:
                out = o[j] - s * slip; w = 2; break
            j += 1
        if not np.isfinite(out):
            out = c[j] - s * slip; w = 2
        gg = s * (out - px) - cost
        if cnt < cap:
            sig[cnt] = i; xb[cnt] = j; pts[cnt] = gg; pct[cnt] = 100.0 * gg / px; why[cnt] = w
            cnt += 1
        busy = j
    return sig[:cnt], xb[:cnt], pts[:cnt], pct[:cnt], why[:cnt]


def run_pine(D, gate, side, stop, tp, hold):
    sig, xb, pts, pct, why = _pine(D["o"], D["h"], D["l"], D["c"], D["atr"],
                                   np.asarray(gate, np.bool_), int(side), float(stop), float(tp),
                                   int(hold), float(D["cost"]), float(D["slip"]), TICK,
                                   300, int(D["last_bar"]))
    return pd.DataFrame(dict(sig=sig, exit_bar=xb, pts=pts, pct=pct, why=why, blk=D["blk"][sig]))


print(__doc__)
D = V.build("NQ", 15)
lo, sh, _, _ = V.triggers(D, 14, 3, 3, 30.0, 70.0)
gate = lo & D["rth"] & (D["c"] > D["vwap"]) & (D["atr_ratio_tod"] <= 1.0)
gate = np.nan_to_num(gate, nan=False).astype(bool)

for lab, hold in (("TRANSCRIPTION (hold cap unreachable)", 100000), ("AS CONFIGURED (hold 48)", 48)):
    e = V.run(D, gate, side=1, stop=1.5, tp=1.5, hold=min(hold, 5000))
    p = run_pine(D, gate, 1, 1.5, 1.5, min(hold, 5000))
    print(f"\n  --- {lab} ---")
    print(f"    trades  engine {len(e):4d}   script {len(p):4d}   ratio {len(p)/max(len(e),1):.4f}")
    m = e.merge(p, on="sig", suffixes=("_e", "_p"))
    same = float((m.exit_bar_e == m.exit_bar_p).mean()) if len(m) else np.nan
    cr = float(np.corrcoef(m.pts_e, m.pts_p)[0, 1]) if len(m) > 2 else np.nan
    for blk, nm in ((0, "research"), (1, "locked")):
        ee, pp = e[e.blk == blk], p[p.blk == blk]
        if len(ee) == 0:
            continue
        gap = 100 * (pp.pts.mean() - ee.pts.mean()) / abs(ee.pts.mean()) if ee.pts.mean() else np.nan
        print(f"    {nm:8s} engine {ee.pts.mean():+8.3f} pts/trade   script {pp.pts.mean():+8.3f}   "
              f"gap {gap:+7.1f}%  ({'conservative' if gap < 0 else 'script reads better'})")
    print(f"    shared trades {len(m)}, identical exit bar {100*same:.2f}%, per-trade corr {cr:.4f}")
