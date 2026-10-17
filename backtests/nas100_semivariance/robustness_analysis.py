"""
Robustness study of the SAM strategy's parameter space (the inputs exposed in
SemivarianceContrarian.pine): W in 1..30 x mode in {long-only contrarian,
long/short contrarian, long/short momentum} = 90 parameter sets, all at fixed
1x sizing (sizing reshapes the distribution, it can't rescue a bad signal).

 1. Parameter stability  — full-sample Sharpe for every set + a plateau check:
    each W's Sharpe vs the mean of its W+/-2 neighbours. A robust optimum sits
    on a plateau; a lucky one is a spike.
 2. Monte Carlo per set  — 2,000-path block bootstrap (20d blocks) of each
    set's net daily returns: median/5th-pct Sharpe, P(Sharpe<0), P(-50% DD).
 3. Cluster analysis     — hierarchical clustering (average linkage) on the
    correlation matrix of the 90 daily-return streams; does the chosen config
    live in a family of similar performers or alone?
 4. Walk-forward         — every 126 trading days, pick the best set by Sharpe
    on the trailing 756 days, trade it for the next 126 out-of-sample; compare
    the stitched OOS curve vs always-W=1-long-only and buy & hold, and report
    walk-forward efficiency (OOS Sharpe / IS Sharpe of the picks).

Outputs in results/: param_grid.csv, clusters.csv, walk_forward.csv,
param_stability.png, cluster_heatmap.png, walk_forward.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster import hierarchy

import backtest as bt

OUT = bt.OUT
RNG = np.random.default_rng(11)
W_GRID = list(range(1, 31))
MODES = ["long-only contra", "L/S contrarian", "L/S momentum"]
N_MC = 2_000
BLOCK = 20
TRAIN, TEST = 756, 126           # 3y train, 6m test
ANN = np.sqrt(bt.TRADING_DAYS)

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#898781", "#e1e0d9", "#fcfcfb"
BLUE, AQUA, YELLOW, RED = "#2a78d6", "#1baf7a", "#eda100", "#e34948"
MODE_COLOR = dict(zip(MODES, [BLUE, AQUA, YELLOW]))


def sharpe(x: np.ndarray) -> float:
    sd = x.std()
    return float(x.mean() / sd * ANN) if sd > 0 else np.nan


def build_grid(daily: pd.DataFrame) -> pd.DataFrame:
    """Net daily returns for all 90 parameter sets, one column per set."""
    cols = {}
    for w in W_GRID:
        s = bt.sam(daily, w)
        for mode in MODES:
            pos = (s < 0).astype(float) if mode == "long-only contra" else \
                  -np.sign(s) if mode == "L/S contrarian" else np.sign(s)
            cols[(w, mode)] = bt.run(daily, pos.fillna(0.0))["net"]
    return pd.DataFrame(cols)


def mc_per_set(net: np.ndarray) -> dict:
    n = len(net)
    starts = RNG.integers(0, n - BLOCK, size=(N_MC, n // BLOCK + 1))
    idx = (starts[:, :, None] + np.arange(BLOCK)).reshape(N_MC, -1)[:, :n]
    sims = net[idx].astype(np.float32)
    sh = sims.mean(1) / sims.std(1) * ANN
    eq = np.cumsum(sims, axis=1)
    dd = (eq - np.maximum.accumulate(eq, axis=1)).min(1)
    return {
        "mc_sharpe_med": np.median(sh),
        "mc_sharpe_p5": np.percentile(sh, 5),
        "P_sharpe_neg_%": 100 * (sh < 0).mean(),
        "P_ruin50_%": 100 * (np.exp(dd) - 1 <= -0.50).mean(),
    }


def stage_1_2(grid: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (w, mode), net in grid.items():
        x = net.to_numpy()
        eq = x.cumsum()
        row = {
            "W": w, "mode": mode,
            "sharpe": sharpe(x),
            "cagr_%": 100 * (np.exp(eq[-1] / (len(x) / bt.TRADING_DAYS)) - 1),
            "max_dd_%": 100 * (np.exp((eq - np.maximum.accumulate(eq)).min()) - 1),
            **mc_per_set(x),
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    # plateau check: Sharpe vs mean of the W+/-2 neighbourhood within the mode
    for mode in MODES:
        m = df["mode"] == mode
        s = df.loc[m].set_index("W")["sharpe"]
        neigh = (s.rolling(5, center=True, min_periods=3).sum() - s) / \
                (s.rolling(5, center=True, min_periods=3).count() - 1)
        df.loc[m, "neighbour_sharpe"] = neigh.to_numpy()
    df["spike"] = df["sharpe"] - df["neighbour_sharpe"]
    return df


def stage_3_clusters(grid: pd.DataFrame, res: pd.DataFrame, n_clusters: int = 5):
    corr = grid.corr().to_numpy()
    dist = 1 - corr
    link = hierarchy.linkage(dist[np.triu_indices_from(dist, 1)], method="average")
    labels = hierarchy.fcluster(link, n_clusters, criterion="maxclust")
    res = res.copy()
    res["cluster"] = labels
    order = hierarchy.leaves_list(link)
    return res, corr, order, labels


def stage_4_walk_forward(grid: pd.DataFrame):
    n = len(grid)
    keys = list(grid.columns)
    X = grid.to_numpy()
    picks, oos = [], np.zeros(n)
    is_sharpes = []
    for start in range(TRAIN, n, TEST):
        train = X[start - TRAIN:start]
        sh = np.array([sharpe(train[:, j]) for j in range(len(keys))])
        best = int(np.nanargmax(sh))
        end = min(start + TEST, n)
        oos[start:end] = X[start:end, best]
        is_sharpes.append(sh[best])
        picks.append({"date": grid.index[start], "W": keys[best][0],
                      "mode": keys[best][1], "train_sharpe": sh[best]})
    mask = np.zeros(n, dtype=bool)
    mask[TRAIN:] = True
    return pd.DataFrame(picks), oos, mask, float(np.mean(is_sharpes))


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


def plot_stability(res: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), dpi=150, sharey=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, mode in zip(axes, MODES):
        d = res[res["mode"] == mode].sort_values("W")
        ax.fill_between(d["W"], d["mc_sharpe_p5"],
                        2 * d["mc_sharpe_med"] - d["mc_sharpe_p5"],
                        color=MODE_COLOR[mode], alpha=0.15, lw=0)
        ax.plot(d["W"], d["sharpe"], color=MODE_COLOR[mode], lw=2)
        ax.axhline(0, color="#c3c2b7", lw=1)
        ax.set_title(mode, loc="left", fontsize=11, color=INK)
        ax.set_xlabel("SAM window W (days)", fontsize=9, color=MUTED)
        style(ax)
    axes[0].set_ylabel("Sharpe (net)", fontsize=9, color=MUTED)
    axes[0].annotate("band: bootstrap 5–95%", (0.35, 0.06),
                     xycoords="axes fraction", fontsize=9, color=MUTED)
    fig.suptitle("Parameter stability — full-sample Sharpe across the W grid",
                 x=0.005, ha="left", fontsize=12, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(OUT / "param_stability.png", facecolor=SURFACE)


def plot_clusters(corr: np.ndarray, order: np.ndarray, labels: np.ndarray,
                  keys: list) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 8), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    im = ax.imshow(corr[np.ix_(order, order)], cmap="RdBu", vmin=-1, vmax=1)
    # cluster boundaries
    lab_sorted = labels[order]
    bounds = np.where(np.diff(lab_sorted) != 0)[0] + 0.5
    for b in bounds:
        ax.axhline(b, color=INK, lw=1)
        ax.axvline(b, color=INK, lw=1)
    ticks, names = [], []
    for c in np.unique(lab_sorted):
        idxs = np.where(lab_sorted == c)[0]
        ticks.append(idxs.mean())
        members = [keys[order[i]] for i in idxs]
        ws = sorted(m[0] for m in members)
        names.append(f"C{c}: {members[0][1]}\nW {ws[0]}–{ws[-1]}")
    ax.set_xticks([]), ax.set_yticks(ticks)
    ax.set_yticklabels(names, fontsize=8, color=INK)
    ax.set_title("Daily-return correlation of all 90 parameter sets, "
                 "ordered by cluster", loc="left", fontsize=11, color=INK, pad=12)
    cb = fig.colorbar(im, ax=ax, shrink=0.7)
    cb.ax.tick_params(colors=MUTED, labelsize=8)
    cb.set_label("correlation", color=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "cluster_heatmap.png", facecolor=SURFACE)


def plot_walk_forward(grid: pd.DataFrame, oos: np.ndarray, mask: np.ndarray,
                      picks: pd.DataFrame, daily: pd.DataFrame) -> None:
    idx = grid.index[mask]
    wf = pd.Series(oos[mask], index=idx).cumsum()
    fixed = grid[(1, "long-only contra")][mask].cumsum()
    bh = daily["ret"].reindex(grid.index)[mask].cumsum()

    fig, axes = plt.subplots(2, 1, figsize=(11, 7.5), dpi=150, sharex=True,
                             gridspec_kw={"height_ratios": [3, 1]})
    fig.patch.set_facecolor(SURFACE)
    ax = axes[0]
    for series, color, label in [(bh, MUTED, "buy & hold"),
                                 (fixed, BLUE, "fixed W=1 long-only"),
                                 (wf, YELLOW, "walk-forward re-selected")]:
        eq = 100 * (np.exp(series) - 1)
        ls = (0, (4, 3)) if label == "buy & hold" else "-"
        ax.plot(eq.index, eq, color=color, lw=2, ls=ls, label=label)
        ax.annotate(label, (eq.index[-1], eq.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", fontsize=9, va="center",
                    color=color if color != MUTED else MUTED)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK, loc="upper left")
    ax.set_title("Walk-forward (re-pick best params every 6m on trailing 3y) — "
                 "out-of-sample only", loc="left", fontsize=11, color=INK)
    ax.set_ylabel("cumulative return (%)", fontsize=9, color=MUTED)
    ax.margins(x=0.12)
    style(ax)

    ax = axes[1]
    ax.step(picks["date"], picks["W"], where="post", color=INK, lw=1.5)
    for mode in picks["mode"].unique():
        d = picks[picks["mode"] == mode]
        ax.scatter(d["date"], d["W"], color=MODE_COLOR[mode], s=28, zorder=3,
                   label=mode)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK, ncol=3, loc="upper left")
    ax.set_ylabel("chosen W", fontsize=9, color=MUTED)
    ax.set_title("Parameters selected at each re-fit", loc="left",
                 fontsize=10, color=INK)
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "walk_forward.png", facecolor=SURFACE)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    daily = bt.load_daily_semivariances()
    grid = build_grid(daily)
    keys = list(grid.columns)
    print(f"grid: {len(keys)} parameter sets x {len(grid)} days\n")

    # stages 1+2
    res = stage_1_2(grid)
    # stage 3
    res, corr, order, labels = stage_3_clusters(grid, res)
    res.to_csv(OUT / "param_grid.csv", index=False)

    print("=== Top 10 by full-sample Sharpe ===")
    top = res.nlargest(10, "sharpe")
    print(top[["W", "mode", "sharpe", "cagr_%", "max_dd_%", "mc_sharpe_p5",
               "P_sharpe_neg_%", "spike", "cluster"]].round(2).to_string(index=False))

    print("\n=== Share of profitable sets per mode (Sharpe > 0) ===")
    print(res.groupby("mode")["sharpe"].agg(
        n="size", positive=lambda s: (s > 0).sum(),
        median="median", max="max").round(2).to_string())

    print("\n=== Clusters ===")
    cl = res.groupby("cluster").agg(
        n=("sharpe", "size"),
        modes=("mode", lambda m: "/".join(sorted(set(m)))),
        W_range=("W", lambda w: f"{w.min()}-{w.max()}"),
        med_sharpe=("sharpe", "median"),
        med_P_ruin=("P_ruin50_%", "median")).round(2)
    print(cl.to_string())
    cl.to_csv(OUT / "clusters.csv")

    # stage 4
    picks, oos, mask, is_sh = stage_4_walk_forward(grid)
    oos_sh = sharpe(oos[mask])
    picks.to_csv(OUT / "walk_forward.csv", index=False)
    fixed_sh = sharpe(grid[(1, "long-only contra")].to_numpy()[mask])
    bh_sh = sharpe(daily["ret"].reindex(grid.index).to_numpy()[mask])
    print(f"\n=== Walk-forward ({len(picks)} refits, {mask.sum()} OOS days) ===")
    print(picks.to_string(index=False))
    print(f"\nWF OOS Sharpe {oos_sh:.2f} | avg IS Sharpe of picks {is_sh:.2f} "
          f"| WF efficiency {oos_sh / is_sh:.2f}")
    print(f"fixed W=1 long-only on same OOS days: Sharpe {fixed_sh:.2f}")
    print(f"buy & hold on same OOS days:          Sharpe {bh_sh:.2f}")

    plot_stability(res)
    plot_clusters(corr, order, labels, keys)
    plot_walk_forward(grid, oos, mask, picks, daily)
    print(f"\nwrote param_grid.csv, clusters.csv, walk_forward.csv + 3 charts in {OUT}")


if __name__ == "__main__":
    main()
