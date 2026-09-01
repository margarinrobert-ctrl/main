"""Can the CMMA strategy be made to perform better -- honestly?

THE BAR, set before anything is run. `STUDY_CMMA.md` found that the component attribution INVERTS
between NQ and US100: on one feed the efficiency-ratio weighting is the whole strategy, on the
other it is a drag. So a change chosen on ONE feed is exactly the trap. A candidate here survives
only if it beats the as-briefed baseline IN-SAMPLE ON BOTH FEEDS; the holdout is read once, after,
for the survivors. Every candidate is counted as a trial on top of the 34 already spent.

THE CANDIDATES, declared up front and not extended afterwards:

  A  as briefed          08:00-15:45, tanh, KER, ewm(com=2)
  B  RTH start           09:30-15:45. `CLAUDE.md`: 07:00-09:30 is the worst part of the day on
                         all three indices, measured four separate times. The briefed window
                         starts inside it.
  C  strip the inert     no tanh, no EMA smoothing -- both measured as never helping on either
                         feed. KER kept, because it is the piece that inverts and stripping it
                         would be choosing a side.
  D  B + C
  E  vol-targeted        A, scaled by trailing-median ATR / today's ATR (clipped 0.25-4), so a
                         unit of signal is a unit of RISK rather than a unit of contracts.
  F  dead band           A, with |signal| below its own trailing 250-day median set to zero --
                         the smallest positions are the ones that round to nothing anyway.
  G  D + E

Costs, split, accounting and the Sharpe standard error are `cmma_core`/`cmma_test`'s, unchanged.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cmma_core as C            # noqa: E402
from cmma_test import stats, sharpe_se_annual   # noqa: E402

PRIOR_TRIALS = 34


def daily_atr_by_trade_date(d, n=5):
    """ATR at the daily label, mapped to the trading date the same way `signal` maps."""
    a = C.atr_wilder(d, n)
    a.index = (a.index - pd.Timedelta(days=1)).date
    return a


def vol_scale(d, sig, n=5, win=250, lo=0.25, hi=4.0):
    a = daily_atr_by_trade_date(d, n).reindex(sig.index)
    ref = a.rolling(win, min_periods=60).median().shift(1)
    k = (ref / a).clip(lo, hi)
    return (sig * k).dropna()


def dead_band(sig, win=250):
    thr = sig.abs().rolling(win, min_periods=60).median().shift(1)
    out = sig.where(sig.abs() >= thr, 0.0)
    return out.dropna()


CANDS = {
    "A  as briefed":        dict(sess=("08:00", "15:45"), kw={}, vol=False, band=False),
    "B  RTH start 09:30":   dict(sess=("09:30", "15:45"), kw={}, vol=False, band=False),
    "C  no tanh, no EMA":   dict(sess=("08:00", "15:45"), kw=dict(use_tanh=False, smooth=0),
                                 vol=False, band=False),
    "D  B + C":             dict(sess=("09:30", "15:45"), kw=dict(use_tanh=False, smooth=0),
                                 vol=False, band=False),
    "E  vol-targeted":      dict(sess=("08:00", "15:45"), kw={}, vol=True, band=False),
    "F  dead band":         dict(sess=("08:00", "15:45"), kw={}, vol=False, band=True),
    "G  D + E":             dict(sess=("09:30", "15:45"), kw=dict(use_tanh=False, smooth=0),
                                 vol=True, band=False),
}


def run(market):
    f = C.load_intraday(market)
    d = C.daily_from_intraday(f)
    px0 = float(d["close"].iloc[0])
    out = {}
    for name, c in CANDS.items():
        s = C.signal(d, **c["kw"])
        if c["vol"]:
            s = vol_scale(d, s)
        if c["band"]:
            s = dead_band(s)
        p = C.session_pnl(f, s, session=c["sess"], mode="endpoints")
        cut = C.split_at(p.index)
        IS = p.index < cut
        r = {}
        for bn, m in (("is", IS), ("ho", ~IS)):
            x = p["net"][m]
            st = stats(x, px0)
            w = x > 0
            r[bn] = dict(n=len(x), sharpe=st["sharpe"], se=sharpe_se_annual(st["sharpe"], len(x)),
                         pts=float(x.mean()),
                         pf=float(x[w].sum() / max(-x[~w].sum(), 1e-9)),
                         win=float(w.mean() * 100), dd=st["max_drawdown"] * 100,
                         turn=float(p["turn"][m].mean()))
        out[name] = r
    return out


def main():
    print("=" * 108)
    print("CAN THE CMMA STRATEGY PERFORM BETTER -- seven pre-declared candidates, two feeds")
    print("=" * 108)
    R = {}
    for mk in ("NQ", "US100L"):
        try:
            R[mk] = run(mk)
        except FileNotFoundError:
            print(f"  {mk}: feed not on disk -- skipped. A container recycle wipes the uploaded")
            print("  files; re-upload to run the two-feed agreement test, which is the point.")
    if len(R) < 2:
        print("  ONLY ONE FEED IS PRESENT. The table below is DESCRIPTIVE: nothing is selected on")
        print("  one feed, because that is exactly the trap STUDY_CMMA.md documents.")
    base = {mk: R[mk]["A  as briefed"] for mk in R}

    print("\n  IN-SAMPLE, net of costs.  A candidate survives only if it beats A on BOTH feeds.")
    print(f"  {'candidate':<22}" + "".join(
        f"{mk + ' Sharpe':>13}{'+-SE':>6}{'PF':>7}{'pts/d':>8}{'vs A':>7}"
        for mk in R) + f"{'survives':>10}")
    survivors = []
    for name in CANDS:
        row = f"  {name:<22}"
        ok = True
        for mk in R:
            r = R[mk][name]["is"]
            dlt = r["sharpe"] - base[mk]["is"]["sharpe"]
            ok &= dlt > 0 or name.startswith("A")
            row += (f"{r['sharpe']:>+13.2f}{r['se']:>6.2f}{r['pf']:>7.3f}"
                    f"{r['pts']:>+8.3f}{dlt:>+7.2f}")
        verdict = "base" if name.startswith("A") else ("yes" if ok and len(R) == 2 else
                                                         ("1 feed" if ok else "no"))
        row += f"{verdict:>10}"
        print(row)
        if ok and not name.startswith("A") and len(R) == 2:
            survivors.append(name)

    print(f"\n  survivors: {survivors if survivors else 'NONE'}")
    n_trials = PRIOR_TRIALS + len(CANDS) - 1
    print(f"  trials to date: {n_trials} ({PRIOR_TRIALS} from the parameter sweep + "
          f"{len(CANDS) - 1} candidates here)")

    print("\n  THE HOLDOUT, read once, for A and the survivors:")
    print(f"  {'candidate':<22}" + "".join(
        f"{mk + ' Sharpe':>13}{'+-SE':>6}{'PF':>7}{'pts/d':>8}{'win':>7}{'maxDD':>8}"
        for mk in R))
    for name in ["A  as briefed"] + survivors:
        row = f"  {name:<22}"
        for mk in R:
            r = R[mk][name]["ho"]
            row += (f"{r['sharpe']:>+13.2f}{r['se']:>6.2f}{r['pf']:>7.3f}{r['pts']:>+8.3f}"
                    f"{r['win']:>6.1f}%{r['dd']:>7.1f}%")
        print(row)

    import metrics as M
    for name in survivors:
        for mk in R:
            r = R[mk][name]["is"]
            dsr = M.deflated_sharpe_ratio(r["sharpe"], n_trials=n_trials, n_obs=r["n"],
                                          periods_per_year=252)
            print(f"  deflated Sharpe, {name.strip()} on {mk}: {dsr['deflated_sharpe']:.3f}  "
                  f"(expected best of {n_trials} random tries: "
                  f"{dsr['expected_max_sr_annualized']:.2f})")


if __name__ == "__main__":
    main()
