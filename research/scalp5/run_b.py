"""B -- the geometry, which the arithmetic says is the binding constraint, not the entry.

A.1 came back negative on all five at a 1.5xATR stop and a 1:1 target, with win rates of 43-50%
against the 53.8% that geometry needs on 5-minute NQ. The barriers are being hit by noise. So
before touching any entry, the DECLARED geometry grid is swept and read by MARGINAL AVERAGE:

  stop     1.0 / 1.5 / 2.0 / 3.0 xATR      (cost is 11.4% / 7.6% / 5.7% / 3.8% of risk)
  target   none / 1 / 1.5 / 2 / 3 R        (no take profit has won 22 times on this branch)
  breakeven off / at 1R                     (moves the stop to +0.25R)
  trail    off / armed at 1R, 1R behind

Every cell is also scored against a MATCHED CONTROL: a random entry inside the same window, same
side mix, same geometry, same position lock, same costs. A cell that makes money because the
window drifts is not a design, and the control is what separates the two.
"""
import sys, os, time, itertools
sys.path.insert(0, "research"); sys.path.insert(0, "research/scalp5")
import numpy as np, pandas as pd
import s5data as S, s5sig as SG, s5walk as W

R = "results/scalp5/"
os.makedirs(R, exist_ok=True)
print(__doc__)
t0 = time.time()
RNG = np.random.default_rng(5)
STOPS = [1.0, 1.5, 2.0, 3.0]
TGTS = [0.0, 1.0, 1.5, 2.0, 3.0]
BES = [(0.0, 0.0), (1.0, 0.25)]
TRS = [(0.0, 0.0), (1.0, 1.0)]
print(f"declared grid: {len(STOPS)*len(TGTS)*len(BES)*len(TRS)} cells x 5 designs x 2 timeframes")

base = S.load_1m()


def walk(D, lg, sh, g):
    sig = lg | sh
    side = np.where(lg, 1, np.where(sh, -1, 0)).astype(np.int64)
    cap = int(sig.sum()) + 4
    a = [np.zeros(cap, np.int64), np.zeros(cap, np.int64)]
    b = [np.full(cap, np.nan) for _ in range(4)]
    w = np.zeros(cap, np.int64); am = np.zeros(cap, np.int64)
    k = W.walk(D["o"], D["h"], D["l"], D["c"], D["atr"], sig, side, D["last_win"],
               S.RT_POINTS, S.SLIP_POINTS, g["stop"], g["tgt"], g["be"], g["be_off"],
               g["arm"], g["tr"], a[0], a[1], b[0], b[1], w, b[2], b[3], am)
    t = pd.DataFrame(dict(sig=a[0][:k], exit=a[1][:k], R=b[0][:k], pts=b[1][:k], why=w[:k]))
    t["blk"] = D["blk"][t.sig.to_numpy()]
    t["day"] = D["day"][t.sig.to_numpy()]
    return t


def control(D, n_target, side_mix, g, draws=120):
    """Random entries in the same window at the same rate, same side mix and geometry."""
    elig = np.flatnonzero(D["inw"])
    out = np.empty(draws)
    rate = min(1.0, n_target / max(len(elig), 1))
    for i in range(draws):
        m = np.zeros(D["n"], bool)
        pick = elig[RNG.random(len(elig)) < rate]
        m[pick] = True
        sd = RNG.random(D["n"]) < side_mix
        t = walk(D, m & sd, m & ~sd, g)
        s = t[t.blk == 0]
        out[i] = s.pts.mean() if len(s) else np.nan
    return out


rows = []
for tf in (3, 5):
    f = S.resample(base, tf)
    D = S.assemble(f, tf)
    F = SG.build(D, base)
    rdays = D["all_days"][D["all_days"] < D["cut_day"]]
    for nm, (fn, p) in SG.DESIGNS.items():
        lg, sh = fn(D, F, p)
        for stop, tgt, (be, beo), (arm, tr) in itertools.product(STOPS, TGTS, BES, TRS):
            g = dict(stop=stop, tgt=tgt, be=be, be_off=beo, arm=arm, tr=tr)
            t = walk(D, lg, sh, g)
            s = t[t.blk == 0]
            if len(s) < 40:
                continue
            r = s.R.to_numpy(); pts = s.pts.to_numpy()
            shp, _ = S.day_sharpe(s.day.to_numpy(), pts, rdays)
            neg = r[r < 0]; pos = r[r > 0]
            rows.append(dict(tf=tf, design=nm, **g, n=len(s), R=r.mean(), pts=pts.mean(),
                             pf=pos.sum() / max(-neg.sum(), 1e-9), win=(r > 0).mean(),
                             sharpe=shp, p_flat=(s.why == 3).mean()))
G = pd.DataFrame(rows)
G.to_csv(R + "b_grid.csv", index=False)
pd.set_option("display.width", 220); pd.set_option("display.max_columns", 30)
print(f"\n{len(G):,} scorable cells in {time.time()-t0:.0f}s")

print("\n" + "=" * 112)
print("B.1  THE POPULATION FIRST")
print("=" * 112)
print(f"  cells with positive EV : {(G.pts>0).mean():6.1%}      with Sharpe > 0 : {(G.sharpe>0).mean():6.1%}")
print(f"  median EV {G.pts.median():+.3f} pts   best {G.pts.max():+.3f}   "
      f"median Sharpe {G.sharpe.median():+.3f}   best {G.sharpe.max():+.3f}")
for nm in SG.DESIGNS:
    s = G[G.design == nm]
    print(f"    {nm:20s} positive EV in {(s.pts>0).mean():6.1%} of {len(s):3d} cells   "
          f"best EV {s.pts.max():+.3f} pts   best Sharpe {s.sharpe.max():+.3f}")

print("\n" + "=" * 112)
print("B.2  MARGINAL AVERAGE PER AXIS -- what a setting does across the whole grid")
print("=" * 112)
for ax in ("stop", "tgt", "be", "arm"):
    t = G.groupby(ax).agg(EV=("pts", "mean"), Sharpe=("sharpe", "mean"),
                          win=("win", "mean"), n=("n", "mean"))
    print(f"\n  {ax}\n" + t.round(4).to_string())

print("\n" + "=" * 112)
print("B.3  THE BEST CELL PER DESIGN, AND WHAT A RANDOM ENTRY EARNS AT THE SAME GEOMETRY")
print("=" * 112)
rows = []
for tf in (3, 5):
    f = S.resample(base, tf)
    D = S.assemble(f, tf)
    F = SG.build(D, base)
    for nm, (fn, p) in SG.DESIGNS.items():
        s = G[(G.design == nm) & (G.tf == tf)]
        if s.empty:
            continue
        b = s.loc[s.sharpe.idxmax()]
        lg, sh = fn(D, F, p)
        g = dict(stop=b.stop, tgt=b.tgt, be=b.be, be_off=b.be_off, arm=b.arm, tr=b.tr)
        side_mix = float(lg.sum() / max((lg | sh).sum(), 1))
        ctl = control(D, int(b.n), side_mix, g)
        pv = float(np.nanmean(ctl >= b.pts))
        rows.append(dict(tf=tf, design=nm, stop=b.stop, tgt=b.tgt, be=b.be, arm=b.arm,
                         n=int(b.n), EV=b.pts, sharpe=b.sharpe, pf=b.pf, win=b.win,
                         ctl_EV=float(np.nanmedian(ctl)), p_ctl=pv))
        print(f"  {tf}m {nm:20s} stop {b.stop:.1f}N tgt {b.tgt:.1f}R be {b.be:.0f} trail {b.arm:.0f}"
              f"   n {int(b.n):4d}  EV {b.pts:+.3f} pts  Sharpe {b.sharpe:+.2f}  PF {b.pf:.3f}"
              f"   |  random entry {np.nanmedian(ctl):+.3f}  p {pv:.3f}")
pd.DataFrame(rows).to_csv(R + "b_best.csv", index=False)
print(f"\ntotal {time.time()-t0:.0f}s")
