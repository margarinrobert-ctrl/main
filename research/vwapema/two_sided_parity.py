"""PARITY -- the SHIPPED two-sided Pine's own order model, written out, diffed against the engine.

`STUDY_PINE_PARITY` and `STUDY_V56`: a Pine port cannot be asserted by reading it. Four differences
between the research walk and what the script can actually place are modelled here explicitly:
  1. the bracket is FILL-RELATIVE and goes out WITH the entry, so the initial stop is live on the
     fill bar -- matched to the engine, which anchors the stop to the SIGNAL bar and tests it from
     the fill bar;
  2. the trail is close-only and, in the script, cannot act on the bar the position filled;
  3. `strategy.close()` fills at the NEXT bar's OPEN, where the engine exits at the breaching
     CLOSE. That is the irreducible gap and it is the one to read;
  4. the exit-bar marker is updated before the entry test, so no re-entry on the bar a trade closed.
"""
import os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vecore as V, ve_markets as M, two_sided as T

pd.set_option("display.width", 200)
print(__doc__)


def run_script(mk, long_cfg=T.LONG_CFG, short_cfg=T.SHORT_CFG, long_priority=True):
    DL, sigL, e50L, e20L, atrL = T._side_arrays(mk, long_cfg)
    DS, sigS, e50S, e20S, atrS = T._side_arrays(mk, short_cfg)
    o, h, l, c = DL["o"], DL["h"], DL["l"], DL["c"]
    n, cost_rt, slip = DL["n"], DL["cost_rt"], DL["slip"]
    rows, busy = [], -1
    for i in range(250, n - 3):
        if i <= busy:
            continue
        tl, ts = sigL[i], sigS[i]
        if not (tl or ts):
            continue
        if tl and ts:
            tl, ts = long_priority, not long_priority
        side = 1 if tl else -1
        cfg = long_cfg if tl else short_cfg
        atr, e50, e20 = (atrL, e50L, e20L) if tl else (atrS, e50S, e20S)
        sess_end = DL["sess_end"] if tl else DS["sess_end"]
        A = atr[i]
        if not (A > 0):
            continue
        a = i + 1
        px = o[a] + side * slip
        risk = (px - (l[i] - cfg["p"]["atr_stop"] * A)) if side > 0 else ((h[i] + cfg["p"]["atr_stop"] * A) - px)
        if risk <= 0:
            continue
        stp = px - side * risk                      # FILL-relative, which is what the script places
        end = sess_end[a] if cfg["flatten"] else n - 3
        end = min(max(end, a), n - 3)
        out, why, j = np.nan, 3, a
        while j <= end:
            if (side > 0 and l[j] <= stp) or (side < 0 and h[j] >= stp):
                out = stp if ((side > 0 and o[j] > stp) or (side < 0 and o[j] < stp)) else o[j]
                why = 0
                break
            if j > a:                                # the trail cannot act on the fill bar
                fl = (c[j] - px) * side / risk
                tr = e20[j] if fl >= cfg["p"]["tighten_R"] else e50[j]
                if (side > 0 and c[j] < tr) or (side < 0 and c[j] > tr):
                    # strategy.close() fills at the NEXT bar's open -- the irreducible gap
                    out, why, j = (o[j + 1] if j + 1 < n else c[j]), 2, min(j + 1, n - 1)
                    break
            j += 1
        if not np.isfinite(out):
            j = min(end + 1, n - 1)
            out, why = o[j], 3                       # the flatten also fills at the next open
        out -= side * slip
        pts = side * (out - px) - cost_rt
        rows.append((i, j, side, pts / risk, 100.0 * pts / px, why))
        busy = j
    t = pd.DataFrame(rows, columns=["sig", "exit_bar", "side", "R", "pct", "why"])
    if len(t):
        t["blk"] = DL["blk"][t.sig.to_numpy()]
    return t


rows = []
for mk in ("US100", "US30", "US30_ISO"):
    eng, _ = T.walk_two_sided(mk)
    scr = run_script(mk)
    shared = set(eng.sig) & set(scr.sig)
    e = eng[eng.sig.isin(shared)].set_index("sig").sort_index()
    s = scr[scr.sig.isin(shared)].set_index("sig").sort_index()
    same_exit = float((e.exit_bar == s.exit_bar).mean())
    corr = float(np.corrcoef(e.R, s.R)[0, 1])
    blocks = (("whole", None),) if mk == "US30_ISO" else (("research", 0), ("LOCKED", 1))
    for bn, b in blocks:
        eb = eng if b is None else eng[eng.blk == b]
        sb = scr if b is None else scr[scr.blk == b]
        if len(eb) < 10:
            continue
        rows.append(dict(feed=mk, block=bn, engine_n=len(eb), script_n=len(sb),
                         count_ratio=round(len(sb) / len(eb), 4),
                         engine_R=round(eb.R.mean(), 4), script_R=round(sb.R.mean(), 4),
                         gap_pct=round(100 * (sb.R.mean() - eb.R.mean()) / abs(eb.R.mean()), 1)
                         if abs(eb.R.mean()) > 1e-9 else np.nan,
                         same_exit_bar=round(same_exit, 4), R_corr=round(corr, 4)))
P = pd.DataFrame(rows)
print(P.to_string(index=False))
P.to_csv("results/vwapema/m8_parity.csv", index=False)
print("\nRead the COUNT first. A negative gap means the script is CONSERVATIVE against the research,")
print("which is the direction to want (STUDY_V56: a script that reads BETTER than its research is")
print("the order-model gap, not an edge).")
