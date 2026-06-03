"""Charts + printed stats (Section 6 report.py). Uses a non-interactive
matplotlib backend so it works headless."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from . import CAVEATS  # noqa: E402

# dark palette echoing the HTML reference
_BG = "#0a0e14"
_SURF = "#121925"
_TXT = "#cdd9ea"
_MUT = "#6b7d96"
_TEAL = "#39c0c8"
_GRN = "#3fb950"
_AMB = "#d6a430"
_DIM = "#475568"
_REGCOL = {"trend": _GRN, "revert": _AMB, "random": _DIM, "na": None}


def _pct(x):
    return f"{'+' if x >= 0 else ''}{x*100:.1f}%"


def stats_table(res, period: str = "", label: str = "Fractal strategy") -> str:
    """Render the backtest stats table as text (Section 2.7)."""
    s, b = res.s, res.b
    rows = [
        ("Total return", _pct(s.total), _pct(b.total)),
        ("Annualized (CAGR)", _pct(s.cagr), _pct(b.cagr)),
        ("Volatility (ann.)", f"{s.vol*100:.1f}%", f"{b.vol*100:.1f}%"),
        ("Sharpe ratio", f"{s.sharpe:.2f}", f"{b.sharpe:.2f}"),
        ("Max drawdown", _pct(s.max_dd), _pct(b.max_dd)),
        ("Time in market", f"{res.exposure*100:.0f}%", "100%"),
        ("Trades", str(res.trades), "1"),
    ]
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(label), max(len(r[1]) for r in rows), 10)
    w2 = max(len("Buy & hold"), max(len(r[2]) for r in rows))
    lines = []
    if period:
        lines.append(period)
    lines.append(f"  (net of {res.cost_bps:.1f} bps/side costs)")
    header = f"{'Metric':<{w0}}  {label:>{w1}}  {'Buy & hold':>{w2}}"
    lines.append(header)
    lines.append("-" * len(header))
    for m, a, c in rows:
        lines.append(f"{m:<{w0}}  {a:>{w1}}  {c:>{w2}}")
    return "\n".join(lines)


def _style(ax):
    ax.set_facecolor(_SURF)
    for sp in ax.spines.values():
        sp.set_color(_DIM)
    ax.tick_params(colors=_MUT, labelsize=8)
    ax.grid(True, color="#1f2a3a", linewidth=0.6, alpha=0.6)


def save_charts(data: dict, sig: dict, res, out_dir: str,
                symbol: str = "") -> list[str]:
    """Save price+FRAMA+regime, Hurst, and equity-curve charts. Returns paths."""
    os.makedirs(out_dir, exist_ok=True)
    dates = np.asarray(data["date"])
    n = len(dates)
    x = np.arange(n)
    paths = []

    # 1) price + FRAMA + regime shading
    fig, ax = plt.subplots(figsize=(11, 4.2), facecolor=_BG)
    _style(ax)
    ax.plot(x, data["close"], color=_TXT, lw=1.1, label="Price")
    ax.plot(x, sig["fr"], color=_TEAL, lw=1.5, label="FRAMA")
    reg = sig["regime"]
    for r, col in _REGCOL.items():
        if col is None:
            continue
        mask = reg == r
        ax.fill_between(x, ax.get_ylim()[0], ax.get_ylim()[1], where=mask,
                        color=col, alpha=0.10, step="mid", linewidth=0)
    ax.set_title(f"{symbol}  Price · FRAMA · Regime", color=_TXT, fontsize=11)
    ax.legend(facecolor=_SURF, edgecolor=_DIM, labelcolor=_TXT, fontsize=8)
    _date_ticks(ax, dates, x)
    p = os.path.join(out_dir, "price_regime.png")
    fig.tight_layout(); fig.savefig(p, dpi=120, facecolor=_BG); plt.close(fig)
    paths.append(p)

    # 2) Hurst over time
    fig, ax = plt.subplots(figsize=(11, 3.2), facecolor=_BG)
    _style(ax)
    ax.plot(x, sig["H"], color=_TEAL, lw=1.4)
    ax.axhline(0.55, color=_GRN, ls="--", lw=0.9, alpha=0.7)
    ax.axhline(0.45, color=_AMB, ls="--", lw=0.9, alpha=0.7)
    ax.axhline(0.50, color=_DIM, ls="--", lw=0.8, alpha=0.6)
    ax.set_title("Hurst exponent over time", color=_TXT, fontsize=11)
    _date_ticks(ax, dates, x)
    p = os.path.join(out_dir, "hurst.png")
    fig.tight_layout(); fig.savefig(p, dpi=120, facecolor=_BG); plt.close(fig)
    paths.append(p)

    # 3) equity curve vs buy & hold
    fig, ax = plt.subplots(figsize=(11, 3.6), facecolor=_BG)
    _style(ax)
    ax.plot(x, res.eq_bh, color=_MUT, lw=1.2, label="Buy & hold")
    ax.plot(x, res.eq_strat, color=_TEAL, lw=1.7, label="Strategy")
    ax.set_title("Growth of $10,000", color=_TXT, fontsize=11)
    ax.legend(facecolor=_SURF, edgecolor=_DIM, labelcolor=_TXT, fontsize=8)
    _date_ticks(ax, dates, x)
    p = os.path.join(out_dir, "equity.png")
    fig.tight_layout(); fig.savefig(p, dpi=120, facecolor=_BG); plt.close(fig)
    paths.append(p)
    return paths


def save_equity(eq_strat, eq_bh, dates, out_path: str, title: str):
    """Standalone equity chart (used for walk-forward OOS curve)."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    x = np.arange(len(eq_strat))
    fig, ax = plt.subplots(figsize=(11, 3.6), facecolor=_BG)
    _style(ax)
    ax.plot(x, eq_bh, color=_MUT, lw=1.2, label="Buy & hold (OOS)")
    ax.plot(x, eq_strat, color=_TEAL, lw=1.7, label="Strategy (OOS)")
    ax.set_title(title, color=_TXT, fontsize=11)
    ax.legend(facecolor=_SURF, edgecolor=_DIM, labelcolor=_TXT, fontsize=8)
    _date_ticks(ax, np.asarray(dates), x)
    fig.tight_layout(); fig.savefig(out_path, dpi=120, facecolor=_BG)
    plt.close(fig)
    return out_path


def save_sweep(grid, hwins, framaNs, out_path: str):
    """Parameter-sweep Sharpe heatmap (Section 7.4)."""
    fig, ax = plt.subplots(figsize=(6, 5), facecolor=_BG)
    im = ax.imshow(grid, aspect="auto", origin="lower", cmap="viridis")
    ax.set_xticks(range(len(framaNs)), framaNs)
    ax.set_yticks(range(len(hwins)), hwins)
    ax.set_xlabel("FRAMA period", color=_TXT)
    ax.set_ylabel("Hurst window", color=_TXT)
    ax.set_title("Sharpe over param grid (overfit check)", color=_TXT,
                 fontsize=10)
    ax.tick_params(colors=_MUT)
    cb = fig.colorbar(im, ax=ax)
    cb.ax.tick_params(colors=_MUT)
    fig.tight_layout(); fig.savefig(out_path, dpi=120, facecolor=_BG)
    plt.close(fig)
    return out_path


def save_vol_forecast(real_vol, msm_path, garch_path, dates, out_path: str):
    """MSM vs GARCH vs realized conditional-vol chart."""
    x = np.arange(len(real_vol))
    fig, ax = plt.subplots(figsize=(11, 3.6), facecolor=_BG)
    _style(ax)
    ax.plot(x, np.asarray(real_vol) * 100, color=_MUT, lw=1.0,
            label="Realized (20d)")
    ax.plot(x, np.asarray(msm_path) * 100, color=_TEAL, lw=1.5, label="MSM")
    if garch_path is not None:
        gx = np.arange(len(garch_path))
        ax.plot(gx, np.asarray(garch_path) * 100, color=_AMB, lw=1.2,
                label="GARCH(1,1)")
    ax.set_title("Conditional volatility (annualized %)", color=_TXT,
                 fontsize=11)
    ax.legend(facecolor=_SURF, edgecolor=_DIM, labelcolor=_TXT, fontsize=8)
    _date_ticks(ax, np.asarray(dates), x)
    fig.tight_layout(); fig.savefig(out_path, dpi=120, facecolor=_BG)
    plt.close(fig)
    return out_path


def _date_ticks(ax, dates, x):
    if len(x) == 0:
        return
    idx = np.linspace(0, len(x) - 1, 5).astype(int)
    ax.set_xticks(x[idx])
    ax.set_xticklabels([str(dates[i])[:7] for i in idx])


def caveats_text() -> str:
    return "Caveats (read before trusting any of this):\n" + "\n".join(
        f"  - {c}" for c in CAVEATS)
