"""The test that decides it: a control matched on TREND STATE as well as minute of day.

WHERE THE EVIDENCE STANDS. The 60-minute Donchian 55 breakout earns +0.25 R on 8.5 years of US30,
+0.22 on the two-year US30 feed and +0.12 on 22 years of gold, is robust to 3x the assumed cost,
and beats a minute-of-day matched control at p 0.005-0.036. Three findings undercut it:

  * the SHORT MIRROR loses almost exactly what the long side wins (-0.165 against +0.251 on US30L,
    -0.272 against +0.218 on US30) -- the signature of directional exposure, not of a breakout edge;
  * the edge lives ENTIRELY ABOVE THE 200-DAY: US30L +0.2689 above against +0.0210 below, gold
    +0.2062 against -0.0464, US30 +0.1575 against -0.0544;
  * three of nine walk-forward years are negative, and they are 2019, 2021 and 2022.

A minute-of-day control on 60-minute bars has about seven distinct minutes to match on, so it is
close to an unconditional random entry -- it prices the CLOCK but not the DIRECTION. The honest null
for a rule that only works in an uptrend is a random entry drawn from the SAME uptrend bars. If the
breakout beats that, something survives beyond drift. If it does not, the strategy is long exposure
with a stop, and should be described that way.
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


def regime_control(P, O, idx, state, lab, stop, draws=1500):
    """Random entries matched on minute-of-day AND drawn only from bars in the same trend state."""
    if len(idx) < 15:
        return np.array([]), np.nan
    mod = P["mod"]
    want = pd.Series(mod[O["sig"][idx]]).value_counts()
    elig = np.flatnonzero((state == lab) & np.isfinite(P["atr"]) & (P["atr"] > 0))
    elig = elig[elig < len(P["c"]) - 2]
    by = {m: elig[mod[elig] == m] for m in want.index}
    if not any(len(v) for v in by.values()):
        return np.array([]), np.nan
    Oa = C.outcomes(P, 1, elig.astype(np.int64), stop_mult=stop, tp_r=0.0)
    pos = {v: i for i, v in enumerate(elig)}
    real = float(O["R"][idx].sum())
    tot = np.empty(draws)
    for d in range(draws):
        pick = np.concatenate([RNG.choice(by[m], size=min(k, len(by[m])), replace=False)
                               for m, k in want.items() if len(by[m])])
        keep = np.zeros(len(elig), bool)
        keep[[pos[v] for v in np.sort(pick)]] = True
        tot[d] = Oa["R"][C.take(Oa, keep)].sum()
    return tot, float((tot >= real).mean())


if __name__ == "__main__":
    print("=" * 116)
    print("THE REGIME-MATCHED CONTROL -- random entries from the SAME up-trend bars")
    print("=" * 116)
    print("   The rule is restricted to bars above the instrument's own 200-day average, which is")
    print("   where all of its return lives. The control is drawn from that same population.\n")
    print(f"   {'market':<8}{'n':>7}{'rule R':>10}{'ctl median':>12}{'ctl p95':>10}{'p':>8}"
          f"{'excess/trade':>14}   reading")
    for k in ("US30L", "US30", "XAU"):
        P = S.ctx_tf(k, TF)
        st = daily_trend_state(P)
        up = st == 1
        O, i = F.run(P, block=up, use_level=False)
        ctl, p = regime_control(P, O, i, st, 1, F.FROZEN["stop"])
        if not np.isfinite(p):
            continue
        r = float(O["R"][i].sum())
        exc = (r - float(np.median(ctl))) / max(len(i), 1)
        v = ("beats the regime" if p <= 0.05 else "marginal" if p <= 0.15
             else "NOT distinguishable from the regime")
        print(f"   {k:<8}{len(i):>7}{r:>+10.1f}{np.median(ctl):>+12.1f}"
              f"{np.percentile(ctl,95):>+10.1f}{p:>8.3f}{exc:>+14.4f}   {v}")

    print("\n" + "=" * 116)
    print("AND THE SAME QUESTION AS A BASELINE: what does simply being long in that state pay?")
    print("=" * 116)
    print("   Every eligible bar above the 200-day taken with the identical geometry -- no breakout,")
    print("   no ADX, no filter of any kind. If the rule cannot beat this it is the regime.\n")
    print(f"   {'market':<8}{'rule n':>8}{'rule EV':>10}{'baseline n':>12}{'baseline EV':>13}"
          f"{'rule - baseline':>17}")
    for k in ("US30L", "US30", "XAU"):
        P = S.ctx_tf(k, TF)
        st = daily_trend_state(P)
        up = st == 1
        O, i = F.run(P, block=up, use_level=False)
        m = F.metrics(P, O, i, up)
        elig = np.flatnonzero(up & np.isfinite(P["atr"]) & (P["atr"] > 0))
        elig = elig[elig < len(P["c"]) - 2]
        Ob = C.outcomes(P, 1, elig.astype(np.int64), stop_mult=F.FROZEN["stop"], tp_r=0.0)
        ib = C.take(Ob, np.ones(len(elig), bool))
        mb = F.metrics(P, Ob, ib, up)
        print(f"   {k:<8}{m['n']:>8}{m['ev']:>+10.4f}{mb['n']:>12}{mb['ev']:>+13.4f}"
              f"{m['ev'] - mb['ev']:>+17.4f}")
