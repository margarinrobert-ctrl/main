"""Figures for the Turtle timeframe / candlestick study.

Four questions, four figures, one series per mark and no dual axes.  Colours are fixed to the
entity, never to the rank: `carried` is always blue and `matched` always orange, so a panel that
changes which one wins does not change which one is which.
"""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

C_CARRIED = "#2a78d6"        # categorical slot 1
C_MATCHED = "#eb6834"        # categorical slot 2
C_THIRD   = "#1baf7a"        # categorical slot 3
INK       = "#0b0b0b"
INK2      = "#52514e"
GRID      = dict(alpha=0.25, lw=0.7, color="#b8b7b2")

plt.rcParams.update({"font.size": 9, "axes.labelcolor": INK2, "text.color": INK,
                     "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": "#c9c8c3", "axes.titlesize": 10,
                     "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb",
                     "savefig.facecolor": "#fcfcfb"})


def _tidy(ax, title=None, xlabel=None, ylabel=None):
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.grid(True, **GRID)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=INK, loc="left")
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)


# ------------------------------------------------------------------ 1. timeframe
def fig_timeframe():
    df = pd.read_csv(f"{HERE}/c2_timeframe.csv")
    df["totA"] = df.pctA * df.nA
    df["totB"] = df.pctB * df.nB
    fig, ax = plt.subplots(1, 3, figsize=(15.5, 4.6))

    for k, (col, blk) in enumerate((("pctA", "research"), ("pctB", "locked"))):
        g = df.groupby(["mode", "tf"])[col].mean().unstack(0)
        ax[k].axhline(0, color=INK2, lw=1.0)
        ax[k].plot(g.index, g["carried"], "o-", lw=2, ms=8, color=C_CARRIED,
                   label="carried (bar counts)")
        ax[k].plot(g.index, g["matched"], "s-", lw=2, ms=8, color=C_MATCHED,
                   label="matched (reach held constant)")
        tfs = sorted(df.tf.unique())
        ax[k].set_xscale("log")
        ax[k].set_xticks(tfs)
        ax[k].set_xticks([], minor=True)
        ax[k].get_xaxis().set_major_formatter(matplotlib.ticker.FixedFormatter(
            [str(t) for t in tfs]))
        _tidy(ax[k], f"Per-trade edge, {blk} block", "chart timeframe (minutes)",
              "% of entry price per trade" if k == 0 else None)
        lo, hi = ax[k].get_ylim()
        ax[k].set_ylim(lo - (hi - lo) * 0.22, hi + (hi - lo) * 0.06)
        ax[k].legend(frameon=False, fontsize=8.5, loc="lower center", ncol=2)
    ax[0].annotate("at 240m the two readings\ncoincide by construction", (240, 0.037),
                   fontsize=7.5, color=INK2, ha="right",
                   textcoords="offset points", xytext=(-10, 10))

    sub = df[df.tf != 240].copy()
    sub["cell"] = sub.mkt + " " + sub.tf.astype(str) + "m"
    order = (sub[["mkt", "tf", "cell"]].drop_duplicates()
             .sort_values(["mkt", "tf"], ascending=[False, False])["cell"].tolist())
    w = sub.pivot_table(index="cell", columns="mode", values="totA").reindex(order)
    y = np.arange(len(w))
    ax[2].barh(y - 0.19, w["carried"], 0.36, color=C_CARRIED, label="carried")
    ax[2].barh(y + 0.19, w["matched"], 0.36, color=C_MATCHED, label="matched")
    ax[2].axvline(0, color=INK2, lw=1.0)
    ax[2].set_yticks(y)
    ax[2].set_yticklabels(w.index, fontsize=8)
    _tidy(ax[2], "Total return, research block", "cumulative % of entry price, 1 unit/trade")
    ax[2].legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.suptitle("A bar count is not a setting: the same preset on a faster chart keeps its numbers "
                 "and loses its reach", fontsize=11.5, x=0.008, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(f"{HERE}/fig1_timeframe.png", dpi=150)
    plt.close(fig)


# ------------------------------------------------------------------ 2. availability
def fig_availability():
    df = pd.read_csv(f"{HERE}/c0_structure.csv")
    pats = [c for c in df.columns if c.startswith(("p1.", "p2.", "p3."))]
    rate = df[pats].mean().sort_values()
    br = pd.read_csv(f"{HERE}/c1_baserates.csv").set_index("feat")

    fig, ax = plt.subplots(1, 2, figsize=(15.0, 6.4),
                           gridspec_kw=dict(width_ratios=[1.25, 1]))
    y = np.arange(len(rate))
    ax[0].barh(y, rate.values * 100, 0.72, color=C_CARRIED)
    ax[0].axvspan(0, 5, color="#e34948", alpha=0.10, lw=0)
    ax[0].axvline(5, color="#e34948", lw=1.2, ls="--")
    ax[0].text(5.6, len(rate) * 0.52, "under 5%:\ncannot support a test",
               color="#a02b2b", fontsize=8.5, va="center")
    ax[0].set_yticks(y)
    ax[0].set_yticklabels([k.split(".", 1)[1] for k in rate.index], fontsize=8)
    for i, (k, v) in enumerate(rate.items()):
        if v <= 0.001:
            ax[0].text(0.35, i, "never fires", va="center", fontsize=7.5, color="#a02b2b")
    _tidy(ax[0], "How often each pattern fires ON A BREAKOUT BAR",
          "% of the trigger's own signal bars")
    ax[0].set_xlim(0, 24)

    fam = {"shp.": "continuous shape", "seq.": "sequence",
           "p1.": "1-bar pattern", "p2.": "2-bar", "p3.": "3-bar"}
    col = {"continuous shape": C_MATCHED, "sequence": C_THIRD,
           "1-bar pattern": C_CARRIED, "2-bar": C_CARRIED, "3-bar": C_CARRIED}
    seen = set()
    for k, r in br.iterrows():
        f = fam[k.split(".")[0] + "."]
        lab = "discrete pattern" if f.endswith(("pattern", "bar")) else f
        ax[1].scatter(r.on_pop * 100, r.on_signal * 100, s=42, alpha=0.85,
                      color=col[f], edgecolor="#fcfcfb", lw=0.8,
                      label=lab if lab not in seen else None)
        seen.add(lab)
    lim = 100
    ax[1].plot([0, lim], [0, lim], color=INK2, lw=1.0, ls="--")
    ax[1].text(52, 47, "no lift over the population", color=INK2, fontsize=8, rotation=38)
    ax[1].axhline(95, color="#a02b2b", lw=1.2, ls=":")
    ax[1].text(2, 96, "above 95% = the trigger restated  (no candlestick pattern reaches it)",
               color="#a02b2b", fontsize=8)
    for k in ("seq.bull_share_10", "seq.up_closes_5", "shp.close_vs_prev_hi"):
        r = br.loc[k]
        ax[1].annotate(k.split(".", 1)[1], (r.on_pop * 100, r.on_signal * 100), fontsize=7.5,
                       color=INK2, textcoords="offset points", xytext=(6, -3))
    _tidy(ax[1], "Signal-bar rate against population rate, NQ 240m research",
          "% of all eligible bars", "% of the trigger's own signal bars")
    ax[1].set_xlim(0, 100)
    ax[1].set_ylim(0, 103)
    ax[1].legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.suptitle("A breakout bar does not restate a candlestick pattern -- it makes most of them "
                 "impossible", fontsize=11.5, x=0.008, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(f"{HERE}/fig2_availability.png", dpi=150)
    plt.close(fig)


# ------------------------------------------------------------------ 3. the screen
def fig_screen():
    df = pd.read_csv(f"{HERE}/c3_screen.csv")
    df["note"] = df["note"].fillna("")
    s = df[df.note == ""].copy()
    fig, ax = plt.subplots(1, 2, figsize=(13.0, 4.8))

    ax[0].scatter(s.mde, np.abs(s.delta), s=44, color=C_CARRIED, alpha=0.85,
                  edgecolor="#fcfcfb", lw=0.8)
    top = max(s.mde.max(), np.abs(s.delta).max()) * 1.08
    ax[0].plot([0, top], [0, top], color="#a02b2b", lw=1.4, ls="--")
    ax[0].text(top * 0.52, top * 0.60, "detectable above this line", color="#a02b2b",
               fontsize=8.5, rotation=34)
    ax[0].set_xlim(0, top)
    ax[0].set_ylim(0, top)
    _tidy(ax[0], f"Every one of the {len(s)} arms is inside its own MDE",
          "minimum detectable effect (% of entry price / trade)",
          "|effect vs the unfiltered base|")

    edges = np.linspace(0, 1, 21)
    ax[1].hist(s.p.dropna(), bins=edges, color=C_CARRIED, alpha=0.9)
    ax[1].axhline(len(s) / 20, color=INK2, lw=1.4, ls="--")
    ax[1].text(0.98, len(s) / 20 + 0.30, "uniform -- what a pool with nothing in it looks like",
               color=INK2, fontsize=8.5, ha="right")
    ax[1].set_ylim(0, max(np.histogram(s.p.dropna(), bins=edges)[0]) * 1.28)
    ax[1].axvline(0.05, color="#a02b2b", lw=1.2)
    ax[1].text(0.062, ax[1].get_ylim()[1] * 0.82,
               f"{int((s.p <= 0.05).sum())} arms clear p<=0.05\n{0.05*len(s):.1f} expected by chance",
               color="#a02b2b", fontsize=8.5, va="top")
    _tidy(ax[1], "Control p-values across the pool", "p against a same-selectivity random gate",
          "arms")
    fig.suptitle("Gate 2: candlestick vetoes on US100L 30m matched, 216 research trades",
                 fontsize=11.5, x=0.008, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(f"{HERE}/fig3_screen.png", dpi=150)
    plt.close(fig)


# ------------------------------------------------------------------ 4. monte carlo
def fig_mc():
    df = pd.read_csv(f"{HERE}/c5_mc.csv")
    z = np.load(f"{HERE}/c5_draws.npz")
    key = "US100L|30|{}|A|{}"
    fig, ax = plt.subplots(1, 4, figsize=(19.0, 4.4))

    for mode, c in (("carried", C_CARRIED), ("matched", C_MATCHED)):
        k = key.format(mode, "boot")
        if k in z:
            ax[0].hist(z[k], bins=48, alpha=0.72, color=c, label=mode)
    ax[0].axvline(0, color="#a02b2b", lw=1.4)
    _tidy(ax[0], "EDGE -- day-block bootstrap", "% of entry price per trade", "draws")
    ax[0].legend(frameon=False, fontsize=8.5)

    k = key.format("matched", "perm")
    if k in z:
        ax[1].hist(z[k], bins=48, color=C_MATCHED, alpha=0.9)
        row = df[(df.mkt == "US100L") & (df.tf == 30) & (df["mode"] == "matched")
                 & (df.block == "A")]
        if len(row):
            r = row.iloc[0]
            ax[1].axvline(r.dd, color=INK, lw=1.6)
            ax[1].text(r.dd, ax[1].get_ylim()[1] * 0.94, f"  realised ({r.dd_pctile:.0%} pctile)",
                       fontsize=8.5, color=INK, va="top")
            ax[1].axvline(r.dd_p99, color="#a02b2b", lw=1.4, ls="--")
            ax[1].text(r.dd_p99, ax[1].get_ylim()[1] * 0.60,
                       f"  p99 = {r.dd_p99/r.dd:.2f}x realised", fontsize=8.5, color="#a02b2b",
                       va="top")
    _tidy(ax[1], "PATH -- permutation of the same trades", "max drawdown, % of entry price",
          "draws")

    for j, (nm, title, xl) in enumerate((("exec_tot", "EXECUTION -- round turn U(0.5x, 2x)",
                                          "total % of entry price"),
                                         ("jit_tot", "DATA -- price jitter, indicators recomputed",
                                          "total % of entry price"))):
        a = ax[2 + j]
        for mode, c in (("carried", C_CARRIED), ("matched", C_MATCHED)):
            k = key.format(mode, nm)
            if k in z:
                a.hist(z[k], bins=34, alpha=0.72, color=c, label=mode)
        a.axvline(0, color="#a02b2b", lw=1.4)
        _tidy(a, title, xl, "draws" if j == 0 else None)
        a.legend(frameon=False, fontsize=8.5)

    fig.suptitle("Four Monte Carlos on US100L 30m, research block -- they answer four different "
                 "questions and are kept apart", fontsize=11.5, x=0.006, ha="left", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(f"{HERE}/fig4_montecarlo.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    which = sys.argv[1:] or ["tf", "avail", "screen", "mc"]
    if "tf" in which:
        fig_timeframe(); print("fig1_timeframe.png")
    if "avail" in which:
        fig_availability(); print("fig2_availability.png")
    if "screen" in which:
        fig_screen(); print("fig3_screen.png")
    if "mc" in which:
        fig_mc(); print("fig4_montecarlo.png")
