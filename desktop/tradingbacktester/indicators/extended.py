"""The rest of the standard indicator set.

:mod:`.library` holds the forty-eight indicators the rest of the application
depends on by name -- the ones the strategy compiler, the finder and the
research modules reference directly. This module holds the thirty that a
trader coming from another platform expects to find and that nothing here
requires, kept separate so that a mistake in an adaptive average cannot stop
``REQUIRED_KEYS`` from registering.

Everything here obeys the same three rules as the core library:

* **Causal.** The value at bar *i* uses bars up to and including *i* and
  nothing after. `tests/test_indicators.py` truncates the series and asserts
  earlier values do not move, for every registered indicator including these.
* **NaN, not a guess,** where the indicator is not yet defined. A warm-up
  filled with zeros or with the first value is a warm-up that trades.
* **The published definition,** not a convenient approximation. Where two
  definitions are in common use the docstring says which one this is, because
  a chart that disagrees with the user's other platform is a bug report either
  way and the only defence is being explicit.

Two indicators that a "complete" list would contain are deliberately absent:
**+DI/-DI** and the **Aroon oscillator** already ship as extra outputs of
``ADX`` and ``AROON``, and registering them again would give the same series
two names and two sets of parameters to keep in step.
"""

from __future__ import annotations

import numpy as np

from ..core.errors import IndicatorError
from ..data.models import BarSeries
from .base import ParamSpec, REGISTRY, safe_divide
from .library import (_BLUE, _GREEN, _GREY, _ORANGE, _PINK, _PURPLE, _RED,
                      _TEAL, _YELLOW, _check_period, _ema, _empty, _f64,
                      _rolling_max, _rolling_mean, _rolling_min, _rolling_std,
                      _rolling_sum, _rma, _shift, _style, _true_range,
                      log)

# ---------------------------------------------------------------------------
# helpers used only here
# ---------------------------------------------------------------------------


def _hl2(bars: BarSeries) -> np.ndarray:
    return (_f64(bars.high) + _f64(bars.low)) / 2.0


def _roc(a: np.ndarray, period: int) -> np.ndarray:
    """Percentage change over ``period`` bars."""
    prior = _shift(a, period)
    return 100.0 * safe_divide(_f64(a) - prior, prior)


def _swma(a: np.ndarray) -> np.ndarray:
    """The symmetric 4-bar weighted average ``(x + 2x₋₁ + 2x₋₂ + x₋₃)/6``.

    Pine calls this ``ta.swma``; the Relative Vigor Index is defined in terms
    of it. Despite the name it is not centred -- it looks back four bars -- so
    it is causal.
    """
    a = _f64(a)
    return (a + 2.0 * _shift(a, 1) + 2.0 * _shift(a, 2) + _shift(a, 3)) / 6.0


def _stochastic(a: np.ndarray, period: int) -> np.ndarray:
    """``100 * (a - min) / (max - min)`` over a rolling window."""
    low = _rolling_min(a, period)
    high = _rolling_max(a, period)
    return 100.0 * safe_divide(_f64(a) - low, high - low)


# ---------------------------------------------------------------------------
# Moving averages
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "KAMA", "Kaufman Adaptive Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Efficiency period", "int", 10, 2, 5000),
            ParamSpec("fast", "Fast period", "int", 2, 1, 5000),
            ParamSpec("slow", "Slow period", "int", 30, 2, 5000)),
    overlay=True, scale_hint="price",
    plot_style=_style(value={"color": _PURPLE, "width": 1.6}),
    description="An average whose smoothing constant follows Kaufman's "
                "efficiency ratio: it tracks price closely in a trend and "
                "flattens in chop.", min_bars=10,
)
def kama(bars: BarSeries, period: int, fast: int, slow: int,
         source: str) -> np.ndarray:
    """Kaufman's adaptive moving average.

    The smoothing constant changes every bar, so unlike every other average
    here this genuinely cannot be written as one linear recursion and is a
    Python loop. It costs about a quarter of a second on half a million bars,
    which is why it lives out here rather than in a hot path.
    """
    price = _f64(bars.source_array(source))
    n = len(price)
    out = _empty(n)
    if not _check_period(period + 1, n, "KAMA"):
        return out

    change = np.abs(price - _shift(price, period))
    volatility = _rolling_sum(np.abs(price - _shift(price, 1)), period)
    ratio = safe_divide(change, volatility, fill=0.0)
    fastest = 2.0 / (float(fast) + 1.0)
    slowest = 2.0 / (float(slow) + 1.0)
    constant = (ratio * (fastest - slowest) + slowest) ** 2

    start = -1
    ok = np.isfinite(constant) & np.isfinite(price)
    found = np.flatnonzero(ok)
    if found.size == 0:
        return out
    start = int(found[0])
    value = float(price[start])
    out[start] = value
    for i in range(start + 1, n):
        c = constant[i]
        p = price[i]
        if not (np.isfinite(c) and np.isfinite(p)):
            out[i] = value
            continue
        value += float(c) * (float(p) - value)
        out[i] = value
    return out


@REGISTRY.register(
    "ZLEMA", "Zero-Lag Exponential Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),),
    overlay=True, scale_hint="price",
    plot_style=_style(value={"color": _TEAL, "width": 1.6}),
    description="An EMA of price plus its own recent momentum, which removes "
                "most of the lag at the cost of overshooting turns.",
    min_bars=20,
)
def zlema(bars: BarSeries, period: int, source: str) -> np.ndarray:
    price = _f64(bars.source_array(source))
    lag = (int(period) - 1) // 2
    return _ema(price + (price - _shift(price, lag)), int(period))


@REGISTRY.register(
    "ALMA", "Arnaud Legoux Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 9, 2, 2000),
            ParamSpec("offset", "Offset", "float", 0.85, 0.0, 1.0, 0.05),
            ParamSpec("sigma", "Sigma", "float", 6.0, 0.1, 100.0, 0.5)),
    overlay=True, scale_hint="price",
    plot_style=_style(value={"color": _PINK, "width": 1.6}),
    description="A Gaussian-weighted average whose peak sits `offset` of the "
                "way along the window: 1.0 is responsive, 0.0 is smooth.",
    min_bars=9,
)
def alma(bars: BarSeries, period: int, offset: float, sigma: float,
         source: str) -> np.ndarray:
    price = _f64(bars.source_array(source))
    n = len(price)
    window = int(period)
    out = _empty(n)
    if not _check_period(window, n, "ALMA"):
        return out
    if sigma <= 0:
        raise IndicatorError("ALMA's sigma must be greater than zero.")

    centre = float(offset) * (window - 1)
    spread = window / float(sigma)
    index = np.arange(window, dtype="float64")
    weights = np.exp(-((index - centre) ** 2) / (2.0 * spread * spread))
    total = weights.sum()
    if not np.isfinite(total) or total <= 0:
        raise IndicatorError(
            "ALMA's weights summed to zero, which makes the average "
            "undefined; try a smaller sigma or a longer period.")
    weights /= total
    # 'valid' correlation with the reversed kernel is the weighted window sum,
    # and NaN in the source propagates through it as it should.
    out[window - 1:] = np.convolve(price, weights[::-1], mode="valid")
    return out


@REGISTRY.register(
    "T3", "Tillson T3 Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 10, 2, 2000),
            ParamSpec("volume_factor", "Volume factor", "float", 0.7, 0.0, 1.0,
                      0.05)),
    overlay=True, scale_hint="price",
    plot_style=_style(value={"color": _ORANGE, "width": 1.6}),
    description="Six nested EMAs combined so that the result is smooth without "
                "the lag six averages would normally cost.", min_bars=10,
)
def t3(bars: BarSeries, period: int, volume_factor: float,
       source: str) -> np.ndarray:
    price = _f64(bars.source_array(source))
    p = int(period)
    e1 = _ema(price, p)
    e2 = _ema(e1, p)
    e3 = _ema(e2, p)
    e4 = _ema(e3, p)
    e5 = _ema(e4, p)
    e6 = _ema(e5, p)
    v = float(volume_factor)
    c1 = -v ** 3
    c2 = 3.0 * v * v + 3.0 * v ** 3
    c3 = -6.0 * v * v - 3.0 * v - 3.0 * v ** 3
    c4 = 1.0 + 3.0 * v + v ** 3 + 3.0 * v * v
    return c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3


@REGISTRY.register(
    "MCGINLEY", "McGinley Dynamic", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 14, 2, 5000),
            ParamSpec("factor", "Factor", "float", 0.6, 0.05, 5.0, 0.05)),
    overlay=True, scale_hint="price",
    plot_style=_style(value={"color": _YELLOW, "width": 1.6}),
    description="An average that speeds up when price runs away from it and "
                "slows when price returns, so it is rarely whipsawed.",
    min_bars=14,
)
def mcginley(bars: BarSeries, period: int, factor: float,
             source: str) -> np.ndarray:
    """McGinley's dynamic line.

    The denominator contains ``(price / line)**4``, so a line that reaches zero
    or a ratio that explodes would produce an infinity. Both are guarded: a
    non-finite step leaves the line where it was, which is the same thing the
    formula does in the limit and is at least a number a chart can draw.
    """
    price = _f64(bars.source_array(source))
    n = len(price)
    out = _empty(n)
    found = np.flatnonzero(np.isfinite(price))
    if found.size == 0:
        return out
    start = int(found[0])
    value = float(price[start])
    out[start] = value
    scale = float(factor) * float(period)
    for i in range(start + 1, n):
        p = price[i]
        if not np.isfinite(p):
            out[i] = value
            continue
        if value == 0.0:
            value = float(p)
        else:
            ratio = float(p) / value
            step = scale * (ratio ** 4)
            if np.isfinite(step) and step != 0.0:
                candidate = value + (float(p) - value) / step
                if np.isfinite(candidate):
                    value = candidate
        out[i] = value
    return out


# ---------------------------------------------------------------------------
# Oscillators
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "AO", "Awesome Oscillator", "Oscillators",
    params=(ParamSpec("fast", "Fast period", "int", 5, 1, 2000),
            ParamSpec("slow", "Slow period", "int", 34, 2, 5000)),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(value={"color": _BLUE, "kind": "histogram"}),
    description="Bill Williams' difference of two simple averages of the bar "
                "midpoint. Above zero is bullish momentum.", min_bars=34,
)
def awesome(bars: BarSeries, fast: int, slow: int) -> np.ndarray:
    mid = _hl2(bars)
    return _rolling_mean(mid, int(fast)) - _rolling_mean(mid, int(slow))


@REGISTRY.register(
    "CMO", "Chande Momentum Oscillator", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 14, 1, 5000),),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _PURPLE}),
    description="Net momentum as a percentage of total movement, from -100 to "
                "+100. Unlike RSI it is not smoothed, so it is more decisive "
                "and noisier.", min_bars=14,
)
def cmo(bars: BarSeries, period: int, source: str) -> np.ndarray:
    price = _f64(bars.source_array(source))
    change = price - _shift(price, 1)
    gains = _rolling_sum(np.where(change > 0, change, 0.0), int(period))
    losses = _rolling_sum(np.where(change < 0, -change, 0.0), int(period))
    # The first difference is NaN, so re-blank the window it contaminates:
    # np.where would otherwise have turned it into a zero.
    out = 100.0 * safe_divide(gains - losses, gains + losses)
    out[:int(period)] = np.nan
    return out


@REGISTRY.register(
    "PPO", "Percentage Price Oscillator", "Oscillators",
    params=(ParamSpec("fast", "Fast period", "int", 12, 1, 5000),
            ParamSpec("slow", "Slow period", "int", 26, 2, 5000),
            ParamSpec("signal", "Signal period", "int", 9, 1, 5000)),
    outputs=("ppo", "signal", "histogram"),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(ppo={"color": _BLUE}, signal={"color": _ORANGE},
                      histogram={"color": _GREY, "kind": "histogram"}),
    description="MACD expressed as a percentage of the slow average, so it is "
                "comparable between instruments at different price levels.",
    min_bars=26,
)
def ppo(bars: BarSeries, fast: int, slow: int, signal: int,
        source: str) -> dict[str, np.ndarray]:
    price = _f64(bars.source_array(source))
    quick = _ema(price, int(fast))
    slow_line = _ema(price, int(slow))
    line = 100.0 * safe_divide(quick - slow_line, slow_line)
    signal_line = _ema(line, int(signal))
    return {"ppo": line, "signal": signal_line,
            "histogram": line - signal_line}


@REGISTRY.register(
    "TRIX", "TRIX", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 15, 1, 2000),
            ParamSpec("signal", "Signal period", "int", 9, 1, 2000)),
    outputs=("trix", "signal"),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(trix={"color": _TEAL}, signal={"color": _ORANGE}),
    description="The one-bar percentage change of a triple-smoothed EMA. The "
                "triple smoothing removes cycles shorter than the period.",
    min_bars=15,
)
def trix(bars: BarSeries, period: int, signal: int,
         source: str) -> dict[str, np.ndarray]:
    price = _f64(bars.source_array(source))
    p = int(period)
    triple = _ema(_ema(_ema(price, p), p), p)
    line = 100.0 * safe_divide(triple - _shift(triple, 1), _shift(triple, 1))
    return {"trix": line, "signal": _ema(line, int(signal))}


@REGISTRY.register(
    "DPO", "Detrended Price Oscillator", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _PINK}),
    description="A past close minus the moving average, which strips the trend "
                "out and leaves the cycle. Causal: the CENTRED version most "
                "platforms draw is shifted into the future and cannot be "
                "traded.", min_bars=20,
)
def dpo(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """The detrended price oscillator, in its tradeable form.

    Charting packages usually plot DPO displaced forward by ``period/2 + 1``
    bars, which lines the cycle up prettily and means the value drawn above
    today's bar was not knowable today. This returns the undisplaced series:
    ``close[i - (period/2 + 1)] - SMA(period)[i]``, every term of which is
    known at bar ``i``. It will therefore not sit exactly on top of the same
    study elsewhere, and that is the intended difference.
    """
    price = _f64(bars.source_array(source))
    back = int(period) // 2 + 1
    return _shift(price, back) - _rolling_mean(price, int(period))


@REGISTRY.register(
    "KST", "Know Sure Thing", "Oscillators",
    params=(ParamSpec("signal", "Signal period", "int", 9, 1, 2000),),
    outputs=("kst", "signal"),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(kst={"color": _BLUE}, signal={"color": _RED}),
    description="Pring's weighted sum of four smoothed rates of change, which "
                "reads short and long momentum in one line.", min_bars=45,
)
def kst(bars: BarSeries, signal: int, source: str) -> dict[str, np.ndarray]:
    """Pring's original settings: ROC 10/15/20/30 smoothed 10/10/10/15."""
    price = _f64(bars.source_array(source))
    parts = ((10, 10, 1.0), (15, 10, 2.0), (20, 10, 3.0), (30, 15, 4.0))
    line = _empty(len(price))
    line[:] = 0.0
    for roc_period, smooth, weight in parts:
        line = line + weight * _rolling_mean(_roc(price, roc_period), smooth)
    return {"kst": line, "signal": _rolling_mean(line, int(signal))}


@REGISTRY.register(
    "FISHER", "Fisher Transform", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 9, 2, 2000),),
    outputs=("fisher", "trigger"),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(fisher={"color": _GREEN}, trigger={"color": _RED}),
    description="Ehlers' transform of the normalised midpoint into something "
                "closer to a normal distribution, which makes its extremes "
                "sharp instead of gradual.", min_bars=9,
)
def fisher(bars: BarSeries, period: int) -> dict[str, np.ndarray]:
    """Ehlers' Fisher transform.

    Two coupled recursions with a clamp, so it is a loop. The clamp at
    +/-0.999 is not cosmetic: the transform is ``ln((1+x)/(1-x))``, which is
    infinite at exactly +/-1, and price touching the top of its own range makes
    that happen on ordinary data rather than as an edge case.
    """
    mid = _hl2(bars)
    n = len(mid)
    low = _rolling_min(mid, int(period))
    high = _rolling_max(mid, int(period))
    span = high - low
    raw = safe_divide(mid - low, span, fill=0.5)

    line = _empty(n)
    trigger = _empty(n)
    value = 0.0
    previous = 0.0
    started = False
    for i in range(n):
        r = raw[i]
        if not np.isfinite(r):
            continue
        value = 0.66 * (2.0 * float(r) - 1.0) + 0.67 * value
        value = min(0.999, max(-0.999, value))
        current = 0.5 * np.log((1.0 + value) / (1.0 - value)) + 0.5 * previous
        line[i] = current
        trigger[i] = previous if started else np.nan
        previous = current
        started = True
    return {"fisher": line, "trigger": trigger}


@REGISTRY.register(
    "BOP", "Balance of Power", "Oscillators",
    params=(ParamSpec("period", "Smoothing", "int", 14, 1, 5000),),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(value={"color": _YELLOW}),
    description="Where the close sat between the open and the extremes, "
                "smoothed. Positive means buyers finished the bar in control.",
    min_bars=14,
)
def bop(bars: BarSeries, period: int) -> np.ndarray:
    span = _f64(bars.high) - _f64(bars.low)
    raw = safe_divide(_f64(bars.close) - _f64(bars.open), span, fill=0.0)
    return _rolling_mean(raw, int(period))


@REGISTRY.register(
    "RVGI", "Relative Vigor Index", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 10, 1, 2000),),
    outputs=("rvgi", "signal"),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(rvgi={"color": _BLUE}, signal={"color": _ORANGE}),
    description="Close-minus-open against high-minus-low, on the theory that "
                "price closes above its open in an uptrend.", min_bars=13,
)
def rvgi(bars: BarSeries, period: int) -> dict[str, np.ndarray]:
    numerator = _swma(_f64(bars.close) - _f64(bars.open))
    denominator = _swma(_f64(bars.high) - _f64(bars.low))
    line = safe_divide(_rolling_sum(numerator, int(period)),
                       _rolling_sum(denominator, int(period)))
    return {"rvgi": line, "signal": _swma(line)}


@REGISTRY.register(
    "SMI", "Stochastic Momentum Index", "Oscillators",
    params=(ParamSpec("period", "Range period", "int", 10, 2, 5000),
            ParamSpec("smooth_1", "First smoothing", "int", 3, 1, 2000),
            ParamSpec("smooth_2", "Second smoothing", "int", 3, 1, 2000),
            ParamSpec("signal", "Signal period", "int", 3, 1, 2000)),
    outputs=("smi", "signal"),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(smi={"color": _PURPLE}, signal={"color": _ORANGE}),
    description="Where the close sits relative to the MIDPOINT of the range "
                "rather than its low, double-smoothed. Runs -100 to +100.",
    min_bars=10,
)
def smi(bars: BarSeries, period: int, smooth_1: int, smooth_2: int,
        signal: int) -> dict[str, np.ndarray]:
    high = _rolling_max(_f64(bars.high), int(period))
    low = _rolling_min(_f64(bars.low), int(period))
    centre = _f64(bars.close) - (high + low) / 2.0
    span = high - low
    top = _ema(_ema(centre, int(smooth_1)), int(smooth_2))
    bottom = _ema(_ema(span, int(smooth_1)), int(smooth_2)) / 2.0
    line = 100.0 * safe_divide(top, bottom)
    return {"smi": line, "signal": _ema(line, int(signal))}


@REGISTRY.register(
    "STC", "Schaff Trend Cycle", "Oscillators",
    params=(ParamSpec("fast", "Fast period", "int", 23, 1, 5000),
            ParamSpec("slow", "Slow period", "int", 50, 2, 5000),
            ParamSpec("cycle", "Cycle period", "int", 10, 2, 2000)),
    overlay=False, scale_hint="oscillator_0_100",
    plot_style=_style(value={"color": _GREEN}),
    description="A stochastic taken twice over the MACD line, which turns a "
                "trend indicator into a 0-100 cycle that leads it.",
    min_bars=50,
)
def stc(bars: BarSeries, fast: int, slow: int, cycle: int,
        source: str) -> np.ndarray:
    """Schaff's trend cycle.

    The smoothing between the two stochastic passes is an EMA with alpha 0.5,
    which is exactly ``EMA(3)`` -- ``alpha = 2/(n+1) = 0.5`` at ``n = 3`` --
    so it reuses the vectorised EMA rather than a second recursion.
    """
    price = _f64(bars.source_array(source))
    macd = _ema(price, int(fast)) - _ema(price, int(slow))
    first = _ema(_stochastic(macd, int(cycle)), 3)
    return _ema(_stochastic(first, int(cycle)), 3)


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "ICHIMOKU", "Ichimoku Cloud", "Trend",
    params=(ParamSpec("conversion", "Conversion (Tenkan)", "int", 9, 1, 2000),
            ParamSpec("base", "Base (Kijun)", "int", 26, 1, 5000),
            ParamSpec("span", "Span B period", "int", 52, 1, 5000),
            ParamSpec("displacement", "Displacement", "int", 26, 0, 2000)),
    outputs=("conversion", "base", "span_a", "span_b"),
    overlay=True, scale_hint="price", uses_source=False,
    plot_style=_style(conversion={"color": _BLUE},
                      base={"color": _RED},
                      span_a={"color": _GREEN},
                      span_b={"color": _ORANGE}),
    description="Tenkan, Kijun and the two cloud edges. The cloud is drawn "
                "where a trader can actually see it at the bar: displaced "
                "BACKWARD into the present, not forward into the future.",
    min_bars=52,
)
def ichimoku(bars: BarSeries, conversion: int, base: int, span: int,
             displacement: int) -> dict[str, np.ndarray]:
    """Ichimoku, with the displacement resolved in the tradeable direction.

    On a chart the two spans are plotted ``displacement`` bars into the FUTURE,
    so the cloud above bar *i* was computed at bar ``i - displacement``. That
    is what a trader compares price against, and it is what this returns:
    ``span_a[i]`` is the value computed at ``i - displacement``. Reading the
    chart's own forward-plotted number at bar *i* would be reading a value
    derived from bars that had not happened.

    **Chikou is not returned.** The lagging span is today's close plotted in
    the past; at bar *i* its charted value comes from bar ``i + displacement``.
    There is no causal version of it, so rather than ship something that looks
    usable and leaks the future, it is absent.
    """
    high, low = _f64(bars.high), _f64(bars.low)

    def middle(period: int) -> np.ndarray:
        return (_rolling_max(high, int(period))
                + _rolling_min(low, int(period))) / 2.0

    tenkan = middle(conversion)
    kijun = middle(base)
    lead = max(0, int(displacement))
    return {"conversion": tenkan, "base": kijun,
            "span_a": _shift((tenkan + kijun) / 2.0, lead),
            "span_b": _shift(middle(span), lead)}


@REGISTRY.register(
    "VORTEX", "Vortex Indicator", "Trend",
    params=(ParamSpec("period", "Period", "int", 14, 1, 5000),),
    outputs=("plus", "minus"),
    overlay=False, scale_hint="price", uses_source=False,
    plot_style=_style(plus={"color": _GREEN}, minus={"color": _RED}),
    description="Two lines built from the distance between this bar's extreme "
                "and the previous opposite one. Their crossover is the signal.",
    min_bars=14,
)
def vortex(bars: BarSeries, period: int) -> dict[str, np.ndarray]:
    high, low = _f64(bars.high), _f64(bars.low)
    up = np.abs(high - _shift(low, 1))
    down = np.abs(low - _shift(high, 1))
    span = _rolling_sum(_true_range(bars), int(period))
    return {"plus": safe_divide(_rolling_sum(up, int(period)), span),
            "minus": safe_divide(_rolling_sum(down, int(period)), span)}


@REGISTRY.register(
    "HEIKIN", "Heikin-Ashi Candles", "Trend",
    outputs=("open", "high", "low", "close"),
    overlay=True, scale_hint="price", uses_source=False,
    plot_style=_style(open={"color": _GREY}, high={"color": _GREEN},
                      low={"color": _RED}, close={"color": _BLUE}),
    description="Averaged candles: the close is the bar's mean price and the "
                "open is the previous Heikin-Ashi body's midpoint, which "
                "smooths a trend into a run of same-coloured bars.",
    min_bars=2,
)
def heikin(bars: BarSeries) -> dict[str, np.ndarray]:
    """Heikin-Ashi.

    ``ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2`` is a first-order
    recursion with ``alpha = beta = 0.5`` over the previous Heikin-Ashi close,
    so it goes through the same vectorised smoother the EMAs use instead of a
    Python loop. ``EMA(3)`` has exactly ``alpha = 2/(3+1) = 0.5``.
    """
    from .library import _recursive_smooth

    open_, high = _f64(bars.open), _f64(bars.high)
    low, close = _f64(bars.low), _f64(bars.close)
    ha_close = (open_ + high + low + close) / 4.0

    # y[i] = 0.5*y[i-1] + 0.5*ha_close[i-1], with y at the first candle fixed
    # to that candle's own midpoint. The seed has to go INTO the driver rather
    # than be written over the answer afterwards: the smoother seeds itself at
    # the first defined input and then runs forward, so overwriting bar 0 after
    # the fact leaves bar 1 built on the wrong initial condition. Putting the
    # midpoint at index 0 of the driver makes the smoother seed on it, and
    # every later bar reads the previous Heikin-Ashi close as it should.
    driver = _shift(ha_close, 1)
    first = np.flatnonzero(np.isfinite(ha_close))
    if first.size:
        start = int(first[0])
        driver[start] = (open_[start] + close[start]) / 2.0
    ha_open = _recursive_smooth(driver, 0.5, 1)

    ha_high = np.maximum(high, np.maximum(ha_open, ha_close))
    ha_low = np.minimum(low, np.minimum(ha_open, ha_close))
    return {"open": ha_open, "high": ha_high, "low": ha_low,
            "close": ha_close}


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------

@REGISTRY.register(
    "CHANDELIER", "Chandelier Exit", "Volatility",
    params=(ParamSpec("period", "Period", "int", 22, 1, 5000),
            ParamSpec("multiplier", "ATR multiplier", "float", 3.0, 0.1, 50.0,
                      0.1)),
    outputs=("long", "short"),
    overlay=True, scale_hint="price", uses_source=False,
    plot_style=_style(long={"color": _GREEN}, short={"color": _RED}),
    description="A trailing stop hung an ATR multiple below the highest high "
                "(for longs) or above the lowest low (for shorts).",
    min_bars=22,
)
def chandelier(bars: BarSeries, period: int, multiplier: float
               ) -> dict[str, np.ndarray]:
    band = float(multiplier) * _rma(_true_range(bars), int(period))
    return {"long": _rolling_max(_f64(bars.high), int(period)) - band,
            "short": _rolling_min(_f64(bars.low), int(period)) + band}


@REGISTRY.register(
    "NATR", "Normalised ATR", "Volatility",
    params=(ParamSpec("period", "Period", "int", 14, 1, 5000),),
    overlay=False, scale_hint="percent", uses_source=False,
    plot_style=_style(value={"color": _ORANGE}),
    description="ATR as a percentage of price, so a stop distance can be "
                "compared between instruments and across years.", min_bars=14,
)
def natr(bars: BarSeries, period: int) -> np.ndarray:
    return 100.0 * safe_divide(_rma(_true_range(bars), int(period)),
                               _f64(bars.close))


@REGISTRY.register(
    "MASS", "Mass Index", "Volatility",
    params=(ParamSpec("period", "Sum period", "int", 25, 2, 5000),
            ParamSpec("smoothing", "EMA period", "int", 9, 1, 2000)),
    overlay=False, scale_hint="price", uses_source=False,
    plot_style=_style(value={"color": _PURPLE}),
    description="Widening range measured by the ratio of a single to a double "
                "EMA of it. A bulge above 27 is read as a reversal warning.",
    min_bars=25,
)
def mass(bars: BarSeries, period: int, smoothing: int) -> np.ndarray:
    span = _f64(bars.high) - _f64(bars.low)
    single = _ema(span, int(smoothing))
    double = _ema(single, int(smoothing))
    return _rolling_sum(safe_divide(single, double), int(period))


@REGISTRY.register(
    "ULCER", "Ulcer Index", "Volatility",
    params=(ParamSpec("period", "Period", "int", 14, 2, 5000),),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _RED}),
    description="The root-mean-square of the drawdown from the period's high. "
                "Unlike standard deviation it charges only for DOWNSIDE, which "
                "is the risk anyone actually minds.", min_bars=14,
)
def ulcer(bars: BarSeries, period: int, source: str) -> np.ndarray:
    price = _f64(bars.source_array(source))
    peak = _rolling_max(price, int(period))
    drawdown = 100.0 * safe_divide(price - peak, peak)
    return np.sqrt(_rolling_mean(drawdown * drawdown, int(period)))


@REGISTRY.register(
    "HISTVOL", "Historical Volatility", "Volatility",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),
            ParamSpec("periods_per_year", "Periods per year", "int", 252, 1,
                      1_000_000)),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _TEAL}),
    description="Annualised standard deviation of log returns. The annualising "
                "factor is a parameter because it depends on the bar size: 252 "
                "for daily, and far larger intraday.", min_bars=20,
)
def histvol(bars: BarSeries, period: int, periods_per_year: int,
            source: str) -> np.ndarray:
    """Annualised realised volatility, as a percentage.

    ``periods_per_year`` is exposed rather than inferred because inferring it
    from the bar size would silently annualise a 5-minute series by 98,280 and
    report a volatility of several hundred percent as though it meant
    something.
    """
    price = _f64(bars.source_array(source))
    previous = _shift(price, 1)
    ratio = safe_divide(price, previous)
    returns = np.where(ratio > 0, np.log(np.where(ratio > 0, ratio, 1.0)),
                       np.nan)
    return (100.0 * _rolling_std(returns, int(period))
            * np.sqrt(float(periods_per_year)))


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------

def _money_flow_volume(bars: BarSeries) -> np.ndarray:
    """Chaikin's money flow volume: where the close sat, times the volume."""
    high, low, close = _f64(bars.high), _f64(bars.low), _f64(bars.close)
    span = high - low
    multiplier = safe_divide((close - low) - (high - close), span, fill=0.0)
    return multiplier * _f64(bars.volume)


@REGISTRY.register(
    "AD", "Accumulation / Distribution Line", "Volume",
    overlay=False, scale_hint="volume", uses_source=False,
    plot_style=_style(value={"color": _BLUE}),
    description="A running total of volume signed by where the bar closed in "
                "its range. Divergence from price is the classic read.",
    min_bars=1,
)
def accumulation(bars: BarSeries) -> np.ndarray:
    flow = _money_flow_volume(bars)
    return np.cumsum(np.where(np.isfinite(flow), flow, 0.0))


@REGISTRY.register(
    "ADOSC", "Chaikin Oscillator", "Volume",
    params=(ParamSpec("fast", "Fast period", "int", 3, 1, 2000),
            ParamSpec("slow", "Slow period", "int", 10, 2, 5000)),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(value={"color": _PURPLE, "kind": "histogram"}),
    description="The MACD of the accumulation line: momentum in money flow "
                "rather than in price.", min_bars=10,
)
def chaikin_oscillator(bars: BarSeries, fast: int, slow: int) -> np.ndarray:
    line = accumulation(bars)
    return _ema(line, int(fast)) - _ema(line, int(slow))


@REGISTRY.register(
    "EOM", "Ease of Movement", "Volume",
    params=(ParamSpec("period", "Smoothing", "int", 14, 1, 5000),
            ParamSpec("scale", "Volume divisor", "float", 1e6, 1.0, 1e12,
                      1000.0)),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(value={"color": _GREEN}),
    description="How far price moved per unit of volume. Large positive means "
                "price rose on little volume, which is easy movement.",
    min_bars=14,
)
def ease_of_movement(bars: BarSeries, period: int, scale: float) -> np.ndarray:
    mid = _hl2(bars)
    moved = mid - _shift(mid, 1)
    span = _f64(bars.high) - _f64(bars.low)
    box = safe_divide(_f64(bars.volume) / float(scale), span)
    return _rolling_mean(safe_divide(moved, box), int(period))


@REGISTRY.register(
    "FI", "Force Index", "Volume",
    params=(ParamSpec("period", "Smoothing", "int", 13, 1, 5000),),
    overlay=False, scale_hint="zero_centred", uses_source=False,
    plot_style=_style(value={"color": _ORANGE}),
    description="Elder's price change times volume, smoothed. It reads the "
                "size of a move and the conviction behind it together.",
    min_bars=13,
)
def force_index(bars: BarSeries, period: int) -> np.ndarray:
    close = _f64(bars.close)
    return _ema((close - _shift(close, 1)) * _f64(bars.volume), int(period))


@REGISTRY.register(
    "PVT", "Price Volume Trend", "Volume",
    overlay=False, scale_hint="volume", uses_source=False,
    plot_style=_style(value={"color": _TEAL}),
    description="Like OBV, but each bar adds the volume scaled by the "
                "percentage move rather than all of it, so a small move counts "
                "for less.", min_bars=2,
)
def pvt(bars: BarSeries) -> np.ndarray:
    close = _f64(bars.close)
    previous = _shift(close, 1)
    step = safe_divide(close - previous, previous, fill=0.0) * _f64(bars.volume)
    return np.cumsum(np.where(np.isfinite(step), step, 0.0))


@REGISTRY.register(
    "PVI_NVI", "Positive / Negative Volume Index", "Volume",
    outputs=("positive", "negative"),
    overlay=False, scale_hint="price", uses_source=False,
    plot_style=_style(positive={"color": _GREEN}, negative={"color": _RED}),
    description="Two indices that move only on rising or only on falling "
                "volume. The idea is that the crowd trades on heavy volume and "
                "the informed on light.", min_bars=2,
)
def volume_index(bars: BarSeries) -> dict[str, np.ndarray]:
    """PVI and NVI, both based at 1000.

    A conditional compounding is still a cumulative product, so this is two
    ``cumprod`` calls rather than a loop: on a bar that does not qualify the
    factor is exactly 1 and the index carries forward unchanged.
    """
    close = _f64(bars.close)
    volume = _f64(bars.volume)
    change = safe_divide(close - _shift(close, 1), _shift(close, 1), fill=0.0)
    previous_volume = _shift(volume, 1)
    rising = np.isfinite(previous_volume) & (volume > previous_volume)
    falling = np.isfinite(previous_volume) & (volume < previous_volume)
    change = np.where(np.isfinite(change), change, 0.0)
    return {
        "positive": 1000.0 * np.cumprod(1.0 + np.where(rising, change, 0.0)),
        "negative": 1000.0 * np.cumprod(1.0 + np.where(falling, change, 0.0)),
    }


log.debug("extended indicator library registered")
