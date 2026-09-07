"""The best defensible versions, and what combining them does.

"Most profitable combination" is the thing this project has measured as harmful three separate
times: best-of-K landed at the 9th to 23rd percentile of out-of-sample outcomes across searches of
225,792, 2,400 and 400,226 configurations. So these versions are NOT the argmax of a grid. Each
component was kept only because it replicated -- across halves, across studies, or against a control
-- and the in-sample maximum is reported beside the defensible choice so the gap is visible.

  V1  IB retracement           the one configuration whose bootstrap CI excludes zero
  V2  BOS/CHoCH 30m + range filter   the best surviving cell of the BOS battery
  V3  V1 + V2 as a two-strategy book

Usage: python3 research/best_versions.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from bos_choch import SPECS, prep, run
from bos_report import sc
from nqdata import session_index

ANN = np.sqrt(252)


def perf(x, capital=100_000.0, label=""):
    x = np.asarray(x, float)
    nz = x[x != 0]
    eq = capital + np.cumsum(x)
    pk = np.maximum.accumulate(eq)
    dd = (pk - eq) / pk
    yrs = len(x) / 252
    down = x[x < 0]
    return dict(
        label=label, total=x.sum(), per_yr=x.sum() / yrs, n=len(nz),
        sharpe=(x.mean() / x.std() * ANN if x.std() > 0 else np.nan),
        sortino=(x.mean() / down.std() * ANN if len(down) > 1 and down.std() > 0 else np.nan),
        maxdd=dd.max(), maxdd_d=(pk - eq).max(),
        calmar=((eq[-1] / capital) ** (1 / yrs) - 1) / dd.max() if dd.max() > 0 and eq[-1] > 0 else np.nan,
        pf=(x[x > 0].sum() / -x[x < 0].sum() if (x < 0).any() else np.inf),
        per_trade=(nz.sum() / len(nz) if len(nz) else np.nan))


HDR = (f"  {'version':<38}{'net $':>11}{'$/yr':>10}{'trades':>8}{'$/trade':>10}{'PF':>7}"
       f"{'Sharpe':>8}{'Sortino':>9}{'Calmar':>8}{'maxDD%':>8}{'maxDD $':>10}")


def line(p):
    f = lambda v, d=2: ("nan" if not np.isfinite(v) else f"{v:.{d}f}")
    return (f"  {p['label']:<38}{p['total']:>11,.0f}{p['per_yr']:>10,.0f}{p['n']:>8,}"
            f"{p['per_trade']:>10,.0f}{f(p['pf']):>7}{f(p['sharpe']):>8}{f(p['sortino']):>9}"
            f"{f(p['calmar']):>8}{100*p['maxdd']:>8.1f}{p['maxdd_d']:>10,.0f}")


def _naive_days(idx) -> pd.DatetimeIndex:
    """Calendar day, timezone stripped.

    The parquet round-trip drops the tz, so a tz-aware bar index and a tz-naive calendar never
    compare equal and every reindex silently returns zeros. Both sides are normalised here.
    """
    di = pd.DatetimeIndex(idx)
    if di.tz is not None:
        di = di.tz_localize(None)
    return di.normalize()


def daily_from_trades(pnl, ti, index, all_days_index):
    s = pd.Series(pnl, index=_naive_days(index[ti])).groupby(level=0).sum()
    return s.reindex(all_days_index, fill_value=0.0)


def vol_size(x, lookback=60, cap=3.0):
    sd = pd.Series(x).rolling(lookback).std().shift(1)
    target = pd.Series(x).expanding().std().shift(1)
    lev = (target / sd).clip(upper=cap).fillna(0.0).to_numpy()
    return x * lev, lev


def main() -> None:
    # ---- shared daily calendar ----
    ibd = pd.read_parquet("research/portfolio_daily.parquet")
    cal = _naive_days(pd.to_datetime(ibd.pop("ts")))
    ib = pd.Series(ibd["IB_retr"].to_numpy(float), index=cal)

    # ---- V2: BOS/CHoCH 30m + range filter ----
    d30 = prep(30)
    side, ti, to, pnl, gross, r, why, delay = run(
        minutes=30, session="rth_0930_1600", min_ema_dist=1.0)
    bos = daily_from_trades(pnl, ti, d30["df"].index, cal)

    print("=" * 120)
    print("THE BEST DEFENSIBLE VERSIONS")
    print("=" * 120)
    print("\n  Every figure is net of $19-24 per round turn. 765 sessions, Dec 2022 - Dec 2025, NQ.\n")
    print(HDR)
    p_ib = perf(ib.to_numpy(), label="V1  IB retracement (validated)")
    p_bos = perf(bos.to_numpy(), label="V2  BOS/CHoCH 30m + range filter")
    print(line(p_ib))
    print(line(p_bos))

    # ---- V3: the book ----
    for w_name, w in (("equal $", (1.0, 1.0)),
                      ("inverse-vol", (1.0 / ib.std(), 1.0 / bos.std()))):
        k = np.array(w) / np.array(w).sum() * 2          # keep gross exposure ~2 units
        comb = ib.to_numpy() * k[0] + bos.to_numpy() * k[1]
        print(line(perf(comb, label=f"V3  book ({w_name})")))

    comb = ib.to_numpy() + bos.to_numpy()
    scaled, lev = vol_size(comb)
    print(line(perf(scaled, label="V3  book + volatility sizing")))

    print("\n  Correlation of daily P&L between V1 and V2: "
          f"{np.corrcoef(ib.to_numpy(), bos.to_numpy())[0,1]:+.3f}")
    both = (ib != 0) & (bos != 0)
    print(f"  Sessions where both trade: {both.sum()} of {len(ib)} "
          f"({100*both.mean():.1f}%) -- they rarely overlap, which is why the book helps.")

    # ---- MNQ translation ----
    print("\n" + "=" * 120)
    print("MNQ TRANSLATION — the only contract that expresses these at retail risk")
    print("=" * 120 + "\n")
    print(HDR)
    for nm, ser, scale in (("V1 on MNQ (1 contract)", ib, 0.1),
                           ("V2 on MNQ (1 contract)", bos, 0.1),
                           ("V3 book on MNQ (1+1)", ib + bos, 0.1)):
        print(line(perf(ser.to_numpy() * scale, capital=10_000.0, label=nm)))
    print("\n  MNQ is 1/10th of NQ, so both P&L and drawdown scale by 0.1 and the capital base")
    print("  above is $10,000 rather than $100,000.")

    # ---- the honest comparison: defensible vs in-sample maximum ----
    print("\n" + "=" * 120)
    print("WHAT THE IN-SAMPLE MAXIMUM WOULD HAVE BEEN, AND WHY IT IS NOT THE ANSWER")
    print("=" * 120 + "\n")
    best = None
    for e in (50, 100, 150, 200, 250, 300):
        for m in (1.0, 1.5, 2.0, 3.0, 4.0):
            for kk in (2, 3, 5):
                for md in (0.0, 0.5, 1.0, 1.5, 2.0):
                    s = sc(30, session="rth_0930_1600", ema_n=e, atr_mult=m, swing_k=kk,
                           min_ema_dist=md)
                    if s.get("n", 0) >= 40 and (best is None or s["total"] > best[0]):
                        best = (s["total"], e, m, kk, md, s["n"], s["exp"], s["t"], s["sharpe"])
    if best:
        print(f"  best of 450 cells: EMA {best[1]}, ATR x{best[2]}, k={best[3]}, "
              f"range filter {best[4]} ATR")
        print(f"    ${best[0]:,.0f} over {best[5]} trades (${best[6]:,.0f}/trade), "
              f"t = {best[7]:.2f}, Sharpe {best[8]:.2f}")
        print(f"  V2 as specified above:  ${p_bos['total']:,.0f}, Sharpe {p_bos['sharpe']:.2f}")
        print(f"\n  A best-of-450 search draws E[max z] ~ {np.sqrt(2*np.log(450)):.2f} from noise")
        print(f"  alone; the winner reaches t = {best[7]:.2f}. That is why V2 is the pre-specified")
        print("  cell (EMA 200, 2xATR, k=3, 1 ATR filter) and not the argmax.")


if __name__ == "__main__":
    main()
