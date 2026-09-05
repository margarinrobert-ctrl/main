"""The configuration that survived every attack, with its full metric set and its limits.

WHAT IT IS. Donchian 55 up-break on 60-MINUTE bars, taken only while the instrument's own close is
above its 200-DAY average, ADX(14) >= 25, stop at the NEARER of 2.5 x ATR(20) and the 20-bar low
capped at the previous close, NO TARGET, market order at the next open, one unit, long only.

WHAT IT IS NOT. It is not V17's rule -- drop-one showed the session-high filter earns nothing at 60
minutes and slightly hurts on the 8.5-year history. It is not a scalp. It is not established on the
Nasdaq family, where it is negative. And its timeframe was chosen after looking at three, so that
one choice is post-hoc and is declared as such.
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
import v19scale as S         # noqa: E402
from v19drift import daily_trend_state   # noqa: E402

RNG = np.random.default_rng(20260828)
TF = 60


def shipped(P, block=None, use_adx=True, stop=None, exit_n=None, entry_n=None, cost_mult=1.0):
    st = daily_trend_state(P)
    up = st == 1
    b = up if block is None else (up & block)
    return F.run(P, block=b, use_adx=use_adx, use_level=False, stop=stop,
                 exit_n=exit_n, entry_n=entry_n, cost_mult=cost_mult), b


if __name__ == "__main__":
    print("=" * 118)
    print("THE SHIPPED CONFIGURATION -- Donchian 55, 60m, above the 200-day, ADX>=25, 2.5N, no TP")
    print("=" * 118)
    print(f"   {'market':<8}{'span':<26}{'n':>7}{'EV(R)':>9}{'PF':>8}{'win%':>7}{'net R':>9}"
          f"{'maxDD':>8}{'MAR':>7}{'Sharpe':>8}{'Sortino':>9}{'Ulcer':>8}")
    keep = {}
    for k in ("US30L", "XAU", "US30", "US100"):
        P = S.ctx_tf(k, TF)
        (O, i), b = shipped(P)
        m = F.metrics(P, O, i, b)
        keep[k] = (P, O, i, b, m)
        span = f"{str(P['ts'][0])[:10]} to {str(P['ts'][-1])[:10]}"
        print(f"   {k:<8}{span:<26}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}{100*m['win']:>7.1f}"
              f"{m['net']:>+9.1f}{m['dd']:>8.1f}{m['mar']:>7.2f}{m['sharpe']:>8.2f}"
              f"{m['sortino']:>9.2f}{m['ulcer']:>8.2f}")

    print("\n   Walk-forward by calendar year, US30 8.5-year history:")
    P, O, i, b, m = keep["US30L"]
    ts = pd.to_datetime(P["ts"][O["sig"][i]])
    r = O["R"][i]
    yrs = sorted(set(ts.year))
    cells = []
    pos = 0
    tot = 0
    for y in yrs:
        s = r[ts.year == y]
        if len(s) < 6:
            continue
        tot += 1
        pos += int(s.sum() > 0)
        cells.append(f"{y}:{s.sum():+.1f}")
    print("      " + "  ".join(cells))
    print(f"      positive years {pos} of {tot}")

    print("\n   Perturbation of the shipped cell, one axis at a time, EV in R:")
    print(f"   {'axis':<12}" + "".join(f"{v:>12}" for v in ("-2 steps", "-1", "SHIPPED", "+1", "+2")))
    for axis, vals in (("entry_n", [40, 45, 55, 65, 75]), ("exit_n", [12, 16, 20, 25, 30]),
                       ("stop", [1.75, 2.0, 2.5, 3.0, 3.5])):
        row = []
        for v in vals:
            (O2, i2), b2 = shipped(keep["US30L"][0], **{axis: v})
            row.append(f"{F.metrics(keep['US30L'][0], O2, i2, b2)['ev']:+.4f}")
        print(f"   {axis:<12}" + "".join(f"{c:>12}" for c in row))

    print("\n   Cost stress on the shipped cell, EV in R:")
    print(f"   {'market':<8}" + "".join(f"{f'x{c:g}':>11}" for c in (1.0, 1.5, 2.0, 3.0)))
    for k in ("US30L", "XAU", "US30"):
        row = []
        for cm in (1.0, 1.5, 2.0, 3.0):
            (O2, i2), b2 = shipped(keep[k][0], cost_mult=cm)
            row.append(f"{F.metrics(keep[k][0], O2, i2, b2)['ev']:+.4f}")
        print(f"   {k:<8}" + "".join(f"{c:>11}" for c in row))

    print("\n   Bootstrap and Monte Carlo on the shipped cell:")
    print(f"   {'market':<8}{'P(mean<=0)':>13}{'realised DD':>13}{'MC med':>9}{'MC p95':>9}{'MC p99':>9}")
    for k in ("US30L", "XAU", "US30"):
        P, O, i, b, m = keep[k]
        d = F.daily_R(P, O, i, b).to_numpy()
        d = d[d != 0]
        bs = np.array([RNG.choice(d, len(d), replace=True).mean() for _ in range(8000)])
        dds = np.array([float((np.maximum.accumulate(RNG.permutation(d).cumsum())
                               - RNG.permutation(d).cumsum()).max()) for _ in range(3000)])
        print(f"   {k:<8}{float((bs <= 0).mean()):>13.4f}{m['dd']:>13.1f}"
              f"{np.median(dds):>9.1f}{np.percentile(dds,95):>9.1f}{np.percentile(dds,99):>9.1f}")
