"""V50 -- does the ADVERSE SELECTION a resting limit suffers grow with the signal's immediacy,
at a FIXED fill rate? Pre-registered under docs/ib/EDGE_BRIEF.md; queue item 1 of EDGE_LEDGER.md.

Declared and not searched: limit 1.0 x ATR, stop 2.0N, no target, max hold 480 min, immediacy
marked at +30 min, target fill rate 0.35 (the STUDY_ATME figure at this depth) with a +/-0.03 band,
research block the first 65% of bars, locked read once at the end for SIGN only.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, "research")
sys.path.insert(0, "research/turtle")
sys.path.insert(0, "research/v50")
import data as TD           # noqa: E402
import v50sel as M          # noqa: E402

LIM_MULT = 1.0
STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN = 2.0, 0.0, 480, 30
FILL_TARGET, FILL_BAND = 0.35, 0.03
SPLIT, TF = 0.65, 5
MIN_FILLS = 100


def load():
    d = TD.bars("NQ", TF)
    d1 = TD.bars("NQ", 1)
    t = pd.to_datetime(pd.Series(d["idx"])); t1 = pd.to_datetime(pd.Series(d1["idx"]))
    m1 = pd.Series(np.arange(len(t1)), index=t1.values).reindex(t.values).to_numpy()
    P = dict(o=d["o"], h=d["h"], l=d["l"], c=d["c"], atr=d["atr"], n=len(d["c"]))
    return P, d1, m1


def audit(P, n_points=25, seed=0):
    """GATE 1. Recompute the whole ladder on history ENDING at bar i and require membership of
    bar i to be unchanged. A full-sample threshold (V49's np.nanquantile on roc) fails this."""
    rng = np.random.default_rng(seed)
    full = M.signals(P, min_n=0)
    pts = np.sort(rng.choice(np.arange(int(P["n"] * 0.45), P["n"] - 60), n_points, replace=False))
    bad, tested = {}, 0
    for i in pts:
        end = i + 51                                    # keep i clear of the ladder's tail mask
        Pt = {k: (v[:end] if isinstance(v, np.ndarray) else v) for k, v in P.items()}
        Pt["n"] = end
        tr = M.signals(Pt, min_n=0)
        for name, idx in full.items():
            if name not in tr:
                continue
            tested += 1
            if (i in idx) != (i in tr[name]):
                bad[name] = bad.get(name, 0) + 1
    return tested, bad


def calibrate(delay, res, valid):
    """Smallest expiry whose RESEARCH-block fill rate is closest to the declared target."""
    elig = res & valid
    if elig.sum() < 150:
        return -1, np.nan
    d = delay[elig]
    best_e, best_gap, best_f = -1, 9e9, np.nan
    for e in range(1, M.DELAY_CAP + 1):
        f = float(np.mean((d >= 0) & (d <= e)))
        gap = abs(f - FILL_TARGET)
        if gap < best_gap - 1e-12:
            best_e, best_gap, best_f = e, gap, f
        if f > FILL_TARGET + 0.25:
            break
    return best_e, best_f


def main():
    P, d1, m1 = load()
    cut = int(P["n"] * SPLIT)

    tested, bad = audit(P)
    print("=" * 100)
    print("  GATE 1 -- TRUNCATION AUDIT of the signal ladder")
    print("=" * 100)
    print(f"  {tested} (family, bar) recomputations on truncated history")
    if bad:
        for k, v in sorted(bad.items()):
            print(f"    LEAK {k}: {v} mismatches")
        print("  -> GATE 1 FAILED")
        return None
    print("  no family changes its value when history is truncated at the bar -> PASS")

    S = M.signals(P)
    rows = []
    for name, idx in sorted(S.items()):
        for side, slab in ((1, "L"), (-1, "S")):
            ent1 = m1[idx + 1]
            ok = np.isfinite(ent1)
            i2, e2 = idx[ok], ent1[ok].astype(np.int64)
            sc, aa = P["c"][i2], P["atr"][i2]
            f0, R0, Rk0, h0 = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], e2, sc, aa,
                                     0.0, 0, STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN,
                                     side, M.COST_PTS, M.SLIP_PTS)
            valid = f0.astype(bool) & np.isfinite(R0)
            dly = M.fill_delays(d1["h"], d1["l"], e2, sc, aa, LIM_MULT, side, M.DELAY_CAP)
            res, lk = (i2 < cut), (i2 >= cut)
            E, fach = calibrate(dly, res, valid)
            if E < 0:
                continue
            f1, _, _, _ = M.walk(d1["o"], d1["h"], d1["l"], d1["c"], e2, sc, aa,
                                 LIM_MULT, E, STOP_MULT, TP_R, MAX_HOLD_MIN, MARK_MIN,
                                 side, M.COST_PTS, M.SLIP_PTS)
            fm = f1.astype(bool)
            rec = {"family": f"{name}.{slab}", "side": slab, "expiry": E, "fill_res": fach}
            for bn, blk in (("res", res), ("lk", lk)):
                a = blk & valid
                b = a & fm
                c_ = a & ~fm
                rec[f"n_{bn}"] = int(a.sum()); rec[f"nf_{bn}"] = int(b.sum())
                if a.sum() < 150 or b.sum() < MIN_FILLS or c_.sum() < 30:
                    continue
                mu_all = float(R0[a].mean()); mu_f = float(R0[b].mean()); mu_n = float(R0[c_].mean())
                rec[f"mkt_{bn}_R"] = mu_all
                rec[f"sel_{bn}"] = mu_f - mu_all
                rec[f"gap_{bn}"] = mu_f - mu_n
                rec[f"immed_{bn}"] = float(np.nanmean(Rk0[a]))
                rec[f"fill_{bn}"] = float(fm[a].mean())
            rows.append(rec)
    D = pd.DataFrame(rows)
    D.to_csv("results/v50/v50_selection.csv", index=False)
    return D


if __name__ == "__main__":
    D = main()
    if D is not None:
        print(f"\n  {len(D)} family-side cells written to results/v50/v50_selection.csv")
