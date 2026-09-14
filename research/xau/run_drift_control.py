"""THE DECISIVE CONTROL. Every cell that passed Gate 1 is LONG-ONLY on block C, where gold rose
167.8%. `STUDY_TURTLE` on this branch already recorded that a channel-breakout-plus-trailing-exit
system is a DRIFT HARVESTER -- its random-entry control earned +0.586 R/trade where the index rose
247.6% and -0.005 where it rose 49.6%. So the passing cells are scored against the drift they are
harvesting: the SAME side, the SAME exit machine, the SAME number of trades, entered at RANDOM bars.

If the breakout does not beat a coin flip in a bull market, the primary has no edge and Gate 1's
apparent pass is the drift.
"""
import os, sys, time, warnings, numpy as np, pandas as pd
from numba import njit
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in ("research", "research/xau"):
    sys.path.insert(0, os.path.join(ROOT, p))
import xau_core as X
warnings.filterwarnings("ignore"); pd.set_option("display.width", 210)
def line(t): print("\n" + "=" * 118 + f"\n{t}\n" + "=" * 118, flush=True)
OUT = os.path.join(ROOT, "results/xau")
print(__doc__)
t0 = time.time()


@njit(cache=True)
def walk_at(o, h, l, c, atr, ex_lo, ex_hi, bars, side, stop_n, tp_n, hold, cost, slip, last_bar):
    """The identical exit machine entered at a supplied list of bars -- the matched control."""
    m = len(c); n = len(bars); pct = np.full(n, np.nan); cnt = 0; busy = -1
    for z in range(n):
        i = bars[z]
        if i <= busy or i < 1000 or i >= last_bar:
            continue
        a = i + 1; anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        s = side; px = o[a] + s * slip; risk = stop_n * anchor; fixed = px - s * risk
        tgt = px + s * tp_n * anchor if tp_n > 0.0 else (1e18 if s > 0 else -1e18)
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan; j = a
        while j <= end:
            lvl = fixed
            if s > 0:
                ch = ex_lo[j]
                if np.isfinite(ch) and ch > lvl: lvl = ch
                cp = c[j - 1]
                if np.isfinite(cp) and lvl > cp: lvl = cp
                if l[j] <= lvl: out = (lvl if o[j] > lvl else o[j]) - slip; break
                if h[j] >= tgt: out = (tgt if o[j] < tgt else o[j]) - slip; break
            else:
                ch = ex_hi[j]
                if np.isfinite(ch) and ch < lvl: lvl = ch
                cp = c[j - 1]
                if np.isfinite(cp) and lvl < cp: lvl = cp
                if h[j] >= lvl: out = (lvl if o[j] < lvl else o[j]) + slip; break
                if l[j] <= tgt: out = (tgt if o[j] > tgt else o[j]) + slip; break
            j += 1
        if not np.isfinite(out):
            j = end; out = c[j] + (-slip if s > 0 else slip)
        pct[cnt] = 100.0 * (s * (out - px) - cost) / px; cnt += 1; busy = j
    return pct[:cnt]


def build30():
    f = X.load()
    g = f.resample("30min").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    o, h, l, c, v = (g[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    ix = pd.DatetimeIndex(g.index); n = len(c)
    d = dict(n=n, o=o, h=h, l=l, c=c, v=v, ix=ix, atr=X._atr(h, l, c),
             day=(ix.year * 10000 + ix.month * 100 + ix.day).to_numpy())
    sh, sl = pd.Series(h), pd.Series(l)
    d["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, 121)])
    d["ent_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, 121)])
    d["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in range(2, 81)])
    d["ex_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in range(2, 81)])
    d["blk"] = np.full(n, -1, np.int64)
    for i, (nm, (a, b)) in enumerate(X.BLOCKS.items()):
        d["blk"][(ix >= a) & (ix <= b)] = i
    d["last_bar"] = n - 500
    return d


Ds = {15: X.build(), 30: build30()}
CELLS = [("V38  70/30 2.5N no-tp", dict(tf=30, ent=70, exN=30, stop=2.5, tp=0.0, hold=480, side=1)),
         ("V24  30/20 2.0N no-tp", dict(tf=30, ent=30, exN=20, stop=2.0, tp=0.0, hold=480, side=1)),
         ("V61i 20/20 2.0N no-tp", dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, side=1)),
         ("V61h 15/30 3.0N 6ATR ", dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480, side=1))]
rng = np.random.default_rng(17)
line("BREAKOUT vs A RANDOM ENTRY -- same side, same exits, same trade count, 400 draws per cell")
print(f"  {'cell':24s} {'block':10s} {'n':>5} {'rule %/ev':>10} {'random p50':>11} {'random p95':>11} {'excess':>9} {'p':>7}  verdict")
rows = []
for cn, p in CELLS:
    D = Ds[p["tf"]]; xi = int(p["exN"]) - 2
    E = X.run(D, p)
    for i, bn in enumerate(X.BLOCKS):
        e = E[E.blk == i]
        if len(e) < 30: continue
        obs = e.pct.mean()
        pool = np.flatnonzero((D["blk"] == i) & (np.arange(D["n"]) >= 1000) & (np.arange(D["n"]) < D["last_bar"]))
        out = np.empty(400)
        for k in range(400):
            bars = np.sort(rng.choice(pool, size=min(len(e) * 3, len(pool)), replace=False))
            q = walk_at(D["o"], D["h"], D["l"], D["c"], D["atr"], D["ex_lo"][xi], D["ex_hi"][xi], bars,
                        int(p["side"]), float(p["stop"]), float(p["tp"]), int(p["hold"]), X.COST_RT, X.SLIP, int(D["last_bar"]))
            out[k] = np.mean(q[:len(e)]) if len(q) >= 30 else np.nan
        pv = float(np.nanmean(out >= obs))
        rows.append(dict(cell=cn, block=bn, n=len(e), obs=obs, ctl=float(np.nanmedian(out)), p=pv))
        print(f"  {cn:24s} {bn:10s} {len(e):>5} {obs:>10.5f} {np.nanmedian(out):>11.5f} {np.nanquantile(out,0.95):>11.5f} "
              f"{obs-np.nanmedian(out):>+9.5f} {pv:>7.3f}  {'PASS' if pv <= 0.05 else 'FAIL'}", flush=True)
T = pd.DataFrame(rows); T.to_parquet(os.path.join(OUT, "drift_control.parquet"))
line("VERDICT")
c_ = T[T.block == "C_locked"]
print(f"  On block C (gold +167.8%) the RANDOM long entry with the same exits earns a median "
      f"{c_.ctl.mean():+.5f} %/event across the four cells, against the breakout's {c_.obs.mean():+.5f}.")
print(f"  cells beating their own random-entry control at p <= 0.05: {int((T.p <= 0.05).sum())} of {len(T)}")
print(f"  on block C specifically: {int((c_.p <= 0.05).sum())} of {len(c_)}")
print(f"\n  runtime {time.time()-t0:.0f}s")
