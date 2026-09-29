"""MONTE CARLO on the incumbent (both timeframes, both session settings) and PORTFOLIO CONSTRUCTION.

MONTE CARLO -- the branch's four, on each of the four configurations:
  bootstrap over whole DAYS with their trades attached (edge), permutation of the realised sequence
  (path, drawdown only), execution perturbation (cost and slippage drawn inside the walk), and a
  five-axis parameter jitter (neighbourhood).

PORTFOLIO -- the question is whether the 15m and 30m legs are two strategies or one. This branch has
recorded the trap twice: STUDY_HYPO found eight "different" breakout hypotheses correlating 0.87-0.96
in daily returns and combining them took Sharpe 0.30 -> 0.11; STUDY_TOP5 found the NQ + US100 book
had daily correlation 0.90, i.e. one index wearing two names. So the correlation is measured on
DAILY STRATEGY RETURNS before any weighting is proposed, and the combination is reported against the
best single leg rather than against the average one.
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
sys.path.insert(0, HERE)
import sess_core as S            # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)
OUT = os.path.join(ROOT, "results/v61sess")
os.makedirs(OUT, exist_ok=True)


def line(t):
    print("\n" + "=" * 126)
    print(t)
    print("=" * 126, flush=True)


def maxdd(x):
    c = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(c) - c)) if len(c) else 0.0


print(__doc__)
t0 = time.time()
rng = np.random.default_rng(4242)
D = {15: S.build(15), 30: S.build(30)}
G = {tf: S.gate(D[tf], 90, 600)[0] for tf in (15, 30)}
CFG = dict(ent=20, exN=20, stop=2.0, tp=0.0, hold=480, piv_min=90, win_min=600, touch=True)
LEGS = {
    "30m all hours": (30, dict(sess=False)),
    "30m 07-11 no flatten": (30, dict(sess=True, s_start=7 * 60, s_stop=11 * 60, flat=False)),
    "15m all hours": (15, dict(sess=False)),
    "15m 07-11 + flatten (yours)": (15, dict(sess=True, s_start=7 * 60, s_stop=11 * 60, flat=True)),
}
T = {nm: S.run(D[tf], **CFG, **kw, g=G[tf]) for nm, (tf, kw) in LEGS.items()}

line("MONTE CARLO -- 1  EDGE. Day-block bootstrap, 2,000 draws, whole days with their trades")
print(f"  {'leg':30s} {'block':9s} {'n':>4} {'mean pts':>9} {'p5':>9} {'p95':>9} {'P(mean<=0)':>12}")
mc = []
for nm, t in T.items():
    for b, bn in ((0, "research"), (1, "locked")):
        z = t[t.blk == b]
        if len(z) < 25:
            continue
        days = z.day.to_numpy(); ud = np.unique(days)
        byd = [z.pts.to_numpy()[days == d] for d in ud]
        means = np.array([np.concatenate([byd[j] for j in rng.integers(0, len(ud), len(ud))]).mean()
                          for _ in range(2000)])
        mc.append(dict(leg=nm, block=bn, test="bootstrap", n=len(z), mean=means.mean(),
                       p5=np.quantile(means, .05), p95=np.quantile(means, .95),
                       p_le0=float(np.mean(means <= 0))))
        print(f"  {nm:30s} {bn:9s} {len(z):>4} {means.mean():>+9.3f} {np.quantile(means,.05):>+9.3f} "
              f"{np.quantile(means,.95):>+9.3f} {np.mean(means<=0):>12.3f}")

line("MONTE CARLO -- 2  PATH. Permutation of the realised trades, drawdown only, 2,000 reshuffles")
print(f"  {'leg':30s} {'block':9s} {'realised DD $':>13} {'MC median $':>12} {'MC p99 $':>10} "
      f"{'pctile':>7} {'p99/real':>9}")
for nm, t in T.items():
    for b, bn in ((0, "research"), (1, "locked")):
        z = t[t.blk == b]
        if len(z) < 25:
            continue
        a = z.pts.to_numpy(); real = maxdd(a)
        dd = np.array([maxdd(rng.permutation(a)) for _ in range(2000)])
        pc = float(np.mean(dd <= real))
        mc.append(dict(leg=nm, block=bn, test="permutation", real_dd=real * 2,
                       p99=float(np.quantile(dd, .99)) * 2, pctile=pc))
        print(f"  {nm:30s} {bn:9s} {real*2:>13.0f} {np.median(dd)*2:>12.0f} "
              f"{np.quantile(dd,.99)*2:>10.0f} {pc:>7.2f} {np.quantile(dd,.99)/max(real,1e-9):>9.2f}x")

line("MONTE CARLO -- 3  EXECUTION. cost ~ U(0.5x, 2x), slippage ~ U(0, 2x), inside the walk, 250 draws")
print(f"  {'leg':30s} {'block':9s} {'p5 $':>9} {'median $':>9} {'p95 $':>9} {'P(total<=0)':>13}")
for nm, (tf, kw) in LEGS.items():
    tot = {0: [], 1: []}
    for d in range(250):
        cm, sm = rng.uniform(.5, 2.) * S.COST, rng.uniform(0., 2.) * S.SLIP
        t = S.run(D[tf], **CFG, **kw, g=G[tf], cost=cm, slip=sm)
        for b in (0, 1):
            z = t[t.blk == b]
            tot[b].append(z.pts.sum() * 2 if len(z) >= 20 else np.nan)
    for b, bn in ((0, "research"), (1, "locked")):
        a = np.array(tot[b], float); a = a[np.isfinite(a)]
        if len(a) < 10:
            continue
        mc.append(dict(leg=nm, block=bn, test="execution", p5=np.quantile(a, .05),
                       med=np.median(a), p95=np.quantile(a, .95), p_le0=float(np.mean(a <= 0))))
        print(f"  {nm:30s} {bn:9s} {np.quantile(a,.05):>9.0f} {np.median(a):>9.0f} "
              f"{np.quantile(a,.95):>9.0f} {np.mean(a<=0):>13.3f}")

line("MONTE CARLO -- 4  PARAMETERS. entry, exit, stop, pivot and window jittered together, 300 draws")
print(f"  {'leg':30s} {'block':9s} {'shipped PF':>11} {'p5 PF':>7} {'median':>7} {'p95':>7} "
      f"{'% PF>1':>8} {'% beating':>10}")
for nm, (tf, kw) in LEGS.items():
    got = {0: [], 1: []}
    for d in range(300):
        e = int(rng.integers(14, 29)); x = int(rng.integers(14, 29))
        st = float(rng.uniform(1.5, 2.6))
        pv = int(rng.choice([60, 90, 120])); wn = int(rng.choice([450, 600, 900]))
        t = S.run(D[tf], ent=e, exN=x, stop=st, tp=0.0, hold=480, piv_min=pv, win_min=wn,
                  touch=True, **kw, g=S.gate(D[tf], pv, wn)[0])
        for b in (0, 1):
            z = t[t.blk == b]
            if len(z) < 20:
                got[b].append(np.nan); continue
            a = z.pts.to_numpy()
            got[b].append(a[a > 0].sum() / max(-a[a < 0].sum(), 1e-9))
    for b, bn in ((0, "research"), (1, "locked")):
        a = np.array(got[b], float); a = a[np.isfinite(a)]
        z = T[nm][T[nm].blk == b]
        if len(a) < 10 or len(z) < 20:
            continue
        p = z.pts.to_numpy()
        ref = p[p > 0].sum() / max(-p[p < 0].sum(), 1e-9)
        mc.append(dict(leg=nm, block=bn, test="params", ref=ref, p5=np.quantile(a, .05),
                       med=np.median(a), p95=np.quantile(a, .95),
                       pos=float(np.mean(a > 1)), beat=float(np.mean(a > ref))))
        print(f"  {nm:30s} {bn:9s} {ref:>11.3f} {np.quantile(a,.05):>7.3f} {np.median(a):>7.3f} "
              f"{np.quantile(a,.95):>7.3f} {100*np.mean(a>1):>7.0f}% {100*np.mean(a>ref):>9.0f}%")
pd.DataFrame(mc).to_csv(os.path.join(OUT, "mc.csv"), index=False)

# ------------------------------------------------------------------ portfolio
line("PORTFOLIO -- are these two strategies, or one wearing two names?")
print("  Daily strategy returns in POINTS, zero-filled on days a leg did not trade -- the only")
print("  honest way to correlate two legs with different trade counts (STUDY_V17: a filter that is")
print("  paid for trading less looks good on traded days only).\n")
allday = sorted(set(np.concatenate([D[15]["day"], D[30]["day"]])))
DR = pd.DataFrame(index=pd.Index(allday, name="day"))
for nm, t in T.items():
    DR[nm] = t.groupby("day").pts.sum().reindex(allday).fillna(0.0)
DR.to_csv(os.path.join(OUT, "daily.csv"))
print("  daily-return correlation matrix (all days, whole sample):")
print("   " + DR.corr().round(3).to_string().replace("\n", "\n   "))

line("PORTFOLIO -- combinations, against the BEST single leg rather than the average one")
blkday = pd.Series(D[30]["blk"], index=D[30]["day"]).groupby(level=0).max().reindex(allday).fillna(1)


def report(name, series, blk):
    z = series[blk == 0].to_numpy(), series[blk == 1].to_numpy()
    out = []
    for a, bn in zip(z, ("research", "locked")):
        nz = a[a != 0]
        if len(nz) < 10:
            continue
        dd = maxdd(a)
        sh = a.mean() / a.std() * np.sqrt(252) if a.std() > 0 else 0.0
        out.append(dict(cfg=name, block=bn, days=len(nz), pts=a.sum(), usd=a.sum() * 2,
                        dd_usd=dd * 2, ret_dd=a.sum() / max(dd, 1e-9), sharpe=sh,
                        pf=nz[nz > 0].sum() / max(-nz[nz < 0].sum(), 1e-9)))
    return out


COMB = {nm: DR[nm] for nm in DR.columns}
COMB["EQUAL 30m+15m all hours"] = 0.5 * (DR["30m all hours"] + DR["15m all hours"])
COMB["EQUAL all four legs"] = DR.mean(axis=1)
COMB["30m all hours + 30m 07-11"] = 0.5 * (DR["30m all hours"] + DR["30m 07-11 no flatten"])
iv = {c: 1.0 / max(DR[c][blkday == 0].std(), 1e-9) for c in DR.columns}
sw = sum(iv.values())
COMB["INVERSE-VOL all four (weights from research only)"] = sum(DR[c] * iv[c] / sw for c in DR.columns)
rows = []
for nm, s in COMB.items():
    rows += report(nm, s, blkday.to_numpy())
P = pd.DataFrame(rows)
P.to_csv(os.path.join(OUT, "portfolio.csv"), index=False)
print(f"  {'combination':46s} {'block':9s} {'days':>5} {'$ (MNQ)':>9} {'maxDD $':>9} "
      f"{'ret/DD':>7} {'Sharpe':>7} {'PF':>6}")
for _, r in P.iterrows():
    print(f"  {r.cfg:46s} {r.block:9s} {int(r.days):>5} {r.usd:>9.0f} {r.dd_usd:>9.0f} "
          f"{r.ret_dd:>7.2f} {r.sharpe:>7.2f} {r.pf:>6.3f}")

line("DOES COMBINING BEAT THE BEST SINGLE LEG?")
for bn in ("research", "locked"):
    z = P[P.block == bn]
    single = z[z.cfg.isin(DR.columns)]
    best = single.loc[single.ret_dd.idxmax()]
    for _, r in z[~z.cfg.isin(DR.columns)].iterrows():
        print(f"  {bn:9s} {r.cfg:46s} ret/DD {r.ret_dd:>6.2f} vs best single leg "
              f"({best.cfg}) {best.ret_dd:>6.2f}   "
              f"{'BETTER' if r.ret_dd > best.ret_dd else 'worse'}")
print(f"\n  runtime {time.time()-t0:.0f}s")
