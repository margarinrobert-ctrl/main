"""The 1,000,000-combination search, with honest out-of-sample accounting.

The point is not to find a winner. It is to measure what searching this wide DOES to the thing
you find -- by taking the research-block winner at each search width K and looking at what it
then earns on a locked block it never saw.
"""
import sys, time, itertools; sys.path.insert(0,'research')
import numpy as np
from bos_choch import prep, run

SPACE = dict(
    minutes      = [15, 30, 60],
    swing_k      = [2, 3, 4, 5, 6],
    ema_n        = [50, 100, 200, 300],
    atr_n        = [10, 14, 20],
    atr_mult     = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
    n_bos        = [1, 2, 3],
    use_ema      = [0, 1],
    use_choch    = [0, 1],
    max_hold     = [0, 10, 20, 40],
    min_ema_dist = [0.0, 0.5, 1.0, 1.5, 2.0],
    side_mode    = [-1, 0, 1],
)
keys = list(SPACE)
total = int(np.prod([len(SPACE[k]) for k in keys]))
print(f"search space: {total:,} cells over {len(keys)} axes", flush=True)

CUT = {}; SESS = {}; SLO = {}; SHI = {}
for m in SPACE["minutes"]:
    d = prep(m); u = np.unique(d["sess"])
    CUT[m] = int(u[int(0.65*len(u))]); SESS[m] = d["sess"]
    SLO[m] = int(u.min()); SHI[m] = int(u.max())

def sharpe(p, e, sess, lo, hi):
    """Daily P&L via bincount over the WHOLE block, so flat days count -- both faster than
    grouping in Python and a more honest Sharpe than one computed only on days that traded."""
    if len(p) < 5: return 0.0, 0.0
    ds = np.bincount(sess[e] - lo, weights=p, minlength=hi - lo + 1)
    sd = ds.std()
    if len(ds) < 5 or sd == 0: return p.sum(), 0.0
    return p.sum(), ds.mean()/sd*np.sqrt(252)

rows = np.zeros((total, 5), np.float32)     # rNet rSh lNet lSh n
t0 = time.time()
for i, combo in enumerate(itertools.product(*[SPACE[k] for k in keys])):
    kw = dict(zip(keys, combo))
    m = kw["minutes"]
    try:
        side, ti, to, pnl, g, r, why, dl = run(session="rth_0930_1600", symbol="MNQ", **kw)
    except Exception:
        continue
    if len(pnl) < 20:
        continue
    sess = SESS[m]; msk = sess[ti] < CUT[m]
    rn, rs = sharpe(pnl[msk],  ti[msk],  sess, SLO[m], CUT[m])
    ln, ls = sharpe(pnl[~msk], ti[~msk], sess, CUT[m], SHI[m])
    rows[i] = (rn, rs, ln, ls, len(pnl))
    if i and i % 25000 == 0:
        el = time.time()-t0
        print(f"  {i:,} / {total:,}   {el:.0f}s elapsed, ~{el/i*(total-i):.0f}s left", flush=True)
np.save("results/mnq/mega_rows.npy", rows)
print(f"done in {time.time()-t0:.0f}s", flush=True)
