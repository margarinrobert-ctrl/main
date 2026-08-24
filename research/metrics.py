"""Every performance metric the brief asks for, a constraint system, and one composite score.

The composite exists because the brief's central instruction is that win rate must not be
allowed to drive the decision. Two mechanisms enforce that here:

  * the score is built from SEVEN dimensions, and each is capped at its own weight, so a perfect
    score on one cannot buy a poor score on another
  * win rate is not a dimension. It appears only inside expectancy, where it is multiplied by
    what a win is actually worth, and inside the excess over the driftless barrier bound, where
    it is measured against what the exit geometry would produce with no edge at all

A 3R strategy winning 30% and a 1R strategy winning 60% are the same edge. Scoring win rate
directly would rank them differently.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

PV = 2.0


# ---------------------------------------------------------------- the metrics
def streaks(p):
    win = lo = bw = bl = 0
    for x in p:
        if x > 0:
            win += 1; lo = 0
        else:
            lo += 1; win = 0
        bw = max(bw, win); bl = max(bl, lo)
    return bw, bl


def drawdowns(daily):
    eq = np.cumsum(daily)
    peak = np.maximum.accumulate(np.r_[0, eq])
    under = peak - np.r_[0, eq]
    runs, cur = [], 0.0
    for x in under:
        if x > 0:
            cur = max(cur, x)
        elif cur > 0:
            runs.append(cur); cur = 0.0
    if cur > 0:
        runs.append(cur)
    return float(under.max()), float(np.mean(runs)) if runs else 0.0, runs


def excursions(bars, ent, ex, side):
    """MAE and MFE per trade, in dollars, from the bars the trade was actually open for."""
    h, l = bars["h"], bars["l"]
    o = bars["o"]
    mae = np.zeros(len(ent)); mfe = np.zeros(len(ent))
    for k, (a, b, s) in enumerate(zip(ent, ex, side)):
        if b <= a:
            continue
        hi = h[a:b + 1].max(); lo = l[a:b + 1].min(); e = o[a]
        if s == 1:
            mae[k] = (lo - e) * PV; mfe[k] = (hi - e) * PV
        else:
            mae[k] = (e - hi) * PV; mfe[k] = (e - lo) * PV
    return mae, mfe


def risk_of_ruin(p, capital=25000.0, ruin=0.5, paths=5000, seed=3):
    """Share of resampled orderings in which equity ever falls `ruin` below the start."""
    if len(p) < 20:
        return np.nan
    rng = np.random.default_rng(seed)
    draw = rng.choice(p, size=(paths, len(p)), replace=True)
    eq = capital + np.cumsum(draw, axis=1)
    return float((eq.min(axis=1) <= capital * (1 - ruin)).mean())


def stability(daily):
    """R-squared of the equity curve against a straight line. 1.0 is a ruler."""
    eq = np.cumsum(daily)
    if len(eq) < 5 or eq.std() == 0:
        return 0.0
    x = np.arange(len(eq))
    b = np.polyfit(x, eq, 1)
    resid = eq - np.polyval(b, x)
    return float(max(0.0, 1 - resid.var() / eq.var()))


def all_metrics(s, daily=None):
    """s is a test_suite.Strategy. Returns every metric the brief lists."""
    p = s.pnl
    d = daily if daily is not None else _daily(s)
    act = d[d != 0]
    wins, losses = p[p > 0], p[p <= 0]
    gp, gl = wins.sum(), -losses.sum()
    mdd, add, _ = drawdowns(d)
    bw, bl = streaks(p)
    sd = d.std(ddof=1) if len(d) > 1 else 0.0
    dn = d[d < 0].std(ddof=1) if (d < 0).sum() > 1 else 0.0
    yrs = max(s.n_sess / 252.0, 1e-9)
    mae, mfe = excursions(s.bars, s.ent_bar, s.ex_bar, s.side)
    tp = s.params.get("tp_r", np.nan)
    bound = 100.0 / (1.0 + tp) if np.isfinite(tp) else np.nan
    M = {
        "trades": len(p),
        "net profit": float(p.sum()),
        "win rate %": float(100 * (p > 0).mean()) if len(p) else 0.0,
        "driftless bound %": bound,
        "win rate excess": float(100 * (p > 0).mean() - bound) if np.isfinite(bound) else np.nan,
        "profit factor": float(gp / gl) if gl > 0 else np.inf,
        "expectancy $": float(p.mean()) if len(p) else 0.0,
        "average trade $": float(p.mean()) if len(p) else 0.0,
        "average win $": float(wins.mean()) if len(wins) else 0.0,
        "average loss $": float(losses.mean()) if len(losses) else 0.0,
        "payoff ratio": float(wins.mean() / -losses.mean()) if len(losses) and losses.mean() else np.nan,
        "Sharpe": float(d.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "Sortino": float(d.mean() / dn * np.sqrt(252)) if dn > 0 else 0.0,
        "Calmar": float(p.sum() / yrs / mdd) if mdd > 0 else np.inf,
        "max drawdown $": mdd,
        "average drawdown $": add,
        "recovery factor": float(p.sum() / mdd) if mdd > 0 else np.inf,
        "return / max drawdown": float(p.sum() / mdd) if mdd > 0 else np.inf,
        "volatility $/session": float(sd),
        "downside volatility": float(dn),
        "stability of returns": stability(d),
        "longest winning streak": bw,
        "longest losing streak": bl,
        "VaR 95 $": float(np.percentile(act, 5)) if len(act) > 20 else np.nan,
        "VaR 99 $": float(np.percentile(act, 1)) if len(act) > 20 else np.nan,
        "CVaR 95 $": float(act[act <= np.percentile(act, 5)].mean()) if len(act) > 20 else np.nan,
        "CVaR 99 $": float(act[act <= np.percentile(act, 1)].mean()) if len(act) > 20 else np.nan,
        "tail ratio": float(abs(np.percentile(p, 95) / np.percentile(p, 5)))
                      if len(p) > 20 and np.percentile(p, 5) else np.nan,
        "skew": float(_skew(p)),
        "kurtosis": float(_kurt(p)),
        "exposure % of bars": float(100 * (s.ex_bar - s.ent_bar).sum() / max(len(s.bars["c"]), 1)),
        "trades per year": float(len(p) / yrs),
        "MAE mean $": float(mae.mean()) if len(mae) else 0.0,
        "MFE mean $": float(mfe.mean()) if len(mfe) else 0.0,
        "MAE/MFE ratio": float(abs(mae.mean() / mfe.mean())) if len(mfe) and mfe.mean() else np.nan,
        "edge ratio (MFE/|MAE|)": float(mfe.mean() / abs(mae.mean())) if len(mae) and mae.mean() else np.nan,
        "risk of ruin (50%)": risk_of_ruin(p),
    }
    return M


def _daily(s):
    d = np.zeros(s.n_sess)
    for x, e in zip(s.pnl, s.ent_sess):
        d[e] += x
    return d


def _skew(x):
    from scipy import stats
    return stats.skew(x) if len(x) > 2 else 0.0


def _kurt(x):
    from scipy import stats
    return stats.kurtosis(x) if len(x) > 3 else 0.0


# ---------------------------------------------------------------- constraints
@dataclass
class Constraints:
    max_drawdown: float = np.inf          # dollars
    max_risk_per_trade: float = np.inf    # dollars, the stop distance at one contract
    min_profit_factor: float = 1.0
    min_sortino: float = 0.0
    min_expectancy: float = 0.0           # dollars per trade
    min_oos: float = 0.0                  # dollars on the locked block
    max_exposure: float = 100.0           # % of bars in the market
    min_trades: int = 30

    def check(self, s, M):
        risk = float(np.nanmedian(s.params.get("atr_mult", np.nan)
                                  * s.bars["atr"][s.ent_bar] * PV)) if len(s.ent_bar) else np.nan
        oos = float(s.pnl[s.ent_sess >= s.cut].sum())
        tests = [
            ("max drawdown", M["max drawdown $"], "<=", self.max_drawdown),
            ("risk per trade", risk, "<=", self.max_risk_per_trade),
            ("profit factor", M["profit factor"], ">=", self.min_profit_factor),
            ("Sortino", M["Sortino"], ">=", self.min_sortino),
            ("expectancy", M["expectancy $"], ">=", self.min_expectancy),
            ("out-of-sample net", oos, ">=", self.min_oos),
            ("exposure %", M["exposure % of bars"], "<=", self.max_exposure),
            ("trades", M["trades"], ">=", self.min_trades),
        ]
        out = []
        for name, got, op, want in tests:
            ok = (got <= want) if op == "<=" else (got >= want)
            out.append((name, float(got), op, float(want), bool(ok) or not np.isfinite(got)))
        return out


# ---------------------------------------------------------------- the composite
WEIGHTS = {
    "alpha quality": 20,
    "risk-adjusted return": 20,
    "robustness": 15,
    "stability": 10,
    "statistical significance": 15,
    "diversification": 10,
    "regime consistency": 10,
}


def _clip(x, lo, hi):
    """A missing or infinite input scores 0 for that term rather than poisoning the whole
    composite with a nan."""
    if x is None or not np.isfinite(x):
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0, 1)) if hi > lo else 0.0


def quant_score(M, extras):
    """extras carries what the metrics alone cannot see: out-of-sample retention, the matched-null
    p-value, parameter-grid survival, book correlation and per-regime consistency."""
    dims = {
        "alpha quality": np.mean([
            _clip(M.get("win rate excess", 0) or 0, 0, 15),
            _clip(M.get("expectancy $", 0), 0, 150),
            _clip(M.get("edge ratio (MFE/|MAE|)", 1) or 1, 1.0, 2.5)]),
        "risk-adjusted return": np.mean([
            _clip(M.get("Sortino", 0), 0, 3),
            _clip(M.get("Calmar", 0), 0, 3),
            _clip(M.get("return / max drawdown", 0), 1, 10)]),
        "robustness": np.mean([
            _clip(extras.get("param grid profitable %", 0), 50, 95),
            _clip(extras.get("cost 4x survives", 0), 0, 1),
            _clip(extras.get("noise draws profitable %", 0), 80, 100)]),
        "stability": np.mean([
            _clip(M.get("stability of returns", 0), 0.5, 0.98),
            _clip(-M.get("longest losing streak", 20), -20, -5),
            _clip(extras.get("positive periods", 0), 3, 6)]),
        "statistical significance": np.mean([
            _clip(-np.log10(max(extras.get("matched null p", 1.0), 1e-6)), 0, 3),
            _clip(extras.get("walk-forward positive folds", 0), 4, 7),
            _clip(extras.get("oos retention", 0), 0.2, 1.0)]),
        "diversification": _clip(1 - abs(extras.get("max book correlation", 1.0)), 0.6, 1.0),
        "regime consistency": _clip(extras.get("profitable regime share", 0), 0.5, 0.95),
    }
    score = sum(WEIGHTS[k] * v for k, v in dims.items())
    return float(score), {k: round(100 * v, 1) for k, v in dims.items()}
