"""The last and most dangerous alternative: is the 60-minute result just long exposure to a rise?

WHAT DROP-ONE LEFT STANDING. Not V17's session-high filter -- on 8.5 years of US30 removing it
IMPROVES the rule (+0.2511 -> +0.2554, control p 0.005 -> 0.001) and on gold both filters hurt. What
survives is a Donchian 55 breakout on 60-minute bars with a 2.5xATR / 20-bar-channel stop and no
target, ADX-gated on the indices and better ungated on gold.

THE OBJECTION THAT HAS TO BE ANSWERED. US30 rose through most of 2016-2025 and gold rose through
most of 2004-2026. A long-only breakout with a trailing stop is a drift harvester, and a
minute-of-day matched control on 60-minute bars has only about seven distinct minutes to match on,
so it is close to an unconditional random entry -- a weak null against a rule whose real exposure
is DIRECTION. Three tests separate edge from drift:

  1. THE SHORT MIRROR. If the result is a breakout edge it should show something inverted; if it is
     drift the short side loses roughly what the long side wins.
  2. THE TREND SPLIT. Score long trades separately in the instrument's own rising and falling
     regimes, keyed on a 200-DAY trend known before the bar. Drift shows up as an edge that exists
     only in the up state.
  3. THE BLOCK SPLIT on the SIMPLIFIED rule, which has not been read out of sample yet.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
sys.path.insert(0, "research/v19")
import indicators as I       # noqa: E402
import v19frozen as F        # noqa: E402
import v19destroy as D       # noqa: E402
import v19scale as S         # noqa: E402

RNG = np.random.default_rng(20260828)
TF = 60
MKT = ["US30L", "US30", "XAU", "US100"]


def daily_trend_state(P, n=200):
    """Close above/below its own 200-DAY average, known strictly before the bar it labels."""
    ts = pd.to_datetime(P["ts"])
    day = pd.Series(P["c"], index=ts).resample("1D").last().dropna()
    ma = day.rolling(n).mean()
    up = (day > ma)
    # a bar is labelled by the last COMPLETED day
    known = day.index.to_numpy().astype("datetime64[ns]")
    pos = np.searchsorted(known, P["ts"].astype("datetime64[ns]"), side="left") - 1
    out = np.zeros(len(P["c"]), np.int8)
    ok = pos >= 0
    v = np.where(np.isfinite(ma.to_numpy()), up.to_numpy().astype(float), np.nan)
    out[ok] = np.nan_to_num(v[pos[ok]], nan=-1)
    lab = np.full(len(P["c"]), 0, np.int8)
    lab[ok] = np.where(np.isnan(v[pos[ok]]), 0, np.where(v[pos[ok]] > 0.5, 1, -1))
    return lab


if __name__ == "__main__":
    CT = {k: S.ctx_tf(k, TF) for k in MKT}
    fullm = {k: np.ones(len(CT[k]["c"]), bool) for k in MKT}

    print("=" * 116)
    print("1. THE SHORT MIRROR -- the identical rule, inverted")
    print("=" * 116)
    print(f"   {'market':<8}{'side':<7}{'n':>7}{'EV(R)':>9}{'PF':>8}{'net R':>9}{'Sharpe':>8}{'ctl p':>8}")
    for k in MKT:
        P = CT[k]
        for side, lab in ((1, "long"), (-1, "short")):
            O, i = F.run(P, side=side, use_level=(side > 0))
            m = F.metrics(P, O, i, fullm[k])
            print(f"   {k:<8}{lab:<7}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}"
                  f"{m['net']:>+9.1f}{m['sharpe']:>8.2f}", flush=True)
        print()
    print("   The level filter is long-only by construction, so the short row runs without it.")

    print("\n" + "=" * 116)
    print("2. THE TREND SPLIT -- long trades in the instrument's own rising vs falling 200-day state")
    print("=" * 116)
    print(f"   {'market':<8}{'state':<12}{'n':>7}{'EV(R)':>9}{'PF':>8}{'net R':>9}{'share of bars':>15}")
    for k in MKT:
        P = CT[k]
        lab = daily_trend_state(P)
        O, i = F.run(P, use_level=False)          # the simplified rule
        sig = O["sig"][i]
        st = lab[sig]
        for v, nm in ((1, "above 200d"), (-1, "below 200d")):
            r = O["R"][i][st == v]
            if len(r) < 10:
                continue
            w, lo = r[r > 0], r[r < 0]
            pf = w.sum() / abs(lo.sum()) if len(lo) and lo.sum() != 0 else np.nan
            print(f"   {k:<8}{nm:<12}{len(r):>7}{r.mean():>+9.4f}{pf:>8.3f}{r.sum():>+9.1f}"
                  f"{float((lab == v).mean()):>14.1%}")
        print()

    print("=" * 116)
    print("3. THE SIMPLIFIED RULE, READ OUT OF SAMPLE -- Donchian 55 + ADX>=25, 60m, no level filter")
    print("=" * 116)
    print("   The session-high filter is dropped because drop-one says it earns nothing. This is")
    print("   the first out-of-sample read of the SIMPLIFIED rule; the split is the first 65% of")
    print("   sessions, as everywhere else on this branch.\n")
    print(f"   {'market':<8}{'block':<10}{'n':>7}{'EV(R)':>9}{'PF':>8}{'net R':>9}{'maxDD':>8}"
          f"{'MAR':>7}{'Sharpe':>8}{'Sortino':>9}{'ctl p':>8}")
    for k in MKT:
        P = CT[k]
        res, lock = F.blocks(P)
        for bn, bb in (("research", res), ("LOCKED", lock)):
            O, i = F.run(P, block=bb, use_level=False)
            m = F.metrics(P, O, i, bb)
            ctl, p = D.control(P, bb, O, i, F.FROZEN["stop"], draws=800)
            print(f"   {k:<8}{bn:<10}{m['n']:>7}{m['ev']:>+9.4f}{m['pf']:>8.3f}{m['net']:>+9.1f}"
                  f"{m['dd']:>8.1f}{m['mar']:>7.2f}{m['sharpe']:>8.2f}{m['sortino']:>9.2f}{p:>8.3f}")
        print()
