"""
NAS100 backtest of the semivariance-asymmetry ("good vs bad volatility") signal.

Strategy source: Barunik, Kocenda, Vacha (SSRN 2815151), "Asymmetric volatility
connectedness on forex markets". The paper itself is a measurement paper, not a
trading-rule paper: it decomposes daily realized variance into a negative
semivariance RS- (volatility from down moves, "bad volatility") and a positive
semivariance RS+ (volatility from up moves, "good volatility"), computed from
intraday returns (Barndorff-Nielsen, Kinnebrock & Shephard 2010), and studies
the asymmetry SAM = RS+ - RS-.

Single-asset adaptation tested here: compute daily RS+ / RS- from 30-minute
returns, form the normalized asymmetry over a rolling window W,

    SAM_W(t) = (sum_W RS+ - sum_W RS-) / (sum_W RS+ + sum_W RS-),

and trade the next day close-to-close on its sign. Variants:

  momentum   : long if SAM_W > 0, short if SAM_W < 0  (good vol -> continuation)
  contrarian : the opposite sign (bad vol -> rebound, asymmetric-vol phenomenon)
  long/flat  : long if SAM_W > 0, flat otherwise

All signals use only information available at day t's close and earn day t+1's
close-to-close return, so there is no look-ahead. Costs are charged per unit of
turnover.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
DATA = HERE / "data" / "nas100_30m.csv"
OUT = HERE / "results"

COST_BPS_PER_SIDE = 2.0          # ~2 pt spread on a ~15k index CFD, rounded up
OOS_SPLIT = "2022-01-01"          # everything from here on is out-of-sample
TRADING_DAYS = 252


def load_daily_semivariances() -> pd.DataFrame:
    df = pd.read_csv(DATA, sep="\t")
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y.%m.%d %H:%M:%S")
    df = df.sort_values("DateTime").reset_index(drop=True)
    df["date"] = df["DateTime"].dt.normalize()

    # Intraday 30m log returns; the first bar of each day is open->close so the
    # overnight gap never enters the semivariances (it belongs to neither RS).
    r = np.log(df["Close"] / df["Close"].shift(1))
    first_bar = df["date"].ne(df["date"].shift(1))
    r[first_bar] = np.log(df["Close"] / df["Open"])[first_bar]
    df["r"] = r

    g = df.groupby("date")
    daily = pd.DataFrame({
        "close": g["Close"].last(),
        "rs_pos": g["r"].apply(lambda x: (x[x > 0] ** 2).sum()),
        "rs_neg": g["r"].apply(lambda x: (x[x < 0] ** 2).sum()),
        "n_bars": g.size(),
    })
    # Drop stub days (holidays / truncated sessions) where RS is unreliable.
    daily = daily[daily["n_bars"] >= 20].copy()
    daily["ret"] = np.log(daily["close"] / daily["close"].shift(1))
    return daily.dropna(subset=["ret"])


def sam(daily: pd.DataFrame, window: int) -> pd.Series:
    pos = daily["rs_pos"].rolling(window).sum()
    neg = daily["rs_neg"].rolling(window).sum()
    return (pos - neg) / (pos + neg)


def run(daily: pd.DataFrame, position: pd.Series) -> pd.DataFrame:
    """Positions decided at day t close, earning day t+1's return."""
    pos = position.shift(1).fillna(0.0)
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * COST_BPS_PER_SIDE / 1e4
    return pd.DataFrame({
        "pos": pos,
        "net": pos * daily["ret"] - cost,
        "turnover": turnover,
    })


def metrics(net: pd.Series) -> dict:
    eq = net.cumsum()
    dd = (eq - eq.cummax()).min()
    mu, sd = net.mean(), net.std()
    years = len(net) / TRADING_DAYS
    return {
        "total_ret_%": 100 * (np.exp(eq.iloc[-1]) - 1),
        "cagr_%": 100 * (np.exp(eq.iloc[-1] / years) - 1),
        "sharpe": mu / sd * np.sqrt(TRADING_DAYS) if sd > 0 else np.nan,
        "max_dd_%": 100 * (np.exp(dd) - 1),
        "hit_rate_%": 100 * (net[net != 0] > 0).mean(),
        "t_stat": mu / sd * np.sqrt(len(net)) if sd > 0 else np.nan,
    }


def main() -> None:
    OUT.mkdir(exist_ok=True)
    daily = load_daily_semivariances()
    print(f"{len(daily)} trading days: {daily.index[0]:%Y-%m-%d} -> {daily.index[-1]:%Y-%m-%d}\n")

    strategies: dict[str, pd.Series] = {}
    for w in (1, 5, 20):
        s = sam(daily, w)
        strategies[f"momentum W={w}"] = np.sign(s)
        strategies[f"contrarian W={w}"] = -np.sign(s)
        strategies[f"long/flat W={w}"] = (s > 0).astype(float)
    strategies["buy & hold"] = pd.Series(1.0, index=daily.index)

    rows, curves = [], {}
    for name, pos in strategies.items():
        res = run(daily, pos.fillna(0.0))
        curves[name] = res["net"].cumsum()
        full = metrics(res["net"])
        ins = metrics(res["net"][res.index < OOS_SPLIT])
        oos = metrics(res["net"][res.index >= OOS_SPLIT])
        rows.append({
            "strategy": name,
            **{k: round(v, 2) for k, v in full.items()},
            "IS_sharpe": round(ins["sharpe"], 2),
            "OOS_sharpe": round(oos["sharpe"], 2),
            "OOS_cagr_%": round(oos["cagr_%"], 2),
            "trades/yr": round(res["turnover"].sum() / 2 / (len(daily) / TRADING_DAYS), 0),
        })

    table = pd.DataFrame(rows).set_index("strategy")
    table.to_csv(OUT / "results.csv")
    print(table.to_string())

    plot(daily, curves)
    print(f"\nwrote {OUT / 'results.csv'} and {OUT / 'equity_curves.png'}")


def plot(daily: pd.DataFrame, curves: dict[str, pd.Series]) -> None:
    surface, grid, muted, ink = "#fcfcfb", "#e1e0d9", "#898781", "#0b0b0b"
    series = {                      # fixed categorical slot order
        "momentum W=1": "#2a78d6",
        "contrarian W=1": "#1baf7a",
        "long/flat W=1": "#eda100",
    }
    fig, ax = plt.subplots(figsize=(11, 6), dpi=150)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)

    bh = 100 * (np.exp(curves["buy & hold"]) - 1)
    ax.plot(bh.index, bh, color=muted, lw=2, ls=(0, (4, 3)), label="buy & hold")
    for name, color in series.items():
        eq = 100 * (np.exp(curves[name]) - 1)
        ax.plot(eq.index, eq, color=color, lw=2, label=name)
        ax.annotate(name, (eq.index[-1], eq.iloc[-1]), xytext=(6, 0),
                    textcoords="offset points", color=ink, fontsize=9, va="center")
    ax.annotate("buy & hold", (bh.index[-1], bh.iloc[-1]), xytext=(6, 0),
                textcoords="offset points", color=muted, fontsize=9, va="center")

    ax.axvline(pd.Timestamp(OOS_SPLIT), color=grid, lw=1)
    ax.annotate("out-of-sample →", (pd.Timestamp(OOS_SPLIT), ax.get_ylim()[1]),
                xytext=(6, -14), textcoords="offset points", color=muted, fontsize=9)
    ax.set_title("NAS100 — semivariance-asymmetry (SAM) strategies vs buy & hold, net of costs",
                 color=ink, fontsize=12, loc="left", pad=14)
    ax.set_ylabel("cumulative return (%)", color=muted, fontsize=9)
    ax.grid(axis="y", color=grid, lw=0.8)
    ax.tick_params(colors=muted, labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.legend(frameon=False, fontsize=9, labelcolor=ink, loc="upper left")
    ax.margins(x=0.10)
    fig.tight_layout()
    fig.savefig(OUT / "equity_curves.png", facecolor=surface)


if __name__ == "__main__":
    main()
