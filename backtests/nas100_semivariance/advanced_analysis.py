"""
Deep-dive on the best variant from backtest.py: contrarian W=1
(long the day after bad volatility dominates, short after good volatility).

Adds:
  1. Advanced risk/return metrics (Sortino, Calmar, profit factor, VaR/CVaR,
     tail ratio, drawdown durations, skew/kurtosis) incl. an ex-COVID view.
  2. Harder benchmarks than buy & hold: 200d moving-average long/flat,
     12-month time-series momentum, and 10%-vol-targeted buy & hold —
     all net of the same 2 bps/side costs.
  3. Monte Carlo:
     a. Stationary block bootstrap (block ~20d, 10,000 paths) of the
        strategy's net daily returns -> distribution of terminal return,
        CAGR, Sharpe, max drawdown; P(loss).
     b. Permutation test: 10,000 random circular shifts of the position
        series against the same price path -> p-value of the realized
        Sharpe vs a timing-free null with identical exposure/turnover.
Outputs: results/advanced_metrics.csv, results/benchmarks.csv,
         results/monte_carlo.png, results/diagnostics.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import backtest as bt

OUT = bt.OUT
RNG = np.random.default_rng(42)
N_SIMS = 10_000
BLOCK = 20

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, AQUA, YELLOW, RED = "#2a78d6", "#1baf7a", "#eda100", "#e34948"


def advanced_metrics(net: pd.Series, pos: pd.Series) -> dict:
    eq = net.cumsum()
    dd = eq - eq.cummax()
    years = len(net) / bt.TRADING_DAYS
    cagr = np.exp(eq.iloc[-1] / years) - 1
    downside = net[net < 0]
    max_dd = np.exp(dd.min()) - 1
    in_dd = dd < 0
    dd_spells = (~in_dd).cumsum()[in_dd]
    wins, losses = net[net > 0], net[net < 0]
    return {
        "total_return_%": 100 * (np.exp(eq.iloc[-1]) - 1),
        "cagr_%": 100 * cagr,
        "ann_vol_%": 100 * net.std() * np.sqrt(bt.TRADING_DAYS),
        "sharpe": net.mean() / net.std() * np.sqrt(bt.TRADING_DAYS),
        "sortino": net.mean() / downside.std() * np.sqrt(bt.TRADING_DAYS),
        "calmar": cagr / abs(max_dd),
        "max_dd_%": 100 * max_dd,
        "longest_dd_days": int(dd_spells.value_counts().max()) if in_dd.any() else 0,
        "profit_factor": wins.sum() / abs(losses.sum()),
        "win_rate_%": 100 * (net[net != 0] > 0).mean(),
        "avg_win_avg_loss": wins.mean() / abs(losses.mean()),
        "skew": stats.skew(net),
        "excess_kurtosis": stats.kurtosis(net),
        "VaR95_daily_%": 100 * np.percentile(net, 5),
        "CVaR95_daily_%": 100 * net[net <= np.percentile(net, 5)].mean(),
        "tail_ratio": abs(np.percentile(net, 95) / np.percentile(net, 5)),
        "best_day_%": 100 * net.max(),
        "worst_day_%": 100 * net.min(),
        "exposure_%": 100 * (pos != 0).mean(),
        "monthly_win_rate_%": 100 * (net.resample("ME").sum() > 0).mean(),
    }


def build_benchmarks(daily: pd.DataFrame) -> dict[str, pd.Series]:
    """Position series (decided at close t), all run through bt.run()."""
    close = daily["close"]
    ma200 = (close > close.rolling(200).mean()).astype(float)
    tsmom = np.sign(close.pct_change(252))
    ann_vol = daily["ret"].rolling(20).std() * np.sqrt(bt.TRADING_DAYS)
    vol_target = (0.10 / ann_vol).clip(upper=1.0)
    return {
        "contrarian W=1": -np.sign(bt.sam(daily, 1)),
        "buy & hold": pd.Series(1.0, index=daily.index),
        "200d MA long/flat": ma200,
        "12m TS momentum": tsmom,
        "vol-target 10% B&H": vol_target,
    }


def block_bootstrap(net: np.ndarray) -> dict:
    """Stationary block bootstrap of daily net returns."""
    n = len(net)
    n_blocks = n // BLOCK + 1
    starts = RNG.integers(0, n - BLOCK, size=(N_SIMS, n_blocks))
    idx = (starts[:, :, None] + np.arange(BLOCK)[None, None, :]).reshape(N_SIMS, -1)[:, :n]
    sims = net[idx].astype(np.float32)

    eq = np.cumsum(sims, axis=1)
    terminal = np.exp(eq[:, -1]) - 1
    years = n / bt.TRADING_DAYS
    cagr = np.exp(eq[:, -1] / years) - 1
    sharpe = sims.mean(1) / sims.std(1) * np.sqrt(bt.TRADING_DAYS)
    max_dd = np.exp((eq - np.maximum.accumulate(eq, axis=1)).min(1)) - 1
    return {"eq": eq, "terminal": terminal, "cagr": cagr,
            "sharpe": sharpe, "max_dd": max_dd}


def permutation_test(daily: pd.DataFrame, pos: pd.Series) -> tuple[float, np.ndarray]:
    """Random circular shifts of the position series vs the same prices:
    keeps exposure, autocorrelation and turnover, destroys timing."""
    p = pos.shift(1).fillna(0.0).to_numpy()
    r = daily["ret"].to_numpy()
    cost = np.abs(np.diff(p, prepend=0.0)) * bt.COST_BPS_PER_SIDE / 1e4
    shifts = RNG.integers(60, len(p) - 60, size=N_SIMS)
    sharpes = np.empty(N_SIMS)
    for i, s in enumerate(shifts):
        ps = np.roll(p, s)
        netp = ps * r - cost  # cost identical by construction (roll preserves diffs)
        sharpes[i] = netp.mean() / netp.std() * np.sqrt(bt.TRADING_DAYS)
    net = p * r - cost
    actual = net.mean() / net.std() * np.sqrt(bt.TRADING_DAYS)
    p_value = (sharpes >= actual).mean()
    return p_value, sharpes


def plot_monte_carlo(mc: dict, actual_eq: pd.Series, p_value: float,
                     perm_sharpes: np.ndarray, actual_sharpe: float) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), dpi=150,
                             gridspec_kw={"width_ratios": [2, 1, 1]})
    fig.patch.set_facecolor(SURFACE)
    x = np.arange(mc["eq"].shape[1])
    pct = lambda q: 100 * (np.exp(np.percentile(mc["eq"], q, axis=0)) - 1)

    ax = axes[0]
    ax.fill_between(x, pct(5), pct(95), color=BLUE, alpha=0.15, lw=0)
    ax.fill_between(x, pct(25), pct(75), color=BLUE, alpha=0.30, lw=0)
    ax.plot(x, pct(50), color=BLUE, lw=2)
    ax.plot(x, 100 * (np.exp(actual_eq.to_numpy()) - 1), color=INK, lw=2)
    ax.annotate("realized", (x[-1], 100 * (np.exp(actual_eq.iloc[-1]) - 1)),
                xytext=(6, 8), textcoords="offset points", fontsize=9,
                va="center", color=INK)
    ax.annotate("median", (x[-1], pct(50)[-1]), xytext=(6, -8),
                textcoords="offset points", fontsize=9, va="center", color=BLUE)
    ax.annotate("5–95% and 25–75% bands", (x[len(x)//3], pct(95)[len(x)//3]),
                xytext=(0, 10), textcoords="offset points", fontsize=9, color=MUTED)
    ax.set_title("Block-bootstrap Monte Carlo — 10,000 resampled paths",
                 loc="left", fontsize=11, color=INK)
    ax.set_ylabel("cumulative return (%)", fontsize=9, color=MUTED)
    ax.set_xlabel("trading days", fontsize=9, color=MUTED)
    ax.margins(x=0.09)

    ax = axes[1]
    clip = np.percentile(100 * mc["terminal"], 99)
    ax.hist(np.minimum(100 * mc["terminal"], clip), bins=60, color=BLUE, alpha=0.85)
    ax.axvline(0, color=RED, lw=1.5)
    ax.axvline(100 * (np.exp(actual_eq.iloc[-1]) - 1), color=INK, lw=1.5)
    ax.annotate(f"P(loss) = {(mc['terminal'] < 0).mean():.1%}",
                (0.55, 0.92), xycoords="axes fraction", fontsize=10, color=INK)
    ax.set_title("Terminal return (%), clipped at p99", loc="left",
                 fontsize=11, color=INK)

    ax = axes[2]
    ax.hist(perm_sharpes, bins=60, color=MUTED, alpha=0.8)
    ax.axvline(actual_sharpe, color=INK, lw=1.5)
    ax.annotate(f"realized Sharpe {actual_sharpe:.2f}\np = {p_value:.3f}",
                (0.04, 0.86), xycoords="axes fraction", fontsize=10, color=INK)
    ax.set_title("Sharpe under random timing", loc="left", fontsize=11, color=INK)

    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.tick_params(colors=MUTED, labelsize=9)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
    fig.tight_layout()
    fig.savefig(OUT / "monte_carlo.png", facecolor=SURFACE)


def plot_diagnostics(net: pd.Series) -> None:
    eq = net.cumsum()
    dd = 100 * (np.exp(eq - eq.cummax()) - 1)
    roll_sharpe = net.rolling(252).mean() / net.rolling(252).std() * np.sqrt(252)

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), dpi=150, sharex=True)
    fig.patch.set_facecolor(SURFACE)
    ax = axes[0]
    ax.plot(roll_sharpe.index, roll_sharpe, color=BLUE, lw=2)
    ax.axhline(0, color="#c3c2b7", lw=1)
    ax.set_title("Contrarian W=1 — rolling 1-year Sharpe", loc="left",
                 fontsize=11, color=INK)
    ax = axes[1]
    ax.fill_between(dd.index, dd, 0, color=RED, alpha=0.35, lw=0)
    ax.plot(dd.index, dd, color=RED, lw=1.5)
    ax.set_title("Underwater curve (drawdown, %)", loc="left", fontsize=11, color=INK)

    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.tick_params(colors=MUTED, labelsize=9)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
    fig.tight_layout()
    fig.savefig(OUT / "diagnostics.png", facecolor=SURFACE)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    daily = bt.load_daily_semivariances()

    # --- benchmarks table -------------------------------------------------
    rows = {}
    results = {}
    for name, pos in build_benchmarks(daily).items():
        res = bt.run(daily, pos.fillna(0.0))
        results[name] = res
        rows[name] = advanced_metrics(res["net"], res["pos"])
    bench = pd.DataFrame(rows).round(2)
    bench.to_csv(OUT / "benchmarks.csv")
    print("=== Contrarian W=1 vs benchmarks (net of costs) ===")
    print(bench.to_string(), "\n")

    # --- ex-COVID view ----------------------------------------------------
    res = results["contrarian W=1"]
    covid = (res["net"].index >= "2020-02-15") & (res["net"].index <= "2020-06-30")
    ex = advanced_metrics(res["net"][~covid], res["pos"][~covid])
    full = rows["contrarian W=1"]
    pd.DataFrame({"full_sample": full, "ex_covid_window": ex}).round(2)\
        .to_csv(OUT / "advanced_metrics.csv")
    print("=== Contrarian W=1, ex Feb-Jun 2020 ===")
    print(f"CAGR {ex['cagr_%']:.1f}%  Sharpe {ex['sharpe']:.2f}  "
          f"Sortino {ex['sortino']:.2f}  Calmar {ex['calmar']:.2f}  "
          f"maxDD {ex['max_dd_%']:.1f}%\n")

    # --- Monte Carlo ------------------------------------------------------
    net = res["net"]
    mc = block_bootstrap(net.to_numpy())
    print("=== Block-bootstrap Monte Carlo (10,000 paths, block=20d) ===")
    for k in ("terminal", "cagr", "sharpe", "max_dd"):
        q = np.percentile(mc[k], [5, 25, 50, 75, 95])
        unit = "%" if k != "sharpe" else ""
        scale = 100 if k != "sharpe" else 1
        print(f"{k:>9}: p5 {scale*q[0]:7.1f}{unit}  p25 {scale*q[1]:7.1f}{unit}  "
              f"median {scale*q[2]:7.1f}{unit}  p75 {scale*q[3]:7.1f}{unit}  "
              f"p95 {scale*q[4]:7.1f}{unit}")
    print(f"P(terminal < 0) = {(mc['terminal'] < 0).mean():.1%}")
    print(f"P(Sharpe < 0)   = {(mc['sharpe'] < 0).mean():.1%}\n")

    pos = -np.sign(bt.sam(daily, 1)).fillna(0.0)
    p_value, perm_sharpes = permutation_test(daily, pos)
    actual_sharpe = full["sharpe"]
    print(f"=== Permutation test (10,000 circular shifts) ===")
    print(f"realized Sharpe {actual_sharpe:.2f} | null mean "
          f"{perm_sharpes.mean():.2f} | p-value {p_value:.3f}")

    plot_monte_carlo(mc, net.cumsum(), p_value, perm_sharpes, actual_sharpe)
    plot_diagnostics(net)
    print(f"\nwrote benchmarks.csv, advanced_metrics.csv, monte_carlo.png, "
          f"diagnostics.png in {OUT}")


if __name__ == "__main__":
    main()
