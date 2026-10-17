"""
Can the walk-forward failure be fixed? robustness_analysis.py showed the
*signal* walks forward fine but greedy 6-monthly re-selection of the single
best (W, mode) collapses (OOS Sharpe 0.19, efficiency 0.16). This script
tests selection processes ranked by how much fitting they do:

  A greedy best-of-90     : the failing baseline (argmax trailing Sharpe).
  B plateau ensemble      : no per-fold fitting at all — equal-weight the
                            long-only contrarian sets W=2..30 every day.
  C smoothed selection    : within long-only, pick the W whose *neighbourhood*
                            (W +/- 2) trailing Sharpe is best — selects the
                            plateau, not the spike.
  D top-5 ensemble        : equal-weight the 5 best sets of all 90 by trailing
                            Sharpe — selection softened by averaging.
  E fixed W=8             : reference (chosen on the full sample, so its OOS
                            number is a benchmark, not a clean validation).

All evaluated on the identical out-of-sample days (fold = trailing 756d train,
126d test), net of costs. The less a method fits per fold, the more its OOS
number can be trusted — B is the only one with nothing to overfit.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import backtest as bt
from robustness_analysis import build_grid, sharpe, W_GRID, TRAIN, TEST

OUT = bt.OUT
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
COLORS = {"A greedy best-of-90": "#e34948", "B plateau ensemble": "#2a78d6",
          "C smoothed selection": "#1baf7a", "D top-5 ensemble": "#eda100",
          "E fixed W=8": "#4a3aa7", "buy & hold": MUTED}


def walk_forward(grid: pd.DataFrame, chooser) -> tuple[np.ndarray, list]:
    """chooser(train_matrix, keys) -> weight vector over the 90 columns."""
    X, keys, n = grid.to_numpy(), list(grid.columns), len(grid)
    oos = np.zeros(n)
    is_sharpes = []
    for start in range(TRAIN, n, TEST):
        w = chooser(X[start - TRAIN:start], keys)
        end = min(start + TEST, n)
        oos[start:end] = X[start:end] @ w
        is_sharpes.append(sharpe(X[start - TRAIN:start] @ w))
    return oos, is_sharpes


def main() -> None:
    daily = bt.load_daily_semivariances()
    grid = build_grid(daily)
    keys = list(grid.columns)
    lo_idx = {k[0]: j for j, k in enumerate(keys) if k[1] == "long-only contra"}

    def greedy(train, keys):
        sh = np.array([sharpe(train[:, j]) for j in range(len(keys))])
        w = np.zeros(len(keys)); w[int(np.nanargmax(sh))] = 1.0
        return w

    def plateau_ensemble(train, keys):
        w = np.zeros(len(keys))
        members = [lo_idx[x] for x in W_GRID if x >= 2]
        w[members] = 1.0 / len(members)
        return w

    def smoothed(train, keys):
        ws = sorted(lo_idx)
        sh = {x: sharpe(train[:, lo_idx[x]]) for x in ws}
        smooth = {x: np.mean([sh[y] for y in ws if abs(y - x) <= 2]) for x in ws}
        best = max(smooth, key=smooth.get)
        w = np.zeros(len(keys)); w[lo_idx[best]] = 1.0
        return w

    def top5(train, keys):
        sh = np.array([sharpe(train[:, j]) for j in range(len(keys))])
        w = np.zeros(len(keys)); w[np.argsort(sh)[-5:]] = 0.2
        return w

    def fixed_w8(train, keys):
        w = np.zeros(len(keys)); w[lo_idx[8]] = 1.0
        return w

    methods = {
        "A greedy best-of-90": greedy,
        "B plateau ensemble": plateau_ensemble,
        "C smoothed selection": smoothed,
        "D top-5 ensemble": top5,
        "E fixed W=8": fixed_w8,
    }

    n = len(grid)
    mask = np.zeros(n, dtype=bool); mask[TRAIN:] = True
    idx = grid.index[mask]
    bh = daily["ret"].reindex(grid.index).to_numpy()

    rows, curves = {}, {}
    for name, chooser in methods.items():
        oos, is_sh = walk_forward(grid, chooser)
        o = oos[mask]
        eq = o.cumsum()
        rows[name] = {
            "OOS_sharpe": round(sharpe(o), 2),
            "avg_IS_sharpe": round(float(np.mean(is_sh)), 2),
            "WF_efficiency": round(sharpe(o) / np.mean(is_sh), 2),
            "OOS_total_%": round(100 * (np.exp(eq[-1]) - 1), 0),
            "OOS_maxdd_%": round(100 * (np.exp((eq - np.maximum.accumulate(eq)).min()) - 1), 1),
        }
        curves[name] = pd.Series(eq, index=idx)
    rows["buy & hold"] = {
        "OOS_sharpe": round(sharpe(bh[mask]), 2), "avg_IS_sharpe": np.nan,
        "WF_efficiency": np.nan,
        "OOS_total_%": round(100 * (np.exp(bh[mask].sum()) - 1), 0),
        "OOS_maxdd_%": round(100 * (np.exp((bh[mask].cumsum() - np.maximum.accumulate(bh[mask].cumsum())).min()) - 1), 1),
    }
    curves["buy & hold"] = pd.Series(bh[mask].cumsum(), index=idx)

    table = pd.DataFrame(rows).T
    print("=== Walk-forward (identical OOS days, Oct 2019 - Oct 2025) ===")
    print(table.to_string())
    table.to_csv(OUT / "wf_optimization.csv")

    fig, ax = plt.subplots(figsize=(11.5, 6), dpi=150)
    fig.patch.set_facecolor(SURFACE); ax.set_facecolor(SURFACE)
    for name, eq in curves.items():
        pct = 100 * (np.exp(eq) - 1)
        ls = (0, (4, 3)) if name == "buy & hold" else "-"
        ax.plot(pct.index, pct, color=COLORS[name], lw=2, ls=ls, label=name)
        ax.annotate(name, (pct.index[-1], pct.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", fontsize=9, va="center",
                    color=COLORS[name])
    ax.set_title("Fixing the walk-forward: selection processes on identical "
                 "out-of-sample days (net of costs)", loc="left", fontsize=12,
                 color=INK, pad=12)
    ax.set_ylabel("cumulative OOS return (%)", fontsize=9, color=MUTED)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.tick_params(colors=MUTED, labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    ax.margins(x=0.16)
    fig.tight_layout()
    fig.savefig(OUT / "wf_optimization.png", facecolor=SURFACE)
    print(f"\nwrote wf_optimization.csv / wf_optimization.png in {OUT}")


if __name__ == "__main__":
    main()
