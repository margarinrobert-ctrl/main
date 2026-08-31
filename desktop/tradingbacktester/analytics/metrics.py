"""Performance statistics for one backtest, and an honest label on each of them.

:func:`compute_metrics` turns a :class:`~tradingbacktester.engine.results.BacktestResult`
into a flat dictionary of numbers plus two companion dictionaries:

``reliability``
    ``metric -> "ok" | "low_sample" | "unavailable"``.
``reliability_notes``
    ``metric -> plain-language reason`` for everything not marked ``"ok"``.

That labelling is not decoration.  A profit factor computed from eleven trades
is not a measurement, it is a coin toss with two decimal places, and the
interface dims it and badges it for exactly that reason.  Anything whose
denominator was degenerate -- no losing trades, a flat equity curve, no defined
risk per trade -- is reported as ``unavailable`` with the reason attached rather
than as a confident ``0.00`` or an unexplained infinity.

Conventions used throughout, all of them stated again in ``docs/METRICS.md``:

* Cash figures are in the account currency, after commission, spread and
  slippage.  ``net_pnl`` on a trade is already net of its costs.
* Every ``*_pct`` value is a percentage, so ``18.18`` means 18.18%.
* ``max_drawdown`` and ``max_drawdown_pct`` are positive magnitudes; the curve
  arrays they come from are negative.  See :mod:`~tradingbacktester.analytics.equity`.
* Sharpe, Sortino, volatility and the annual return figures are computed from
  **per-bar equity returns**, not from trade P&L, and annualised by the factor
  described in :func:`annualization_factor`.
* Nothing here divides by zero, and no value is ever NaN: a metric that cannot
  be computed is ``None`` (or a deliberate ``inf``) and is marked accordingly.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Iterable, Sequence

import numpy as np

from ..core.errors import BacktesterError, BacktestError
from ..core.timeframe import Timeframe, TimeframeUnit
from ..core.types import Side, Trade
from ..engine.results import BacktestResult, EquityCurves
from . import equity as equity_mod
from .periodic import monthly_returns

log = logging.getLogger(__name__)

__all__ = [
    "compute_metrics",
    "annualization_factor",
    "years_of_data",
    "METRIC_KEYS",
    "OK",
    "LOW_SAMPLE",
    "UNAVAILABLE",
]

# -- reliability vocabulary -------------------------------------------------

OK = "ok"
LOW_SAMPLE = "low_sample"
UNAVAILABLE = "unavailable"

_SEVERITY = {OK: 0, LOW_SAMPLE: 1, UNAVAILABLE: 2}

#: Below this many trades every ratio is dominated by sampling noise.  Thirty is
#: not a magic number -- it is simply the point at which the standard error of a
#: win rate stops being larger than the effects people try to read from it.
MIN_TRADES_FOR_RATIOS = 30

#: Sharpe and Sortino need a *series*, not just trades: too few bars and the
#: estimate of volatility is meaningless even if the trade count looks healthy.
MIN_BARS_FOR_RISK_RATIOS = 100
MIN_TRADES_FOR_RISK_RATIOS = 20

#: Annualising a run shorter than this exaggerates wildly (a 3% week is not a
#: 365% year), so CAGR and anything derived from it is withheld below it.
MIN_DAYS_TO_ANNUALISE = 7.0

#: Seconds in an average calendar year, leap years included.
SECONDS_PER_YEAR = 365.25 * 86_400.0
_NS_PER_YEAR = SECONDS_PER_YEAR * 1e9

#: Conventional periods per year for calendar timeframes, used only when the
#: data itself cannot supply an observed bar spacing.
_CALENDAR_PERIODS = {
    TimeframeUnit.DAY: 252.0,      # trading days, not calendar days
    TimeframeUnit.WEEK: 52.0,
    TimeframeUnit.MONTH: 12.0,
}

#: Metrics that are ratios of trade statistics, and therefore only mean anything
#: once the sample is big enough.
_RATIO_METRICS: tuple[str, ...] = (
    "win_rate", "loss_rate", "profit_factor", "payoff_ratio", "expectancy",
    "expectancy_r", "avg_trade", "avg_win", "avg_loss", "avg_r_multiple",
    "std_r_multiple", "sqn", "kelly_fraction", "recovery_factor",
    "calmar_ratio", "long_win_rate", "short_win_rate", "avg_mae", "avg_mfe",
)

#: The keys :func:`compute_metrics` always produces.  Exposed so the report and
#: the tests can assert the contract without hard-coding a list twice.
METRIC_KEYS: tuple[str, ...] = (
    "net_profit", "gross_profit", "gross_loss", "return_pct",
    "starting_balance", "ending_balance", "total_trades", "winning_trades",
    "losing_trades", "breakeven_trades", "win_rate", "loss_rate", "avg_trade",
    "avg_win", "avg_loss", "largest_win", "largest_loss", "profit_factor",
    "expectancy", "expectancy_r", "payoff_ratio", "max_drawdown",
    "max_drawdown_pct", "max_drawdown_duration_bars", "max_drawdown_start_ts",
    "max_drawdown_end_ts", "recovery_factor", "sharpe_ratio", "sortino_ratio",
    "calmar_ratio", "cagr", "annual_return_pct", "annual_volatility_pct",
    "downside_deviation", "ulcer_index", "avg_trade_duration_seconds",
    "median_trade_duration_seconds", "max_consecutive_wins",
    "max_consecutive_losses", "avg_bars_held", "total_commission",
    "total_slippage", "total_spread_cost", "total_costs", "exposure_pct",
    "time_in_market_pct", "long_trades", "short_trades", "long_win_rate",
    "short_win_rate", "long_net_profit", "short_net_profit", "avg_mae",
    "avg_mfe", "avg_r_multiple", "std_r_multiple", "sqn", "kelly_fraction",
    "best_month_pct", "worst_month_pct", "profitable_months_pct", "turnover",
    "trades_per_year", "exit_reason_breakdown", "reliability",
)


# --------------------------------------------------------------------------
# Small guarded helpers
# --------------------------------------------------------------------------

def _div(numerator: float, denominator: float,
         default: float | None = None) -> float | None:
    """``numerator / denominator``, or ``default`` when that is not a number.

    Every ratio in this module goes through here.  There is exactly one place
    that can divide by zero and it returns instead.
    """
    try:
        d = float(denominator)
        n = float(numerator)
    except (TypeError, ValueError):
        return default
    if d == 0.0 or not math.isfinite(d) or not math.isfinite(n):
        return default
    value = n / d
    return value if math.isfinite(value) else default


def _finite(value: Any) -> float | None:
    """A plain finite ``float``, or ``None``.  Infinities survive; NaN does not."""
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return None
    return v


def _mean(values: np.ndarray) -> float | None:
    return float(np.mean(values)) if values.size else None


def _max_streak(mask: np.ndarray) -> int:
    """Longest run of ``True`` in a boolean array, without a Python loop."""
    if mask.size == 0:
        return 0
    changes = np.flatnonzero(np.concatenate(([True], mask[1:] != mask[:-1], [True])))
    lengths = np.diff(changes)
    values = mask[changes[:-1]]
    return int(lengths[values].max()) if values.any() else 0


class _Reliability:
    """The two companion dictionaries, with severity that only ever increases."""

    def __init__(self) -> None:
        self.states: dict[str, str] = {}
        self.notes: dict[str, str] = {}

    def mark(self, keys: str | Iterable[str], state: str, note: str) -> None:
        if isinstance(keys, str):
            keys = (keys,)
        for key in keys:
            current = self.states.get(key, OK)
            if _SEVERITY[state] >= _SEVERITY[current]:
                self.states[key] = state
                if state == OK:
                    self.notes.pop(key, None)
                else:
                    self.notes[key] = note

    def default_ok(self, metrics: dict[str, Any]) -> None:
        for key, value in metrics.items():
            if isinstance(value, (dict, list, tuple)):
                continue
            self.states.setdefault(key, OK)


# --------------------------------------------------------------------------
# Timebase
# --------------------------------------------------------------------------

def _timestamps(result: BacktestResult) -> np.ndarray:
    """The best per-bar timestamp series available on a result."""
    curves = getattr(result, "curves", None)
    if curves is not None and len(curves) > 0:
        return np.asarray(curves.ts, dtype="int64")
    bars = getattr(result, "bars", None)
    if bars is not None and len(bars) > 0:
        return np.asarray(bars.ts, dtype="int64")
    return np.empty(0, dtype="int64")


def _timeframe(result: BacktestResult) -> Timeframe | None:
    bars = getattr(result, "bars", None)
    tf = getattr(bars, "timeframe", None)
    if isinstance(tf, Timeframe):
        return tf
    label = str(getattr(result, "timeframe_label", "") or "")
    if not label:
        return None
    try:
        return Timeframe.parse(label)
    except BacktesterError:
        return None


def years_of_data(result: BacktestResult) -> float:
    """Calendar years spanned by the run, from the first bar to the last.

    Calendar years, not trading years: a strategy that ran for six months made
    whatever it made in six months of wall-clock time, and that is the honest
    denominator for a per-year figure.
    """
    ts = _timestamps(result)
    if ts.size < 2:
        return 0.0
    span = float(ts[-1] - ts[0])
    return span / _NS_PER_YEAR if span > 0 else 0.0


def annualization_factor(result: BacktestResult) -> float:
    """Periods per year for the run's bars.

    Resolution order:

    1. ``BacktestConfig.annualization_factor`` when the user set one.  An
       explicit number always wins; this is the escape hatch for data whose
       calendar the application cannot infer.
    2. **Observed**: the number of bar intervals that fit in a calendar year at
       this data's own average spacing --
       ``(bars - 1) / (span in calendar years)``.  This is the default because
       it prices in the real session length automatically: hourly bars from a
       6.5-hour equity session give roughly 1,638 per year, not 8,766, and no
       assumption about which exchange it is has to be made.
    3. **Nominal**, when the span is degenerate (fewer than two bars, or every
       bar sharing a timestamp): derived from the timeframe, with 252 days,
       52 weeks or 12 months per year for calendar units and continuous time
       for sub-daily ones.
    4. 252 as a last resort when there is no timeframe either.

    Never returns zero or a negative number, so it is always safe to take a
    square root of it or divide by it.
    """
    config = getattr(result, "config", None)
    configured = getattr(config, "annualization_factor", None)
    value = _finite(configured)
    if value is not None and value > 0:
        return float(value)

    ts = _timestamps(result)
    if ts.size >= 2:
        span = float(ts[-1] - ts[0])
        if span > 0:
            years = span / _NS_PER_YEAR
            observed = _div(ts.size - 1, years)
            # An absurd factor means the timestamps are not what they claim to
            # be; fall through to the nominal calculation rather than reporting
            # a Sharpe ratio scaled by a million.
            if observed is not None and 1.0 <= observed <= 366.0 * 24.0 * 60.0:
                return float(observed)

    tf = _timeframe(result)
    if tf is not None:
        if tf.unit in _CALENDAR_PERIODS:
            return max(1.0, _CALENDAR_PERIODS[tf.unit] / float(tf.multiplier))
        seconds = tf.approx_seconds
        nominal = _div(SECONDS_PER_YEAR, seconds)
        if nominal is not None and nominal > 0:
            return float(nominal)
    return 252.0


def _risk_free_per_period(annual_rate: float, factor: float) -> float:
    """The annual risk-free rate expressed per bar, compounded, not divided.

    ``(1 + r) ** (1 / factor) - 1`` rather than ``r / factor`` so that the
    per-bar rate compounds back to exactly the annual one, which matters when
    the factor is large (a minute bar has ~370,000 of them).
    """
    rate = _finite(annual_rate) or 0.0
    if rate == 0.0 or factor <= 0.0 or rate <= -1.0:
        return 0.0
    try:
        return float((1.0 + rate) ** (1.0 / factor) - 1.0)
    except (OverflowError, ValueError):        # pragma: no cover - defensive
        return 0.0


# --------------------------------------------------------------------------
# The main entry point
# --------------------------------------------------------------------------

def compute_metrics(result: BacktestResult) -> dict[str, Any]:
    """Every performance statistic for one run, plus its reliability labelling.

    Raises
    ------
    BacktestError
        Only if the result is so malformed that nothing can be computed from
        it.  Degenerate-but-legal runs -- no trades, one bar, a flat curve --
        are handled and reported, not refused.
    """
    if result is None:
        raise BacktestError("There is no backtest result to compute statistics for.")
    try:
        return _compute(result)
    except BacktesterError:
        raise
    except Exception as exc:  # pragma: no cover - safety net, see module docstring
        log.exception("Metric computation failed")
        raise BacktestError(
            "The performance statistics for this run could not be computed.",
            detail=f"{type(exc).__name__}: {exc}") from exc


def _compute(result: BacktestResult) -> dict[str, Any]:
    rel = _Reliability()
    metrics: dict[str, Any] = {}

    trades: list[Trade] = list(getattr(result, "trades", None) or [])
    curves: EquityCurves | None = getattr(result, "curves", None)
    if curves is not None and len(curves) == 0:
        curves = None

    n = len(trades)
    net = np.array([float(t.net_pnl) for t in trades], dtype="float64") \
        if n else np.empty(0, dtype="float64")
    wins_mask = net > 0.0
    losses_mask = net < 0.0
    wins = net[wins_mask]
    losses = net[losses_mask]

    _cash_and_counts(result, metrics, rel, trades, net, wins, losses, curves)
    _averages(metrics, rel, net, wins, losses, n)
    _drawdown(metrics, rel, curves)
    _risk_ratios(result, metrics, rel, curves, n)
    _trade_shape(metrics, rel, trades, net, wins_mask, losses_mask, n)
    _costs(metrics, trades)
    _exposure(result, metrics, rel, curves, trades)
    _sides(metrics, rel, trades)
    _excursions(metrics, rel, trades, n)
    _periods(result, metrics, rel)
    _activity(result, metrics, rel, trades, n)
    _exit_reasons(metrics, trades, n)
    _market_neutral(result, metrics, rel, n)

    _low_sample_pass(metrics, rel, n, curves)
    _sanitise(metrics, rel)

    rel.default_ok(metrics)
    metrics["reliability"] = dict(sorted(rel.states.items()))
    metrics["reliability_notes"] = dict(sorted(rel.notes.items()))
    return metrics


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------

def _market_neutral(result: BacktestResult, m: dict[str, Any],
                    rel: "_Reliability", n: int) -> None:
    """Beta, residual Sharpe and concentration, beside the ordinary Sharpe.

    Computed here rather than offered as a separate report because a Sharpe on
    raw account currency cannot tell an edge from leverage, and a number nobody
    goes and asks for does not stop anyone shipping one. See
    :mod:`tradingbacktester.analytics.neutral`.
    """
    from .neutral import analyse

    report = analyse(result)
    if report is None:
        return
    neutral, spread = report.neutral, report.concentration
    m["sessions"] = report.sessions
    m["traded_sessions"] = report.traded_sessions
    m["session_sharpe"] = neutral.sharpe
    m["beta"] = neutral.beta
    m["alpha"] = neutral.alpha
    m["market_correlation"] = neutral.correlation
    m["residual_sharpe"] = neutral.residual_sharpe
    m["beta_pnl_share"] = neutral.beta_pnl_share
    m["market_neutral_verdict"] = neutral.verdict()
    m["concentration"] = spread.share
    m["concentration_parts"] = list(spread.parts)
    m["concentration_passed"] = spread.passed
    m["concentration_verdict"] = spread.verdict()

    # These are per-SESSION statistics, so the sample that matters is the
    # session count, not the trade count the rest of the panel is labelled by.
    if report.sessions < 30:
        for key in ("session_sharpe", "beta", "alpha", "market_correlation",
                    "residual_sharpe", "beta_pnl_share", "concentration"):
            rel.mark(key, "low_sample",
                     f"Regressed on {report.sessions} session(s). A beta needs "
                     f"a few dozen before it is distinguishable from zero.")
    # Deliberately NOT routed through the reliability states: those mean "the
    # sample is too small", and badging a Sharpe built on 2,704 sessions as
    # LOW n would be a lie about why it should not be trusted. The caveat is
    # its own field and the panel flags it on its own terms.
    m["mostly_beta"] = neutral.mostly_beta
    if neutral.mostly_beta:
        m["beta_warning"] = (
            f"{neutral.beta_pnl_share * 100:.0f}% of this result is the "
            f"market's own move across the strategy's window. Stripped of it "
            f"the Sharpe is {neutral.residual_sharpe:.3f} against "
            f"{neutral.sharpe:.3f}.")


def _cash_and_counts(result: BacktestResult, m: dict[str, Any], rel: _Reliability,
                     trades: Sequence[Trade], net: np.ndarray, wins: np.ndarray,
                     losses: np.ndarray, curves: EquityCurves | None) -> None:
    """Headline cash, the trade census, and the profit factor.

    ``gross_profit`` and ``gross_loss`` are sums of **net** trade P&L -- after
    commission, spread and slippage -- because a trade is classified as a winner
    by what it actually put in the account, and because a profit factor built
    from pre-cost figures flatters exactly the high-frequency strategies whose
    costs are the whole story.
    """
    start = _finite(getattr(getattr(result, "config", None), "starting_capital", None))
    if start is None or start <= 0:
        start = 100_000.0
        rel.mark(("return_pct", "starting_balance"), UNAVAILABLE,
                 "This run has no starting capital recorded, so percentage "
                 "returns are measured against a nominal 100,000.")

    if curves is not None:
        ending = float(curves.equity[-1])
    else:
        ending = start + float(net.sum()) if net.size else start

    gross_profit = float(wins.sum()) if wins.size else 0.0
    gross_loss = float(losses.sum()) if losses.size else 0.0     # negative
    net_profit = ending - start

    m["starting_balance"] = float(start)
    m["ending_balance"] = float(ending)
    m["net_profit"] = float(net_profit)
    m["gross_profit"] = gross_profit
    m["gross_loss"] = gross_loss
    m["return_pct"] = _div(net_profit * 100.0, start, 0.0)

    m["total_trades"] = int(len(trades))
    m["winning_trades"] = int(wins.size)
    m["losing_trades"] = int(losses.size)
    m["breakeven_trades"] = int(len(trades) - wins.size - losses.size)

    if losses.size == 0:
        m["profit_factor"] = math.inf if gross_profit > 0 else 0.0
        rel.mark("profit_factor", UNAVAILABLE,
                 "Unavailable - no losing trades, so there is nothing to divide "
                 "by. A profit factor of infinity is a sample size problem, not "
                 "a strategy.")
    else:
        m["profit_factor"] = _div(gross_profit, abs(gross_loss), 0.0)


def _averages(m: dict[str, Any], rel: _Reliability, net: np.ndarray,
              wins: np.ndarray, losses: np.ndarray, n: int) -> None:
    """Per-trade averages, extremes, payoff and expectancy."""
    m["win_rate"] = _div(wins.size * 100.0, n, 0.0)
    m["loss_rate"] = _div(losses.size * 100.0, n, 0.0)

    avg_trade = _mean(net)
    m["avg_trade"] = avg_trade
    m["expectancy"] = avg_trade            # the same number under both names
    m["avg_win"] = _mean(wins)
    m["avg_loss"] = _mean(losses)
    m["largest_win"] = float(wins.max()) if wins.size else None
    m["largest_loss"] = float(losses.min()) if losses.size else None

    if n == 0:
        rel.mark(("win_rate", "loss_rate", "avg_trade", "expectancy", "avg_win",
                  "avg_loss", "largest_win", "largest_loss", "payoff_ratio",
                  "profit_factor", "expectancy_r"), UNAVAILABLE,
                 "Unavailable - this run produced no trades.")
    if wins.size == 0 and n:
        rel.mark(("avg_win", "largest_win"), UNAVAILABLE,
                 "Unavailable - no winning trades.")
    if losses.size == 0 and n:
        rel.mark(("avg_loss", "largest_loss"), UNAVAILABLE,
                 "Unavailable - no losing trades.")

    avg_win = m["avg_win"]
    avg_loss = m["avg_loss"]
    if avg_win is None or avg_loss is None:
        # No losers: the payoff is unbounded.  No winners: it is zero.  Both are
        # statements about the sample, so both are labelled.
        m["payoff_ratio"] = math.inf if (avg_win is not None and avg_loss is None) \
            else 0.0 if n else None
        if n:
            rel.mark("payoff_ratio", UNAVAILABLE,
                     "Unavailable - the average win or the average loss does not "
                     "exist yet, so their ratio cannot be formed.")
    else:
        m["payoff_ratio"] = _div(avg_win, abs(avg_loss), 0.0)


def _drawdown(m: dict[str, Any], rel: _Reliability,
              curves: EquityCurves | None) -> None:
    """Depth, duration and dates of the worst fall, plus the Ulcer index.

    ``max_drawdown_duration_bars`` is the **longest** time spent below a peak,
    which is not always the deepest excursion: a shallow drawdown that lasts a
    year is the one that ends careers.
    """
    periods = equity_mod.underwater_periods(curves)
    m["ulcer_index"] = equity_mod.ulcer_index(curves)
    m["time_under_water_pct"] = equity_mod.time_under_water_pct(curves)

    if not periods:
        m["max_drawdown"] = 0.0
        m["max_drawdown_pct"] = 0.0
        m["max_drawdown_duration_bars"] = 0
        m["max_drawdown_start_ts"] = None
        m["max_drawdown_end_ts"] = None
        m["max_drawdown_recovered_ts"] = None
        m["deepest_drawdown_bars"] = 0
        if curves is None:
            rel.mark(("max_drawdown", "max_drawdown_pct", "ulcer_index",
                      "max_drawdown_duration_bars", "time_under_water_pct"),
                     UNAVAILABLE,
                     "Unavailable - this run has no equity curve to measure a "
                     "drawdown on.")
        rel.mark(("max_drawdown_start_ts", "max_drawdown_end_ts",
                  "max_drawdown_recovered_ts"), UNAVAILABLE,
                 "Unavailable - equity never fell below a previous peak, so there "
                 "is no drawdown to date.")
        return

    deepest = min(periods, key=lambda p: p["depth"])
    longest = max(periods, key=lambda p: p["length_bars"])
    start_index = int(deepest["start_index"])
    # The fall starts at the peak, one bar before the first bar under water.
    peak_index = max(0, start_index - 1)

    m["max_drawdown"] = abs(float(deepest["depth"]))
    m["max_drawdown_pct"] = abs(float(deepest["depth_pct"]))
    m["max_drawdown_duration_bars"] = int(longest["length_bars"])
    m["max_drawdown_start_ts"] = int(curves.ts[peak_index])   # type: ignore[union-attr]
    m["max_drawdown_end_ts"] = int(deepest["trough_ts"])
    m["max_drawdown_recovered_ts"] = deepest["end_ts"]
    m["deepest_drawdown_bars"] = int(deepest["length_bars"])
    if deepest["end_ts"] is None:
        rel.mark("max_drawdown_recovered_ts", UNAVAILABLE,
                 "Unavailable - the deepest drawdown had not recovered by the end "
                 "of the data. It is still open.")


def _risk_ratios(result: BacktestResult, m: dict[str, Any], rel: _Reliability,
                 curves: EquityCurves | None, n_trades: int) -> None:
    """Sharpe, Sortino, Calmar, CAGR, volatility -- all from per-bar returns.

    Per-bar rather than per-trade: the account's volatility is what a risk
    manager sees, and it includes the bars a position sat open doing nothing,
    which per-trade statistics quietly drop.
    """
    factor = annualization_factor(result)
    rate = _finite(getattr(getattr(result, "config", None), "risk_free_rate", None)) or 0.0
    per_period_rf = _risk_free_per_period(rate, factor)
    returns = equity_mod.bar_returns(curves)

    m["annualization_factor"] = float(factor)
    m["risk_free_rate"] = float(rate)
    m["bars"] = int(len(curves)) if curves is not None else int(
        getattr(result, "bars_processed", 0) or 0)

    if returns.size < 2:
        m["sharpe_ratio"] = None
        m["sortino_ratio"] = None
        m["annual_volatility_pct"] = None
        m["downside_deviation"] = None
        m["annual_return_pct"] = None
        rel.mark(("sharpe_ratio", "sortino_ratio", "annual_volatility_pct",
                  "downside_deviation", "annual_return_pct"), UNAVAILABLE,
                 "Unavailable - at least three bars of equity are needed before "
                 "a return series exists to measure.")
    else:
        excess = returns - per_period_rf
        mean_excess = float(np.mean(excess))
        # ddof=1: these returns are a sample of the process, not the population.
        std = float(np.std(excess, ddof=1))
        root = math.sqrt(factor)

        if std <= 0.0:
            m["sharpe_ratio"] = 0.0
            rel.mark("sharpe_ratio", UNAVAILABLE,
                     "Unavailable - every bar returned the same amount, so there "
                     "is no volatility to divide by. Reported as zero rather than "
                     "as an infinity.")
        else:
            m["sharpe_ratio"] = mean_excess / std * root

        # Sortino's denominator counts only shortfalls but divides by the FULL
        # sample size, which is what keeps it on the same scale as Sharpe.
        shortfall = np.minimum(excess, 0.0)
        downside = float(np.sqrt(np.mean(np.square(shortfall))))
        m["downside_deviation"] = float(downside * root * 100.0)
        if downside <= 0.0:
            m["sortino_ratio"] = math.inf if mean_excess > 0 else 0.0
            rel.mark("sortino_ratio", UNAVAILABLE,
                     "Unavailable - no bar returned less than the risk-free rate, "
                     "so there is no downside deviation to divide by.")
        else:
            m["sortino_ratio"] = mean_excess / downside * root

        m["annual_volatility_pct"] = float(np.std(returns, ddof=1) * root * 100.0)
        m["annual_return_pct"] = float(np.mean(returns) * factor * 100.0)

    # CAGR compounds the actual account, so it is computed from the endpoints of
    # the equity curve rather than from the mean of the returns.
    years = years_of_data(result)
    m["years"] = float(years)
    start = float(m.get("starting_balance") or 0.0)
    end = float(m.get("ending_balance") or 0.0)
    cagr: float | None = None
    if years * 365.25 < MIN_DAYS_TO_ANNUALISE:
        rel.mark(("cagr", "calmar_ratio"), UNAVAILABLE,
                 f"Unavailable - the run covers less than {MIN_DAYS_TO_ANNUALISE:.0f} "
                 f"days. Annualising a period that short produces a number with no "
                 f"meaning.")
    elif start <= 0 or end <= 0:
        rel.mark(("cagr", "calmar_ratio"), UNAVAILABLE,
                 "Unavailable - a compound growth rate needs a positive balance at "
                 "both ends of the run.")
    else:
        try:
            cagr = float(((end / start) ** (1.0 / years) - 1.0) * 100.0)
        except (OverflowError, ValueError, ZeroDivisionError):  # pragma: no cover
            cagr = None
        if cagr is not None and not math.isfinite(cagr):
            cagr = None
        if cagr is None:
            rel.mark(("cagr", "calmar_ratio"), UNAVAILABLE,
                     "Unavailable - the compound growth rate overflowed, which "
                     "means the run is far too short to annualise.")
    m["cagr"] = cagr

    max_dd = float(m.get("max_drawdown") or 0.0)
    max_dd_pct = float(m.get("max_drawdown_pct") or 0.0)
    net_profit = float(m.get("net_profit") or 0.0)

    if max_dd <= 0.0:
        m["recovery_factor"] = math.inf if net_profit > 0 else 0.0
        rel.mark("recovery_factor", UNAVAILABLE,
                 "Unavailable - this run never drew down, so there is no drawdown "
                 "to divide the profit by.")
    else:
        m["recovery_factor"] = _div(net_profit, max_dd, 0.0)

    if cagr is None:
        m["calmar_ratio"] = None
    elif max_dd_pct <= 0.0:
        m["calmar_ratio"] = math.inf if cagr > 0 else 0.0
        rel.mark("calmar_ratio", UNAVAILABLE,
                 "Unavailable - this run never drew down, so there is no drawdown "
                 "to divide the annual return by.")
    else:
        m["calmar_ratio"] = _div(cagr, max_dd_pct, 0.0)


def _trade_shape(m: dict[str, Any], rel: _Reliability, trades: Sequence[Trade],
                 net: np.ndarray, wins_mask: np.ndarray, losses_mask: np.ndarray,
                 n: int) -> None:
    """Durations, streaks, R-multiple statistics, SQN and the Kelly fraction."""
    durations = np.array([float(t.duration_seconds) for t in trades],
                         dtype="float64") if n else np.empty(0)
    bars_held = np.array([float(t.bars_held) for t in trades],
                         dtype="float64") if n else np.empty(0)

    m["avg_trade_duration_seconds"] = _mean(durations)
    m["median_trade_duration_seconds"] = (float(np.median(durations))
                                          if durations.size else None)
    m["avg_bars_held"] = _mean(bars_held)
    m["max_consecutive_wins"] = _max_streak(wins_mask)
    m["max_consecutive_losses"] = _max_streak(losses_mask)

    if n == 0:
        rel.mark(("avg_trade_duration_seconds", "median_trade_duration_seconds",
                  "avg_bars_held"), UNAVAILABLE,
                 "Unavailable - this run produced no trades.")

    r_values = np.array([float(t.r_multiple) for t in trades
                         if t.r_multiple is not None
                         and math.isfinite(float(t.r_multiple))], dtype="float64")
    defined = r_values.size
    m["r_defined_trades"] = int(defined)

    if defined:
        m["avg_r_multiple"] = float(np.mean(r_values))
        m["expectancy_r"] = m["avg_r_multiple"]
        m["std_r_multiple"] = float(np.std(r_values, ddof=1)) if defined >= 2 else None
    else:
        m["avg_r_multiple"] = None
        m["expectancy_r"] = None
        m["std_r_multiple"] = None
        rel.mark(("avg_r_multiple", "expectancy_r", "std_r_multiple", "sqn"),
                 UNAVAILABLE,
                 "Unavailable - no trade recorded an initial stop, so there is no "
                 "risk per trade to express the result as a multiple of.")

    if defined and defined < 2:
        rel.mark("std_r_multiple", UNAVAILABLE,
                 "Unavailable - a standard deviation needs at least two trades.")

    # SQN is only honest when most trades actually have a defined R.  A sample
    # where half the trades had no stop is not a system quality number, it is a
    # number computed from whichever half happened to have one.
    if defined and n and defined < 0.5 * n:
        m["sqn"] = None
        rel.mark("sqn", UNAVAILABLE,
                 f"Unavailable - only {defined} of {n} trades had a defined initial "
                 f"risk, so an R-multiple statistic would describe a minority of "
                 f"the run.")
    elif defined >= 2:
        std_r = float(np.std(r_values, ddof=1))
        if std_r <= 0.0:
            m["sqn"] = None
            rel.mark("sqn", UNAVAILABLE,
                     "Unavailable - every trade returned the same R multiple, so "
                     "there is no dispersion to divide by.")
        else:
            m["sqn"] = float(math.sqrt(defined) * float(np.mean(r_values)) / std_r)
    elif defined:
        m["sqn"] = None
        rel.mark("sqn", UNAVAILABLE,
                 "Unavailable - the system quality number needs at least two "
                 "trades with a defined risk.")
    else:
        m["sqn"] = None

    _kelly(m, rel, n)


def _kelly(m: dict[str, Any], rel: _Reliability, n: int) -> None:
    """Kelly fraction from the win rate and the payoff ratio.

    ``f = p - (1 - p) / b``.  Clamped to ``[-1, 1]``: the formula is derived for
    a repeated bet with a known edge, and the estimate it produces from a
    backtest is an upper bound on a number nobody should size at in full.
    """
    win_rate = _finite(m.get("win_rate"))
    payoff = m.get("payoff_ratio")
    if n == 0 or win_rate is None:
        m["kelly_fraction"] = None
        rel.mark("kelly_fraction", UNAVAILABLE,
                 "Unavailable - this run produced no trades.")
        return
    p = win_rate / 100.0
    if payoff is None:
        m["kelly_fraction"] = None
        rel.mark("kelly_fraction", UNAVAILABLE,
                 "Unavailable - the payoff ratio it needs could not be computed.")
        return
    payoff = float(payoff)
    if math.isinf(payoff):
        value = p                       # no losers: the loss term vanishes
    elif payoff <= 0.0:
        value = -1.0                    # no winners: the bet has no positive edge
    else:
        loss_term = _div(1.0 - p, payoff, None)
        value = p - loss_term if loss_term is not None else -1.0
    m["kelly_fraction"] = float(max(-1.0, min(1.0, value)))


def _costs(m: dict[str, Any], trades: Sequence[Trade]) -> None:
    """What the strategy paid to trade.  All three are positive cash amounts."""
    commission = float(sum(float(t.commission) for t in trades))
    slippage = float(sum(float(t.slippage_cost) for t in trades))
    spread = float(sum(float(t.spread_cost) for t in trades))
    m["total_commission"] = commission
    m["total_slippage"] = slippage
    m["total_spread_cost"] = spread
    m["total_costs"] = commission + slippage + spread
    gross = float(m.get("gross_profit") or 0.0)
    m["cost_to_gross_profit_pct"] = _div(m["total_costs"] * 100.0, gross, None)


def _exposure(result: BacktestResult, m: dict[str, Any], rel: _Reliability,
              curves: EquityCurves | None, trades: Sequence[Trade]) -> None:
    """Two different questions, deliberately answered separately.

    ``exposure_pct`` is the share of **bars** on which a position was open --
    what the statistics panel labels "time in market" and what the exposure
    ribbon draws.  ``time_in_market_pct`` is the share of **elapsed calendar
    time** covered by an open trade, with overlapping trades merged so a
    multi-position strategy cannot count the same hour twice.  They differ
    whenever the data has gaps: an overnight hole between two session bars is
    one bar, but it is sixteen hours.
    """
    if curves is not None:
        exposure = np.asarray(curves.exposure, dtype="float64")
        held = np.isfinite(exposure) & (exposure != 0.0)
        m["exposure_pct"] = float(held.mean() * 100.0) if held.size else 0.0
        m["avg_position_units"] = float(np.mean(np.abs(exposure[held]))) \
            if held.any() else 0.0
    else:
        m["exposure_pct"] = None
        m["avg_position_units"] = None
        rel.mark(("exposure_pct", "avg_position_units"), UNAVAILABLE,
                 "Unavailable - this run has no per-bar exposure series.")

    ts = _timestamps(result)
    span = float(ts[-1] - ts[0]) if ts.size >= 2 else 0.0
    if not trades or span <= 0:
        m["time_in_market_pct"] = 0.0
        rel.mark("time_in_market_pct", UNAVAILABLE,
                 "Unavailable - this run produced no trades."
                 if not trades else
                 "Unavailable - the run does not span any elapsed time.")
        return

    intervals = sorted((int(t.entry_ts), int(t.exit_ts)) for t in trades)
    covered = 0
    current_start, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start > current_end:
            covered += max(0, current_end - current_start)
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    covered += max(0, current_end - current_start)
    m["time_in_market_pct"] = float(min(100.0, max(0.0, covered / span * 100.0)))


def _sides(m: dict[str, Any], rel: _Reliability, trades: Sequence[Trade]) -> None:
    """The long and short books, split.  A strategy is often only one of them."""
    for side, prefix in ((Side.LONG, "long"), (Side.SHORT, "short")):
        subset = [t for t in trades if t.side is side]
        pnl = np.array([float(t.net_pnl) for t in subset], dtype="float64") \
            if subset else np.empty(0, dtype="float64")
        count = len(subset)
        m[f"{prefix}_trades"] = int(count)
        m[f"{prefix}_net_profit"] = float(pnl.sum()) if count else 0.0
        m[f"{prefix}_win_rate"] = _div(float((pnl > 0).sum()) * 100.0, count, 0.0)
        m[f"{prefix}_avg_trade"] = _mean(pnl)
        if count == 0:
            rel.mark((f"{prefix}_win_rate", f"{prefix}_avg_trade"), UNAVAILABLE,
                     f"Unavailable - this run took no {prefix} trades.")


def _excursions(m: dict[str, Any], rel: _Reliability, trades: Sequence[Trade],
                n: int) -> None:
    """Average MAE and MFE in price points, and what they imply about barriers."""
    mae = np.array([float(t.mae) for t in trades], dtype="float64") if n \
        else np.empty(0, dtype="float64")
    mfe = np.array([float(t.mfe) for t in trades], dtype="float64") if n \
        else np.empty(0, dtype="float64")
    m["avg_mae"] = _mean(mae)
    m["avg_mfe"] = _mean(mfe)
    m["max_mae"] = float(mae.max()) if mae.size else None
    m["max_mfe"] = float(mfe.max()) if mfe.size else None
    if n == 0:
        rel.mark(("avg_mae", "avg_mfe", "max_mae", "max_mfe"), UNAVAILABLE,
                 "Unavailable - this run produced no trades.")


def _periods(result: BacktestResult, m: dict[str, Any], rel: _Reliability) -> None:
    """Best, worst and hit rate over calendar months of the equity curve."""
    try:
        monthly = monthly_returns(result)
    except BacktesterError:                    # pragma: no cover - defensive
        monthly = {"months": []}
    values = [v for row in monthly.get("months", []) for v in row
              if isinstance(v, (int, float)) and not isinstance(v, bool)
              and math.isfinite(float(v))]

    if not values:
        m["best_month_pct"] = None
        m["worst_month_pct"] = None
        m["profitable_months_pct"] = None
        m["months_counted"] = 0
        rel.mark(("best_month_pct", "worst_month_pct", "profitable_months_pct"),
                 UNAVAILABLE,
                 "Unavailable - the run does not cover a full calendar month of "
                 "equity.")
        return

    m["best_month_pct"] = float(max(values))
    m["worst_month_pct"] = float(min(values))
    m["profitable_months_pct"] = _div(
        sum(1 for v in values if v > 0) * 100.0, len(values), 0.0)
    m["months_counted"] = int(len(values))
    if len(values) < 6:
        rel.mark(("best_month_pct", "worst_month_pct", "profitable_months_pct"),
                 LOW_SAMPLE,
                 f"Based on {len(values)} calendar month(s). The best and worst "
                 f"month of a short run are just its two extreme weeks.")


def _activity(result: BacktestResult, m: dict[str, Any], rel: _Reliability,
              trades: Sequence[Trade], n: int) -> None:
    """Turnover and trade frequency.

    ``turnover`` is the total traded notional -- both legs of every trade -- as
    a multiple of starting capital.  It is the number that says whether a small
    edge is being handed back in costs.  When the result carries no instrument
    the point value is taken as 1.0, which understates a futures book; that is
    stated here and in the metrics document rather than hidden.
    """
    point_value = 1.0
    instrument = getattr(getattr(result, "bars", None), "instrument", None)
    pv = _finite(getattr(instrument, "point_value", None))
    if pv is not None and pv > 0:
        point_value = pv
    elif n:
        rel.mark("turnover", LOW_SAMPLE,
                 "This run carries no instrument, so notional is measured with a "
                 "point value of 1.0 and understates a leveraged product.")

    notional = 0.0
    for t in trades:
        qty = abs(float(t.quantity))
        notional += (abs(float(t.entry_price)) + abs(float(t.exit_price))) * qty * point_value
    start = float(m.get("starting_balance") or 0.0)
    m["total_traded_notional"] = float(notional)
    m["turnover"] = _div(notional, start, None)
    if m["turnover"] is None:
        rel.mark("turnover", UNAVAILABLE,
                 "Unavailable - turnover needs a positive starting balance.")

    years = float(m.get("years") or 0.0)
    m["trades_per_year"] = _div(float(n), years, None) if years > 0 else None
    if m["trades_per_year"] is None:
        rel.mark("trades_per_year", UNAVAILABLE,
                 "Unavailable - the run does not span enough time to express a "
                 "rate per year.")
    elif years < 1.0 / 12.0:
        rel.mark("trades_per_year", LOW_SAMPLE,
                 "The run covers less than a month, so a per-year rate is an "
                 "extrapolation from a very short window.")


def _exit_reasons(m: dict[str, Any], trades: Sequence[Trade], n: int) -> None:
    """P&L split by *why* each trade ended.

    This is the single most diagnostic table in the application: a strategy that
    claims to be a 1R barrier system but earns its money at the time stop is a
    directional bet wearing a costume, and only this breakdown shows it.
    """
    breakdown: dict[str, dict[str, Any]] = {}
    for t in trades:
        key = t.exit_reason.value if hasattr(t.exit_reason, "value") else str(t.exit_reason)
        entry = breakdown.setdefault(key, {
            "label": key.replace("_", " ").title(), "count": 0, "net_pnl": 0.0,
            "gross_profit": 0.0, "gross_loss": 0.0, "wins": 0, "losses": 0,
        })
        pnl = float(t.net_pnl)
        entry["count"] += 1
        entry["net_pnl"] += pnl
        if pnl > 0:
            entry["gross_profit"] += pnl
            entry["wins"] += 1
        elif pnl < 0:
            entry["gross_loss"] += pnl
            entry["losses"] += 1

    for entry in breakdown.values():
        count = int(entry["count"])
        entry["avg_pnl"] = _div(entry["net_pnl"], count, 0.0)
        entry["win_rate"] = _div(entry["wins"] * 100.0, count, 0.0)
        entry["share_pct"] = _div(count * 100.0, n, 0.0)
    m["exit_reason_breakdown"] = breakdown


# --------------------------------------------------------------------------
# Reliability passes
# --------------------------------------------------------------------------

def _low_sample_pass(m: dict[str, Any], rel: _Reliability, n: int,
                     curves: EquityCurves | None) -> None:
    """Flag everything whose sample is too small to support it."""
    if n == 0:
        rel.mark(_RATIO_METRICS, UNAVAILABLE,
                 "Unavailable - this run produced no trades.")
    elif n < MIN_TRADES_FOR_RATIOS:
        rel.mark(_RATIO_METRICS, LOW_SAMPLE,
                 f"Based on {n} trade(s). Below about {MIN_TRADES_FOR_RATIOS} "
                 f"trades this ratio is dominated by sampling noise: reordering "
                 f"or removing one trade moves it materially.")

    bars = int(len(curves)) if curves is not None else 0
    if bars < MIN_BARS_FOR_RISK_RATIOS or n < MIN_TRADES_FOR_RISK_RATIOS:
        rel.mark(("sharpe_ratio", "sortino_ratio", "annual_volatility_pct",
                  "downside_deviation", "annual_return_pct", "ulcer_index"),
                 LOW_SAMPLE,
                 f"Based on {bars} bar(s) and {n} trade(s). A risk-adjusted ratio "
                 f"needs at least {MIN_BARS_FOR_RISK_RATIOS} bars and "
                 f"{MIN_TRADES_FOR_RISK_RATIOS} trades before its denominator "
                 f"means anything.")

    if 0 < n < MIN_TRADES_FOR_RATIOS:
        rel.mark(("max_drawdown", "max_drawdown_pct"), LOW_SAMPLE,
                 f"Based on {n} trade(s). The worst drawdown of a short run is "
                 f"usually just its worst trade.")


def _sanitise(m: dict[str, Any], rel: _Reliability) -> None:
    """Last line of defence: no NaN escapes, and nothing degenerate goes unlabelled.

    Every metric above sets its own state deliberately.  This pass exists so
    that a value which slipped through as NaN or as an unexplained infinity is
    still reported honestly instead of being rendered as a number.
    """
    for key, value in list(m.items()):
        if isinstance(value, (dict, list, tuple, str)) or value is None:
            if value is None and rel.states.get(key, OK) == OK:
                rel.mark(key, UNAVAILABLE,
                         "Unavailable - this metric could not be computed from "
                         "this run.")
            continue
        if isinstance(value, bool) or isinstance(value, int):
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):        # pragma: no cover - defensive
            continue
        if math.isnan(v):
            m[key] = None
            rel.mark(key, UNAVAILABLE,
                     "Unavailable - the calculation had no defined value for this "
                     "run.")
        elif math.isinf(v):
            m[key] = math.inf if v > 0 else -math.inf
            if rel.states.get(key, OK) == OK:
                rel.mark(key, UNAVAILABLE,
                         "Unavailable - the denominator of this metric was zero, "
                         "so it is reported as infinite rather than as a number.")
        else:
            m[key] = v
