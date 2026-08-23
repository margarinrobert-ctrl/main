"""Read the EMA search results and answer: is there an edge, and does it ADD to the BOS book?"""
import sys; sys.path.insert(0,'research')
import numpy as np
R = np.load("/tmp/ema_rows.npy")
rn, rs, ln, ls, ntr, side, ef, es, tp, sl, mins = [R[:, i] for i in range(11)]
rng = np.random.default_rng(20260823)
N = len(R)
print(f"{N:,} cells with >= 20 trades\n")

print("="*80); print("1. HOW MANY CELLS ARE PROFITABLE AT ALL?"); print("="*80)
print(f"   positive on research      : {100*(rn>0).mean():>5.1f}%")
print(f"   positive on LOCKED        : {100*(ln>0).mean():>5.1f}%")
print(f"   positive on BOTH          : {100*((rn>0)&(ln>0)).mean():>5.1f}%")
print(f"   median LOCKED net $       : {np.median(ln):>8,.0f}")
print(f"   best research cell's LOCKED result: ${ln[np.argmax(rs)]:,.0f} "
      f"(research Sharpe {rs.max():.2f}, locked Sharpe {ls[np.argmax(rs)]:.2f})")

print(); print("="*80); print("2. SEARCH CURVE — best-on-research at width K, then its LOCKED result"); print("="*80)
print(f"{'K cells':>10}{'locked Sharpe':>15}{'locked net $':>14}{'P(locked<0)':>13}")
def curve(mask, tag):
    idx = np.flatnonzero(mask)
    if len(idx) < 100: return
    print(f"  -- {tag} ({len(idx):,} cells) --")
    for K in (1, 10, 100, 1000, 10000, 100000, len(idx)):
        if K > len(idx): K = len(idx)
        sh, neg, net = [], 0, []
        for _ in range(400):
            pick = rng.choice(idx, size=K, replace=False) if K < len(idx) else idx
            b = pick[np.argmax(rs[pick])]
            sh.append(ls[b]); net.append(ln[b]); neg += (ln[b] < 0)
        print(f"{K:>10,}{np.mean(sh):>15.2f}{np.mean(net):>14,.0f}{100*neg/400:>12.0f}%")
        if K == len(idx): break
curve(np.ones(N, bool), "ALL cells (direction free)")
print()
curve(side == 0, "BOTH SIDES ONLY (direction held fixed)")

print(); print("="*80); print("3. WHAT DO THE 'WINNERS' ACTUALLY HAVE IN COMMON?"); print("="*80)
win = (rn > 0) & (ln > 0)
print(f"   {win.sum():,} cells positive on both blocks ({100*win.mean():.1f}%)")
for nm, arr, vals in (("side", side, [-1, 0, 1]), ("timeframe", mins, [15, 30, 60]),
                      ("target R", tp, [1.0, 1.5, 2.0, 2.5, 3.0])):
    print(f"   {nm}:")
    for v in vals:
        base = (arr == v).mean(); got = (arr[win] == v).mean()
        print(f"      {v:>6}  {100*got:>5.1f}% of winners vs {100*base:>5.1f}% of all"
              f"   lift {got/base if base>0 else 0:>4.2f}")
