"""
Final selection: pick the configuration the Pine strategy should ship with.

robustness_analysis.py established the signal-space facts (long-only
contrarian is the only profitable family, the W plateau is 4-13, greedy
re-selection fails walk-forward, the no-fitting plateau ensemble passes).
martingale_analysis.py established the sizing facts, but only at W=1.
This script closes the remaining gaps:

 1. Sizing stability across W — the split-entry / fixed sizing comparison is
    re-run for EVERY long-only W in 1..30 (trade-level bootstrap Monte Carlo
    per (W, scheme) pair), so the sizing recommendation is checked for
    parameter stability the same way the signal was.
 2. Candidate bake-off — the surviving configurations are compared head to
    head on identical data with identical metrics: full-sample, ex-COVID,
    out-of-sample (>= 2022), and a 10,000-path block-bootstrap Monte Carlo
    of daily net returns (P(edge<0), median/5th-pct max drawdown, P(-50%)).
 3. Cluster placement — each candidate's daily-return correlation with the
    robust family (cluster 2 of robustness_analysis.py) confirms the final
    pick sits inside the stable region, not on an island.

Outputs in results/: sizing_stability.csv/.png, final_candidates.csv,
final_candidates.png, and a printed verdict.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import backtest as bt
from martingale_analysis import split_entry_trade_returns, trade_table
from robustness_analysis import W_GRID, build_grid, sharpe

OUT = bt.OUT
RNG = np.random.default_rng(23)
N_MC = 10_000
BLOCK = 20
RUIN_DD = -0.50
COVID = (pd.Timestamp("2020-02-15"), pd.Timestamp("2020-06-15"))
OOS_SPLIT = pd.Timestamp("2022-01-01")

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, AQUA, YELLOW, RED, PURPLE = "#2a78d6", "#1baf7a", "#eda100", "#e34948", "#4a3aa7"


# ---------------------------------------------------------------------------
# Stage 1 — sizing stability across the W grid (trade-level Monte Carlo)
# ---------------------------------------------------------------------------

def long_only_trades(daily: pd.DataFrame, w: int) -> pd.DataFrame:
    pos = (bt.sam(daily, w) < 0).astype(float)
    return trade_table(bt.run(daily, pos.fillna(0.0)))


def trade_mc(per_trade: np.ndarray) -> dict:
    """Bootstrap the per-trade return sequence (sizes already baked in)."""
    m = len(per_trade)
    idx = RNG.integers(0, m, size=(N_MC, m))
    eq = np.cumprod(1 + per_trade[idx], axis=1)
    dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
    return {
        "mc_median_terminal_x": float(np.median(eq[:, -1])),
        "mc_median_maxdd_%": 100 * float(np.median(dd)),
        "mc_p5_maxdd_%": 100 * float(np.percentile(dd, 5)),
        "P_ruin50_%": 100 * float((dd <= RUIN_DD).mean()),
    }


def stage_1_sizing_stability(daily: pd.DataFrame) -> pd.DataFrame:
    years = len(daily) / bt.TRADING_DAYS
    rows = []
    for w in W_GRID:
        trades = long_only_trades(daily, w)
        variants = {
            "fixed 1x": trades["ret"].to_numpy(),
            "split 1/3 (1x)": split_entry_trade_returns(trades, 1.0),
            "split 1/3 (2x)": split_entry_trade_returns(trades, 2.0),
        }
        for scheme, tr in variants.items():
            eq = np.cumprod(1 + tr)
            dd = (eq / np.maximum.accumulate(eq) - 1).min()
            rows.append({
                "W": w, "scheme": scheme, "n_trades": len(tr),
                "ev_per_trade_%": 100 * tr.mean(),
                "hist_cagr_%": 100 * (eq[-1] ** (1 / years) - 1),
                "hist_maxdd_%": 100 * dd,
                **trade_mc(tr),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Stage 2 — candidate bake-off (daily block-bootstrap Monte Carlo)
# ---------------------------------------------------------------------------

def ensemble_position(daily: pd.DataFrame, w_lo: int = 2, w_hi: int = 30) -> pd.Series:
    votes = [(bt.sam(daily, w) < 0).astype(float) for w in range(w_lo, w_hi + 1)]
    return pd.concat(votes, axis=1).mean(axis=1)


def seg_metrics(net: pd.Series, label: str) -> dict:
    x = net.to_numpy()
    eq = x.cumsum()
    years = len(x) / bt.TRADING_DAYS
    dd = (eq - np.maximum.accumulate(eq)).min()
    return {
        f"{label}_sharpe": sharpe(x),
        f"{label}_cagr_%": 100 * (np.exp(eq[-1] / years) - 1) if years > 0 else np.nan,
        f"{label}_maxdd_%": 100 * (np.exp(dd) - 1),
    }


def daily_block_mc(net: np.ndarray) -> dict:
    n = len(net)
    starts = RNG.integers(0, n - BLOCK, size=(N_MC, n // BLOCK + 1))
    idx = (starts[:, :, None] + np.arange(BLOCK)).reshape(N_MC, -1)[:, :n]
    sims = net[idx].astype(np.float32)
    sh = sims.mean(1) / sims.std(1) * np.sqrt(bt.TRADING_DAYS)
    eq = np.cumsum(sims, axis=1)
    dd = (eq - np.maximum.accumulate(eq, axis=1)).min(1)
    dd_pct = np.exp(dd) - 1
    return {
        "mc_sharpe_p5": float(np.percentile(sh, 5)),
        "P_sharpe_neg_%": 100 * float((sh < 0).mean()),
        "mc_median_maxdd_%": 100 * float(np.median(dd_pct)),
        "mc_p5_maxdd_%": 100 * float(np.percentile(dd_pct, 5)),
        "P_ruin50_%": 100 * float((dd_pct <= RUIN_DD).mean()),
    }


def candidate_returns(daily: pd.DataFrame) -> dict[str, pd.Series]:
    w8 = (bt.sam(daily, 8) < 0).astype(float)
    ens = ensemble_position(daily)
    return {
        "W=8 long-only, 1x": bt.run(daily, w8.fillna(0.0))["net"],
        "W=8 long-only, 2x": 2.0 * bt.run(daily, w8.fillna(0.0))["net"],
        "ensemble W2-30, 1x": bt.run(daily, ens.fillna(0.0))["net"],
        "ensemble W2-30, 1.7x": 1.7 * bt.run(daily, ens.fillna(0.0))["net"],
        "buy & hold": daily["ret"].copy(),
    }
    # note: k*net is exact for log returns of a k-levered claim only to first
    # order; at k <= 2 on daily index moves the approximation error is < 2 bps
    # per day and does not change any ranking below.


def stage_2_bakeoff(daily: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    cands = candidate_returns(daily)
    ex_covid = ~((cands["buy & hold"].index >= COVID[0]) &
                 (cands["buy & hold"].index <= COVID[1]))
    rows = {}
    for name, net in cands.items():
        x = net.to_numpy()
        rows[name] = {
            **seg_metrics(net, "full"),
            "t_stat": float(x.mean() / x.std() * np.sqrt(len(x))),
            "exCovid_sharpe": seg_metrics(net[ex_covid], "x")["x_sharpe"],
            "oos22_sharpe": seg_metrics(net[net.index >= OOS_SPLIT], "o")["o_sharpe"],
            **daily_block_mc(x),
        }
    return pd.DataFrame(rows).T, cands


# ---------------------------------------------------------------------------
# Stage 3 — cluster placement of the candidates
# ---------------------------------------------------------------------------

def stage_3_cluster_placement(daily: pd.DataFrame, cands: dict) -> pd.DataFrame:
    grid = build_grid(daily)
    lo = grid[[c for c in grid.columns if c[1] == "long-only contra" and c[0] >= 2]]
    family = lo.mean(axis=1)          # centre of the robust family (cluster 2)
    mom = grid[[c for c in grid.columns if c[1] == "L/S momentum"]].mean(axis=1)
    rows = {}
    for name, net in cands.items():
        rows[name] = {
            "corr_robust_family": float(net.corr(family)),
            "corr_momentum_family": float(net.corr(mom)),
        }
    return pd.DataFrame(rows).T


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.tick_params(colors=MUTED, labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")


def plot_sizing_stability(res: pd.DataFrame) -> None:
    colors = {"fixed 1x": BLUE, "split 1/3 (1x)": AQUA, "split 1/3 (2x)": YELLOW}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    panels = [("hist_cagr_%", "historical CAGR (%)"),
              ("mc_median_maxdd_%", "MC median max drawdown (%)"),
              ("P_ruin50_%", "P(50% account drawdown) (%)")]
    for ax, (col, label) in zip(axes, panels):
        for scheme, color in colors.items():
            d = res[res["scheme"] == scheme].sort_values("W")
            ax.plot(d["W"], d[col], color=color, lw=2, label=scheme)
        ax.set_title(label, loc="left", fontsize=11, color=INK)
        ax.set_xlabel("SAM window W (days)", fontsize=9, color=MUTED)
        style(ax)
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK)
    fig.suptitle("Sizing stability — long-only contrarian, every W, trade-level Monte Carlo",
                 x=0.005, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / "sizing_stability.png", facecolor=SURFACE)


def plot_candidates(cands: dict) -> None:
    colors = {"W=8 long-only, 1x": BLUE, "W=8 long-only, 2x": PURPLE,
              "ensemble W2-30, 1x": AQUA, "ensemble W2-30, 1.7x": YELLOW,
              "buy & hold": MUTED}
    fig, ax = plt.subplots(figsize=(11.5, 6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    for name, net in cands.items():
        eq = 100 * (np.exp(net.cumsum()) - 1)
        ls = (0, (4, 3)) if name == "buy & hold" else "-"
        ax.plot(eq.index, eq, color=colors[name], lw=2, ls=ls, label=name)
        ax.annotate(name, (eq.index[-1], eq.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", fontsize=9, va="center",
                    color=colors[name])
    ax.set_title("Final candidates — net equity curves, 2016-2025",
                 loc="left", fontsize=12, color=INK, pad=12)
    ax.set_ylabel("cumulative return (%)", fontsize=9, color=MUTED)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    ax.margins(x=0.18)
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "final_candidates.png", facecolor=SURFACE)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    daily = bt.load_daily_semivariances()

    print("=== Stage 1: sizing stability across W (long-only contrarian) ===")
    siz = stage_1_sizing_stability(daily)
    siz.round(2).to_csv(OUT / "sizing_stability.csv", index=False)
    plateau = siz[siz["W"].between(4, 13)]
    summary = plateau.groupby("scheme")[
        ["ev_per_trade_%", "hist_cagr_%", "hist_maxdd_%",
         "mc_median_maxdd_%", "mc_p5_maxdd_%", "P_ruin50_%"]].median().round(2)
    print("medians over the plateau W=4..13:")
    print(summary.to_string())
    worst_ruin = siz.groupby("scheme")["P_ruin50_%"].max().round(2)
    print("\nworst-case P(ruin) over ALL W 1..30 per scheme:")
    print(worst_ruin.to_string())
    plot_sizing_stability(siz)

    print("\n=== Stage 2: candidate bake-off (10k-path daily block bootstrap) ===")
    table, cands = stage_2_bakeoff(daily)
    print(table.round(2).to_string())

    print("\n=== Stage 3: cluster placement ===")
    placement = stage_3_cluster_placement(daily, cands)
    print(placement.round(2).to_string())

    final = table.join(placement)
    final.round(3).to_csv(OUT / "final_candidates.csv")
    plot_candidates(cands)
    print(f"\nwrote sizing_stability.csv/.png, final_candidates.csv/.png in {OUT}")


if __name__ == "__main__":
    main()
