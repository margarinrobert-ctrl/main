"""~1,000,000 combinations of the EMA cross -> pullback -> reclaim rule, with OOS accounting.

Reports, in this order:
  1. the search curve -- best-on-research at each width K, and what it then earns on the LOCKED block
  2. the same curve with DIRECTION HELD FIXED (both sides only), per RESEARCH_PROTOCOL.md 4c
  3. whether anything survives, and if so its correlation with the existing BOS/CHoCH book
"""
import sys, time, itertools; sys.path.insert(0,'research')
import numpy as np
from numba import njit
from ema_pullback import simulate
from bos_choch import prep, SPECS

S = SPECS['MNQ']

@njit(cache=True)
def _ema(x, nn):
    a = 2.0/(nn+1.0); out = np.full(len(x), np.nan)
    s = 0.0
    for j in range(nn): s += x[j]
    out[nn-1] = s/nn
    for i in range(nn, len(x)): out[i] = a*x[i] + (1.0-a)*out[i-1]
    return out

@njit(cache=True)
def _atr(h, l, c, nn):
    n = len(c); tr = np.zeros(n)
    for i in range(1, n):
        a = h[i]-l[i]; b = abs(h[i]-c[i-1]); d = abs(l[i]-c[i-1])
        tr[i] = max(a, max(b, d))
    out = np.full(n, np.nan); s = 0.0
    for j in range(1, nn+1): s += tr[j]
    out[nn] = s/nn
    for i in range(nn+1, n): out[i] = (out[i-1]*(nn-1)+tr[i])/nn
    return out

SPACE = dict(
    minutes   = [15, 30, 60],
    ema_fast  = [5, 8, 13, 21, 34, 50],
    ema_slow  = [34, 48, 55, 89, 100, 200],
    atr_n     = [10, 14, 20],
    max_wait  = [5, 10, 20, 40, 80],
    depth     = [-0.5, -0.25, 0.0, 0.25, 0.5],
    sl_mult   = [1.0, 1.5, 2.0, 3.0],
    tp_r      = [1.0, 1.5, 2.0, 2.5, 3.0],
    reclaim   = [0, 1],
    side      = [-1, 0, 1],
)
keys = list(SPACE)
gross = int(np.prod([len(SPACE[k]) for k in keys]))
print(f"grid {gross:,} cells before the fast<slow constraint", flush=True)

DATA, CUT, TRAD, EMAS, ATRS = {}, {}, {}, {}, {}
for m in SPACE["minutes"]:
    d = prep(m); DATA[m] = d
    u = np.unique(d["sess"]); CUT[m] = u[int(0.65*len(u))]
    TRAD[m] = ((d["mod"] >= 570) & (d["mod"] < 960)).astype(np.uint8)
    for L in set(SPACE["ema_fast"] + SPACE["ema_slow"]):
        EMAS[(m, L)] = _ema(d["c"], L)
    for L in SPACE["atr_n"]:
        ATRS[(m, L)] = _atr(d["h"], d["l"], d["c"], L)
print("indicators cached", flush=True)

rows = []
t0 = time.time(); done = 0
for combo in itertools.product(*[SPACE[k] for k in keys]):
    kw = dict(zip(keys, combo))
    if kw["ema_fast"] >= kw["ema_slow"]:
        continue
    m = kw["minutes"]; d = DATA[m]
    p, ti, sd, why = simulate(
        d["o"], d["h"], d["l"], d["c"], d["sess"], TRAD[m],
        EMAS[(m, kw["ema_fast"])], EMAS[(m, kw["ema_slow"])], ATRS[(m, kw["atr_n"])],
        kw["max_wait"], kw["depth"], kw["sl_mult"], kw["tp_r"], kw["side"], kw["reclaim"],
        S["pv"], S["tick"], 1.0, S["spread_t"], S["slip_t"], S["stop_slip_t"])
    done += 1
    if len(p) < 20:
        continue
    msk = d["sess"][ti] < CUT[m]
    rn, ln = p[msk].sum(), p[~msk].sum()
    s = d["sess"][ti][msk]
    if len(s) < 10: continue
    u = np.unique(s); ds = np.array([p[msk][s == q].sum() for q in u])
    rs = ds.mean()/ds.std()*np.sqrt(252) if ds.std() > 0 else 0.0
    s2 = d["sess"][ti][~msk]
    if len(s2) < 10: continue
    u2 = np.unique(s2); ds2 = np.array([p[~msk][s2 == q].sum() for q in u2])
    ls = ds2.mean()/ds2.std()*np.sqrt(252) if ds2.std() > 0 else 0.0
    rows.append((rn, rs, ln, ls, len(p), kw["side"], kw["ema_fast"], kw["ema_slow"],
                 kw["tp_r"], kw["sl_mult"], m))
    if done % 100000 == 0:
        el = time.time()-t0
        print(f"  {done:,} evaluated, {len(rows):,} kept, {el:.0f}s", flush=True)

R = np.array(rows, np.float32)
np.save("results/ema/ema_rows.npy", R)
print(f"\nevaluated {done:,} valid cells in {time.time()-t0:.0f}s; {len(R):,} had >=20 trades", flush=True)
