"""Attacking the 60-minute result on every axis that could falsify it.

WHAT IS BEING ATTACKED. At 60 minutes the frozen rule is positive on US30 (+0.218 R), on 8.5 years
of US30 (+0.251) and on 22 years of gold (+0.115), monotone in bar size on all three, and it beats
a minute-of-day matched control at p 0.003 on the long US30 history. It INVERTS on US100 -- the one
market that duplicates the NQ trades the rule was found on -- which is consistent with the 15-minute
result having been the NQ artifact and this being something else.

THE FIRST AND MOST DANGEROUS ALTERNATIVE EXPLANATION: that none of this is the RULE, and all of it
is "trend-following works better on slower bars", which is old, weak and already known. Drop-one
settles that. If removing the session-high filter or the ADX floor costs nothing at 60 minutes, then
what has been found is a timeframe, not a rule.

Six attacks, in the order that can kill it fastest:
  1. DROP-ONE          is any component doing work, or is 60m the whole effect?
  2. PERTURBATION      +/-20% on every axis; a real edge is a ridge, an artifact is a spike
  3. WALK-FORWARD      rolling out-of-sample folds across 8.5 years
  4. REGIME            by calendar year and by volatility state
  5. COST STRESS       1.5x and 2x the assumed friction
  6. BOOTSTRAP / MC    day-block resampling for the edge, permutation for the drawdown
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v19")
import v16core as C          # noqa: E402
import v19frozen as F        # noqa: E402
import v19destroy as D       # noqa: E402
import v19scale as S         # noqa: E402

RNG = np.random.default_rng(20260828)
TF = 60
MKT = ["US30L", "US30", "XAU", "US100"]


def full(P):
    return np.ones(len(P["c"]), bool)


if __name__ == "__main__":
    CT = {k: S.ctx_tf(k, TF) for k in MKT}

    print("=" * 118)
    print("1. DROP-ONE -- is any component doing work at 60 minutes, or is the timeframe everything?")
    print("=" * 118)
    print(f"   {'market':<8}{'configuration':<34}{'n':>7}{'EV(R)':>9}{'PF':>8}{'Sharpe':>8}"
          f"{'maxDD':>8}{'ctl p':>8}")
    for k in MKT:
        P = CT[k]
        for lab, adx, lvl in (("full rule", True, True),
                              ("no session-high filter", True, False),
                              ("no ADX floor", False, True),
                              ("neither -- bare Donchian 55", False, False)):
            O, i = F.run(P, use_adx=adx, use_level=lvl)
            m = F.metrics(P, O, i, full(P))
            ctl, p = D.control(P, full(P), O, i, F.FROZEN["stop"], draws=800)
            print(f"   {k:<8}{lab:<34}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}"
                  f"{m['sharpe']:>8.2f}{m['dd']:>8.1f}{p:>8.3f}")
        print()

    print("=" * 118)
    print("2. PERTURBATION -- move each axis on its own; a real edge is a ridge, not a spike")
    print("=" * 118)
    AX = [("entry_n", [40, 45, 55, 65, 75]), ("exit_n", [12, 16, 20, 25, 30]),
          ("stop", [1.75, 2.0, 2.5, 3.0, 3.5]), ("adx_min", [18, 22, 25, 28, 32])]
    for axis, vals in AX:
        print(f"\n   {axis}")
        print(f"   {'value':>8}" + "".join(f"{k:>13}" for k in MKT) + f"{'pooled EV':>12}")
        for v in vals:
            cells, allr = [], []
            for k in MKT:
                kw = {axis: v}
                O, i = F.run(CT[k], **kw)
                m = F.metrics(CT[k], O, i, full(CT[k]))
                cells.append(f"{m['ev']:+.4f}")
                allr.append(O["R"][i])
            pooled = np.concatenate(allr)
            mark = "  <- shipped" if v == F.FROZEN.get(axis, F.FROZEN.get("adx") if axis == "adx_min" else None) else ""
            print(f"   {v:>8g}" + "".join(f"{c:>13}" for c in cells)
                  + f"{pooled.mean():>+12.4f}{mark}")

    print("\n" + "=" * 118)
    print("3. WALK-FORWARD on the 8.5-year US30 history -- rolling, non-overlapping folds")
    print("=" * 118)
    P = CT["US30L"]
    O, i = F.run(P)
    ts = pd.to_datetime(P["ts"][O["sig"][i]])
    r = O["R"][i]
    yr = ts.year
    print(f"   {'fold':<14}{'trades':>8}{'EV(R)':>9}{'PF':>8}{'net R':>9}")
    pos = 0
    for y in sorted(set(yr)):
        s = r[yr == y]
        if len(s) < 8:
            continue
        w, lo = s[s > 0], s[s < 0]
        pf = w.sum() / abs(lo.sum()) if len(lo) and lo.sum() != 0 else np.nan
        pos += int(s.sum() > 0)
        print(f"   {y:<14}{len(s):>8}{s.mean():>+9.4f}{pf:>8.3f}{s.sum():>+9.1f}")
    print(f"   positive years: {pos} of {len([y for y in sorted(set(yr)) if (yr==y).sum()>=8])}")

    print("\n" + "=" * 118)
    print("4. COST STRESS -- the spread is assumed in every feed here, so bend it until it breaks")
    print("=" * 118)
    print(f"   {'market':<8}" + "".join(f"{f'x{m:g}':>12}" for m in (1.0, 1.5, 2.0, 3.0)))
    for k in MKT:
        cells = []
        for cm in (1.0, 1.5, 2.0, 3.0):
            O, i = F.run(CT[k], cost_mult=cm)
            m = F.metrics(CT[k], O, i, full(CT[k]))
            cells.append(f"{m['ev']:+.4f}")
        print(f"   {k:<8}" + "".join(f"{c:>12}" for c in cells))

    print("\n" + "=" * 118)
    print("5. BOOTSTRAP AND MONTE CARLO")
    print("=" * 118)
    print(f"   {'market':<8}{'net R':>9}{'P(mean<=0)':>13}{'realised DD':>13}{'MC med':>9}"
          f"{'MC p95':>9}{'MC p99':>9}")
    for k in MKT:
        P = CT[k]
        O, i = F.run(P)
        d = F.daily_R(P, O, i, full(P)).to_numpy()
        d = d[d != 0] if (d != 0).sum() > 40 else d
        bs = np.array([RNG.choice(d, len(d), replace=True).mean() for _ in range(8000)])
        dds = []
        for _ in range(8000):
            e = RNG.permutation(d).cumsum()
            dds.append(float((np.maximum.accumulate(e) - e).max()))
        dds = np.asarray(dds)
        m = F.metrics(P, O, i, full(P))
        print(f"   {k:<8}{m['net']:>+9.1f}{float((bs <= 0).mean()):>13.4f}{m['dd']:>13.1f}"
              f"{np.median(dds):>9.1f}{np.percentile(dds,95):>9.1f}{np.percentile(dds,99):>9.1f}")
