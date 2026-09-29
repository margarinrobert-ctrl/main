"""AutoBNN on the user's Donchian cell, two ways, each against a shuffled twin and a same-selectivity
random filter. Research block for everything; ONE pre-declared locked read per arm.

ARM A -- FORECASTER GATE. At every signal bar the strategy fires on, AutoBNN is fitted to the
last 200 bars of log close (t in [0,1], daily period = 26 bars) and asked for the log close 26
bars ahead. The signal is kept if the posterior probability of a positive move, Phi(mu/sd),
clears a threshold. The structure is searched once per sequential fold on that fold's first
window (ELBO), then that structure is refitted at every signal bar. Nothing after the signal bar
is seen.

ARM B -- BAYESIAN META-LABEL. AutoBNN with exogenous inputs (eight causal features at the signal
bar) predicts the trade's R; trades are kept by posterior mean, or by 'confident' (mean - sd > 0).
Purged sequential folds: the training set ends before the test fold's first signal and every
training trade's EXIT precedes it."""
import os, sys, warnings, time
import numpy as np, pandas as pd, torch
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/v61", "research/v53", "research/v54", "research/v56", "research/inst"):
    sys.path.insert(0, os.path.join(ROOT, p))
import v61core as V, autobnn as AB
from donchian500k import signal_sets, geometry
warnings.filterwarnings("ignore"); pd.set_option("display.width", 250)
def line(t): print("\n" + "=" * 126 + f"\n{t}\n" + "=" * 126, flush=True)
t0 = time.time()
D = V.build(15); rth = (D["mod"] >= 570) & (D["mod"] < 930)
Gd = geometry(15); rows, offs, vals, K = signal_sets(D, rth)
exlo = np.vstack([D["ex_lo"][e] for e in V.EXITS])
calm = np.zeros(D["n"], np.bool_); v = D["vpct"]; calm[np.isfinite(v)] = v[np.isfinite(v)] <= 0.5
gi = int(np.flatnonzero((Gd.exN == 30) & (Gd.stop == 1.5) & (Gd.tp == 0.0) & (Gd.hold_name == "swing") & (Gd.adapt == 1))[0])
si = int(np.flatnonzero((K.ent == 55) & (K.ma == 2.0) & (K.chop == 40.0))[0])
g1 = Gd.iloc[[gi]]
xb, R, pts = V._tensor(D["o"], D["h"], D["l"], D["c"], D["atr"], rows.astype(np.int64), exlo, calm,
                       g1["ei"].to_numpy(np.int64), g1["shi"].to_numpy(float), g1["slo"].to_numpy(float),
                       g1["tp"].to_numpy(float), g1["hold"].to_numpy(np.int64), V.COST, V.SLIP, D["n"])
epx = D["o"][np.minimum(rows + 1, D["n"] - 1)]
sel = vals[offs[si]:offs[si + 1]]; sb = rows[sel]; CUT = D["cut"]
c = D["c"]; lc = np.log(c)
def lock(mask):
    free = -1; out = []
    for j, kk in enumerate(sel):
        if not mask[j] or xb[kk, 0] < 0 or not np.isfinite(R[kk, 0]) or rows[kk] <= free: continue
        free = xb[kk, 0]; out.append((int(rows[kk]), int(xb[kk, 0]), float(R[kk, 0]), 100 * float(pts[kk, 0]) / epx[kk]))
    return pd.DataFrame(out, columns=["sig", "xb", "R", "pct"])
def st(T, res=True):
    t = T[(T.sig < CUT) if res else (T.sig >= CUT)]; p = t.pct.to_numpy()
    if len(p) < 5: return dict(n=len(p), pf=np.nan, pct=np.nan, win=np.nan, tot=np.nan)
    return dict(n=len(p), pf=p[p > 0].sum() / max(1e-9, -p[p <= 0].sum()), pct=p.mean(), win=100 * (p > 0).mean(), tot=p.sum())
def fmt(s): return f"n {s['n']:>4} PF {s['pf']:6.3f} {s['pct']:+.4f}%/tr total {s['tot']:+6.2f}%"
ones = np.ones(len(sel), bool); T0 = lock(ones)
line("THE CELL, unfiltered (position-locked): research / locked")
print("  " + fmt(st(T0)) + "  |  " + fmt(st(T0, False)))
rng = np.random.default_rng(11)
def null_filter(keep_mask_res_count, ndraw=200):
    """same-selectivity random filter on the RESEARCH signal bars"""
    res_idx = np.flatnonzero(sb < CUT); out = []
    for _ in range(ndraw):
        m = np.zeros(len(sel), bool); m[rng.choice(res_idx, size=min(keep_mask_res_count, len(res_idx)), replace=False)] = True
        out.append(st(lock(m))["pf"])
    return np.array(out)

# ---------------------------------------------------------------- ARM A: forecaster gate
line("ARM A -- AutoBNN FORECASTER as an entry gate (window 200 bars, horizon 26 bars, period 26)")
W, H, PER = 200, 26, 26.0
n_sig = len(sb); folds = 6
fold_of = np.minimum((np.arange(n_sig) * folds) // n_sig, folds - 1)
mu_a = np.full(n_sig, np.nan); sd_a = np.full(n_sig, np.nan); struct = {}
tt = np.linspace(0, 1, W + H)
for f in range(folds):
    idx = np.flatnonzero(fold_of == f)
    # structure search once, on the first signal bar's window of this fold (the window ENDS at that bar)
    i0 = sb[idx[0]]; y0 = lc[i0 - W + 1:i0 + 1]; y0 = y0 - y0[0]
    m = AB.AutoBNN(period=PER / (W + H), epochs=250, n_mc=48, seed=f).fit(tt[:W], y0)
    struct[f] = m.name
    # refit that structure at every signal bar in the fold (epochs trimmed; same structure)
    for j in idx:
        i = sb[j]; y = lc[i - W + 1:i + 1]; y = y - y[0]
        mm = AB.AutoBNN(period=PER / (W + H), epochs=120, n_mc=48, seed=j)
        mod = AB.structures(0, PER / (W + H))[m.name]
        mod, ln, _ = mm._fit_one(mod, torch.as_tensor(tt[:W], dtype=torch.float32), None,
                                 torch.as_tensor((y - y.mean()) / (y.std() + 1e-8), dtype=torch.float32))
        mm.model, mm.log_noise, mm.ym, mm.ys = mod, ln, torch.tensor(float(y.mean())), torch.tensor(float(y.std() + 1e-8))
        pm, ps = mm.predict(tt[W + H - 1:W + H])
        mu_a[j] = pm[0] - y[-1]; sd_a[j] = ps[0]
    print(f"  fold {f}: structure {m.name:24s} ({idx.size} signals, {time.time()-t0:.0f}s)", flush=True)
from scipy.stats import norm
p_up = norm.cdf(mu_a / np.maximum(sd_a, 1e-9))
res = sb < CUT
fwd = np.array([lc[min(i + H, len(lc) - 1)] - lc[i] for i in sb])
ic = np.corrcoef(mu_a[res], fwd[res])[0, 1]; ic_r = pd.Series(mu_a[res]).corr(pd.Series(fwd[res]), method="spearman")
print(f"  forecast quality on the research signal bars: IC {ic:+.3f} (Spearman {ic_r:+.3f}) against the realised 26-bar move; "
      f"mean P(up) {p_up[res].mean():.3f}")
print(f"  {'gate':28s} {'research':>44s} | {'random filter, same selectivity':>34s}")
declared = None
for q in (0.50, 0.55, 0.60, 0.70):
    m = p_up >= q; T = lock(m); s = st(T); keep = int((m & res).sum())
    nf = null_filter(keep); p = np.mean(nf >= s["pf"]) if np.isfinite(s["pf"]) else np.nan
    sh = rng.permutation(p_up); ms = sh >= q; ss = st(lock(ms))
    print(f"  P(up) >= {q:.2f}  keeps {100*keep/res.sum():4.0f}%  {fmt(s)} | median PF {np.nanmedian(nf):.3f}  p {p:.3f}   shuffled-gate PF {ss['pf']:.3f}")
    if q == 0.60: declared = m
line("ARM A -- the ONE locked read, pre-declared: P(up) >= 0.60")
print("  base   locked: " + fmt(st(T0, False)))
print("  gated  locked: " + fmt(st(lock(declared), False)))

# ---------------------------------------------------------------- ARM B: Bayesian meta-label
line("ARM B -- AutoBNN META-LABEL: eight causal features at the signal bar -> trade R, with uncertainty")
ret = lambda k: np.log(c / np.roll(c, k)); r1, r4, r16, r64 = ret(1), ret(4), ret(16), ret(64)
atrp = D["atr"] / c
X_all = np.column_stack([D["d_ma"], D["chop"], D["vpct"], atrp, r1, r4, r16, r64])
tr = lock(ones); n_tr = len(tr)
Xt = X_all[tr.sig.to_numpy()]; yt = tr.R.to_numpy(); sig_t = tr.sig.to_numpy(); xb_t = tr.xb.to_numpy()
good = np.isfinite(Xt).all(1); Xt, yt, sig_t, xb_t = Xt[good], yt[good], sig_t[good], xb_t[good]
tr = tr[good].reset_index(drop=True)
res_t = sig_t < CUT; ridx = np.flatnonzero(res_t)
mu_b = np.full(len(yt), np.nan); sd_b = np.full(len(yt), np.nan); mu_sh = np.full(len(yt), np.nan)
fb = np.minimum((np.arange(len(ridx)) * folds) // len(ridx), folds - 1)
zs = lambda A, mu, sd: (A - mu) / (sd + 1e-9)
for f in range(folds):
    te = ridx[fb == f]; first = sig_t[te].min()
    trn = ridx[(fb != f) & (xb_t[ridx] < first)]                       # purged: exits before the test fold starts
    trn = trn[sig_t[trn] < first]
    if len(trn) < 30: continue
    mu, sd = Xt[trn].mean(0), Xt[trn].std(0)
    m = AB.AutoBNN(d_x=8, period=0.25, epochs=250, n_mc=64, seed=f).fit(np.linspace(0, 1, len(trn)), yt[trn], zs(Xt[trn], mu, sd))
    pm, ps = m.predict(np.full(len(te), 1.0), zs(Xt[te], mu, sd)); mu_b[te], sd_b[te] = pm, ps
    ysh = rng.permutation(yt[trn])
    m2 = AB.AutoBNN(d_x=8, period=0.25, epochs=250, n_mc=64, seed=f + 100).fit(np.linspace(0, 1, len(trn)), ysh, zs(Xt[trn], mu, sd))
    mu_sh[te], _ = m2.predict(np.full(len(te), 1.0), zs(Xt[te], mu, sd))
    print(f"  fold {f}: train {len(trn)} test {len(te)} structure {m.name} ({time.time()-t0:.0f}s)", flush=True)
ok = np.isfinite(mu_b) & res_t
print(f"  OOF IC (posterior mean vs realised R): {np.corrcoef(mu_b[ok], yt[ok])[0,1]:+.3f}   shuffled twin IC {np.corrcoef(mu_sh[ok], yt[ok])[0,1]:+.3f}")
def sub_stats(mask):
    p = tr.pct.to_numpy()[mask]
    return dict(n=int(mask.sum()), pf=p[p > 0].sum() / max(1e-9, -p[p <= 0].sum()) if len(p) else np.nan, pct=p.mean() if len(p) else np.nan, win=100 * (p > 0).mean() if len(p) else np.nan, tot=p.sum() if len(p) else np.nan)
def null_sub(k, ndraw=300):
    out = []
    for _ in range(ndraw):
        m = np.zeros(len(yt), bool); m[rng.choice(np.flatnonzero(ok), size=k, replace=False)] = True; out.append(sub_stats(m)["pf"])
    return np.array(out)
base = sub_stats(ok); print(f"  research trades scored: {fmt(base)}")
print(f"  {'rule':36s} {'research':>44s} | {'random subset, same size':>26s} | shuffled twin")
for nm, sc, scs in (("keep top 70% by posterior mean", mu_b, mu_sh), ("keep top 50% by posterior mean", mu_b, mu_sh), ("keep top 30% by posterior mean", mu_b, mu_sh),
                    ("keep 'confident': mean - sd > 0", None, None), ("keep posterior mean > 0", None, None)):
    if sc is not None:
        q = float(nm.split("top ")[1].split("%")[0]) / 100
        thr = np.nanquantile(sc[ok], 1 - q); m = ok & (sc >= thr); ms = ok & (scs >= np.nanquantile(scs[ok], 1 - q))
    elif "confident" in nm:
        m = ok & ((mu_b - sd_b) > 0); ms = ok & ((mu_sh - sd_b) > 0)
    else:
        m = ok & (mu_b > 0); ms = ok & (mu_sh > 0)
    s = sub_stats(m); nf = null_sub(int(m.sum())) if m.sum() >= 5 else np.array([np.nan]); ss = sub_stats(ms)
    print(f"  {nm:36s} {fmt(s)} | median PF {np.nanmedian(nf):.3f}  p {np.mean(nf >= s['pf']):.3f} | PF {ss['pf']:.3f} n {ss['n']}")
line("ARM B -- the ONE locked read, pre-declared: fit on ALL research trades, keep top 50% by posterior mean")
mu, sd = Xt[res_t].mean(0), Xt[res_t].std(0)
mf = AB.AutoBNN(d_x=8, period=0.25, epochs=300, n_mc=64, seed=7).fit(np.linspace(0, 1, res_t.sum()), yt[res_t], zs(Xt[res_t], mu, sd))
lk = ~res_t; pm, ps = mf.predict(np.full(lk.sum(), 1.0), zs(Xt[lk], mu, sd))
thr = np.nanquantile(mu_b[ok], 0.5)   # the research-block cut for 'top 50%'
keepL = np.zeros(len(yt), bool); keepL[np.flatnonzero(lk)[pm >= thr]] = True
print(f"  structure {mf.name}; locked IC {np.corrcoef(pm, yt[lk])[0,1]:+.3f}")
print("  base   locked: " + fmt(sub_stats(lk)))
print("  kept   locked: " + fmt(sub_stats(keepL)))
print(f"\n  total runtime {time.time()-t0:.0f}s")
