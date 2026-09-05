"""B. The configured script and its trail-off twin across feeds and timeframes, both blocks."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
print(f"  {'feed':7s}{'tf':>4s}{'variant':22s}{'block':10s}{'n':>6s}{'%/trade':>10s}{'PF':>8s}{'win':>7s}{'R':>8s}{'$ 5ct':>11s}{'hold':>6s}{'trail%':>7s}")
for m, tf in (("NQ", 1), ("NQ", 5), ("NQ", 15), ("US100", 15)):
    D = M.build(m, tf)
    for nm, cfg in (("as configured", M.CFG), ("trail OFF", dict(M.CFG, trail_on=0))):
        t = M.run(D, cfg=cfg)
        blocks = (("research", "locked") if m == "NQ" else ("research", "locked"))
        for b in blocks:
            r = t[t.block == b]; s = M.stats(r)
            tr = 100 * (r["exit"] == "trail").mean() if len(r) else np.nan
            print(f"  {m:7s}{tf:>4d}{nm:22s}{b:10s}{s['n']:>6d}{s['pct']:>10.4f}{s['pf']:>8.3f}{s['win']:>7.1f}{s['R']:>8.3f}{s['usd_tot']:>11,.0f}{s['hold']:>6.0f}{tr:>7.0f}")
    print()
print("  US100 is scored in its own points ($1/pt, 0.75/side); '$ 5ct' there is 5 x its point value, not MNQ.")
print("  US100's 'research'/'locked' here is the same 65/35 session split applied to its own 9 years.")
