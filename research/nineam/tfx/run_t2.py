"""T2 -- DECLARED CONVERSION ARMS per timeframe, each against a matched random ENTRY and a
same-selectivity random GATE (400 draws each), with the MDE beside every row; then a LATENCY
DECOMPOSITION executed on the 30-second path so the chart's bar size is the only thing moved.

Arms, declared before running:
  (a) as configured: EMA 13/48 BARS, cross reach max(1, round(7/tf)) bars, range stamps in [540,545)
  (b) EMA held at MATCHED MINUTES: fast = max(1, round(6.5/tf)), slow = max(2, round(24/tf))
  (c) (b) + the two further hidden resolution dependences T1 found:
        - cross reach in CLOCK MINUTES (age x tf <= 7, so floor(7/tf) bars, 0 allowed): the
          script's max(1, round()) is 8 min at 2m/4m and 15 min at 15m;
        - range = only bars lying ENTIRELY inside 09:00-09:05 (at 2m that is 09:00-09:04, at 4m
          09:00-09:04, at 3m 09:00-09:03); at 15m no bar fits, so the 09:00 bar is kept and the
          distortion is IRREDUCIBLE there.
ATR is not an arm: T1 showed the signal set and every trade identical at ATR 7/14/45.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tfx_core as X   # noqa: E402

pd.set_option("display.width", 240)
P0 = dict(X.TV)
ND = 400


def hd(t):
    print("\n" + "=" * 110); print(t); print("=" * 110)


def arm(tf, a):
    if a == "a":
        return (13, 48), dict(P0)
    fs = X.matched(tf)
    if a == "b":
        return fs, dict(P0)
    re_ = 540 + tf * int(np.floor(5 / tf)) if tf <= 5 else 545
    re_ = int(round(re_)) if tf >= 1 else 545
    return fs, dict(P0, ma_mode="xmin", cross_min=7, range_end=re_)


c30 = X.ctx(0.5)
alld, is_d, oos_d = X.split(c30, P0)

hd("3  CONVERSION ARMS x TIMEFRAME -- both nulls, day-block bootstrap, MDE")
rows = []
for tf in X.TFS:
    for a in ("a", "b", "c"):
        (fa, sl), P = arm(tf, a)
        c = X.ctx(tf, fa, sl)
        row, tr = X.full(c, P, ND, seed=int(tf * 100) + ord(a))
        for lab, dd in (("is", is_d), ("oos", oos_d)):
            s = X.stats(X.S.sub(tr, dd) if tr is not None else None)
            row[f"{lab}_n"] = s["n"]; row[f"{lab}_pct"] = s["pct"]; row[f"{lab}_pf"] = s["pf"]
        row.update(tf=tf, arm=a, fast=fa, slow=sl, range_end=P["range_end"],
                   gate=P["ma_mode"] + (f"{P['cross_min']}m"))
        rows.append(row)
        print(f"  {tf:>4}m ({a}) EMA {fa:>2}/{sl:<3} re {P['range_end']} n {row['n']:3d} sess {row['sess']:3d} "
              f"kept {row['kept']:3d}/{row['ungated']:3d}  %/tr {row['pct']:+.4f} PF {row['pf']:.3f} "
              f"win {row['win']:.3f}  MDE {row['mde']:.4f} ratio {row['ratio']:+.2f}  "
              f"p_entry {row.get('p_entry', np.nan):.3f} p_gate {row.get('p_gate', np.nan):.3f} "
              f"boot {row.get('p_boot', np.nan):.3f}  IS {row['is_pct']:+.4f}/{row['is_n']} "
              f"OOS {row['oos_pct']:+.4f}/{row['oos_n']}", flush=True)
res = pd.DataFrame(rows)
res.to_csv(os.path.join(HERE, "t2_arms.csv"), index=False)

# ============================================================ latency decomposition on the 30s path
hd("3b LATENCY DECOMPOSITION -- the 30s rule, gate and exits UNCHANGED, fill delayed to the close "
   "of the tf-bar containing the touch")
f30 = c30.f0
t_open = c30.tclose - 0.5
lat = []
sig_g, sd_g = c30.sigs(P0)
atrf = c30.atr_frame(14)
for tf in X.TFS:
    if tf == 0.5:
        s2 = sig_g.copy()
    else:
        end = (np.floor(t_open[sig_g] / tf) + 1.0) * tf          # close time of the tf bar
        nxt = np.searchsorted(t_open, end - 1e-9, side="left")   # first 30s bar opening at/after it
        s2 = np.minimum(nxt - 1, len(t_open) - 2)
    o = np.argsort(s2, kind="stable")
    tr = c30._walk_sig(P0, atrf, s2[o], sd_g[o])
    s = X.stats(tr)
    delay = np.median(t_open[np.minimum(s2 + 1, len(t_open) - 1)] - t_open[np.minimum(sig_g + 1, len(t_open) - 1)])
    ce = X.control(c30, P0, s2[o], sd_g[o], 200, seed=7) if tr is not None else np.array([np.nan])
    lat.append(dict(tf=tf, median_extra_delay_min=float(delay), n=s["n"], pct=s["pct"], pf=s["pf"],
                    win=s["win"], mde=s["mde"], ratio=s["ratio"], p_entry=X.pval(s["pct"], ce)))
    print(f"  {tf:>4}m-equivalent fill  +{delay:4.2f} min  n {s['n']:3d} %/tr {s['pct']:+.4f} "
          f"PF {s['pf']:.3f} win {s['win']:.3f}  ratio {s['ratio']:+.2f}  p_entry {lat[-1]['p_entry']:.3f}",
          flush=True)
pd.DataFrame(lat).to_csv(os.path.join(HERE, "t2_latency.csv"), index=False)
print("  The random-entry null here draws from the 30s bars of the same sessions/window, so it does")
print("  NOT carry the imposed latency -- read the p-values as 'delayed rule vs undelayed random'.")
print("\ndone.")
