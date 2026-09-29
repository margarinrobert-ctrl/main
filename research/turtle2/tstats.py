"""The full metric suite the brief asks for, computed on a realised trade ledger.

Reported in the units each question is actually asked in: CAGR and drawdown in percent of equity,
expectancy in R and in dollars, concentration as the share of total profit carried by the top 1%,
5% and 10% of trades. Every one of these has caught something on this branch that profit factor
alone did not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANN = 252.0


def _streak(mask):
    best = cur = 0
    for x in mask:
        cur = cur + 1 if x else 0
        best = max(best, cur)
    return int(best)


def suite(df, start_equity=1_000_000.0, label=""):
    if df is None or len(df) == 0:
        return None
    d = df.sort_values("out_date").reset_index(drop=True)
    pnl = d["pnl"].to_numpy(float)
    eq = d["equity"].to_numpy(float)
    curve = np.r_[start_equity, eq]
    peak = np.maximum.accumulate(curve)
    dd = (peak - curve) / peak
    days = (pd.Timestamp(d["out_date"].iloc[-1]) - pd.Timestamp(d["in_date"].iloc[0])).days
    years = max(days / 365.25, 1e-9)
    total_ret = eq[-1] / start_equity
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]

    daily = d.groupby(pd.to_datetime(d["out_date"]).dt.date)["pnl"].sum()
    base = pd.Series(np.r_[start_equity, eq], index=range(len(eq) + 1))
    dret = daily.to_numpy() / start_equity
    sd = dret.std(ddof=1) if len(dret) > 1 else np.nan
    neg = dret[dret < 0]
    dsd = neg.std(ddof=1) if len(neg) > 1 else np.nan

    order = np.sort(pnl)[::-1]
    gross = pnl[pnl > 0].sum()
    conc = {}
    for q in (1, 5, 10):
        take = max(1, int(round(len(pnl) * q / 100)))
        conc[f"top{q}pct"] = float(order[:take].sum() / gross) if gross > 0 else np.nan

    yr = pd.to_datetime(d["out_date"]).dt.year
    by_year = d.groupby(yr)["pnl"].sum()

    lg, sh = d[d["dir"] == 1], d[d["dir"] == -1]
    return dict(
        label=label, n=len(d), years=round(years, 2),
        cagr_pct=100.0 * (total_ret ** (1 / years) - 1) if total_ret > 0 else -100.0,
        total_return_pct=100.0 * (total_ret - 1),
        max_dd_pct=100.0 * float(dd.max()),
        sharpe=float(dret.mean() / sd * np.sqrt(ANN)) if sd and sd > 0 else np.nan,
        sortino=float(dret.mean() / dsd * np.sqrt(ANN)) if dsd and dsd > 0 else np.nan,
        pf=float(gross / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
        expectancy_R=float(np.nanmean(d["R"])), expectancy_usd=float(pnl.mean()),
        win_pct=100.0 * float((pnl > 0).mean()),
        avg_win=float(wins.mean()) if len(wins) else np.nan,
        avg_loss=float(losses.mean()) if len(losses) else np.nan,
        win_loss_ratio=float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else np.nan,
        longest_losing_streak=_streak(pnl <= 0),
        long_n=len(lg), long_expR=float(np.nanmean(lg["R"])) if len(lg) else np.nan,
        long_pnl=float(lg["pnl"].sum()) if len(lg) else 0.0,
        short_n=len(sh), short_expR=float(np.nanmean(sh["R"])) if len(sh) else np.nan,
        short_pnl=float(sh["pnl"].sum()) if len(sh) else 0.0,
        profitable_years=int((by_year > 0).sum()), total_years=int(len(by_year)),
        ambiguous_pct=100.0 * float(d["amb"].mean()),
        **conc)


def show(s):
    if s is None:
        print("  (no trades)"); return
    print(f"  {'trades':<22}{s['n']:>12,}      {'win rate':<20}{s['win_pct']:>9.2f}%")
    print(f"  {'CAGR':<22}{s['cagr_pct']:>11.2f}%      {'total return':<20}{s['total_return_pct']:>9.1f}%")
    print(f"  {'max drawdown':<22}{s['max_dd_pct']:>11.2f}%      {'profit factor':<20}{s['pf']:>10.3f}")
    print(f"  {'Sharpe':<22}{s['sharpe']:>12.2f}      {'Sortino':<20}{s['sortino']:>10.2f}")
    print(f"  {'expectancy (R)':<22}{s['expectancy_R']:>12.4f}      {'expectancy ($)':<20}{s['expectancy_usd']:>10,.0f}")
    print(f"  {'avg win':<22}{s['avg_win']:>12,.0f}      {'avg loss':<20}{s['avg_loss']:>10,.0f}")
    print(f"  {'win/loss ratio':<22}{s['win_loss_ratio']:>12.2f}      {'longest losing run':<20}{s['longest_losing_streak']:>10}")
    print(f"  {'long':<10}{s['long_n']:>5} trades  E[R] {s['long_expR']:>+7.3f}   "
          f"{'short':<8}{s['short_n']:>5} trades  E[R] {s['short_expR']:>+7.3f}")
    print(f"  {'profitable years':<22}{s['profitable_years']:>5} / {s['total_years']:<6}"
          f"      {'intrabar ambiguous':<20}{s['ambiguous_pct']:>9.2f}%")
    print(f"  {'top 1% of trades':<22}{100*s['top1pct']:>11.1f}%      "
          f"{'top 5% / top 10%':<20}{100*s['top5pct']:>9.1f}% / {100*s['top10pct']:.1f}%")
