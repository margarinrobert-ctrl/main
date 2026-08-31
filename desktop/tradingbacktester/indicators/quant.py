"""Indicators that measure the market's *statistics* rather than its shape.

:mod:`.library` and :mod:`.extended` between them cover the standard chart
set -- averages, oscillators, bands, volume.  What they do not cover is the
family a quantitative reader reaches for first: how persistent returns are,
how much of the recent move was trend and how much was noise, where today sits
in its own recent distribution, and how asymmetric the downside has been.
Those are the measurements that decide *whether a rule should be trading at
all*, and none of them can be read off a price chart.

Everything here obeys the same three rules as the rest of the library:

* **Causal.**  Bar *i* uses bars up to and including *i*.
  ``tests/test_indicators.py`` truncates the series and asserts that earlier
  values do not move, for every registered indicator including these.
* **NaN, not a guess,** through the warm-up.  A window that is not full yet
  has no value, and filling it with zeros produces a warm-up that trades.
* **The published definition,** and where two are in common use, the docstring
  says which one this is.

One caution that applies to the whole module.  A regime measurement is not a
signal.  ``EFFICIENCY_RATIO`` says the last twenty bars were mostly one
direction; it does not say the next twenty will be, and a rule that trades it
directly is trading autocorrelation that has to be measured before it can be
relied on.  These are built to be *conditions* on a rule that already has an
edge, and the matched control in the Diagnose dialog is what says whether they
added anything.
"""

from __future__ import annotations

import numpy as np

from ..data.models import BarSeries
from .base import ParamSpec, REGISTRY, safe_divide
from .library import (_BLUE, _GREEN, _GREY, _ORANGE, _PINK, _PURPLE, _RED,
                      _TEAL, _YELLOW, _check_period, _empty, _f64,
                      _rolling_max, _rolling_mean, _rolling_min, _rolling_std,
                      _rolling_sum, _shift, _style, _true_range, log)

__all__: list[str] = []


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _log_returns(price: np.ndarray) -> np.ndarray:
    """``ln(p / p₋₁)``, NaN on the first bar and wherever price is not positive."""
    price = _f64(price)
    prior = _shift(price, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(price / prior)
    return np.where(np.isfinite(out), out, np.nan)


def _rolling_window(a: np.ndarray, period: int) -> np.ndarray:
    """A ``(n, period)`` view whose row *i* is the window ending at *i*.

    Rows before the window is full are NaN.  Built with stride tricks, so it
    allocates nothing: on half a million bars a 100-bar window would otherwise
    be a 400 MB copy.
    """
    a = _f64(a)
    n = a.size
    padded = np.concatenate([np.full(period - 1, np.nan), a])
    return np.lib.stride_tricks.sliding_window_view(padded, period)[:n]


def _nan_rolling(a: np.ndarray, period: int, func) -> np.ndarray:
    """Apply ``func`` down each rolling window, ignoring all-NaN rows."""
    windows = _rolling_window(a, period)
    with np.errstate(invalid="ignore"):
        out = func(windows)
    return np.asarray(out, dtype="float64")


# ---------------------------------------------------------------------------
# Trend quality
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "EFFICIENCY_RATIO", "Kaufman Efficiency Ratio", "Statistics",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _TEAL, "width": 1.4}),
    description="Net movement divided by the distance actually travelled: 1 "
                "is a straight line, 0 is pure noise. This is the ratio "
                "inside KAMA, exposed on its own so a rule can gate on it.",
    min_bars=20,
)
def efficiency_ratio(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """``|p - p₋ₙ| / Σ|p - p₋₁|`` over the window, in the range 0 to 1.

    Reported as a **ratio**, not a percentage, because that is how Kaufman
    defines it and how it appears inside KAMA. A window with no movement at
    all has no ratio and is NaN rather than 0: zero would say "pure noise",
    which is a different statement from "nothing happened".
    """
    price = _f64(bars.source_array(source))
    out = _empty(price.size)
    if not _check_period(period + 1, price.size, "EFFICIENCY_RATIO"):
        return out
    direction = np.abs(price - _shift(price, period))
    travelled = _rolling_sum(np.abs(price - _shift(price, 1)), period)
    return safe_divide(direction, travelled)


@REGISTRY.register(
    "RSQUARED", "Trend R-Squared", "Statistics",
    params=(ParamSpec("period", "Period", "int", 20, 3, 5000),),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _PURPLE, "width": 1.4}),
    description="How well a straight line fits the last N closes, from 0 to "
                "1. High means the move was orderly, not that it was large.",
    min_bars=20,
)
def rsquared(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """Coefficient of determination of price against bar number.

    Computed in closed form from the rolling sums rather than by fitting, so
    it costs one pass. A window with no variance in price -- a flat market --
    has an undefined fit and is NaN, which is the honest answer: a horizontal
    line fits perfectly and means nothing.
    """
    price = _f64(bars.source_array(source))
    n = price.size
    out = _empty(n)
    if not _check_period(period, n, "RSQUARED"):
        return out
    x = np.arange(float(period))
    x_mean = x.mean()
    x_var = float(((x - x_mean) ** 2).sum())
    if x_var <= 0:
        return out
    windows = _rolling_window(price, period)
    y_mean = windows.mean(axis=1)
    centred = windows - y_mean[:, None]
    covariance = centred @ (x - x_mean)
    y_var = (centred ** 2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        r2 = (covariance ** 2) / (x_var * y_var)
    return np.where(np.isfinite(r2), np.clip(r2, 0.0, 1.0), np.nan)


@REGISTRY.register(
    "AUTOCORR", "Return Autocorrelation", "Statistics",
    params=(ParamSpec("period", "Period", "int", 60, 5, 5000),
            ParamSpec("lag", "Lag in bars", "int", 1, 1, 500)),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _ORANGE, "width": 1.4}),
    description="Correlation of each return with the one N bars earlier. "
                "Positive means moves continued, negative means they "
                "reversed; near zero is what an efficient market looks like.",
    min_bars=60,
)
def autocorr(bars: BarSeries, period: int, lag: int, source: str) -> np.ndarray:
    """Pearson correlation of log returns against themselves at ``lag``.

    This is the number that decides whether a momentum rule and a mean
    reversion rule are even asking a sensible question of this instrument, and
    on most liquid series it sits close to zero -- which is a finding, not a
    defect in the calculation.
    """
    price = _f64(bars.source_array(source))
    returns = _log_returns(price)
    n = returns.size
    out = _empty(n)
    if not _check_period(period + lag + 1, n, "AUTOCORR"):
        return out
    lagged = _shift(returns, lag)
    both = np.isfinite(returns) & np.isfinite(lagged)
    a = np.where(both, returns, 0.0)
    b = np.where(both, lagged, 0.0)
    counts = _rolling_sum(both.astype("float64"), period)
    sum_a = _rolling_sum(a, period)
    sum_b = _rolling_sum(b, period)
    sum_aa = _rolling_sum(a * a, period)
    sum_bb = _rolling_sum(b * b, period)
    sum_ab = _rolling_sum(a * b, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = sum_ab - sum_a * sum_b / counts
        var_a = sum_aa - sum_a * sum_a / counts
        var_b = sum_bb - sum_b * sum_b / counts
        rho = cov / np.sqrt(var_a * var_b)
    # A window that is not mostly real observations has no correlation.
    enough = counts >= max(3.0, 0.8 * period)
    return np.where(enough & np.isfinite(rho), np.clip(rho, -1.0, 1.0), np.nan)


# ---------------------------------------------------------------------------
# Position within a distribution
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "PERCENTILE_RANK", "Percentile Rank", "Statistics",
    params=(ParamSpec("period", "Period", "int", 100, 5, 5000),),
    overlay=False, scale_hint="oscillator_0_100",
    plot_style=_style(value={"color": _BLUE, "width": 1.4}),
    description="Where the current value sits inside its own last N values, "
                "0 to 100. Scale-free, so it compares across instruments in "
                "a way a raw level never can.",
    min_bars=100,
)
def percentile_rank(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """Share of the window at or below the current value, times 100.

    Inclusive of the current bar, so a new high reads 100 rather than
    ``(n-1)/n``. That choice matters for a rule written as ``rank > 99``: on
    the exclusive definition a 100-bar window can never reach it.
    """
    price = _f64(bars.source_array(source))
    n = price.size
    out = _empty(n)
    if not _check_period(period, n, "PERCENTILE_RANK"):
        return out
    windows = _rolling_window(price, period)
    current = price[:, None]
    with np.errstate(invalid="ignore"):
        below = np.sum(windows <= current, axis=1).astype("float64")
        valid = np.sum(np.isfinite(windows), axis=1).astype("float64")
    ranked = 100.0 * safe_divide(below, valid)
    return np.where(valid >= period, ranked, np.nan)


@REGISTRY.register(
    "DRAWDOWN", "Drawdown From Rolling High", "Statistics",
    params=(ParamSpec("period", "Lookback", "int", 250, 2, 20000),),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _RED, "width": 1.4}),
    description="How far price is below its highest close of the last N "
                "bars, as a negative percentage. Zero means at the high.",
    min_bars=250,
)
def drawdown(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """``100 * (p / rolling max - 1)``, so it is zero or negative.

    The instrument's own drawdown, not the strategy's: this is a market state
    a rule can condition on, and it is a different series from the equity
    drawdown the metrics report.
    """
    price = _f64(bars.source_array(source))
    out = _empty(price.size)
    if not _check_period(period, price.size, "DRAWDOWN"):
        return out
    peak = _rolling_max(price, period)
    return 100.0 * (safe_divide(price, peak) - 1.0)


# ---------------------------------------------------------------------------
# Asymmetry and tails
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "SEMIVAR_RATIO", "Semivariance Ratio", "Statistics",
    params=(ParamSpec("period", "Period", "int", 60, 5, 5000),),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _PINK, "width": 1.4}),
    description="Downside variance divided by upside variance over the "
                "window. Above 1 means falls have been the larger moves.",
    min_bars=60,
)
def semivariance_ratio(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """``Σ(negative returns²) / Σ(positive returns²)`` over the window.

    A scale-free reading of asymmetry: unlike skewness it does not need a
    third moment, so it is far steadier on the few hundred bars a rolling
    window actually has. A window with no positive returns at all has no
    ratio and is NaN rather than infinity.
    """
    returns = _log_returns(_f64(bars.source_array(source)))
    out = _empty(returns.size)
    if not _check_period(period + 1, returns.size, "SEMIVAR_RATIO"):
        return out
    clean = np.where(np.isfinite(returns), returns, 0.0)
    down = _rolling_sum(np.where(clean < 0, clean * clean, 0.0), period)
    up = _rolling_sum(np.where(clean > 0, clean * clean, 0.0), period)
    return safe_divide(down, up)


@REGISTRY.register(
    "SKEW", "Rolling Return Skew", "Statistics",
    params=(ParamSpec("period", "Period", "int", 60, 8, 5000),),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _YELLOW, "width": 1.4}),
    description="Third standardised moment of log returns over the window. "
                "Negative means the large moves have been downward.",
    min_bars=60,
)
def skew(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """Population skewness of log returns.

    Population rather than sample: the sample correction is unstable on the
    short windows this is used with, and the two differ by a factor that is
    constant for a fixed period, so no rule threshold changes meaning.
    """
    returns = _log_returns(_f64(bars.source_array(source)))
    out = _empty(returns.size)
    if not _check_period(period + 1, returns.size, "SKEW"):
        return out
    # From rolling power sums rather than nan-aggregates over a window view:
    # the warm-up rows are then ordinary arithmetic on zeros instead of an
    # all-NaN slice, which numpy reports as a RuntimeWarning on every call.
    finite = np.isfinite(returns)
    x = np.where(finite, returns, 0.0)
    counts = _rolling_sum(finite.astype("float64"), period)
    s1 = _rolling_sum(x, period)
    s2 = _rolling_sum(x * x, period)
    s3 = _rolling_sum(x * x * x, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean = s1 / counts
        m2 = s2 / counts - mean * mean
        m3 = s3 / counts - 3.0 * mean * s2 / counts + 2.0 * mean ** 3
        value = m3 / np.power(m2, 1.5)
    enough = counts >= max(3.0, period - 1.0)
    return np.where(enough & np.isfinite(value), value, np.nan)


@REGISTRY.register(
    "CVAR", "Rolling Conditional Value At Risk", "Statistics",
    params=(ParamSpec("period", "Period", "int", 100, 10, 5000),
            ParamSpec("tail", "Tail %", "float", 5.0, 0.5, 49.0, step=0.5)),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _RED, "width": 1.4}),
    description="Mean of the worst N% of returns in the window, as a "
                "percentage. What a bad bar has actually looked like lately.",
    min_bars=100,
)
def cvar(bars: BarSeries, period: int, tail: float, source: str) -> np.ndarray:
    """Expected shortfall of log returns at the given tail.

    The **mean of the tail**, not the quantile at its edge: value-at-risk
    reports the best of the bad cases, which is precisely the number that
    understates a bad day.
    """
    returns = _log_returns(_f64(bars.source_array(source)))
    n = returns.size
    out = _empty(n)
    if not _check_period(period + 1, n, "CVAR"):
        return out
    take = max(1, int(round(period * float(tail) / 100.0)))
    windows = _rolling_window(returns, period)
    filled = np.where(np.isfinite(windows), windows, np.inf)
    worst = np.partition(filled, take - 1, axis=1)[:, :take]
    complete = np.isfinite(worst).all(axis=1)
    safe = np.where(complete[:, None], worst, 0.0)
    value = 100.0 * safe.mean(axis=1)
    counts = np.sum(np.isfinite(windows), axis=1)
    return np.where(complete & (counts >= period - 1), value, np.nan)


# ---------------------------------------------------------------------------
# Volatility regime
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "VOL_RATIO", "Volatility Ratio", "Statistics",
    params=(ParamSpec("fast", "Recent period", "int", 10, 2, 5000),
            ParamSpec("slow", "Baseline period", "int", 100, 3, 20000)),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _GREEN, "width": 1.4}),
    description="Recent true-range average divided by a longer one. Above 1 "
                "means the market is livelier than its own baseline.",
    min_bars=100, uses_source=False,
)
def vol_ratio(bars: BarSeries, fast: int, slow: int) -> np.ndarray:
    """Short average true range over long average true range.

    Built on true range rather than close-to-close returns so that a gap is
    counted as movement, which is the whole reason a stop is sized on ATR
    rather than on standard deviation.
    """
    out = _empty(len(bars))
    if not _check_period(max(fast, slow) + 1, len(bars), "VOL_RATIO"):
        return out
    tr = _true_range(bars)
    return safe_divide(_rolling_mean(tr, int(fast)),
                       _rolling_mean(tr, int(slow)))


@REGISTRY.register(
    "ZSCORE_VOL", "Volatility Z-Score", "Statistics",
    params=(ParamSpec("period", "Volatility period", "int", 20, 2, 5000),
            ParamSpec("lookback", "Baseline period", "int", 250, 5, 20000)),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _GREY, "width": 1.4}),
    description="How unusual current volatility is against its own history, "
                "in standard deviations. Zero is typical for this market.",
    min_bars=250,
)
def zscore_vol(bars: BarSeries, period: int, lookback: int,
               source: str) -> np.ndarray:
    """Standardised realised volatility.

    Trading "high volatility" as an absolute number ties a rule to one
    instrument and one era; standardising it against the instrument's own
    recent history is what lets the same threshold mean the same thing on a
    different market.
    """
    returns = _log_returns(_f64(bars.source_array(source)))
    n = returns.size
    out = _empty(n)
    if not _check_period(period + lookback + 1, n, "ZSCORE_VOL"):
        return out
    volatility = _rolling_std(np.where(np.isfinite(returns), returns, np.nan),
                              int(period))
    mean = _rolling_mean(volatility, int(lookback))
    spread = _rolling_std(volatility, int(lookback))
    return safe_divide(volatility - mean, spread)


# ---------------------------------------------------------------------------
# Well-known composites the standard set is missing
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "CONNORS_RSI", "Connors RSI", "Oscillators",
    params=(ParamSpec("rsi_period", "RSI period", "int", 3, 2, 5000),
            ParamSpec("streak_period", "Streak RSI period", "int", 2, 2, 5000),
            ParamSpec("rank_period", "Rank period", "int", 100, 2, 5000)),
    overlay=False, scale_hint="oscillator_0_100",
    plot_style=_style(value={"color": _ORANGE, "width": 1.5}),
    description="The average of a short RSI, an RSI of the up/down streak "
                "length, and the percentile rank of the one-bar return. "
                "Connors' short-term mean-reversion oscillator.",
    min_bars=100,
)
def connors_rsi(bars: BarSeries, rsi_period: int, streak_period: int,
                rank_period: int, source: str) -> np.ndarray:
    """Connors' three-component RSI, equally weighted.

    The percentile-rank component is over the **previous** ``rank_period``
    one-bar returns and excludes the current one, which is Connors'
    definition; including it would let a single new extreme move the reading
    it is being compared against.
    """
    price = _f64(bars.source_array(source))
    n = price.size
    out = _empty(n)
    if not _check_period(rank_period + 2, n, "CONNORS_RSI"):
        return out

    change = price - _shift(price, 1)
    streak = _streak(change)
    ret = 100.0 * safe_divide(change, _shift(price, 1))

    prior = _shift(ret, 1)
    windows = _rolling_window(prior, int(rank_period))
    with np.errstate(invalid="ignore"):
        below = np.sum(windows < ret[:, None], axis=1).astype("float64")
        valid = np.sum(np.isfinite(windows), axis=1).astype("float64")
    rank = 100.0 * safe_divide(below, valid)
    rank = np.where(valid >= rank_period, rank, np.nan)

    return (_wilder_rsi(price, int(rsi_period))
            + _wilder_rsi(streak, int(streak_period)) + rank) / 3.0


def _streak(change: np.ndarray) -> np.ndarray:
    """Consecutive up bars as ``+k``, down bars as ``-k``, unchanged as 0."""
    change = _f64(change)
    out = np.zeros(change.size, dtype="float64")
    run = 0.0
    for i in range(change.size):
        value = change[i]
        if not np.isfinite(value) or value == 0.0:
            run = 0.0
        elif value > 0:
            run = run + 1.0 if run > 0 else 1.0
        else:
            run = run - 1.0 if run < 0 else -1.0
        out[i] = run
    return out


def _wilder_rsi(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's RSI over an arbitrary series, matching ``library.rsi``."""
    from .library import _rma

    values = _f64(values)
    out = _empty(values.size)
    if values.size <= period:
        return out
    change = values - _shift(values, 1)
    gain = _rma(np.where(change > 0, change, 0.0), period)
    loss = _rma(np.where(change < 0, -change, 0.0), period)
    strength = safe_divide(gain, loss)
    rsi = 100.0 - 100.0 / (1.0 + strength)
    # An all-gain window has no loss to divide by; Wilder's limit is 100.
    return np.where(np.isfinite(rsi), rsi,
                    np.where(np.isfinite(gain) & (gain > 0), 100.0, np.nan))


@REGISTRY.register(
    "COPPOCK", "Coppock Curve", "Momentum",
    params=(ParamSpec("long_roc", "Long rate of change", "int", 14, 2, 5000),
            ParamSpec("short_roc", "Short rate of change", "int", 11, 2, 5000),
            ParamSpec("period", "Weighted average period", "int", 10, 2, 5000)),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _PURPLE, "width": 1.5}),
    description="A weighted average of two rates of change. Coppock's "
                "long-term bottom indicator, defined on monthly bars and "
                "used on any timeframe since.",
    min_bars=40,
)
def coppock(bars: BarSeries, long_roc: int, short_roc: int, period: int,
            source: str) -> np.ndarray:
    """``WMA(ROC(long) + ROC(short), period)``.

    Coppock defined this on **monthly** closes with 14, 11 and 10. It is
    registered with those defaults; on a 5-minute chart the same numbers
    describe fifty minutes, which is a different indicator with the same name.
    """
    price = _f64(bars.source_array(source))
    n = price.size
    out = _empty(n)
    if not _check_period(max(long_roc, short_roc) + period, n, "COPPOCK"):
        return out
    prior_long = _shift(price, int(long_roc))
    prior_short = _shift(price, int(short_roc))
    combined = (100.0 * safe_divide(price - prior_long, prior_long)
                + 100.0 * safe_divide(price - prior_short, prior_short))
    return _wma(combined, int(period))


def _wma(a: np.ndarray, period: int) -> np.ndarray:
    """Linearly weighted moving average, heaviest on the most recent bar."""
    a = _f64(a)
    if period <= 0 or a.size < period:
        return _empty(a.size)
    weights = np.arange(1.0, period + 1.0)
    weights /= weights.sum()
    windows = _rolling_window(a, period)
    with np.errstate(invalid="ignore"):
        return windows @ weights


log.debug("quantitative indicator library registered")
