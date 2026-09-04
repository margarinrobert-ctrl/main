"""STAGE 5 - PROBABILITY OF BACKTEST OVERFITTING (CSCV).

Bailey & Lopez de Prado's combinatorially-symmetric cross-validation. Splits the
per-session P&L of MANY configurations into S contiguous blocks; for every
balanced train/test partition, asks where the IN-SAMPLE winner lands OUT OF
SAMPLE. PBO is the share of partitions where it falls below the median.

This tests the SELECTION PROCEDURE, not any one strategy. PBO above 0.5 means a
better in-sample number is actively BAD news - the search is mining noise.

Research block only; the locked block is never touched.
"""
import numpy as np, pandas as pd, itertools
from engine import build_walk, stats
from strategy import run
import lab, data as D

SYM = "NAS"
df, w, res = lab.research(SYM)
sess = df.sess.values
res_sess = np.unique(sess[res])

# ---- build a realistic configuration grid (what a search would actually try)
grid = []
for n_e in (5, 10, 15, 20, 30, 40, 60):
    for sm in (0.75, 1.0, 1.5, 2.0, 2.5):
        for tm in (1.0, 1.5, 2.0, 3.0):
            grid.append((n_e, sm, tm))
print("="*100)
print(f"CSCV / PBO  -  {SYM}, 07:00-11:00 New York, RESEARCH BLOCK ONLY")
print(f"  configurations in grid: {len(grid)}")

# per-session net P&L matrix: rows = sessions, cols = configs
M = np.zeros((len(res_sess), len(grid)))
smap = {s: i for i, s in enumerate(res_sess)}
for c, (n_e, sm, tm) in enumerate(grid):
    tr = run(df, w, n_entry=n_e, stop_mult=sm, targ_mult=tm,
             cost_pts=lab.COST[SYM], slip_pts=lab.SLIP[SYM])
    tr = tr[np.isin(tr.sig_bar, np.where(res)[0])]
    if not len(tr): continue
    ss = sess[tr.sig_bar.values]
    agg = pd.Series(tr.net.values).groupby(ss).sum()
    for s_, v in agg.items():
        if s_ in smap: M[smap[s_], c] += v
print(f"  session x config P&L matrix: {M.shape}")
print(f"  best config in sample: {grid[int(np.argmax(M.sum(0)))]}  total {M.sum(0).max():,.0f} pts")
print(f"  configs with positive total: {(M.sum(0)>0).sum()} / {len(grid)}")

# ---- CSCV
S = 12                                    # contiguous blocks (must be even)
blocks = np.array_split(np.arange(len(res_sess)), S)
combos = list(itertools.combinations(range(S), S//2))
print(f"  CSCV: S={S} blocks -> {len(combos)} balanced partitions")

ranks, lam = [], []
for tr_b in combos:
    te_b = [b for b in range(S) if b not in tr_b]
    tr_i = np.concatenate([blocks[b] for b in tr_b])
    te_i = np.concatenate([blocks[b] for b in te_b])
    # in-sample performance -> pick winner
    is_perf = M[tr_i].mean(0)
    n_star = int(np.argmax(is_perf))
    # out-of-sample rank of that winner among all configs
    oos = M[te_i].mean(0)
    r = (oos < oos[n_star]).sum() / (len(oos) - 1)     # relative rank in [0,1]
    ranks.append(r)
    w_ = max(min(r, 1-1e-9), 1e-9)
    lam.append(np.log(w_/(1-w_)))
ranks = np.array(ranks); lam = np.array(lam)
pbo = float((lam <= 0).mean())

print("\n" + "="*100)
print(f"  median OOS rank of the IS winner : {np.median(ranks):.3f}   (0.5 = no better than median)")
print(f"  PBO (share of partitions where the IS winner lands below the OOS median): {pbo:.3f}")
print()
if pbo > 0.5:
    print("  PBO > 0.5  ->  PICKING THE IN-SAMPLE BEST IS WORSE THAN PICKING AT RANDOM.")
    print("  A better research number from this grid is actively bad news. Any candidate")
    print("  selected by maximising research performance over this family must be treated")
    print("  as noise until it clears an out-of-sample test it could not have been fitted to.")
elif pbo > 0.25:
    print("  PBO in (0.25, 0.5] -> substantial overfitting risk in the selection procedure.")
else:
    print("  PBO <= 0.25 -> the selection procedure carries acceptable overfitting risk.")

# ---- performance degradation: IS vs OOS scatter slope
is_all, oos_all = [], []
for tr_b in combos:
    te_b = [b for b in range(S) if b not in tr_b]
    tr_i = np.concatenate([blocks[b] for b in tr_b]); te_i = np.concatenate([blocks[b] for b in te_b])
    n_star = int(np.argmax(M[tr_i].mean(0)))
    is_all.append(M[tr_i].mean(0)[n_star]); oos_all.append(M[te_i].mean(0)[n_star])
is_all=np.array(is_all); oos_all=np.array(oos_all)
sl = np.polyfit(is_all, oos_all, 1)[0]
print(f"\n  performance degradation: OOS = {sl:+.3f} x IS + c")
print(f"    mean IS  of chosen config: {is_all.mean():+.3f} pts/session")
print(f"    mean OOS of chosen config: {oos_all.mean():+.3f} pts/session")
print(f"    {'negative slope: better in-sample predicts WORSE out-of-sample' if sl<0 else 'positive slope: some signal survives selection'}")
