"""Does the CORRECTED order model (trail live on the fill bar, matching what strategy.exit
actually does when stop=/limit= are still na) beat a matched random-entry control? Same session,
same side mix, same geometry -- draws sorted into chronological order (STUDY_V59's fix)."""
import os, sys, warnings
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s89_core as M, s89_pine as P
warnings.filterwarnings("ignore")

def control(D, side, cfg, fill_mode, n_draw=300, seed=0):
    rng = np.random.default_rng(seed)
    real_n = int((side != 0).sum())
    idx = np.where((D["mod"] >= M.CFG["sess_start"]) & (D["mod"] < M.CFG["sess_end"]))[0]
    idx = idx[(idx > 200) & (idx < D["n"] - 3)]
    sides_pool = side[side != 0]
    out = []
    for _ in range(n_draw):
        pick = np.sort(rng.choice(idx, size=real_n, replace=False))
        rs = rng.permutation(sides_pool)
        s2 = np.zeros(D["n"], np.int64); s2[pick] = rs[:len(pick)]
        t = P.run(D, cfg=cfg, side_override=s2, fill_mode=fill_mode)
        out.append(t["pct"].mean() if len(t) else np.nan)
    return np.array(out)

for tf in (15, 5):
    D = M.build("NQ", tf); side = M.signals(D, M.CFG)
    for blk_name, mask in (("research", D["sess"] < D["cut"]), ("locked", D["sess"] >= D["cut"])):
        side_b = side.copy(); side_b[~mask] = 0
        t = P.run(D, side_override=side_b, fill_mode=1)
        obs = t["pct"].mean() if len(t) else np.nan
        ctl = control(D, side_b, M.CFG, fill_mode=1, n_draw=300, seed=hash((tf, blk_name)) % 2**31)
        p = float(np.mean(ctl >= obs))
        print(f"NQ {tf:2d}m {blk_name:8s}: n={len(t):4d}  observed %/trade {obs:+.4f}  "
              f"control median {np.nanmedian(ctl):+.4f}  5-95% [{np.nanpercentile(ctl,5):+.4f}, {np.nanpercentile(ctl,95):+.4f}]  p {p:.3f}")
