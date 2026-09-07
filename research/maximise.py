"""Maximise profitability, using the levers that actually scale returns.

Four levers, in order of how much they add and how defensible they are:

  1. ENSEMBLE      run several timeframes at once instead of choosing one. Each is a separate
                   stream; partially correlated, so the sum has a better Sharpe than any leg.
  2. ADD V1        the IB retracement is near-zero-correlation with all of them.
  3. SIZE TO A DRAWDOWN BUDGET  1 contract is an arbitrary size. Scaling to a stated drawdown
                   tolerance is the single largest multiplier available and adds no new parameter.
  4. COMPOUND      re-size as equity grows, capped so a bad run cannot force liquidation.

Levers 1-3 do not require choosing anything new from the data, which is why they are preferred to
widening the grid. The true grid maximum is reported at the end for comparison.

Usage: python3 research/maximise.py
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research")
from best_versions import HDR, _naive_days, daily_from_trades, line, perf
from bos_choch import prep, run
from bos_report import sc

ANN = np.sqrt(252)


def leg(tf, md, cal):
    d = prep(tf)
    side, ti, to, pnl, gross, r, why, delay = run(
        minutes=tf, session="rth_0930_1600", min_ema_dist=md)
    return daily_from_trades(pnl, ti, d["df"].index, cal), len(pnl)


def main() -> None:
    ibd = pd.read_parquet("research/portfolio_daily.parquet")
    cal = _naive_days(pd.to_datetime(ibd.pop("ts")))
    ib = pd.Series(ibd["IB_retr"].to_numpy(float), index=cal)

    print("=" * 122)
    print("1. THE ENSEMBLE — stop choosing a timeframe, run them all")
    print("=" * 122 + "\n")
    legs = {}
    for tf, md in ((15, 1.0), (30, 1.0), (60, 0.0)):
        s, n = leg(tf, md, cal)
        legs[f"{tf}m"] = s
    print(HDR)
    for nm, s in legs.items():
        print(line(perf(s.to_numpy(), label=f"BOS {nm} alone")))
    ens = sum(legs.values())
    print(line(perf(ens.to_numpy(), label="ensemble 15m+30m+60m")))
    L = pd.DataFrame(legs)
    print("\n  correlation between legs:")
    print("      " + "".join(f"{c:>9}" for c in L.columns))
    for c in L.columns:
        print(f"  {c:<5}" + "".join(f"{L.corr().loc[c,o]:>9.2f}" for o in L.columns))

    print("\n" + "=" * 122)
    print("2. ADD THE IB RETRACEMENT — a fourth, near-uncorrelated stream")
    print("=" * 122 + "\n")
    book = ens + ib
    print(HDR)
    print(line(perf(ens.to_numpy(), label="ensemble (3 BOS legs)")))
    print(line(perf(book.to_numpy(), label="ensemble + IB (4 legs)")))
    print(f"\n  corr(ensemble, IB) = {np.corrcoef(ens.to_numpy(), ib.to_numpy())[0,1]:+.3f}")

    print("\n" + "=" * 122)
    print("3. SIZE TO A DRAWDOWN BUDGET — the largest multiplier, and it adds no parameter")
    print("=" * 122 + "\n")
    base = book.to_numpy()
    eq = np.cumsum(base)
    dd_frac = ((np.maximum.accumulate(eq) - eq).max()) / 100_000
    print(f"  1-contract-per-leg book: max drawdown {100*dd_frac:.1f}% of $100,000\n")
    print(f"  {'drawdown tolerance':<24}{'multiplier':>12}{'net $':>13}{'$/yr':>12}"
          f"{'maxDD $':>12}{'Sharpe':>9}")
    for tol in (0.10, 0.15, 0.20, 0.25, 0.30):
        mult = tol / dd_frac
        x = base * mult
        p = perf(x)
        print(f"  {f'{100*tol:.0f}% of $100k':<24}{mult:>12.2f}{x.sum():>13,.0f}"
              f"{x.sum()/(len(x)/252):>12,.0f}{p['maxdd_d']:>12,.0f}{p['sharpe']:>9.2f}")
    print("\n  Sharpe is unchanged by construction -- leverage moves return and risk together.")
    print("  This is the honest way to state 'more profit': it is a position-size decision,")
    print("  not a better signal.")

    print("\n" + "=" * 122)
    print("4. COMPOUNDING — re-size as equity grows")
    print("=" * 122 + "\n")
    print(f"  {'mode':<34}{'final equity':>15}{'CAGR':>9}{'maxDD%':>9}{'Sharpe':>9}")
    for tol, nm in ((0.15, "15% drawdown budget"), (0.25, "25% drawdown budget")):
        mult = tol / dd_frac
        for compound in (False, True):
            capital = 100_000.0
            e = capital
            path = [e]
            scale = mult
            for v in base:
                e += v * scale
                if compound:
                    scale = mult * max(e, 1) / capital
                path.append(e)
            path = np.array(path)
            pk = np.maximum.accumulate(path)
            mdd = ((pk - path) / pk).max()
            yrs = len(base) / 252
            cagr = (path[-1] / capital) ** (1 / yrs) - 1 if path[-1] > 0 else np.nan
            rets = np.diff(path) / path[:-1]
            sh = rets.mean() / rets.std() * ANN if rets.std() > 0 else np.nan
            tag = "compounded" if compound else "fixed size"
            print(f"  {nm + ', ' + tag:<34}{path[-1]:>15,.0f}{100*cagr:>8.1f}%{100*mdd:>8.1f}%{sh:>9.2f}")

    print("\n" + "=" * 122)
    print("5. THE TRUE GRID MAXIMUM, since you asked for it")
    print("=" * 122 + "\n")
    best = None
    cells = 0
    for tf in (15, 30, 60):
        for e in (50, 100, 150, 200, 250, 300):
            for m in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
                for kk in (2, 3, 5, 8):
                    for md in (0.0, 0.5, 1.0, 1.5, 2.0):
                        for nb in (1, 2, 3):
                            s = sc(tf, session="rth_0930_1600", ema_n=e, atr_mult=m, swing_k=kk,
                                   min_ema_dist=md, n_bos=nb)
                            cells += 1
                            if s.get("n", 0) >= 40 and (best is None or s["total"] > best[0]):
                                best = (s["total"], tf, e, m, kk, md, nb, s["n"], s["exp"],
                                        s["t"], s["sharpe"], s["maxdd"])
    if best:
        print(f"  {cells:,} cells evaluated")
        print(f"  MAXIMUM: {best[1]}m, EMA {best[2]}, ATR x{best[3]}, k={best[4]}, "
              f"filter {best[5]}, enter on BOS #{best[6]}")
        print(f"    ${best[0]:,.0f} over {best[7]} trades (${best[8]:,.0f}/trade), "
              f"t = {best[9]:.2f}, Sharpe {best[10]:.2f}, maxDD {100*best[11]:.1f}%")
        hurdle = np.sqrt(2 * np.log(cells))
        print(f"\n    E[max z] over {cells:,} cells = {hurdle:.2f}; this reaches {best[9]:.2f}"
              f" -> {'clears' if best[9] > hurdle else 'DOES NOT CLEAR'}")
        print(f"    Compare the 4-leg book: ${book.sum():,.0f} at Sharpe "
              f"{perf(book.to_numpy())['sharpe']:.2f} with no cell selected at all.")


if __name__ == "__main__":
    main()
