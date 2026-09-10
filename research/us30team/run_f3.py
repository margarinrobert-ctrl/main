"""Two things run_f2 left open: the dose-response as a rank correlation, and whether the PAIRED
verdict survives the other intrabar convention. Descriptive; no new cells."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "us30scalp"))
import session as X  # noqa: E402
import s30core as S  # noqa: E402

pd.set_option("display.width", 200); pd.set_option("display.max_columns", 30)


def sigs(f, mask):
    s, d = S.donchian(f, 20, 1)
    m = mask[s]
    return s[m], d[m]


f = S.load("US30L"); bl = S.blocks(f)
fi = S.load("US30I"); Cm = S.blocks(fi, "US30I")["C_forward"]
BLK = [("A_research", f, bl["A_research"]), ("B_holdout", f, bl["B_holdout"]),
       ("C_forward", fi, Cm)]

print("=" * 96)
print("E1. PAIRED cost of the 11:00 bell under BOTH intrabar conventions "
      "(same entries, only the exit differs)")
print("=" * 96)
rows = []
for name, ff, mk in BLK:
    s, d = sigs(ff, mk)
    for tie in (0, 1):
        base = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660,
                       flat=660, hold=0, tie=tie)
        for lname, flat, hold in X.LADDER[1:]:
            alt = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660,
                          flat=flat, hold=hold, tie=tie)
            j = base[["e_bar", "pts"]].merge(alt[["e_bar", "pts"]], on="e_bar",
                                             suffixes=("_b", "_a"))
            dl = (j.pts_a - j.pts_b).to_numpy()
            ch = float((np.abs(dl) > 1e-9).mean())
            rows.append(dict(block=name, tie="stop-first" if tie == 0 else "target-first",
                             alt=lname, n=len(j), delta=float(dl.mean()),
                             t=float(dl.mean() / (dl.std(ddof=1) / np.sqrt(len(dl)))),
                             mde=X.mde(dl), pnl_changed=ch))
df = pd.DataFrame(rows)
print(df.round(4).to_string(index=False))
p = df.pivot_table(index=["block", "alt"], columns="tie", values="delta")
p["spread"] = p["target-first"] - p["stop-first"]
p["same_sign"] = np.sign(p["target-first"]) == np.sign(p["stop-first"])
print("\n" + p.round(4).to_string())
print(f"\ndeltas keeping their sign across the two conventions: "
      f"{int(p.same_sign.sum())} of {len(p)}")

print("\n" + "=" * 96)
print("E2. DOSE-RESPONSE: the cost of the bell against how often it binds")
print("=" * 96)
rows = []
for wname, m0, m1 in X.SUBWINDOWS:
    for bn, ff, mk in BLK:
        s, d = sigs(ff, mk)
        tt = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=m0, m1=m1, flat=660, hold=0)
        tn = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=m0, m1=m1, flat=0, hold=16)
        if len(tt) < 30:
            continue
        j = tt[["e_bar", "pts"]].merge(tn[["e_bar", "pts"]], on="e_bar", suffixes=("_f", "_n"))
        dl = (j.pts_n - j.pts_f).to_numpy()
        rows.append(dict(block=bn, window=wname, n=len(tt),
                         flat_sh=float((tt.why == 3).mean()),
                         med_min=float(tt["mins"].median()),
                         cost_of_bell=float(dl.mean()), t=float(
                             dl.mean() / (dl.std(ddof=1) / np.sqrt(len(dl)))),
                         mde=X.mde(dl)))
df = pd.DataFrame(rows)
print(df.round(4).to_string(index=False))
for bn in df.block.unique():
    z = df[df.block == bn]
    if len(z) < 3:
        continue
    r = stats.spearmanr(z.flat_sh, z.cost_of_bell)
    print(f"{bn}: Spearman(flatten share, cost of the bell) = {r.statistic:+.3f}  "
          f"(n={len(z)} windows), Pearson {z.flat_sh.corr(z.cost_of_bell):+.3f}")

print("\n" + "=" * 96)
print("E3. THE HEADLINE NUMBERS, one line each")
print("=" * 96)
for name, ff, mk in BLK:
    s, d = sigs(ff, mk)
    a = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660, flat=660, hold=0)
    b = X.walkx(ff, s, d, stop_a=30., tgt_a=150., use_pts=1, m0=420, m1=660, flat=0, hold=16)
    j = a[["e_bar", "pts"]].merge(b[["e_bar", "pts"]], on="e_bar", suffixes=("_f", "_n"))
    dl = (j.pts_n - j.pts_f).to_numpy()
    cl = a[a.why == 3]
    va = X.daily_pnl(ff, a, mk); vb = X.daily_pnl(ff, b, mk)
    ra, da = X.perm_dd(va.to_numpy(), 4000, 11)
    rb, db = X.perm_dd(vb.to_numpy(), 4000, 11)
    print(f"{name}: bell costs {dl.mean():+.3f} pts/trade paired (t {dl.mean()/(dl.std(ddof=1)/np.sqrt(len(dl))):.2f},"
          f" MDE {X.mde(dl):.2f}) | binds on {(a.why==3).mean():.1%} | "
          f"give-back {cl.give_atr.mean() if len(cl) else float('nan'):.2f} ATR | "
          f"DD on {ra:.0f} (pct {np.mean(da<=ra):.2f}) vs off {rb:.0f} (pct {np.mean(db<=rb):.2f}) | "
          f"ret/DD {a.pts.sum()/ra:.2f} vs {b.pts.sum()/rb:.2f}")
print("\nDONE")
