"""Diagnostics for run_f1. No new hypotheses: every number here decomposes a cell already scored.

The one that matters is the PAIRED comparison. Comparing two exit policies by their book means
confounds the exit with the TRADE SET -- holding longer keeps the position lock closed and refuses
later signals, so `flat 11:00` and `no flat` do not trade the same bars. Matched on ENTRY BAR, only
the exit differs, which is the question actually being asked.
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

pd.set_option("display.width", 220); pd.set_option("display.max_columns", 40)


def hr(s):
    print("\n" + "=" * 100 + f"\n{s}\n" + "=" * 100, flush=True)


def sigs(f, mask):
    s, d = S.donchian(f, 20, 1)
    m = mask[s]
    return s[m], d[m]


f = S.load("US30L"); bl = S.blocks(f)
fi = S.load("US30I"); Cm = S.blocks(fi, "US30I")["C_forward"]
BLK = [("A_research", f, bl["A_research"]), ("B_holdout", f, bl["B_holdout"]),
       ("C_forward", fi, Cm)]

hr("D1. A 30-POINT STOP IS A DIFFERENT GEOMETRY IN EACH BLOCK (`STUDY_DL50`)")
rows = []
for name, ff, mk in BLK:
    w = X.elig_mask(ff, 420, 660) & mk
    a = np.nanmedian(ff["atr"].to_numpy()[w])
    rows.append(dict(block=name, bars=int(w.sum()), atr=a, stop30_in_atr=30 / a,
                     stop50_in_atr=50 / a, tgt150_in_atr=150 / a,
                     cost_over_30=X.COST / 30, be_1to5=X.be_pts(30, 150)))
print(pd.DataFrame(rows).round(4).to_string(index=False), flush=True)

hr("D2. PAIRED ON THE ENTRY BAR -- only the exit differs")
for name, ff, mk in BLK:
    s, d = sigs(ff, mk)
    base = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660, flat=660, hold=0)
    rows = []
    for lname, flat, hold in X.LADDER:
        alt = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660,
                      flat=flat, hold=hold)
        j = base[["e_bar", "pts", "why"]].merge(alt[["e_bar", "pts", "why"]], on="e_bar",
                                                suffixes=("_b", "_a"))
        dl = (j.pts_a - j.pts_b).to_numpy()
        moved = j[j.why_b != j.why_a]
        rows.append(dict(block=name, alt=lname, shared=len(j), share_of_base=len(j) / len(base),
                         flat11=float(j.pts_b.mean()), alt_pts=float(j.pts_a.mean()),
                         delta=float(dl.mean()),
                         t=float(dl.mean() / (dl.std(ddof=1) / np.sqrt(len(dl))))
                         if dl.std(ddof=1) > 0 else np.nan,
                         mde=X.mde(dl), n_changed=len(moved),
                         changed_sh=len(moved) / len(j),
                         delta_on_changed=float((moved.pts_a - moved.pts_b).mean())
                         if len(moved) else 0.0))
    print(pd.DataFrame(rows).round(4).to_string(index=False), flush=True)
    print(flush=True)

hr("D3. WHAT THE BELL CLOSES, SPLIT BY WHETHER IT WAS WINNING AT THE TIME")
s, d = sigs(f, bl["A_research"])
t = X.walkx(f, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660, flat=660, hold=0)
cl = t[t.why == 3].copy()
cl["won_at_bell"] = cl.pts > 0
g = cl.groupby("won_at_bell").agg(n=("pts", "size"), at_bell=("pts", "mean"),
                                  became=("cont", "mean"), mfe_atr=("mfe_atr", "mean"),
                                  give_atr=("give_atr", "mean"),
                                  to_target=("cont_why", lambda x: (x == 1).mean()),
                                  to_stop=("cont_why", lambda x: (x == 0).mean()))
print(g.round(4).to_string(), flush=True)
print(f"\nflattened trades: {len(cl)} of {len(t)} ({len(cl)/len(t):.1%}); "
      f"mean at bell {cl.pts.mean():+.2f} pts, mean if held {cl.cont.mean():+.2f}, "
      f"delta {(cl.cont-cl.pts).mean():+.2f} on those trades "
      f"= {(cl.cont-cl.pts).sum()/len(t):+.2f} on the whole book", flush=True)
dl = (cl.cont - cl.pts).to_numpy()
print(f"delta on flattened trades: sd {dl.std(ddof=1):.1f}, "
      f"t {dl.mean()/(dl.std(ddof=1)/np.sqrt(len(dl))):.3f}, MDE {X.mde(dl):.2f} pts", flush=True)

hr("D4. FLATTEN SHARE AGAINST RESULT -- the dose-response, windows that all end at 11:00")
rows = []
for wname, m0, m1 in X.SUBWINDOWS:
    for bn, ff, mk in BLK[:2]:
        ss, dd = sigs(ff, mk)
        tt = X.walkx(ff, ss, dd, stop_a=30., tgt_a=150., use_pts=1, m0=m0, m1=m1, flat=660,
                     hold=0)
        tn = X.walkx(ff, ss, dd, stop_a=30., tgt_a=150., use_pts=1, m0=m0, m1=m1, flat=0,
                     hold=16)
        j = tt[["e_bar", "pts"]].merge(tn[["e_bar", "pts"]], on="e_bar", suffixes=("_f", "_n"))
        rows.append(dict(window=wname, block=bn, n=len(tt), flat_sh=float((tt.why == 3).mean()),
                         med_min=float(tt["mins"].median()), pts=float(tt.pts.mean()),
                         paired_flat=float(j.pts_f.mean()), paired_nofl=float(j.pts_n.mean()),
                         paired_delta=float((j.pts_n - j.pts_f).mean())))
df = pd.DataFrame(rows)
print(df.round(4).to_string(index=False), flush=True)
for bn in ("A_research", "B_holdout"):
    z = df[df.block == bn]
    print(f"{bn}: corr(flatten share, pts) = "
          f"{z.flat_sh.corr(z.pts):+.3f} Pearson / {z.flat_sh.corr(z.pts, 'spearman'):+.3f} "
          f"Spearman", flush=True)
a = df[df.block == "A_research"].set_index("window").pts
b = df[df.block == "B_holdout"].set_index("window").pts
print(f"\nsub-window rank transfer A->B: Pearson {a.corr(b):+.3f}, "
      f"Spearman {a.corr(b, 'spearman'):+.3f}; best on A = {a.idxmax()}, best on B = {b.idxmax()}",
      flush=True)

hr("D5. DRAWDOWN -- where it comes from, and whether the stop already caps it")
s, d = sigs(f, bl["A_research"])
for lname, flat, hold in (("flat 11:00", 660, 0), ("no flat, 4h cap", 0, 16),
                          ("no flat, 1d cap", 0, 96)):
    tt = X.walkx(f, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660, flat=flat,
                 hold=hold)
    v = X.daily_pnl(f, tt, bl["A_research"])
    real, dist = X.perm_dd(v.to_numpy(), n=4000, seed=11)
    p = tt.pts.to_numpy()
    print(f"{lname:18s} n {len(tt):5d}  worst trade {p.min():8.1f}  p1 {np.percentile(p,1):7.1f}"
          f"  worst day {v.min():8.1f}  DD {real:8.1f} (pct {np.mean(dist<=real):.3f}, "
          f"p99 {np.percentile(dist,99):.0f})  total {p.sum():8.1f}  ret/DD {p.sum()/real:5.2f}",
          flush=True)
print("\nEvery loss is already bounded by the 30-point stop plus slippage, so a bell cannot cut "
      "the losing tail -- it can only cut the winning one.", flush=True)
print("\nDONE", flush=True)
