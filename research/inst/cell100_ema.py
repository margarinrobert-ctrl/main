"""The user's three EMA conditions -- EMA200 as support, a 20/50 cross as momentum, a pullback to
EMA20 before the entry -- measured ON THE FRONTIER-100 BASE, not carried over from the Turtle Scalp
where they were last measured. STUDY_V52: a filter is a property of a geometry, not of a market."""
import os, sys, warnings
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V
from frontier import signal_sets, geometry
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126)
D = V.build(15); rth = (D["mod"] >= 570) & (D["mod"] < 930)
Gd = geometry(15); rows, offs, vals, K = signal_sets(D, rth)
exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
calm = np.zeros(D["n"], np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
# the cell
CELL = dict(ent=55, exN=20, stop=1.5, tp=0.0, hold=26, adapt=1, k=0, w=0, ma=2.0, chop=40.0, psh=0)
gi = int(np.flatnonzero((Gd.exN == 20) & (Gd.stop == 1.5) & (Gd.tp == 0.0) & (Gd.hold == 26) & (Gd.adapt == 1))[0])
si = int(np.flatnonzero((K.ent == 55) & (K.k == 0) & (K.w == 0) & (K.ma == 2.0) & (K.chop == 40.0) & (K.psh == 0))[0])
g1 = Gd.iloc[[gi]]
xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                       g1["ei"].to_numpy(np.int64), g1["shi"].to_numpy(float), g1["slo"].to_numpy(float),
                       g1["tp"].to_numpy(float), g1["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
sel = vals[offs[si]:offs[si + 1]]                      # the cell's signal bars (row indices into rows)
sig_bars = rows[sel]
c = D["c"]; l = D["l"]; atr = D["atr"]
ema = lambda n: pd.Series(c).ewm(span=n, adjust=False).mean().to_numpy()
e20, e50, e200 = ema(20), ema(50), ema(200)
def lock(mask):
    free = -1; out = []
    for j, kk in enumerate(sel):
        if not mask[j] or xb[kk, 0] < 0 or not np.isfinite(R[kk, 0]) or rows[kk] <= free: continue
        free = xb[kk, 0]; out.append((rows[kk], float(R[kk, 0]), 100 * float(pts[kk, 0]) / epx[kk]))
    T = pd.DataFrame(out, columns=["sig", "R", "pct"]); T["res"] = T.sig < D["cut"]; return T
def st(T, m):
    t = T[m]; p = t.pct.to_numpy()
    if len(p) < 5: return dict(n=len(p), tpy=np.nan, pf=np.nan, win=np.nan, pct=np.nan)
    yrs = V.YEARS["res"] if m.iloc[0] else V.YEARS["lock"]
    return dict(n=len(p), tpy=len(p) / yrs, pf=p[p > 0].sum() / max(1e-9, -p[p <= 0].sum()), win=100 * (p > 0).mean(), pct=p.mean())
def row(nm, mask):
    T = lock(mask); a = st(T, T.res); b = st(T, ~T.res)
    print(f"  {nm:52s} res n {a['n']:>4} {a['tpy']:>5.0f}/yr PF {a['pf']:>6.3f} win {a['win']:>5.1f}% | lock n {b['n']:>4} {b['tpy']:>5.0f}/yr PF {b['pf']:>6.3f} win {b['win']:>5.1f}%")
    return T
# the gates, read at the signal bar
at = sig_bars
G = {}
G["EMA200 support: above and within 1 ATR"] = (c[at] > e200[at]) & ((c[at] - e200[at]) <= 1.0 * atr[at])
G["EMA200 support: above and within 2 ATR"] = (c[at] > e200[at]) & ((c[at] - e200[at]) <= 2.0 * atr[at])
G["EMA200 support: above and within 3 ATR"] = (c[at] > e200[at]) & ((c[at] - e200[at]) <= 3.0 * atr[at])
G["EMA200 touched (low <= EMA200) within 5 bars, close above"] = pd.Series(l <= e200).rolling(5, min_periods=1).max().to_numpy().astype(bool)[at] & (c[at] > e200[at])
G["20>50 state, aligned (50 > 200)"] = (e20[at] > e50[at]) & (e50[at] > e200[at])
up = e20 > e50; x = up & ~np.roll(up, 1); x[0] = False
G["fresh 20/50 cross within 5, 20 > 200"] = pd.Series(x).rolling(5, min_periods=1).max().to_numpy().astype(bool)[at] & (e20[at] > e200[at])
for w in (3, 5, 10):
    G[f"pullback: low <= EMA20 within {w} bars"] = pd.Series(l <= e20).rolling(w, min_periods=1).max().to_numpy().astype(bool)[at]
line("A. BASE RATES on the cell's own signal bars (research) -- lift vs all RTH bars")
allm = rth.copy(); allm[:1000] = False
for nm, m in G.items():
    # recompute the same condition on all rth bars for the lift
    if "support" in nm:
        k = float(nm.split("within ")[1].split(" ")[0]); full = (c > e200) & ((c - e200) <= k * atr)
    elif "touched" in nm: full = pd.Series(l <= e200).rolling(5, min_periods=1).max().to_numpy().astype(bool) & (c > e200)
    elif "state" in nm: full = (e20 > e50) & (e50 > e200)
    elif "fresh" in nm: full = pd.Series(x).rolling(5, min_periods=1).max().to_numpy().astype(bool) & (e20 > e200)
    else:
        w = int(nm.split("within ")[1].split(" ")[0]); full = pd.Series(l <= e20).rolling(w, min_periods=1).max().to_numpy().astype(bool)
    rm = at < D["cut"]
    ps = m[rm].mean(); pa = full[allm & (np.arange(D["n"]) < D["cut"])].mean()
    print(f"  {nm:52s} on signal bars {100*ps:5.1f}%   all bars {100*pa:5.1f}%   lift {ps/max(pa,1e-9):.2f}x")
line("B. EACH GATE ON THE FRONTIER-100 CELL -- research and locked (the locked column is descriptive)")
ones = np.ones(len(sel), bool)
T0 = row("FRONTIER-100 as shipped (SMA200 floor >= 2 ATR, CHOP <= 40)", ones)
for nm, m in G.items(): row("  + " + nm, m)
print("  the ask in full:")
ask = G["EMA200 support: above and within 3 ATR"] & G["20>50 state, aligned (50 > 200)"] & G["pullback: low <= EMA20 within 5 bars"]
Task = row("  + EMA200 support(3) AND 20>50>200 AND pullback(5)", ask)
row("  + 20>50>200 AND pullback(5), no EMA200 support", G["20>50 state, aligned (50 > 200)"] & G["pullback: low <= EMA20 within 5 bars"])
row("  + EMA200 support(3) AND 20>50>200, no pullback", G["EMA200 support: above and within 3 ATR"] & G["20>50 state, aligned (50 > 200)"])
line("C. SAME-SELECTIVITY RANDOM FILTER on research -- keep as many of the cell's signal bars at random")
rng = np.random.default_rng(5)
res_idx = np.flatnonzero(at < D["cut"])
for nm, m in [("EMA200 support(3)", G["EMA200 support: above and within 3 ATR"]), ("20>50>200 state", G["20>50 state, aligned (50 > 200)"]),
              ("pullback(5)", G["pullback: low <= EMA20 within 5 bars"]), ("THE ASK (all three)", ask)]:
    T = lock(m); obs = st(T, T.res)["pf"]; keep = int(m[res_idx].sum()); cf = []
    for _ in range(300):
        mm = np.zeros(len(sel), bool); mm[rng.choice(res_idx, size=keep, replace=False)] = True
        cf.append(st(lock(mm), lock(mm).res)["pf"])
    cf = np.array(cf)
    print(f"  {nm:22s} research PF {obs:.3f} | random filter median {np.nanmedian(cf):.3f}  5-95% [{np.nanpercentile(cf,5):.3f}, {np.nanpercentile(cf,95):.3f}]  p {np.nanmean(cf >= obs):.3f}")
