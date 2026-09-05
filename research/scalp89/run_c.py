"""C. Does the ENTRY carry information at all? Two tests that do not depend on the exits."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 124 + f"\n{t}\n" + "=" * 124)
D = M.build("NQ", 5); rng = np.random.default_rng(3)
res = D["blocks"]["research"]; sig = M.signals(D)
c, atr = D["c"], D["atr"]

line("1. FIXED-HORIZON FORWARD RETURN at signal bars vs random in-session bars, in ATR units (research)")
ins = (D["mod"] >= M.CFG["sess_start"]) & (D["mod"] < M.CFG["sess_end"]) & res & np.isfinite(atr) & (atr > 0)
print(f"  {'horizon':>8s}{'long n':>8s}{'long fwd/ATR':>14s}{'short n':>9s}{'short fwd/ATR':>15s}{'random':>10s}{'long-rand':>11s}{'short-rand':>12s}{'p long':>8s}{'p short':>9s}")
for hz in (1, 3, 6, 12, 24, 48):
    fwd = (np.roll(c, -hz - 1) - np.roll(c, -1)) / atr        # from next open-ish (next close proxy) to hz bars later
    fwd[-hz - 2:] = np.nan
    L = fwd[(sig == 1) & res]; S = -fwd[(sig == -1) & res]
    pool = np.flatnonzero(ins); 
    rl = np.array([np.nanmean(fwd[rng.choice(pool, len(L))]) for _ in range(500)])
    rs = np.array([np.nanmean(-fwd[rng.choice(pool, len(S))]) for _ in range(500)])
    print(f"  {hz:>8d}{len(L):>8d}{np.nanmean(L):>14.4f}{len(S):>9d}{np.nanmean(S):>15.4f}{np.nanmean(fwd[pool]):>10.4f}"
          f"{np.nanmean(L)-rl.mean():>11.4f}{np.nanmean(S)-rs.mean():>12.4f}{(rl>=np.nanmean(L)).mean():>8.3f}{(rs>=np.nanmean(S)).mean():>9.3f}")
print("  'random' is the unconditional forward move of an in-session research bar (long sign). p is the share of")
print("  500 random same-size draws that match or beat the signal's mean forward move in ITS direction.")

line("2. MATCHED CONTROL -- same bars' GEOMETRY and side, random in-session entry bar, trail OFF and as configured")
for nm, cfg in (("trail OFF (1.5 / 2.5 ATR bracket)", dict(M.CFG, trail_on=0)), ("as configured (15/8 trail)", M.CFG)):
    t = M.run(D, cfg=cfg); r = t[t.block == "research"]
    obs = r["pct"].mean(); nL = int((r.side == 1).sum()); nS = int((r.side == -1).sum())
    pool = np.flatnonzero(ins); draws = np.zeros(300)
    for d in range(300):
        pick = np.sort(rng.choice(pool, size=min(len(pool), 3 * len(r)), replace=False))
        so = np.zeros(D["n"], np.int64)
        sides = rng.choice([1, -1], size=len(pick), p=[nL / (nL + nS), nS / (nL + nS)])
        so[pick] = sides
        tc = M.run(D, cfg=cfg, side_override=so); tc = tc[tc.block == "research"]
        draws[d] = tc["pct"].mean() if len(tc) else 0.0
    print(f"  {nm:36s} n {len(r):5d}  observed {obs:+.4f}  control median {np.median(draws):+.4f}"
          f"  5-95% [{np.quantile(draws,.05):+.4f}, {np.quantile(draws,.95):+.4f}]  p {(draws>=obs).mean():.3f}")
print("  The control draws the same MIX of long/short at random in-session bars and runs the identical exit machine")
print("  (with the position lock), so it prices the geometry, the session and the drift; the rule must beat it.")
