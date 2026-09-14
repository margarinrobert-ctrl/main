"""PARITY -- the shipped script's own order model, diffed against the research engine.

ONE difference is structural and cannot be removed, which is the whole reason to measure it:
  THE CLOSE-ONLY TRAIL. The research exits AT the close that breaches the EMA. A script cannot:
  `strategy.close()` on a confirmed bar fills at the NEXT bar's OPEN. On a rule where 61% of
  trades die on that trail, the gap is not cosmetic.
Two more the harness models: Pine rounds the bracket to whole ticks, and the fill-relative bracket
is placed WITH the entry so the initial stop is live on the fill bar (as in the research).
"""
import os, sys
import numpy as np, pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.vwapema import vecore as V

TICK = 0.01


@njit(cache=True)
def _pine(o, h, l, c, atr, e50, e20, sess_end, sig, side, atr_stop, tgt_R, tighten_R,
          trail_next_open, cost_rt, slip, first, last_bar, os_, ox, oR, owhy):
    n = 0; busy = -1
    for i in range(first, last_bar):
        if i <= busy or not sig[i]:
            continue
        a = i + 1
        A = atr[i]
        if not (A > 0.0):
            continue
        px = o[a] + side * slip
        raw = (c[i] - (l[i] - atr_stop * A)) if side > 0 else ((h[i] + atr_stop * A) - c[i])
        risk = np.round(raw / TICK) * TICK          # Pine rounds the bracket to ticks
        if risk <= 0.0:
            continue
        stp = px - side * risk
        tgt = px + side * tgt_R * risk if tgt_R > 0 else (1e18 if side > 0 else -1e18)
        end = last_bar - 1
        out = np.nan; why = 3; j = a
        pending = 0
        while j <= end:
            if pending == 1:
                out = o[j]; why = 2; break        # the trail fills at the NEXT bar's open
            if side > 0:
                if l[j] <= stp:
                    out = stp if o[j] > stp else o[j]; why = 0; break
                if h[j] >= tgt:
                    out = tgt if o[j] < tgt else o[j]; why = 1; break
            else:
                if h[j] >= stp:
                    out = stp if o[j] < stp else o[j]; why = 0; break
                if l[j] <= tgt:
                    out = tgt if o[j] > tgt else o[j]; why = 1; break
            if j > a:
                fl = (c[j] - px) * side / risk
                tr = e20[j] if fl >= tighten_R else e50[j]
                breached = (c[j] < tr) if side > 0 else (c[j] > tr)
                if breached:
                    if trail_next_open == 1:
                        pending = 1
                    else:
                        out = c[j]; why = 2; break
            j += 1
        if np.isnan(out):
            j = min(j, end); out = c[j]; why = 3
        out = out - side * slip
        pts = side * (out - px) - cost_rt
        os_[n] = i; ox[n] = j; oR[n] = pts / risk; owhy[n] = why
        n += 1; busy = j
    return n


def run_pine(D, sig, side, trail_next_open=1, p=None, **kw):
    """kw: tgt_R. `p` carries the preset's own periods -- WITHOUT it this harness diffs the script
    against `build()`'s CACHED default EMA/ATR series, which is the same caching defect that made
    an EMA ladder return five identical rungs earlier in this study. It read as a -105% parity gap."""
    pp = {**V.PARAMS, **(p or {})}
    _e200, e50p, e20p, atrp = V.periods(D, pp)
    cap = int(sig.sum()) + 8
    a1, a2 = np.zeros(cap, np.int64), np.zeros(cap, np.int64)
    a3 = np.full(cap, np.nan); a4 = np.zeros(cap, np.int64)
    k = _pine(D["o"], D["h"], D["l"], D["c"], atrp, e50p, e20p, D["sess_end"],
              np.asarray(sig, np.bool_), int(side), float(pp["atr_stop"]), float(kw.get("tgt_R", 3.0)),
              float(pp["tighten_R"]), int(trail_next_open), float(V.COST_RT), float(V.SLIP),
              250, D["n"] - 2, a1, a2, a3, a4)
    t = pd.DataFrame(dict(sig=a1[:k], exit_bar=a2[:k], R=a3[:k], why=a4[:k]))
    t["blk"] = D["blk"][t.sig.to_numpy()]
    return t


if __name__ == "__main__":
    print(__doc__)
    D = V.build()
    for side, nm in ((1, "LONG"), (-1, "SHORT")):
        sig, _ = V.triggers(D, side=side)
        e = V.run(D, sig, side=side)
        print(f"\n  [{nm}] engine trades {len(e)}")
        for arm, tno in (("A: trail exits at the breaching CLOSE (the research convention)", 0),
                         ("B: trail exits at the NEXT bar's OPEN (what a script does)", 1)):
            p = run_pine(D, sig, side, trail_next_open=tno)
            m = e.merge(p, on="sig", suffixes=("_e", "_p"))
            same = float((m.exit_bar_e == m.exit_bar_p).mean()) if len(m) else np.nan
            cr = float(np.corrcoef(m.R_e, m.R_p)[0, 1]) if len(m) > 2 else np.nan
            line = (f"    {arm}\n      script {len(p)} ({len(p)/max(len(e),1):.4f}), shared {len(m)}, "
                    f"same exit bar {100*same:.2f}%, R corr {cr:.4f}")
            for blk, bn in ((0, "research"), (1, "locked")):
                ee, pp = e[e.blk == blk], p[p.blk == blk]
                gap = 100 * (pp.R.mean() - ee.R.mean()) / max(abs(ee.R.mean()), 1e-9)
                line += f"\n      {bn:8s} engine {ee.R.mean():+.4f} R   script {pp.R.mean():+.4f}   gap {gap:+7.1f}%"
            print(line)
