"""E. Does the entry's fixed-horizon information reproduce on the other feeds? No exits involved."""
from __future__ import annotations
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
rng = np.random.default_rng(3)
print(f"  {'feed':7s}{'tf':>3s}{'block':10s}{'h':>4s}{'long n':>8s}{'long excess/ATR':>17s}{'p':>7s}{'short n':>9s}{'short excess/ATR':>18s}{'p':>7s}")
for m, tf in (("NQ", 1), ("NQ", 5), ("NQ", 15), ("US100", 15)):
    D = M.build(m, tf); sig = M.signals(D); c, atr = D["c"], D["atr"]
    for bname in ("research", "locked"):
        blk = D["blocks"][bname]
        ins = (D["mod"] >= M.CFG["sess_start"]) & (D["mod"] < M.CFG["sess_end"]) & blk & np.isfinite(atr) & (atr > 0)
        pool = np.flatnonzero(ins)
        for hz in ((3, 6, 12) if tf == 5 else ((15, 30, 60) if tf == 1 else (1, 2, 4))):
            fwd = (np.roll(c, -hz - 1) - np.roll(c, -1)) / atr; fwd[-hz - 2:] = np.nan
            L = fwd[(sig == 1) & blk]; S = -fwd[(sig == -1) & blk]
            rl = np.array([np.nanmean(fwd[rng.choice(pool, len(L))]) for _ in range(300)])
            rs = np.array([np.nanmean(-fwd[rng.choice(pool, len(S))]) for _ in range(300)])
            print(f"  {m:7s}{tf:>3d}{bname:10s}{hz:>4d}{len(L):>8d}{np.nanmean(L)-rl.mean():>17.4f}{(rl>=np.nanmean(L)).mean():>7.3f}"
                  f"{len(S):>9d}{np.nanmean(S)-rs.mean():>18.4f}{(rs>=np.nanmean(S)).mean():>7.3f}")
    print()
print("  horizons are ~15 / 30 / 60 minutes on every feed. 'excess' is the signal's mean forward move in its own")
print("  direction minus a random same-size in-session draw. The NQ locked and US100 columns are reads of blocks")
print("  that had no part in noticing the short-side effect on NQ 5m research.")
