"""MONTE CARLO on the shipped gold Donchian + CVD gate (the VETO configuration).

FIVE DISTINCT QUESTIONS, and this branch's rule is that they are five different simulations. From
CLAUDE.md: BOOTSTRAP FOR THE EDGE, PERMUTE FOR THE PATH, and never read an endpoint off a
permutation -- an earlier version here printed a 5th-95th endpoint spread of 0.6R on +27R, which is
meaningless because permuting trades cannot change their sum.

  1 DAY-BLOCK BOOTSTRAP     edge uncertainty. Resample whole DAYS with their trades attached, then
                            take the trade-weighted mean. Trades cluster, so the day is the unit.
  2 PERMUTATION             path risk only. Reshuffle the realised sequence and read the DRAWDOWN
                            distribution. Gives the realised path's percentile and the p99 -- which
                            is the sizing number, and has run 1.1x to 2.8x the realised on every
                            strategy measured on this branch.
  3 EXECUTION PERTURBATION  cost and slippage drawn per trade INSIDE the walk. Prices the assumption,
                            not the strategy. Run it FIRST so the demanding tests are not mistaken
                            for it. Gold's 0.30 USD/oz round turn is an assumption no feed here can
                            check, so this one matters more on gold than anywhere else.
  4 PRICE JITTER            the demanding one. Jitter every bar's OHLC, repair the bar, and RECOMPUTE
                            ATR, both Donchian channels, the CVD and the whole pivot structure from
                            the jittered bars. If the signal set is fragile this is where it shows.
  5 PARAMETER JITTER        the neighbourhood, jointly: entry, exit, stop, pivot width, window.

CAVEAT THAT STAYS ATTACHED (STUDY_ATME_LIVE): a perturbation prices execution and data noise ON THE
TRADES YOU SELECTED. It can never price the SELECTION. This gate is one cell of 229 screened.
"""
from __future__ import annotations

import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, os.path.join(ROOT, "research"), os.path.join(ROOT, "research/xau"),
          os.path.join(ROOT, "research/v54")):
    sys.path.insert(0, p)

import xcvd                     # noqa: E402
import xau_core as X            # noqa: E402
import v54cvd as V54            # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)
OUT = os.path.join(ROOT, "results/xaucvd")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 122)
    print(t)
    print("=" * 122, flush=True)


G = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, side=1)
K, W = 2, 20
NB = 2000


def gate_from(h, l, cvd, k, w, n):
    P = V54.patterns(h, l, cvd, k, n)
    return pd.Series(P[0].astype(float)).rolling(w).max().to_numpy() > 0


def maxdd(x):
    """Max drawdown of the cumulative %-of-price curve, in the same units."""
    c = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(c) - c)) if len(c) else 0.0


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(2026)
D = xcvd.build(60)
gate = gate_from(D["h"], D["l"], D["cvd"], K, W, D["n"])
E = X.run(D, G, gate=gate)
E["dayk"] = D["day"][E.sig.to_numpy()]
store = {}

line("REFERENCE -- the shipped configuration, as measured")
for i, bn in enumerate(X.BLOCKS):
    e = E[E.blk == i]
    pf = e.pct[e.pct > 0].sum() / max(-e.pct[e.pct < 0].sum(), 1e-9)
    print(f"  {bn:10s} n {len(e):>4}   {e.pct.mean():+.5f} %/event   total {e.pct.sum():>7.2f}%   "
          f"PF {pf:.3f}   maxDD {maxdd(e.pct.to_numpy()):>6.2f}%   win {100*(e.pct>0).mean():.1f}%")

# ---------------------------------------------------------------- 1  day-block bootstrap
line("1  DAY-BLOCK BOOTSTRAP -- edge uncertainty. Whole days resampled WITH their trades attached")
print(f"  {NB} draws. The unit of inference is the DAY because trades cluster inside one.\n")
print(f"  {'block':10s} {'n':>5} {'days':>5} {'mean':>9} {'p5':>9} {'p95':>9} {'P(mean<=0)':>12}")
for i, bn in enumerate(X.BLOCKS):
    e = E[E.blk == i]
    if len(e) < 20:
        continue
    days = e.dayk.to_numpy()
    ud = np.unique(days)
    byday = [e.pct.to_numpy()[days == d] for d in ud]
    means = np.empty(NB)
    for b in range(NB):
        pick = rng.integers(0, len(ud), len(ud))
        means[b] = np.concatenate([byday[j] for j in pick]).mean()
    store[f"boot_{bn}"] = means
    print(f"  {bn:10s} {len(e):>5} {len(ud):>5} {means.mean():>+9.5f} {np.quantile(means,0.05):>+9.5f} "
          f"{np.quantile(means,0.95):>+9.5f} {np.mean(means<=0):>12.3f}")

# ---------------------------------------------------------------- 2  permutation
line("2  PERMUTATION -- path risk only. Reshuffle the realised trades and read the DRAWDOWN")
print("  The SUM is invariant under permutation, so no endpoint is reported here. Only the path.\n")
print(f"  {'block':10s} {'realised DD':>12} {'MC median':>10} {'MC p95':>9} {'MC p99':>9} "
      f"{'realised pctile':>16} {'p99 / realised':>15}")
for i, bn in enumerate(X.BLOCKS):
    e = E[E.blk == i]
    if len(e) < 20:
        continue
    r = e.pct.to_numpy()
    real = maxdd(r)
    dd = np.array([maxdd(rng.permutation(r)) for _ in range(NB)])
    store[f"perm_{bn}"] = dd
    store[f"realdd_{bn}"] = real
    pct = float(np.mean(dd <= real))
    print(f"  {bn:10s} {real:>11.2f}% {np.median(dd):>9.2f}% {np.quantile(dd,0.95):>8.2f}% "
          f"{np.quantile(dd,0.99):>8.2f}% {pct:>16.2f} {np.quantile(dd,0.99)/max(real,1e-9):>15.2f}x")

# ---------------------------------------------------------------- 3  execution perturbation
line("3  EXECUTION PERTURBATION -- cost and slippage drawn per run INSIDE the walk. 300 draws")
print("  Gold's 0.30 USD/oz round turn is an ASSUMPTION -- no feed here carries bid/ask -- so this")
print("  prices the thing most likely to be wrong. cost ~ U(0.5x, 2x), slip ~ U(0, 2x).\n")
print(f"  {'block':10s} {'p5 total':>10} {'median':>9} {'p95':>9} {'P(total<=0)':>13}")
tot = {bn: [] for bn in X.BLOCKS}
for d in range(300):
    cm = rng.uniform(0.5, 2.0) * X.COST_RT
    sm = rng.uniform(0.0, 2.0) * X.SLIP
    Ed = X.run(D, G, cost=cm, slip=sm, gate=gate)
    for i, bn in enumerate(X.BLOCKS):
        z = Ed[Ed.blk == i]
        tot[bn].append(z.pct.sum() if len(z) else np.nan)
for bn in X.BLOCKS:
    a = np.array(tot[bn], float)
    if not np.isfinite(a).any():
        continue
    store[f"exec_{bn}"] = a
    print(f"  {bn:10s} {np.nanquantile(a,0.05):>9.2f}% {np.nanmedian(a):>8.2f}% "
          f"{np.nanquantile(a,0.95):>8.2f}% {np.nanmean(a<=0):>13.3f}")

# ---------------------------------------------------------------- 4  price jitter
line("4  PRICE JITTER -- every OHLC jittered, the bar repaired, and ATR, BOTH CHANNELS, the CVD")
print("   and the WHOLE PIVOT STRUCTURE recomputed from the jittered bars. 150 draws per level.")
print("   This is the only perturbation that can move the SIGNAL SET, which is why it is the")
print("   demanding one. Gold's tick is 0.01, so 1 tick = 0.01 USD/oz.\n")
o0, h0, l0, c0 = D["o"].copy(), D["h"].copy(), D["l"].copy(), D["c"].copy()
print(f"  {'ticks':>6} {'block':10s} {'n median':>9} {'total p5':>10} {'median':>9} {'p95':>9} "
      f"{'sign kept':>10}")
for ticks in (0.5, 1.0, 2.0):
    amp = ticks * 0.01
    res = {bn: [] for bn in X.BLOCKS}
    cnt = {bn: [] for bn in X.BLOCKS}
    for d in range(150):
        j = rng.normal(0.0, amp, (4, D["n"]))
        oo, cc = o0 + j[0], c0 + j[1]
        hh, ll = h0 + j[2], l0 + j[3]
        hh = np.maximum.reduce([hh, oo, cc])
        ll = np.minimum.reduce([ll, oo, cc])
        Dj = dict(D)
        Dj["o"], Dj["h"], Dj["l"], Dj["c"] = oo, hh, ll, cc
        Dj["atr"] = X._atr(hh, ll, cc)
        sh, sl = pd.Series(hh), pd.Series(ll)
        Dj["ent_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in (G["ent"],)])
        Dj["ent_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in (G["ent"],)])
        Dj["ex_lo"] = np.vstack([sl.rolling(k).min().shift(1).to_numpy() for k in (G["exN"],)])
        Dj["ex_hi"] = np.vstack([sh.rolling(k).max().shift(1).to_numpy() for k in (G["exN"],)])
        Gj = dict(G, ent=2, exN=2)                       # index 0 of the single-row stacks
        # CVD is a running sum of SUB-bar deltas; jitter its increments in proportion
        cvdj = np.cumsum(D["delta"] * (1.0 + rng.normal(0.0, 0.05, D["n"])))
        gj = gate_from(hh, ll, cvdj, K, W, D["n"])
        Ej = X.run(Dj, Gj, gate=gj)
        for i, bn in enumerate(X.BLOCKS):
            z = Ej[Ej.blk == i]
            res[bn].append(z.pct.sum() if len(z) else np.nan)
            cnt[bn].append(len(z))
    for i, bn in enumerate(X.BLOCKS):
        a = np.array(res[bn], float)
        if not np.isfinite(a).any():
            continue
        store[f"jit{ticks}_{bn}"] = a
        ref = E[E.blk == i].pct.sum()
        print(f"  {ticks:>6.1f} {bn:10s} {np.median(cnt[bn]):>9.0f} {np.nanquantile(a,0.05):>9.2f}% "
              f"{np.nanmedian(a):>8.2f}% {np.nanquantile(a,0.95):>8.2f}% "
              f"{np.nanmean(np.sign(a) == np.sign(ref)):>10.3f}")

# ---------------------------------------------------------------- 5  parameter jitter
line("5  PARAMETER JITTER -- five axes moved together. 400 draws")
print("  entry 15-25, exit 15-25, stop 1.5-2.5 ATR, pivot k 1-3, window 12-28 bars.\n")
prm = []
for d in range(400):
    ent = int(rng.integers(15, 26)); exn = int(rng.integers(15, 26))
    stp = float(rng.uniform(1.5, 2.5)); kk = int(rng.integers(1, 4)); ww = int(rng.integers(12, 29))
    gj = gate_from(D["h"], D["l"], D["cvd"], kk, ww, D["n"])
    Ej = X.run(D, dict(G, ent=ent, exN=exn, stop=stp), gate=gj)
    row = dict(ent=ent, exN=exn, stop=stp, k=kk, w=ww)
    for i, bn in enumerate(X.BLOCKS):
        z = Ej[Ej.blk == i]
        row[bn] = z.pct.mean() if len(z) >= 20 else np.nan
        row[bn + "_tot"] = z.pct.sum() if len(z) >= 20 else np.nan
    prm.append(row)
PR = pd.DataFrame(prm)
PR.to_csv(os.path.join(OUT, "mc_params.csv"), index=False)
print(f"  {'block':10s} {'shipped':>9} {'p5':>9} {'median':>9} {'p95':>9} {'% positive':>11} "
      f"{'% beating shipped':>18}")
for i, bn in enumerate(X.BLOCKS):
    a = PR[bn].dropna().to_numpy()
    ref = E[E.blk == i].pct.mean()
    store[f"par_{bn}"] = a
    print(f"  {bn:10s} {ref:>+9.5f} {np.quantile(a,0.05):>+9.5f} {np.median(a):>+9.5f} "
          f"{np.quantile(a,0.95):>+9.5f} {100*np.mean(a>0):>10.1f}% {100*np.mean(a>ref):>17.1f}%")

np.savez(os.path.join(OUT, "mc.npz"), **{k: np.asarray(v) for k, v in store.items()})
E.to_csv(os.path.join(OUT, "mc_events.csv"), index=False)
line("WHAT THIS PRICES, AND WHAT IT CANNOT")
print("  It prices execution noise, data noise and parameter noise ON THE TRADES SELECTED.")
print("  It cannot price THE SELECTION: this gate is one cell of a 229-cell screen in which 13 cells")
print("  cleared p<=0.05 against 11.5 expected by chance. No Monte Carlo addresses that; only a")
print("  fresh market or a fresh block does. (STUDY_ATME_LIVE.)")
print(f"\n  runtime {time.time()-t0:.0f}s")
