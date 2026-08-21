"""
Futures adaptation: what whole-contract granularity does to each signal mode.

On a futures symbol you cannot hold 0.58 of a contract. The plateau ensemble's
edge comes from holding a GRADED position (vote share 0..1), so rounding it to
whole contracts is a real, measurable degradation - and the fewer contracts the
account can afford, the coarser the grid. The binary W=8 signal is unaffected
by rounding (it only ever wants 0 or full size).

This quantifies the trade-off so the futures Pine script can default correctly:
for each contract budget N (the max whole contracts at full size), the ensemble
holds floor(vote * N) / N of full size instead of vote.

Also reports the equity needed per budget on NQ (point value 20) and MNQ (2).
"""

import numpy as np
import pandas as pd

import backtest as bt
from final_selection import ensemble_position

BUDGETS = [1, 2, 3, 5, 8, 10, 20, 50, 100]
ANN = np.sqrt(bt.TRADING_DAYS)


def stats(net: pd.Series) -> dict:
    x = net.to_numpy()
    eq = x.cumsum()
    years = len(x) / bt.TRADING_DAYS
    dd = (eq - np.maximum.accumulate(eq)).min()
    return {
        "sharpe": x.mean() / x.std() * ANN,
        "cagr_%": 100 * (np.exp(eq[-1] / years) - 1),
        "maxdd_%": 100 * (np.exp(dd) - 1),
        "avg_exposure": None,
    }


def main() -> None:
    daily = bt.load_daily_semivariances()
    vote = ensemble_position(daily).fillna(0.0)
    binary = (bt.sam(daily, 8) < 0).astype(float).fillna(0.0)

    rows = []
    for n in BUDGETS:
        rounded_vote = np.floor(vote * n) / n
        rounded_bin = np.floor(binary * n) / n
        for name, pos in [("ensemble W2-30", rounded_vote), ("single W=8", rounded_bin)]:
            res = bt.run(daily, pos)
            s = stats(res["net"])
            rows.append({
                "contracts": n, "mode": name,
                "sharpe": round(s["sharpe"], 3),
                "cagr_%": round(s["cagr_%"], 2),
                "maxdd_%": round(s["maxdd_%"], 1),
                "avg_exposure": round(res["pos"].mean(), 3),
            })

    # continuous (fractional) reference
    for name, pos in [("ensemble W2-30", vote), ("single W=8", binary)]:
        res = bt.run(daily, pos)
        s = stats(res["net"])
        rows.append({
            "contracts": 9999, "mode": name,
            "sharpe": round(s["sharpe"], 3),
            "cagr_%": round(s["cagr_%"], 2),
            "maxdd_%": round(s["maxdd_%"], 1),
            "avg_exposure": round(res["pos"].mean(), 3),
        })

    df = pd.DataFrame(rows)
    pivot = df.pivot(index="contracts", columns="mode",
                     values=["sharpe", "cagr_%", "avg_exposure"])
    print("=== Effect of whole-contract rounding (contracts = max at full size) ===")
    print("(contracts 9999 = fractional / CFD reference)")
    print(pivot.to_string())

    print("\n=== Equity needed for each contract budget (index at 24,000) ===")
    px = 24_000
    for sym, pv in [("NQ  (E-mini, $20/pt)", 20), ("MNQ (Micro, $2/pt)", 2)]:
        needs = "  ".join(f"{n}c:${n * px * pv:,.0f}" for n in (1, 2, 5, 10, 20))
        print(f"{sym}: {needs}")

    df.to_csv(bt.OUT / "futures_granularity.csv", index=False)
    print(f"\nwrote {bt.OUT / 'futures_granularity.csv'}")


if __name__ == "__main__":
    main()
