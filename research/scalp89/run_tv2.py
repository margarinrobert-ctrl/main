"""The TradingView report reconciled with what the user has now said: MNQ, 15-MINUTE chart, NO
execution option ticked. So the platform ran the script at bar close and the model to match is the
broker emulator's -- which the first transliteration got wrong on the fill bar (see s89_pine.py).
Prints the old model and the Pine-faithful one side by side, on every window I have."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M, s89_pine as P
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 122 + f"\n{t}\n" + "=" * 122)
def hdr(): print(f"  {'':58s}{'n':>6s}{'PF':>7s}{'win%':>6s}{'avgW':>7s}{'avgL':>7s}{'$ 5 MNQ':>10s}{'fillbar%':>9s}  exits")
def row(nm, t):
    if len(t) == 0:
        print(f"  {nm:58s}     0"); return
    s = M.stats(t); w = t.net_pts[t.net_pts > 0]; l = t.net_pts[t.net_pts <= 0]
    mix = t["exit"].value_counts(normalize=True).mul(100).round(0).to_dict()
    fb = 100 * t["on_fill_bar"].mean() if "on_fill_bar" in t else float("nan")
    print(f"  {nm:58s}{s['n']:>6d}{s['pf']:>7.3f}{s['win']:>6.1f}{w.mean():>7.1f}{l.mean():>7.1f}{s['usd_tot']:>10,.0f}{fb:>9.1f}  "
          + " ".join(f"{k}{int(v)}%" for k, v in mix.items()))
WIN = {"research": lambda t: t.block == "research", "locked": lambda t: t.block == "locked",
       "last 365d of data (2024-12-11 ->)": lambda t: pd.DatetimeIndex(t.ts) >= "2024-12-11",
       "overlap with the screen (2025-09-04 ->)": lambda t: pd.DatetimeIndex(t.ts) >= "2025-09-04"}

for tf in (15, 5):
    D = M.build("NQ", tf)
    line(f"NQ {tf}m, MNQ economics ($2/pt, 1.24 $/contract/side, 1 tick slippage), as configured: 15/8 fixed trail, 1.5/2.5 ATR")
    models = [("OLD model: naked fill bar, trail cannot arm there (s89_core.walk)", M.run(D, protect_fill=0, path=1, cost=0.62 + 0.25)),
              ("PINE model: TRAIL LIVE on the fill bar, no stop/target there (the script)", P.run(D, fill_mode=1)),
              ("PINE model, fill bar naked (fill_mode 0)", P.run(D, fill_mode=0)),
              ("PINE model, everything live on the fill bar (fill_mode 2 = v2)", P.run(D, fill_mode=2)),
              ("PINE model, trail OFF", P.run(D, cfg=dict(M.CFG, trail_on=0), fill_mode=1)),
              ("PINE model, stop-first tie-break instead of the path", P.run(D, fill_mode=1, path=0)),
              ("PINE model, zero commission and slippage", P.run(D, fill_mode=1, fee=0.0, slip=0.0))]
    for wn, f in WIN.items():
        print(f"\n  -- {wn} --"); hdr()
        for nm, t in models:
            row(nm, t[f(t)] if len(t) else t)

line("WHAT THE FILL BAR DOES on 15m: trades that exit on the fill bar itself, under the script's model")
D = M.build("NQ", 15); t = P.run(D, fill_mode=1)
fb = t[t.on_fill_bar == 1]; rest = t[t.on_fill_bar == 0]
print(f"  exits on the fill bar: {len(fb)} of {len(t)} ({100*len(fb)/len(t):.1f}%), win {100*(fb.net_pts>0).mean():.1f}%, "
      f"mean {fb.net_pts.mean():+.1f} pts, all '{fb.exit.unique()}'")
print(f"  the rest:              {len(rest)}, win {100*(rest.net_pts>0).mean():.1f}%, mean {rest.net_pts.mean():+.1f} pts, "
      f"exits " + " ".join(f"{k}{int(v)}%" for k, v in rest.exit.value_counts(normalize=True).mul(100).round(0).items()))
rng = (D["h"] - D["l"]); ins = D["mod"] >= 0
print(f"  median 15m bar range: {np.nanmedian(rng[1000:]):.1f} pts; median ATR(14): {np.nanmedian(D['atr'][1000:]):.1f}; "
      f"so a 15-pt arm is reached inside the fill bar on {100*np.mean(rng[1000:] >= 15):.0f}% of bars")
print(f"  screenshot arithmetic: PF 3.08 at 84% wins needs avgW/avgL = {3.081*0.16/0.84:.2f}")
