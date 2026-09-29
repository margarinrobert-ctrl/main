"""Price the 11:00 flatten in the ONE configuration the user insists on. Research block only for
everything chosen; two reserved reads at the end, on cells named in `session.py` before either
block was opened.

TRIAL COUNT: 15 research hypotheses (10 ladder cells + 5 sub-windows). The tie=1 pass is a
ROBUSTNESS re-read of those same 15, not 15 more. Give-back and the permutation are descriptive.
Reserved: B_holdout and C_forward, 2 declared cells each plus the sub-window shape on B.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "us30scalp"))
import session as X  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 40)
np.set_printoptions(suppress=True)

BASE = dict(stop_a=30.0, tgt_a=150.0, use_pts=1)


def hr(s):
    print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100, flush=True)


def sigs(f, mask):
    s, d = S.donchian(f, 20, 1)
    m = mask[s]
    return s[m], d[m]


def cell(f, mask, m0, m1, flat, hold, stop, tgt, tie=0, label="", ctl=True, seed=0):
    s, d = sigs(f, mask)
    t = X.walkx(f, s, d, stop_a=stop, tgt_a=tgt, use_pts=1, m0=m0, m1=m1, flat=flat, hold=hold,
                tie=tie)
    r = X.summ(t, stop, tgt, label)
    if ctl and len(t) >= 20:
        p, med = X.control_p(f, t, m0, m1, n_draw=400, seed=seed, stop_a=stop, tgt_a=tgt,
                             use_pts=1, flat=flat, hold=hold, tie=tie)
        r["ctl"], r["ctl_p"] = med, p
    else:
        r["ctl"], r["ctl_p"] = np.nan, np.nan
    r["inside_mde"] = abs(r.get("pts", 0.0)) < r.get("mde", np.inf)
    return t, r


def show(rows, cols=None):
    df = pd.DataFrame(rows)
    if cols:
        df = df[cols]
    print(df.round(4).to_string(index=False), flush=True)
    return df


LADCOLS = ["cell", "n", "pts", "sd", "t", "mde", "inside_mde", "pf", "win", "be", "res_win",
           "med_min", "stop_sh", "tgt_sh", "cap_sh", "flat_sh", "amb", "ctl", "ctl_p"]

# ============================================================================================
f = S.load("US30L")
bl = S.blocks(f)
A, B = bl["A_research"], bl["B_holdout"]
print(f"US30L {f.index.min()} .. {f.index.max()}  {len(f)} bars", flush=True)
print(f"A_research {A.sum()} bars, B_holdout {B.sum()} bars", flush=True)
at = f["atr"].to_numpy(); w = X.elig_mask(f, 420, 660) & A
print(f"in-window median ATR(14) research: {np.nanmedian(at[w]):.2f} pts   "
      f"cost {X.COST} = {X.COST/30*100:.2f}% of a 30-pt stop, {X.COST/50*100:.2f}% of a 50-pt",
      flush=True)

# --- parity, stated rather than assumed -----------------------------------------------------
s0, d0 = sigs(f, A)
for kw in (dict(flat=660, hold=0), dict(flat=0, hold=16), dict(flat=0, hold=96)):
    t1 = S.walk(f, s0, d0, **BASE, **kw)
    t2 = X.walkx(f, s0, d0, **BASE, **kw)
    ok = (len(t1) == len(t2) and np.array_equal(t1.x_bar, t2.x_bar)
          and np.allclose(t1.pts, t2.pts) and np.array_equal(t1.why, t2.why))
    print(f"parity vs s30core.walk {kw}: n={len(t1)} identical={ok}", flush=True)

# ============================================================================================
hr("1. THE FLATTEN LADDER -- 10 declared cells, research block, tie=0 (stop-first)")
lad = {}
rows = []
for gname, stop, tgt in X.GEOMS:
    for k, (lname, flat, hold) in enumerate(X.LADDER):
        t, r = cell(f, A, 420, 660, flat, hold, stop, tgt, tie=0,
                    label=f"{gname} {lname}", seed=k)
        lad[(gname, lname)] = t
        rows.append(r)
show(rows, LADCOLS)

print("\n-- what the clock closed, and what it became (per-trade counterfactual: same position, "
      "same barriers, left open to stop/target or 96 bars)", flush=True)
rows = []
for gname, stop, tgt in X.GEOMS:
    for lname, flat, hold in X.LADDER:
        t = lad[(gname, lname)]
        cl = t[t.why.isin([2, 3])]
        if not len(cl):
            rows.append(dict(cell=f"{gname} {lname}", n_clock=0))
            continue
        rows.append(dict(
            cell=f"{gname} {lname}", n_clock=len(cl), clock_sh=len(cl) / len(t),
            at_bell=float(cl.pts.mean()), became=float(cl.cont.mean()),
            delta=float((cl.cont - cl.pts).mean()),
            became_tgt=float((cl.cont_why == 1).mean()),
            became_stop=float((cl.cont_why == 0).mean()),
            book_pts=float(t.pts.mean()), book_if_held=float(t.cont.mean()),
            book_delta=float((t.cont - t.pts).mean())))
show(rows)

# ============================================================================================
hr("2. GIVE-BACK on the trades the clock closes -- ATR at the SIGNAL bar, never R")
rows = []
for gname, stop, tgt in X.GEOMS:
    for lname, flat, hold in X.LADDER:
        t = lad[(gname, lname)]
        cl = t[t.why.isin([2, 3])]
        if len(cl) < 5:
            continue
        rows.append(dict(
            cell=f"{gname} {lname}", n_clock=len(cl),
            mfe_atr=float(cl.mfe_atr.mean()), mfe_atr_med=float(cl.mfe_atr.median()),
            mae_atr=float(cl.mae_atr.mean()),
            realised_atr=float((cl.gross / cl.atr_sig).mean()),
            give_atr=float(cl.give_atr.mean()), give_atr_med=float(cl.give_atr.median()),
            give_pts=float((cl.mfe - cl.gross).mean()),
            p90_give=float(cl.give_atr.quantile(0.90)),
            in_profit_at_bell=float((cl.pts > 0).mean()),
            reached_1atr=float((cl.mfe_atr >= 1.0).mean())))
show(rows)

print("\n-- the same three numbers for ALL trades of each cell, so the clock trades can be "
      "compared with the ones that resolved", flush=True)
rows = []
for gname, stop, tgt in X.GEOMS:
    for lname, flat, hold in X.LADDER:
        t = lad[(gname, lname)]
        rs = t[t.why.isin([0, 1])]
        rows.append(dict(cell=f"{gname} {lname}", n=len(t),
                         all_mfe_atr=float(t.mfe_atr.mean()),
                         all_mae_atr=float(t.mae_atr.mean()),
                         all_give_atr=float(t.give_atr.mean()),
                         res_mfe_atr=float(rs.mfe_atr.mean()) if len(rs) else np.nan,
                         res_give_atr=float(rs.give_atr.mean()) if len(rs) else np.nan))
show(rows)

# ============================================================================================
hr("3. ENTRY SUB-WINDOWS UNDER THE 11:00 FLATTEN -- 5 declared cells, 30/150")
rows = []
for k, (wname, m0, m1) in enumerate(X.SUBWINDOWS):
    _, r = cell(f, A, m0, m1, 660, 0, 30.0, 150.0, tie=0, label=f"A {wname}", seed=100 + k)
    rows.append(r)
show(rows, LADCOLS)
print("\n-- the SHAPE on B_holdout (declared read; expect it not to hold -- a session preference "
      "has failed to transfer six times here)", flush=True)
rows = []
for k, (wname, m0, m1) in enumerate(X.SUBWINDOWS):
    _, r = cell(f, B, m0, m1, 660, 0, 30.0, 150.0, tie=0, label=f"B {wname}", seed=200 + k)
    rows.append(r)
show(rows, LADCOLS)

# ============================================================================================
hr("4. THE INTRABAR TIE-BREAK BRACKET -- every cell above under tie=0 and tie=1")
rows = []
for gname, stop, tgt in X.GEOMS:
    for lname, flat, hold in X.LADDER:
        t0 = lad[(gname, lname)]
        t1, _ = cell(f, A, 420, 660, flat, hold, stop, tgt, tie=1, ctl=False)
        rows.append(dict(cell=f"{gname} {lname}", n=len(t0), amb=float(t0.amb.mean()),
                         stop_first=float(t0.pts.mean()), tgt_first=float(t1.pts.mean()),
                         spread=float(t1.pts.mean() - t0.pts.mean()),
                         pf_stop=S.pf(t0.pts), pf_tgt=S.pf(t1.pts),
                         sign_flip=bool((t0.pts.mean() > 0) != (t1.pts.mean() > 0)),
                         mde=X.mde(t0.pts)))
for k, (wname, m0, m1) in enumerate(X.SUBWINDOWS):
    ta, _ = cell(f, A, m0, m1, 660, 0, 30.0, 150.0, tie=0, ctl=False)
    tb, _ = cell(f, A, m0, m1, 660, 0, 30.0, 150.0, tie=1, ctl=False)
    rows.append(dict(cell=f"A {wname}", n=len(ta), amb=float(ta.amb.mean()),
                     stop_first=float(ta.pts.mean()), tgt_first=float(tb.pts.mean()),
                     spread=float(tb.pts.mean() - ta.pts.mean()),
                     pf_stop=S.pf(ta.pts), pf_tgt=S.pf(tb.pts),
                     sign_flip=bool((ta.pts.mean() > 0) != (tb.pts.mean() > 0)),
                     mde=X.mde(ta.pts)))
show(rows)

# ============================================================================================
hr("5. DRAWDOWN, SEPARATELY FROM RETURN -- 4,000-draw permutation of the daily series")
rows = []
for gname, stop, tgt in X.GEOMS:
    for lname, flat, hold in X.LADDER:
        t = lad[(gname, lname)]
        v = X.daily_pnl(f, t, A)
        real, dist = X.perm_dd(v.to_numpy(), n=4000, seed=11)
        rows.append(dict(cell=f"{gname} {lname}", n=len(t), total=float(t.pts.sum()),
                         days=len(v), dd=real, pct_of_perm=float(np.mean(dist <= real)),
                         p50=float(np.percentile(dist, 50)), p99=float(np.percentile(dist, 99)),
                         p99_over_real=float(np.percentile(dist, 99) / max(real, 1e-9)),
                         ret_dd=float(t.pts.sum() / max(real, 1e-9))))
show(rows)

# ============================================================================================
hr("6. RESERVED READS -- declared cells only: flat 11:00 vs no-flat 4h cap, 30/150, 07:00-11:00")
rows = []
for bname, mask, ff in (("A_research", A, f), ("B_holdout", B, f)):
    for lname, flat, hold in (("flat 11:00", 660, 0), ("no flat, 4h cap", 0, 16)):
        _, r = cell(ff, mask, 420, 660, flat, hold, 30.0, 150.0, tie=0,
                    label=f"{bname} {lname}", seed=300)
        rows.append(r)
fi = S.load("US30I")
Cm = S.blocks(fi, "US30I")["C_forward"]
print(f"US30I {fi.index.min()} .. {fi.index.max()}  C_forward {Cm.sum()} bars", flush=True)
for lname, flat, hold in (("flat 11:00", 660, 0), ("no flat, 4h cap", 0, 16)):
    _, r = cell(fi, Cm, 420, 660, flat, hold, 30.0, 150.0, tie=0,
                label=f"C_forward {lname}", seed=300)
    rows.append(r)
show(rows, LADCOLS)

print("\n-- and the same six cells under tie=1, so the reserved reads carry their bracket too",
      flush=True)
rows = []
for bname, mask, ff in (("A_research", A, f), ("B_holdout", B, f), ("C_forward", Cm, fi)):
    mk = mask if bname != "C_forward" else Cm
    src = ff
    for lname, flat, hold in (("flat 11:00", 660, 0), ("no flat, 4h cap", 0, 16)):
        t0, _ = cell(src, mk, 420, 660, flat, hold, 30.0, 150.0, tie=0, ctl=False)
        t1, _ = cell(src, mk, 420, 660, flat, hold, 30.0, 150.0, tie=1, ctl=False)
        rows.append(dict(cell=f"{bname} {lname}", n=len(t0), amb=float(t0.amb.mean()),
                         stop_first=float(t0.pts.mean()), tgt_first=float(t1.pts.mean()),
                         spread=float(t1.pts.mean() - t0.pts.mean()),
                         pf_stop=S.pf(t0.pts), pf_tgt=S.pf(t1.pts),
                         sign_flip=bool((t0.pts.mean() > 0) != (t1.pts.mean() > 0))))
show(rows)
print("\nDONE", flush=True)
