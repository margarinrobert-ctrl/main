"""What actually survived: the breakout as specified, on 30-minute bars, with no momentum filter.

The whole point of the study was to find a momentum indicator that improves a Donchian breakout.
It does not exist on this data. What the search produced instead is a measurement of the breakout
itself, and the configuration that holds its edge across both blocks is the one the request
already named -- entry 30, exit 20, market order, long side, on 30-minute bars.

This file is the confirmation run for that configuration and for the negative result beside it.
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "research")
sys.path.insert(0, "research/v16")
import v16core as C          # noqa: E402
import v16phase2 as P2       # noqa: E402

RNG = np.random.default_rng(20260827)
TF, EXIT_N, STOP, TP = 30, 20, 2.0, 0.0


def daily(P, O, idx):
    """Daily R keyed on the CALENDAR DAY of the signal bar. `sess` is an ordinal session index and
    grouping on it produces a series whose index is not a date -- which silently collapsed a
    quarterly breakdown into one bucket labelled 1970Q1."""
    day = np.asarray(P["ts"])[O["sig"][idx]].astype("datetime64[ns]").astype("datetime64[D]")
    return pd.Series(O["R"][idx]).groupby(day).sum()


def curve(P, O, idx, label):
    d = daily(P, O, idx)
    p = d.to_numpy(); eq = p.cumsum()
    dd = float((np.maximum.accumulate(eq) - eq).max())
    sh = float(p.mean() / p.std(ddof=1) * np.sqrt(252)) if p.std(ddof=1) > 0 else np.nan
    print(f"   {label:<26}{len(idx):>7} trades{len(d):>7} days{p.sum():>+9.1f}R"
          f"{sh:>8.2f} Sharpe{dd:>8.2f} maxDD{p.sum()/dd if dd > 0 else np.nan:>8.2f} ret/DD"
          f"{p.min():>+8.2f} worst day")
    return d


if __name__ == "__main__":
    P, pool, res, lock = P2.ctx(TF, exit_n=EXIT_N)

    print("=" * 108)
    print(f"THE SHIPPED CONFIGURATION -- Donchian {30}/{EXIT_N}, MARKET order at the next open, "
          f"long only, {TF}m")
    print("=" * 108)
    ds = {}
    for name, bb in (("RESEARCH", res), ("LOCKED", lock)):
        O, idx, s, _k = P2.leg(P, pool, 1, bb, None, 0, stop_mult=STOP, tp_r=TP)
        ds[name] = curve(P, O, idx, name)
        print(f"   {'':<26}{'':>7}       {'':>7}     PF {s['pf']:.3f}   "
              f"win {100*s['win']:.2f}%   R/trade {s['perR']:+.4f}")
    print("\n   The two blocks agree to within 0.01 R per trade. Nothing else in this study does.")

    print("\n   Against the MINUTE-OF-DAY matched control -- random entries, same side, same")
    print("   geometry, same time-of-day mix, 2,000 draws:")
    for name, bb in (("research", res), ("locked", lock)):
        s, ctl, p = P2.mod_control(P, pool, 1, bb, None, 0, draws=2000, stop_mult=STOP, tp_r=TP)
        print(f"      {name:<9} rule {s['R']:+7.1f}R   control median {np.median(ctl):+7.1f}R   "
              f"p95 {np.percentile(ctl, 95):+7.1f}R   p = {p:.4f}")

    print("\n" + "=" * 108)
    print("THE NEGATIVE RESULT, STATED AS A NUMBER -- what momentum does to this configuration")
    print("=" * 108)
    print(f"   {'filter':<26}{'research R/trade':>20}{'locked R/trade':>18}{'locked vs base':>17}")
    _O, _i, b_res, _k = P2.leg(P, pool, 1, res, None, 0, stop_mult=STOP, tp_r=TP)
    _O, _i, b_lock, _k = P2.leg(P, pool, 1, lock, None, 0, stop_mult=STOP, tp_r=TP)
    print(f"   {'none (shipped)':<26}{b_res['perR']:>+20.4f}{b_lock['perR']:>+18.4f}{0.0:>+17.4f}")
    for feat, off in (("tsmom40", 0.5), ("tsmom40", 1.0), ("roc40", 2.0), ("agree20_60", 1.0),
                      ("rsi14", 5.0), ("cmo21", 20.0), ("aroon7", 60.0), ("macd", 0.5),
                      ("emadist50", 0.5), ("slope50", 0.02)):
        _O, _i, sr, _k = P2.leg(P, pool, 1, res, feat, off, stop_mult=STOP, tp_r=TP)
        _O, _i, sl, _k = P2.leg(P, pool, 1, lock, feat, off, stop_mult=STOP, tp_r=TP)
        print(f"   {feat + '>=' + f'{off:g}':<26}{sr['perR']:>+20.4f}{sl['perR']:>+18.4f}"
              f"{sl['perR'] - b_lock['perR']:>+17.4f}")
    print("\n   Ten filters spanning every family in the pool. On the locked block not one of them")
    print("   adds a hundredth of an R per trade, and most subtract.")

    print("\n" + "=" * 108)
    print("STABILITY OF THE SHIPPED CONFIGURATION")
    print("=" * 108)
    allday = pd.concat([ds["RESEARCH"], ds["LOCKED"]]).sort_index()
    ix = pd.to_datetime(allday.index)
    q = allday.groupby(pd.PeriodIndex(ix, freq="Q")).sum()
    print("   quarter by quarter, R:")
    print("   " + "  ".join(f"{str(k)[-6:]}:{v:+.1f}" for k, v in q.items()))
    print(f"   positive quarters: {int((q > 0).sum())} of {len(q)}   worst {q.min():+.1f}R")
    p = ds["LOCKED"].to_numpy()
    dds = []
    for _ in range(20000):
        e = RNG.permutation(p).cumsum()
        dds.append(float((np.maximum.accumulate(e) - e).max()))
    dds = np.asarray(dds)
    eq = p.cumsum()
    print(f"\n   Monte Carlo on the locked daily series, 20,000 shuffles:")
    print(f"      realised maxDD {float((np.maximum.accumulate(eq)-eq).max()):.2f}R   "
          f"median {np.median(dds):.2f}   p95 {np.percentile(dds,95):.2f}   "
          f"p99 {np.percentile(dds,99):.2f}")
    bs = np.asarray([RNG.choice(p, len(p), replace=True).mean() for _ in range(20000)])
    print(f"   Bootstrap P(mean daily R <= 0) on locked = {float((bs <= 0).mean()):.3f}")


    print("\n" + "=" * 108)
    print("WHY MOMENTUM ADDS NOTHING: THE BREAKOUT HAS ALREADY SELECTED FOR IT")
    print("=" * 108)
    print("   A Donchian break IS a momentum event. If breakout bars already satisfy a momentum")
    print("   condition far more often than bars in general, the filter is mostly redundant with")
    print("   the trigger and can only remove trades, not information.\n")
    import v16mom as M
    poolm = M.build(P["b"])
    sig = C.signals(P, 1)
    sig = sig[res[sig]]
    allbars = np.flatnonzero(res & np.isfinite(P["atr"]) & (P["atr"] > 0))
    print(f"   {'condition':<20}{'share of ALL bars':>20}{'share of BREAKOUT bars':>25}{'lift':>8}")
    for feat, off in (("tsmom40", 0.5), ("tsmom40", 1.0), ("roc40", 2.0), ("agree20_60", 1.0),
                      ("rsi14", 5.0), ("cmo21", 20.0), ("aroon7", 60.0), ("emadist50", 0.5)):
        score, center, _o = poolm[feat]
        a = float(M.mask_for(score[allbars], center, off, 1).mean())
        b = float(M.mask_for(score[sig], center, off, 1).mean())
        print(f"   {feat + '>=' + f'{off:g}':<20}{a:>19.1%}{b:>24.1%}{b / max(a, 1e-9):>8.2f}x")
