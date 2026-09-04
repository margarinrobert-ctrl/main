"""The screenshots set the session to 06:00-11:30 CHICAGO with a 1-minute warmup.
Chicago is New York minus one hour, so that window is 07:01-12:30 NEW YORK - not
the 07:00-11:00 New York the strategy is described as trading. This measures both,
plus the sub-windows, on the research block under every exit convention.
"""
import numpy as np, pandas as pd, sys, json, warnings
sys.path.insert(0, "/home/user/main/research/donchian"); sys.path.insert(0, ".")
warnings.filterwarnings("ignore")
import nqs, cache, data as D

df = D.load("NAS"); B = cache.build(df); R, H = D.blocks(df)
WINDOWS = [
    ("as configured: 06:00-11:30 Chicago = 07:01-12:30 NY", 6, 0, 11, 30),
    ("07:00-11:00 NEW YORK = 06:00-10:00 Chicago",           6, 0, 10, 0),
    ("09:30-11:00 NEW YORK = 08:30-10:00 Chicago (RTH only)", 8, 30, 10, 0),
    ("08:30-11:30 Chicago (US cash open onward)",             8, 30, 11, 30),
    ("full RTH 08:30-15:00 Chicago",                          8, 30, 15, 0),
]
print("=" * 118)
print("19. SESSION WINDOW - the screenshots do not trade 07:00-11:00 New York")
print("=" * 118)
rows = []
for lbl, sh_, sm_, eh_, em_ in WINDOWS:
    out = {}
    for tm in ("barclose", "intrabar"):
        I, p = cache.indicators(df, B, sess_start_h=sh_, sess_start_m=sm_,
                                sess_end_h=eh_, sess_end_m=em_)
        (lo, s2), _ = nqs.conditions(df, I, p)
        tr = nqs.simulate(df, I, p, lo & R, s2 & R, order="adverse", trail_mode=tm)
        g = nqs.simulate(df, I, p, lo & R, s2 & R, order="adverse", trail_mode=tm, cost_mult=0.0)
        out[tm] = (len(tr), tr.net_pts.mean(), tr.net_usd.sum(), g.net_pts.mean())
    rows.append(dict(window=lbl, n=out["barclose"][0],
                     bc_exp=out["barclose"][1], bc_gross=out["barclose"][3], bc_usd=out["barclose"][2],
                     ib_exp=out["intrabar"][1], ib_usd=out["intrabar"][2]))
    print(f"\n  {lbl}")
    print(f"    barclose/adverse  n={out['barclose'][0]:>5}  gross {out['barclose'][3]:+.2f}  "
          f"net {out['barclose'][1]:+.2f} pts/trade  ${out['barclose'][2]:+,.0f}")
    print(f"    intrabar/adverse  n={out['intrabar'][0]:>5}  "
          f"net {out['intrabar'][1]:+.2f} pts/trade  ${out['intrabar'][2]:+,.0f}")
pd.DataFrame(rows).to_csv("/home/user/main/docs/nqscalp/session_windows.csv", index=False)
print("\n  written: session_windows.csv")
