"""GOLD x DONCHIAN x CVD -- base rates first, then the control battery, then ONE locked read.

ORDER OF OPERATIONS, and it is not negotiable on this branch:
  1. THE BASE, on every block, against a random ENTRY. If the base is a drift exposure, say so
     before anything is added to it.
  2. BASE RATES on the trigger's OWN bars. `STUDY_V60_AROON` (Aroon 100.0% of breakout bars),
     `STUDY_V16_MOMENTUM` (RSI>=55 94.7%), `STUDY_V62` (MACD 99.8-100.0%, MFI 91.7%) -- four
     indicators that turned out to BE the breakout restated. Two lines, before any P&L.
  3. Every feature against a SAME-SELECTIVITY RANDOM FILTER on the RESEARCH blocks (A + B), never
     against total dollars and never against per-trade edge.
  4. Benjamini-Hochberg across the whole pool, because 60 features is 60 tests.
  5. ONE read of block C for the survivors.

>>> BLOCK C HAS ALREADY BEEN READ ONCE ON GOLD, by STUDY_XAU_TWO_LAYER. This is the SECOND read.
>>> Everything it returns is correspondingly weaker and is reported as descriptive.
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
for p in (HERE, os.path.join(ROOT, "research"), os.path.join(ROOT, "research/xau")):
    sys.path.insert(0, p)

import xcvd                      # noqa: E402
import xau_core as X             # noqa: E402
from numba import njit           # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 240)
OUT = os.path.join(ROOT, "results/xaucvd")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124, flush=True)


# five geometries frozen elsewhere on this branch; nothing fitted on gold
GEOM = {
    "V54  20/20 2.0N no-tp": dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, side=1),
    "V38  70/30 2.5N no-tp": dict(ent=70, exN=30, stop=2.5, tp=0.0, hold=480, side=1),
}
TFS = (60, 240)


@njit(cache=True)
def walk_at(o, h, l, c, atr, ex_lo, bars, stop_n, hold, cost, slip, last_bar):
    """The identical exit machine entered at supplied bars -- the matched random-entry control."""
    m = len(c); nb = len(bars); pct = np.full(nb, np.nan); cnt = 0; busy = -1
    for z in range(nb):
        i = bars[z]
        if i <= busy or i < 300 or i >= last_bar:
            continue
        a = i + 1; anchor = atr[i]
        if not np.isfinite(anchor) or anchor <= 0.0:
            continue
        px = o[a] + slip; fixed = px - stop_n * anchor
        end = a + hold
        if end > m - 2:
            end = m - 2
        out = np.nan; j = a
        while j <= end:
            lvl = fixed
            ch = ex_lo[j]
            if np.isfinite(ch) and ch > lvl:
                lvl = ch
            cp = c[j - 1]
            if np.isfinite(cp) and lvl > cp:
                lvl = cp
            if l[j] <= lvl:
                out = (lvl if o[j] > lvl else o[j]) - slip
                break
            j += 1
        if not np.isfinite(out):
            j = end; out = c[j] - slip
        pct[cnt] = 100.0 * (out - px - cost) / px
        cnt += 1; busy = j
    return pct[:cnt]


def events(D, g, gate=None):
    return X.run(D, g, gate=gate)


def blkmask(e, i):
    return e.blk == i


def ctl_filter(r, keep_n, draws, rng):
    """A random filter keeping the same NUMBER of the SAME events."""
    if keep_n < 10 or keep_n >= len(r):
        return None
    return np.array([r[rng.choice(len(r), keep_n, replace=False)].mean() for _ in range(draws)])


def bh(pvals, q=0.10):
    p = np.asarray(pvals, float)
    order = np.argsort(p)
    m = len(p)
    keep = np.zeros(m, bool)
    for rank, idx in enumerate(order, start=1):
        if p[idx] <= q * rank / m:
            keep[order[:rank]] = True
    return keep


t0 = time.time()
print(__doc__)
rng = np.random.default_rng(5)

DATA = {}
for tf in TFS:
    D = xcvd.build(tf)
    F = xcvd.features(D)
    DATA[tf] = (D, F)
    print(f"  {tf}m: {D['n']:,} bars, {F.shape[1]} CVD features, "
          f"{tf // xcvd.SUB_TF} sub-bars a bar for the delta")

line("STEP 0 -- THE BASE, against a RANDOM ENTRY with the same exits. Read this before anything else")
print(f"  {'tf':>5} {'geometry':24s} {'block':10s} {'n':>5} {'rule %/ev':>10} {'random p50':>11} {'excess':>9} {'p':>7}")
base_rows = []
for tf in TFS:
    D, F = DATA[tf]
    for gn, g in GEOM.items():
        E = events(D, g)
        xi = int(g["exN"]) - 2
        pool_all = np.arange(D["n"])
        for i, bn in enumerate(X.BLOCKS):
            e = E[blkmask(E, i)]
            if len(e) < 30:
                continue
            obs = e.pct.mean()
            pool = pool_all[(D["blk"] == i) & (pool_all >= 300) & (pool_all < D["last_bar"])]
            draws = np.empty(300)
            for kk in range(300):
                bb = np.sort(rng.choice(pool, size=min(len(e) * 3, len(pool)), replace=False))
                q = walk_at(D["o"], D["h"], D["l"], D["c"], D["atr"], D["ex_lo"][xi], bb,
                            float(g["stop"]), int(g["hold"]), X.COST_RT, X.SLIP, int(D["last_bar"]))
                draws[kk] = np.mean(q[:len(e)]) if len(q) >= 20 else np.nan
            pv = float(np.nanmean(draws >= obs))
            base_rows.append(dict(tf=tf, geom=gn, block=bn, n=len(e), obs=obs,
                                  ctl=float(np.nanmedian(draws)), p=pv))
            print(f"  {tf:>5} {gn:24s} {bn:10s} {len(e):>5} {obs:>10.5f} {np.nanmedian(draws):>11.5f} "
                  f"{obs-np.nanmedian(draws):>+9.5f} {pv:>7.3f}")
BASE = pd.DataFrame(base_rows)
BASE.to_csv(os.path.join(OUT, "base.csv"), index=False)

line("STEP 1 -- BASE RATES ON THE TRIGGER'S OWN BARS. Does the feature bind at all, before any P&L?")
print("  A pass rate near 1.00 with a lift near 1.00 means the feature IS the breakout restated and")
print("  removes nothing. Four indicators have died this way on this branch (RSI, Aroon, MACD, MFI).\n")
print(f"  {'tf':>5} {'feature':38s} {'pass on signals':>16} {'pass on all bars':>17} {'lift':>7} {'binds?':>8}")
br_rows = []
for tf in TFS:
    D, F = DATA[tf]
    g = GEOM["V54  20/20 2.0N no-tp"]
    E = events(D, g)
    sig = E.sig.to_numpy()
    for col in F.columns:
        x = F[col].to_numpy(float)
        if not np.isfinite(x).any():
            continue
        binary = set(np.unique(x[np.isfinite(x)])) <= {0.0, 1.0}
        if binary:
            ps = float(np.nanmean(x[sig])); pa = float(np.nanmean(x))
        else:                                  # continuous: use its own research-block median
            med = float(np.nanmedian(x[(D["blk"] < 2) & np.isfinite(x)]))
            ps = float(np.nanmean(x[sig] >= med)); pa = float(np.nanmean(x >= med))
        lift = ps / max(pa, 1e-9)
        br_rows.append(dict(tf=tf, feature=col, pass_sig=ps, pass_all=pa, lift=lift, binary=binary))
BR = pd.DataFrame(br_rows)
BR.to_csv(os.path.join(OUT, "base_rates.csv"), index=False)
show = BR[BR.tf == 240].sort_values("pass_sig", ascending=False)
for _, r in pd.concat([show.head(8), show.tail(4)]).iterrows():
    tag = "restated" if r.pass_sig > 0.95 else ("inert" if abs(r.lift - 1) < 0.03 else "binds")
    print(f"  {r.tf:>5.0f} {r.feature:38s} {100*r.pass_sig:>15.1f}% {100*r.pass_all:>16.1f}% "
          f"{r.lift:>7.2f} {tag:>8}")
print(f"\n  features passing >95% of signal bars (the breakout restated): "
      f"{int((BR.pass_sig > 0.95).sum())} of {len(BR)}")
print(f"  features with lift within 3% of 1.00 (inert on these bars): {int((BR.lift.sub(1).abs() < 0.03).sum())}")

line("STEP 2 -- EVERY FEATURE vs a SAME-SELECTIVITY RANDOM FILTER, on the RESEARCH blocks (A + B)")
print("  The base's own events, filtered; the null keeps the same NUMBER of the same events at random.")
print("  Continuous features are cut at their research-block median; binaries at True.\n")
rows = []
for tf in TFS:
    D, F = DATA[tf]
    for gn, g in GEOM.items():
        E = events(D, g)
        sig = E.sig.to_numpy()
        res = E.blk.to_numpy() < 2
        r_res = E.pct.to_numpy()[res]
        if len(r_res) < 60:
            continue
        for col in F.columns:
            x = F[col].to_numpy(float)[sig]
            xr = x[res]
            if not np.isfinite(xr).any():
                continue
            binary = set(np.unique(xr[np.isfinite(xr)])) <= {0.0, 1.0}
            keep = (xr > 0.5) if binary else (xr >= np.nanmedian(xr))
            keep = keep & np.isfinite(xr)
            nk = int(keep.sum())
            if nk < 30 or nk > len(xr) - 10:
                continue
            obs = float(r_res[keep].mean())
            draws = ctl_filter(r_res, nk, 600, rng)
            if draws is None:
                continue
            pv = float(np.mean(draws >= obs))
            rows.append(dict(tf=tf, geom=gn, feature=col, n_res=len(r_res), kept=nk,
                             keep_frac=nk / len(r_res), base=float(r_res.mean()), filt=obs,
                             edge=obs - float(r_res.mean()), p=pv, binary=binary))
S = pd.DataFrame(rows)
S["bh"] = bh(S.p.to_numpy(), 0.10)
S = S.sort_values("p")
S.to_csv(os.path.join(OUT, "screen.csv"), index=False)
print(f"  {len(S)} scorable cells.  cells at p<=0.05: {int((S.p <= 0.05).sum())} "
      f"(expected by chance {0.05*len(S):.1f}).  surviving BH q=0.10: {int(S.bh.sum())}")
print(f"\n  {'tf':>5} {'geometry':24s} {'feature':36s} {'keep':>6} {'base':>9} {'filtered':>9} {'edge':>9} {'p':>7} {'BH':>4}")
for _, r in S.head(14).iterrows():
    print(f"  {r.tf:>5.0f} {r.geom:24s} {r.feature:36s} {100*r.keep_frac:>5.0f}% {r.base:>9.5f} "
          f"{r.filt:>9.5f} {r.edge:>+9.5f} {r.p:>7.3f} {'yes' if r.bh else '':>4}")

line("STEP 3 -- THE FOUR PATTERNS, SEPARATELY (STUDY_V55: a union is diluted by its weaker member)")
print(f"  {'tf':>5} {'pattern':22s} {'k':>2} {'w':>3} {'keep':>6} {'A+B edge':>10} {'p':>7} {'C edge':>10} {'C n':>5}")
pat_rows = []
for tf in TFS:
    D, F = DATA[tf]
    g = GEOM["V54  20/20 2.0N no-tp"]
    E = events(D, g)
    sig = E.sig.to_numpy(); res = E.blk.to_numpy() < 2; lok = E.blk.to_numpy() == 2
    r_res, r_lok = E.pct.to_numpy()[res], E.pct.to_numpy()[lok]
    for col in [c for c in F.columns if c.startswith("div.")]:
        x = F[col].to_numpy(float)[sig]
        kr = (x[res] > 0.5); kl = (x[lok] > 0.5)
        if kr.sum() < 30:
            continue
        obs = float(r_res[kr].mean())
        draws = ctl_filter(r_res, int(kr.sum()), 600, rng)
        pv = float(np.mean(draws >= obs)) if draws is not None else np.nan
        parts = col.split("_")
        nm = "_".join(parts[:-2]).replace("div.", "")
        kk, ww = parts[-2], parts[-1]
        pat_rows.append(dict(tf=tf, pattern=nm, k=kk, w=ww, keep=kr.mean(),
                             edge=obs - r_res.mean(), p=pv,
                             c_edge=(float(r_lok[kl].mean() - r_lok.mean()) if kl.sum() >= 20 else np.nan),
                             c_n=int(kl.sum())))
P = pd.DataFrame(pat_rows)
P.to_csv(os.path.join(OUT, "patterns.csv"), index=False)
for _, r in P[P.tf == 240].sort_values(["pattern", "k", "w"]).iterrows():
    print(f"  {r.tf:>5.0f} {r.pattern:22s} {r.k:>2} {r.w:>3} {100*r.keep:>5.0f}% {r.edge:>+10.5f} "
          f"{r.p:>7.3f} {r.c_edge:>+10.5f} {r.c_n:>5.0f}")
print("\n  by pattern, pooled over both timeframes, all pivot widths and windows:")
print(P.groupby("pattern").agg(cells=("edge", "size"), mean_edge=("edge", "mean"),
                               pos=("edge", lambda z: 100 * (z > 0).mean()),
                               best_p=("p", "min")).to_string(float_format=lambda z: f"{z:9.5f}"))
print(f"\n  runtime {time.time()-t0:.0f}s")
