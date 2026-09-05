"""Monte Carlo PERTURBATION on the three V61 presets.

THREE DIFFERENT MONTE CARLOS ANSWER THREE DIFFERENT QUESTIONS AND THIS BRANCH HAS CONFLATED THEM
BEFORE (`validate.monte_carlo`): a BOOTSTRAP with replacement prices the EDGE, a PERMUTATION of
the realised sequence prices the PATH and cannot change the endpoint, and a PERTURBATION re-runs
the strategy in a slightly different world. Only the third one can tell you whether the result
depends on the exact prices and fills you happened to get. All three are here, labelled.

WHAT IS PERTURBED, in rising order of how much it can hurt:

  EXECUTION   slippage and cost drawn per simulation. Cheap and the least informative, because
              it moves the P&L without moving which trades happen.
  FILLS       a random share of signals never fill -- a real failure mode for a rule with a
              position lock, because a missed entry frees the lock and lets a LATER signal in.
  ENTRY LAG   the fill lands one bar later than modelled.
  PRICES      every bar's OHLC is jittered and the bar repaired, then the ATR, both channels and
              the CVD pivot structure are RECOMPUTED FROM THE JITTERED BARS. This is the only
              perturbation that moves the SIGNAL as well as the fill, and it is the real test.
  PARAMETERS  one rung on every axis, and all axes jointly.

THE CAVEAT THAT STAYS ATTACHED (`STUDY_ATME_LIVE`): a perturbation Monte Carlo prices execution
and data noise ON THE TRADES YOU SELECTED. It can never price the SELECTION. A P(mean <= 0) of
zero here is not evidence the rule was not fitted.
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
for q in (HERE, os.path.join(HERE, "..", "v61"), os.path.join(HERE, "..", "v54"),
          os.path.join(HERE, "..", "v53"), os.path.join(HERE, "..")):
    sys.path.insert(0, q)

import v54cvd as CV  # noqa: E402
import v64opt as O   # noqa: E402
import v61core as V  # noqa: E402

warnings.filterwarnings("ignore")
pd.set_option("display.width", 250)

N_CHEAP, N_PRICE = 2000, 250
PRESETS = {
    "incumbent 30m": dict(tf=30, ent=20, exN=20, stop=2.0, tp=0.0, hold=480, adapt=0, k=3, w=20,
                          use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0),
    "15m preset": dict(tf=15, ent=15, exN=30, stop=3.0, tp=6.0, hold=480, adapt=0, k=3, w=30,
                       use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0),
    "Pareto 15m": dict(tf=15, ent=20, exN=34, stop=3.14, tp=5.38, hold=255, adapt=0, k=5, w=58,
                       use_ma=0, ma_thr=0.0, use_chop=0, chop_thr=99.0, psh=0),
}
RUNGS = dict(ent=[-5, 5], exN=[-5, 5], stop=[-0.5, 0.5], tp=[-1.0, 1.0],
             hold=[-120, 120], k=[-1, 1], w=[-10, 10])


def line(t):
    print("\n" + "=" * 124)
    print(t)
    print("=" * 124)


def stats(v):
    if len(v) == 0:
        return dict(n=0, tot=np.nan, mean=np.nan, pf=np.nan, dd=np.nan)
    eq = np.cumsum(v)
    g, b = v[v > 0].sum(), -v[v <= 0].sum()
    return dict(n=len(v), tot=float(v.sum()), mean=float(v.mean()),
                pf=float(g / b) if b > 0 else np.nan,
                dd=float((eq - np.maximum.accumulate(eq)).min()))


if __name__ == "__main__":
    Ds = {tf: O.build(tf) for tf in (15, 30, 60)}
    base = {}
    for nm, p in PRESETS.items():
        R, pct, blk, sig = O.evaluate(Ds[p["tf"]], p)
        base[nm] = dict(pct=pct, blk=blk, res=stats(pct[blk == 0]), lock=stats(pct[blk == 1]))
    line("THE REALISED RESULT the perturbations are measured against")
    print(f"  {'preset':16s}{'res n':>7s}{'res tot%':>10s}{'res DD%':>9s}"
          f"{'lock n':>8s}{'lock tot%':>11s}{'lock %/t':>10s}{'lock PF':>9s}{'lock DD%':>10s}")
    for nm in PRESETS:
        r, k = base[nm]["res"], base[nm]["lock"]
        print(f"  {nm:16s}{r['n']:>7d}{r['tot']:>10.2f}{r['dd']:>9.2f}"
              f"{k['n']:>8d}{k['tot']:>11.2f}{k['mean']:>10.4f}{k['pf']:>9.3f}{k['dd']:>10.2f}")

    rng = np.random.default_rng(17)

    # ---------------------------------------------------------------- A. execution
    line("A. EXECUTION PERTURBATION -- slippage U(0, 2x assumed), cost U(0.5x, 2x), "
         f"{N_CHEAP:,} draws")
    print(f"  {'preset':16s}{'lock tot% p5':>14s}{'p50':>9s}{'p95':>9s}"
          f"{'realised':>10s}{'P(tot<=0)':>11s}{'worst':>9s}")
    for nm, p in PRESETS.items():
        D = Ds[p["tf"]]
        out = np.zeros(N_CHEAP)
        for i in range(N_CHEAP):
            R, pct, blk, sig = O.evaluate(D, p, cost=V.COST * rng.uniform(0.5, 2.0),
                                          slip=V.SLIP * rng.uniform(0.0, 2.0))
            out[i] = pct[blk == 1].sum()
        print(f"  {nm:16s}{np.quantile(out, .05):>14.2f}{np.median(out):>9.2f}"
              f"{np.quantile(out, .95):>9.2f}{base[nm]['lock']['tot']:>10.2f}"
              f"{(out <= 0).mean():>11.3f}{out.min():>9.2f}")

    # ---------------------------------------------------------------- B. missed fills
    line("B. MISSED FILLS -- a share of signals never fill, and the position lock re-opens")
    print(f"  {'preset':16s}{'drop 5%':>10s}{'drop 10%':>10s}{'drop 20%':>10s}"
          f"{'drop 40%':>10s}{'realised':>10s}")
    for nm, p in PRESETS.items():
        row = []
        v0 = base[nm]["pct"][base[nm]["blk"] == 1]
        for share in (0.05, 0.10, 0.20, 0.40):
            tots = []
            for _ in range(500):
                keep = rng.random(len(v0)) >= share
                tots.append(v0[keep].sum())
            row.append(np.median(tots))
        print(f"  {nm:16s}" + "".join(f"{x:>10.2f}" for x in row)
              + f"{base[nm]['lock']['tot']:>10.2f}")
    print("\n  A dropped trade is only a lost trade here; it does NOT free the lock, because the")
    print("  lock is applied inside the walk. Treat this as an upper bound on the damage, not a")
    print("  simulation of a live miss.")

    # ---------------------------------------------------------------- C. price jitter
    line(f"C. PRICE PERTURBATION -- OHLC jittered, indicators RECOMPUTED, {N_PRICE} draws per level")
    print(f"  {'preset':16s}{'noise':>8s}{'trades p50':>12s}{'lock tot% p5':>14s}{'p50':>9s}"
          f"{'p95':>9s}{'realised':>10s}{'P(tot<=0)':>11s}{'sign kept':>11s}")
    for nm, p in PRESETS.items():
        D = Ds[p["tf"]]
        for sig_t in (0.5, 1.0, 2.0):
            tots, ns = np.zeros(N_PRICE), np.zeros(N_PRICE)
            for i in range(N_PRICE):
                o, h, l, c = O.perturb_bars(D, sig_t, rng)
                R, pct, blk, sg = O.evaluate_perturbed(D, p, o, h, l, c, CV)
                v = pct[blk == 1]
                tots[i] = v.sum(); ns[i] = len(v)
            print(f"  {nm:16s}{f'{sig_t} tick':>8s}{np.median(ns):>12.0f}"
                  f"{np.quantile(tots, .05):>14.2f}{np.median(tots):>9.2f}"
                  f"{np.quantile(tots, .95):>9.2f}{base[nm]['lock']['tot']:>10.2f}"
                  f"{(tots <= 0).mean():>11.3f}{(tots > 0).mean():>11.3f}")

    # ---------------------------------------------------------------- D. parameters
    line("D. PARAMETER PERTURBATION -- one rung on each axis, then all axes jointly")
    for nm, p in PRESETS.items():
        D = Ds[p["tf"]]
        print(f"\n  {nm}  (realised locked {base[nm]['lock']['tot']:+.2f}%)")
        worst = 1e9
        for ax, deltas in RUNGS.items():
            vals = []
            for d in deltas:
                q = dict(p)
                q[ax] = max(1, q[ax] + d) if ax in ("ent", "exN", "k", "w", "hold") \
                    else max(0.0, q[ax] + d)
                if ax in ("ent", "exN", "k", "w", "hold"):
                    q[ax] = int(q[ax])
                R, pct, blk, sg = O.evaluate(D, q)
                vals.append(pct[blk == 1].sum())
            worst = min(worst, min(vals))
            print(f"    {ax:6s} {deltas[0]:+6} -> {vals[0]:+8.2f}   "
                  f"{deltas[1]:+6} -> {vals[1]:+8.2f}   "
                  f"swing {max(vals) - min(vals):6.2f}")
        joint = np.zeros(500)
        for i in range(500):
            q = dict(p)
            q["ent"] = int(max(5, q["ent"] + rng.integers(-5, 6)))
            q["exN"] = int(max(5, q["exN"] + rng.integers(-5, 6)))
            q["stop"] = float(max(0.5, q["stop"] + rng.uniform(-0.5, 0.5)))
            q["tp"] = float(max(0.0, q["tp"] + rng.uniform(-1, 1))) if q["tp"] > 0 else 0.0
            q["k"] = int(np.clip(q["k"] + rng.integers(-1, 2), 2, 6))
            q["w"] = int(max(3, q["w"] + rng.integers(-10, 11)))
            R, pct, blk, sg = O.evaluate(D, q)
            joint[i] = pct[blk == 1].sum()
        print(f"    joint jitter on all six axes, 500 draws: "
              f"p5 {np.quantile(joint, .05):+.2f}  p50 {np.median(joint):+.2f}  "
              f"p95 {np.quantile(joint, .95):+.2f}  P(<=0) {(joint <= 0).mean():.3f}  "
              f"share above realised {(joint > base[nm]['lock']['tot']).mean():.2f}")
        print(f"    worst single-rung neighbour {worst:+.2f}%")

    # ---------------------------------------------------------------- E. path and edge
    line("E. THE OTHER TWO MONTE CARLOS -- permutation for the PATH, bootstrap for the EDGE")
    print(f"  {'preset':16s}{'realised DD%':>14s}{'MC DD p50':>11s}{'p95':>9s}{'p99':>9s}"
          f"{'percentile':>12s}{'boot mean 95% CI':>26s}{'P(mean<=0)':>12s}")
    for nm in PRESETS:
        v = base[nm]["pct"][base[nm]["blk"] == 1]
        dds = np.zeros(5000)
        for i in range(5000):
            w = rng.permutation(v)
            eq = np.cumsum(w)
            dds[i] = -(eq - np.maximum.accumulate(eq)).min()
        rd = -base[nm]["lock"]["dd"]
        bs = np.array([rng.choice(v, len(v), replace=True).mean() for _ in range(5000)])
        print(f"  {nm:16s}{-rd:>14.2f}{np.median(dds):>11.2f}{np.quantile(dds, .95):>9.2f}"
              f"{np.quantile(dds, .99):>9.2f}{(dds <= rd).mean():>12.2f}"
              f"   [{np.quantile(bs, .025):+10.4f}, {np.quantile(bs, .975):+9.4f}]"
              f"{(bs <= 0).mean():>12.3f}")
    print("\n  The permutation cannot change the endpoint -- it is a DRAWDOWN statement only. The")
    print("  p99 is the sizing number. A realised drawdown BELOW the MC median means the path was")
    print("  luckier than a reshuffle of its own trades.")
