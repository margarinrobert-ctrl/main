"""V3 -- the null in V2 is TOO EASY, and this is the corrected one.

V2 permutes the target freely. That destroys its autocorrelation, and an IC computed on 46,000
OVERLAPPING observations of a highly persistent target has a standard error far larger than a
freely-permuted null suggests. The symptom is unmistakable in V2's own output: the max of 71
features over 40 permutations lands at |IC| ~0.015 for EVERY target, so `dir` at 0.0231 and `er` at
0.0274 formally "clear" -- which would mean direction is predictable, and it is not. What cleared is
the null's own weakness.

THE FIX IS A CIRCULAR BLOCK PERMUTATION. Cut the target into contiguous blocks much longer than the
horizon and permute the BLOCKS, so local persistence survives and only the alignment between
feature and target is destroyed. That is the null the question actually poses.

`STUDY_V47` recorded the same lesson from the t-statistic side: Newey-West at lag h deflated the
naive t by 1.9x to 3.2x. The naive permutation makes the same mistake in the other direction.
"""
import os, sys, time
import numpy as np, pandas as pd
sys.path.insert(0, "research/v67"); sys.path.insert(0, "research/v22")
import v67core as V
import v22vol as VV

t0 = time.time(); pd.set_option("display.width", 220)
def say(*a): print(*a, flush=True)
say(__doc__)

D = V.load(15)
mR = D["blk"] == 0
X = pd.DataFrame(VV.build(D["o"], D["h"], D["l"], D["c"]))
Xa = X.to_numpy(float)
FEATS = list(X.columns)
say(f"[{time.time()-t0:6.1f}s] {D['n']:,} bars, {len(FEATS)} features")


def block_perm(y, block, rng):
    """Circular block permutation: local structure kept, alignment destroyed."""
    n = len(y)
    nb = int(np.ceil(n / block))
    starts = rng.integers(0, n, nb)
    out = np.empty(n)
    p = 0
    for s in starts:
        take = min(block, n - p)
        idx = (np.arange(s, s + take)) % n
        out[p:p + take] = y[idx]
        p += take
        if p >= n:
            break
    return out


NPERM = 40
say(f"\n[{time.time()-t0:6.1f}s] CORRECTED NULL -- circular block permutation, block = 20 x horizon")
say(f"{'h':>4} {'target':>7} {'real':>8} {'free p95':>9} {'block p95':>10} {'block max':>10} "
    f"{'NW t':>8} {'verdict':>8}")
rows = []
free = pd.read_csv("results/v67/v2_maxnull.csv") if os.path.exists("results/v67/v2_maxnull.csv") \
    else None
for h in V.HORIZONS:
    T = V.build_targets(D, h)
    blk = 20 * h
    for tg in V.TARGETS:
        y = T[tg]
        m = mR & np.isfinite(y)
        yy = y[m]; Z = Xa[m]
        rng = np.random.default_rng(hash((h, tg)) % 99991)
        real = 0.0; bestk = -1
        for k in range(Z.shape[1]):
            v = V.ic(Z[:, k], yy)
            if np.isfinite(v) and abs(v) > real:
                real, bestk = abs(v), k
        nulls = np.empty(NPERM)
        for j in range(NPERM):
            ys = block_perm(yy, blk, rng)
            b = 0.0
            for k in range(Z.shape[1]):
                v = V.ic(Z[:, k], ys)
                if np.isfinite(v) and abs(v) > b:
                    b = abs(v)
            nulls[j] = b
        _, nwt = V.newey_west_t(Z[:, bestk], yy, h)
        fp = float(free[(free.h == h) & (free.target == tg)].p95.iloc[0]) if free is not None \
            else np.nan
        ok = real > nulls.max()
        rows.append(dict(h=h, target=tg, real=real, free_p95=fp,
                         blk_p95=np.quantile(nulls, 0.95), blk_max=nulls.max(),
                         nwt=nwt, clears=bool(ok)))
        say(f"{h:>4} {tg:>7} {real:>8.4f} {fp:>9.4f} {np.quantile(nulls,0.95):>10.4f} "
            f"{nulls.max():>10.4f} {nwt:>8.2f} {str(ok):>8}")
    say(f"      ... h={h} done  [{time.time()-t0:6.1f}s]")
R = pd.DataFrame(rows)
R.to_csv("results/v67/v3_blocknull.csv", index=False)
say("")
say(f"  cells clearing the BLOCK null: {int(R.clears.sum())} of {len(R)}")
for tg in V.TARGETS:
    q = R[R.target == tg]
    say(f"    {tg:>5}  real {q.real.mean():.4f}   free-null p95 {q.free_p95.mean():.4f}   "
        f"BLOCK-null p95 {q.blk_p95.mean():.4f}   clears {int(q.clears.sum())}/{len(q)}")
say(f"\n  the correction: the free null's p95 averages {R.free_p95.mean():.4f} against the block "
    f"null's {R.blk_p95.mean():.4f}, a factor of {R.blk_p95.mean()/max(R.free_p95.mean(),1e-9):.1f}")
say(f"\n[{time.time()-t0:6.1f}s] done")
