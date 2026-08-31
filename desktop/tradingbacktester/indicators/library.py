"""The indicator library.

Importing this module registers every indicator the application ships with into
:data:`tradingbacktester.indicators.base.REGISTRY`.  Nothing else has to be
touched to add one: the parameter editor, the chart, the rule builder and the
optimiser all read the registry.

Implementation notes that are easy to get wrong and are therefore deliberate
here:

* **Warm-up is NaN, never a fabricated number.**  Every array returned is
  ``float64``, exactly ``len(bars)`` long, and NaN until the indicator is
  genuinely defined.  Rules treat NaN as "condition false", so a strategy can
  never trade on a half-formed average.
* **No look-ahead.**  Index ``i`` only ever reads bars ``0..i``.  The pivot
  indicators are the interesting case: a pivot high is not *knowable* until
  ``right`` bars later, so it is published at the bar that confirms it, not at
  the bar it happened on.
* **Recursion loops, everything else vectorises.**  Wilder smoothing, the
  exponential moving average, SuperTrend and the parabolic SAR are defined by
  ``y[i] = f(y[i-1], ...)`` and cannot be expressed as a stable closed form over
  a long series, so they use one ``O(n)`` Python loop each.  Measured on a
  million bars that loop costs about 0.25 s -- faster than ``pandas.ewm`` -- and
  it keeps the NaN semantics under our control.  Rolling windows use a
  cumulative-sum decomposition (mean, sum, standard deviation) or the van
  Herk/Gil-Werman two-pass trick (max, min), both ``O(n)`` and fully vectorised.
* **Nothing divides by zero.**  A flat window, an empty volume day or an
  undefined ratio yields NaN or a documented neutral value, never an exception
  and never ``inf`` by accident.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from ..core.errors import IndicatorError
from ..data.models import BarSeries
from .base import REGISTRY, IndicatorRegistry, ParamSpec, safe_divide

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Palette
#
# A small fixed palette so a chart with six indicators on it looks designed
# rather than random.  Chosen to stay legible on the dark theme and to keep the
# usual conventions: rising/positive green, falling/negative red, bands grey.
# --------------------------------------------------------------------------

_BLUE = "#4aa3ff"
_ORANGE = "#ff9f43"
_GREEN = "#26de81"
_RED = "#fc5c65"
_PURPLE = "#a55eea"
_TEAL = "#2bcbba"
_YELLOW = "#fed330"
_GREY = "#8f9bb3"
_PINK = "#f368e0"

def _style(**outputs: dict[str, Any]) -> dict[str, Any]:
    """Tiny helper so the registrations below stay readable."""
    return dict(outputs)


# --------------------------------------------------------------------------
# Array helpers -- all O(n), all NaN-aware
# --------------------------------------------------------------------------


def _f64(a: Any) -> np.ndarray:
    """A contiguous float64 copy-or-view of ``a``."""
    return np.ascontiguousarray(a, dtype="float64")


def _empty(n: int) -> np.ndarray:
    return np.full(n, np.nan, dtype="float64")


def _shift(a: np.ndarray, k: int) -> np.ndarray:
    """``out[i] = a[i - k]``, NaN-filled at the front.  ``k >= 0``."""
    out = _empty(len(a))
    if k <= 0:
        out[:] = a
    elif k < len(a):
        out[k:] = a[:-k]
    return out


def _first_valid(a: np.ndarray) -> int:
    """Index of the first finite value, or ``-1`` if there is none."""
    ok = np.flatnonzero(np.isfinite(a))
    return int(ok[0]) if ok.size else -1


def _check_period(period: int, n: int, what: str) -> bool:
    """Return True if the window fits inside the data, logging when it does not.

    A period longer than the dataset is a user mistake with a harmless answer
    (all NaN), so it is not worth an exception -- but it *is* worth a log line,
    because "my indicator is blank" is otherwise a mystery.
    """
    if period <= 0:
        raise IndicatorError(f"{what} needs a period of at least 1 bar.")
    if n < period:
        log.debug("%s: %d bars is fewer than the %d-bar period; result is all NaN",
                  what, n, period)
        return False
    return True


def _rolling_sum(a: np.ndarray, period: int) -> np.ndarray:
    """Rolling sum over ``period`` bars, NaN until the window is full.

    Uses a cumulative sum (``O(n)``) rather than a strided window (``O(n*w)``
    memory).  The series is shifted by its first finite value before the cumsum
    so that a million bars of a 20,000-point index do not lose precision in the
    accumulator, and a parallel cumsum of the NaN mask invalidates any window
    that contains a NaN instead of silently treating it as zero.
    """
    n = len(a)
    out = _empty(n)
    if not _check_period(period, n, "A rolling sum"):
        return out
    bad = ~np.isfinite(a)
    fv = _first_valid(a)
    shift = float(a[fv]) if fv >= 0 else 0.0
    clean = np.where(bad, 0.0, a - shift)
    csum = np.cumsum(clean)
    total = csum[period - 1:].copy()
    total[1:] -= csum[:-period]
    out[period - 1:] = total + shift * period
    nan_count = np.cumsum(bad.astype("int64"))
    cnt = nan_count[period - 1:].copy()
    cnt[1:] -= nan_count[:-period]
    out[period - 1:][cnt > 0] = np.nan
    return out


def _rolling_mean(a: np.ndarray, period: int) -> np.ndarray:
    """Simple moving average.  ``SMA([1,2,3,4,5], 3) == [nan, nan, 2, 3, 4]``."""
    return _rolling_sum(a, period) / float(period)


def _rolling_std(a: np.ndarray, period: int) -> np.ndarray:
    """Population standard deviation (``ddof=0``) over a rolling window.

    Population, not sample, because that is what every charting package uses for
    Bollinger Bands and it is what a user comparing this application against
    TradingView will expect to see.
    """
    n = len(a)
    out = _empty(n)
    if not _check_period(period, n, "A rolling standard deviation"):
        return out
    fv = _first_valid(a)
    shift = float(a[fv]) if fv >= 0 else 0.0
    centred = a - shift          # conditioning only; variance is shift-invariant
    mean = _rolling_mean(centred, period)
    mean_sq = _rolling_mean(centred * centred, period)
    var = mean_sq - mean * mean
    # Cancellation can leave a variance a few ULPs below zero on a flat window.
    np.maximum(var, 0.0, out=var, where=np.isfinite(var))
    return np.sqrt(var)


def _rolling_extreme(a: np.ndarray, period: int, largest: bool) -> np.ndarray:
    """Rolling max (``largest``) or min over ``period`` bars.

    van Herk / Gil-Werman: split the series into blocks of ``period``, take a
    forward running extreme inside each block and a backward one, and every
    window is then the extreme of exactly two precomputed values because a
    window of width ``period`` can straddle at most two such blocks.  That is
    ``O(n)`` with vectorised NumPy, where the obvious sliding-window view would
    be ``O(n*period)`` in memory.  NaN propagates through ``np.maximum`` /
    ``np.minimum``, so a window containing NaN correctly yields NaN.
    """
    n = len(a)
    out = _empty(n)
    if not _check_period(period, n, "A rolling maximum" if largest else "A rolling minimum"):
        return out
    if period == 1:
        return _f64(a).copy()
    pad = (-n) % period
    fill = -np.inf if largest else np.inf
    padded = np.concatenate([_f64(a), np.full(pad, fill)])
    blocks = padded.reshape(-1, period)
    acc = np.maximum.accumulate if largest else np.minimum.accumulate
    prefix = acc(blocks, axis=1).ravel()
    suffix = acc(blocks[:, ::-1], axis=1)[:, ::-1].ravel()
    idx = np.arange(period - 1, n)
    pick = np.maximum if largest else np.minimum
    out[idx] = pick(suffix[idx - period + 1], prefix[idx])
    return out


def _rolling_max(a: np.ndarray, period: int) -> np.ndarray:
    return _rolling_extreme(a, period, True)


def _rolling_min(a: np.ndarray, period: int) -> np.ndarray:
    return _rolling_extreme(a, period, False)


def _bars_since_extreme(a: np.ndarray, period: int, largest: bool) -> np.ndarray:
    """Bars since the highest (or lowest) value of the last ``period`` bars.

    ``0`` means this bar is the extreme; ties resolve to the most recent bar,
    which is the Aroon convention.  Implemented as ``period`` vectorised passes
    (cheap for the 14-25 bar windows Aroon uses) rather than an argmax over a
    materialised strided window.
    """
    n = len(a)
    out = _empty(n)
    if not _check_period(period, n, "Aroon"):
        return out
    best = _f64(a).copy()
    off = np.zeros(n, dtype="float64")
    for k in range(1, period):
        cand = _shift(a, k)
        better = cand > best if largest else cand < best
        better &= np.isfinite(cand)
        best = np.where(better, cand, best)
        off = np.where(better, float(k), off)
    out[period - 1:] = off[period - 1:]
    # Reuse the rolling extreme purely as a NaN mask so that a window holding a
    # NaN is undefined here exactly as it is there.
    poisoned = ~np.isfinite(_rolling_extreme(a, period, largest))
    out[poisoned] = np.nan
    return out


#: Orders of magnitude of head-room left in the block-wise recursion below.
#: The reciprocal weights grow as ``beta**-k``, so the block is cut short of
#: overflowing a float64 (about 1e308) with room to spare for the series
#: itself.  Precision is not what this protects -- see the note in
#: :func:`_recursive_smooth` -- only the exponent range.
_IIR_HEADROOM = 240.0

#: And an upper bound on the block, so a very slow decay does not allocate a
#: weight array larger than the data it is smoothing.
_IIR_MAX_BLOCK = 1 << 16


def _recursive_smooth(a: np.ndarray, alpha: float, seed_period: int) -> np.ndarray:
    """``y[i] = alpha*a[i] + (1-alpha)*y[i-1]``, seeded with an SMA.

    Seeding from the simple average of the first ``seed_period`` values (rather
    than from the first value alone) is what every charting package does and it
    is what makes ``EMA`` comparable across platforms.  Leading NaN -- from a
    composed indicator such as ``EMA(RSI)`` -- is skipped, so the seed lands on
    the first ``seed_period`` *defined* values.

    **Why this is not a Python loop.**  It used to be one, and on the shipped
    581,195-bar file that loop was 46% of an entire strategy search -- fifteen
    seconds of the thirty-three, because a search asks for a hundred and
    thirty smoothed series.  The recursion cannot be removed, but it can be
    done a block at a time.  Within a block starting at ``s`` with
    ``y[s-1] = p``::

        y[s+j] = beta**(j+1) * p  +  alpha * beta**j * SUM(x[s+k] * beta**-k)

    which is one ``cumsum`` per block.  The old docstring said the closed form
    "underflows and costs O(n^2)", and both are true of the *whole-array* form;
    neither is true of a block short enough to keep ``beta**-k`` inside a
    float64's exponent range, which is what :data:`_IIR_HEADROOM` picks.

    Precision is not the constraint people expect it to be.  The cumulative sum
    spans many orders of magnitude, but it is dominated by its newest term --
    the one with the largest ``beta**-k`` -- and multiplying back by ``beta**j``
    returns the error to machine epsilon relative to the input.  Measured
    against the old loop on 581,195 bars at seven different periods, the worst
    relative difference is 2.7e-15 and the speed-up is 18-25x.
    """
    n = len(a)
    out = _empty(n)
    start = _first_valid(a)
    if start < 0 or n - start < seed_period:
        return out
    seed_end = start + seed_period          # exclusive
    prev = float(np.mean(a[start:seed_end]))
    if not np.isfinite(prev):
        return out                          # a NaN inside the seed window
    out[seed_end - 1] = prev
    if seed_end >= n:
        return out

    beta = 1.0 - alpha
    values = _f64(a)
    if beta <= 0.0:                         # alpha == 1: no memory at all
        out[seed_end:] = alpha * values[seed_end:]
        return out
    if beta >= 1.0:                         # alpha == 0: nothing ever moves
        out[seed_end:] = prev
        return out

    block = int(_IIR_HEADROOM * math.log(10.0) / -math.log(beta))
    block = max(1, min(_IIR_MAX_BLOCK, block))
    weight = beta ** np.arange(block, dtype="float64")
    reciprocal = 1.0 / weight

    for lo in range(seed_end, n, block):
        hi = min(lo + block, n)
        width = hi - lo
        w = weight[:width]
        # A NaN anywhere in the chunk poisons the cumulative sum from that
        # point on and carries into ``prev``, which is exactly what the loop
        # did: once the recursion has seen a NaN it never recovers.
        out[lo:hi] = beta * w * prev + alpha * w * np.cumsum(values[lo:hi]
                                                             * reciprocal[:width])
        prev = out[hi - 1]
    return out


def _ema(a: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average, ``alpha = 2/(period+1)``, SMA-seeded."""
    if not _check_period(period, len(a), "An exponential moving average"):
        return _empty(len(a))
    return _recursive_smooth(a, 2.0 / (period + 1.0), period)


def _rma(a: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing, ``alpha = 1/period``, SMA-seeded.

    Wilder's original averages are exponential with a period-length memory
    rather than the ``2/(n+1)`` of a conventional EMA; RSI, ATR and ADX are all
    defined in terms of this and disagree visibly with the EMA version.
    """
    if not _check_period(period, len(a), "Wilder's smoothing"):
        return _empty(len(a))
    return _recursive_smooth(a, 1.0 / float(period), period)


def _wma(a: np.ndarray, period: int) -> np.ndarray:
    """Linearly weighted moving average -- weight ``period`` on the newest bar."""
    n = len(a)
    if not _check_period(period, n, "A weighted moving average"):
        return _empty(n)
    if period == 1:
        return _f64(a).copy()
    weights = np.arange(1.0, period + 1.0)
    weights /= weights.sum()
    out = _empty(n)
    # 'valid' correlation with the reversed kernel == weighted rolling sum.
    out[period - 1:] = np.convolve(_f64(a), weights[::-1], mode="valid")
    return out


def _smooth(a: np.ndarray, period: int, method: str) -> np.ndarray:
    """Dispatch for the ``wilder|ema|sma`` choice shared by ATR and friends."""
    if method == "wilder":
        return _rma(a, period)
    if method == "ema":
        return _ema(a, period)
    if method == "sma":
        return _rolling_mean(a, period)
    raise IndicatorError(
        f"'{method}' is not a smoothing method; choose wilder, ema or sma."
    )


def _true_range(bars: BarSeries) -> np.ndarray:
    """True range per bar; the first bar has no previous close so it is high-low."""
    high, low, close = bars.high, bars.low, bars.close
    prev = _shift(close, 1)
    tr = high - low
    if len(bars) > 1:
        alt1 = np.abs(high - prev)
        alt2 = np.abs(low - prev)
        tr = np.where(np.isfinite(prev), np.maximum(tr, np.maximum(alt1, alt2)), tr)
    return _f64(tr)


def _session_group(bars: BarSeries, anchor: str) -> np.ndarray:
    """Integer key that changes whenever a new VWAP session starts.

    The key is derived from the bar's *local* wall clock in
    ``bars.instrument.timezone``, so a 22:00 UTC bar belongs to the New York
    trading day that is still in progress, not to the next UTC day.
    """
    import pandas as pd                     # local: only the tz path needs pandas

    tz = bars.instrument.timezone or "UTC"
    try:
        local = pd.to_datetime(bars.ts, unit="ns", utc=True).tz_convert(tz)
    except Exception as exc:                # unknown zone name on the instrument
        raise IndicatorError(
            f"'{tz}' is not a timezone this computer recognises, so the session "
            f"boundaries for {bars.instrument.symbol} cannot be worked out.",
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc
    naive = local.tz_localize(None).to_numpy()
    if anchor == "day":
        return naive.astype("datetime64[D]").astype("int64")
    if anchor == "week":
        # datetime64[W] weeks start on Thursday (the epoch); shift to Monday.
        days = naive.astype("datetime64[D]").astype("int64")
        return (days + 3) // 7
    if anchor == "month":
        return naive.astype("datetime64[M]").astype("int64")
    raise IndicatorError(f"'{anchor}' is not a VWAP anchor; choose day, week or month.")


def _reset_cumsum(values: np.ndarray, group: np.ndarray) -> np.ndarray:
    """Cumulative sum of ``values`` that restarts whenever ``group`` changes."""
    n = len(values)
    if n == 0:
        return _empty(0)
    csum = np.cumsum(np.where(np.isfinite(values), values, 0.0))
    starts = np.empty(n, dtype=bool)
    starts[0] = True
    starts[1:] = group[1:] != group[:-1]
    idx = np.flatnonzero(starts)
    base = np.zeros(len(idx), dtype="float64")
    base[1:] = csum[idx[1:] - 1]
    which = np.cumsum(starts) - 1
    return csum - base[which]


def _cross_flags(diff: np.ndarray) -> np.ndarray:
    """Boolean array: True on a bar where ``diff`` changed sign (either way)."""
    prev = _shift(diff, 1)
    ok = np.isfinite(diff) & np.isfinite(prev)
    up = (diff > 0) & (prev <= 0)
    down = (diff < 0) & (prev >= 0)
    return (up | down) & ok


# --------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------

@REGISTRY.register(
    "SMA", "Simple Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _BLUE, "width": 1.6}),
    description="Unweighted mean of the source over the period.", min_bars=20,
)
def sma(bars: BarSeries, period: int, source: str) -> np.ndarray:
    return _rolling_mean(bars.source_array(source), period)


@REGISTRY.register(
    "EMA", "Exponential Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _ORANGE, "width": 1.6}),
    description="Exponentially weighted mean, seeded with the simple average of "
                "the first period bars.", min_bars=20,
)
def ema(bars: BarSeries, period: int, source: str) -> np.ndarray:
    return _ema(bars.source_array(source), period)


@REGISTRY.register(
    "RMA", "Wilder Moving Average (RMA)", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 14, 1, 5000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _TEAL, "width": 1.6}),
    description="Wilder's smoothing: an EMA with alpha = 1/period. The average "
                "underneath RSI, ATR and ADX.", min_bars=14,
)
def rma(bars: BarSeries, period: int, source: str) -> np.ndarray:
    return _rma(bars.source_array(source), period)


@REGISTRY.register(
    "WMA", "Weighted Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 1, 2000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _PURPLE, "width": 1.6}),
    description="Linear weights, heaviest on the most recent bar.", min_bars=20,
)
def wma(bars: BarSeries, period: int, source: str) -> np.ndarray:
    return _wma(bars.source_array(source), period)


@REGISTRY.register(
    "HMA", "Hull Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 16, 2, 2000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _PINK, "width": 1.8}),
    description="WMA(2*WMA(n/2) - WMA(n), sqrt(n)): far less lag than an EMA of "
                "the same period, at the cost of overshoot.", min_bars=16,
)
def hma(bars: BarSeries, period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    half = max(1, int(period // 2))
    root = max(1, int(round(np.sqrt(period))))
    raw = 2.0 * _wma(src, half) - _wma(src, period)
    return _wma(raw, root)


@REGISTRY.register(
    "DEMA", "Double Exponential Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 1, 2000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _YELLOW, "width": 1.6}),
    description="2*EMA - EMA(EMA): removes most of the EMA's lag.", min_bars=40,
)
def dema(bars: BarSeries, period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    e1 = _ema(src, period)
    return 2.0 * e1 - _ema(e1, period)


@REGISTRY.register(
    "TEMA", "Triple Exponential Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 1, 2000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _GREEN, "width": 1.6}),
    description="3*EMA - 3*EMA(EMA) + EMA(EMA(EMA)).", min_bars=60,
)
def tema(bars: BarSeries, period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    e1 = _ema(src, period)
    e2 = _ema(e1, period)
    e3 = _ema(e2, period)
    return 3.0 * e1 - 3.0 * e2 + e3


@REGISTRY.register(
    "VWMA", "Volume Weighted Moving Average", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _BLUE, "width": 1.6}),
    description="Mean of the source weighted by volume. NaN over any window with "
                "no volume at all.", min_bars=20,
)
def vwma(bars: BarSeries, period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    vol = bars.volume
    return safe_divide(_rolling_sum(src * vol, period), _rolling_sum(vol, period))


@REGISTRY.register(
    "LINREG", "Linear Regression Curve", "Moving Averages",
    params=(ParamSpec("period", "Period", "int", 20, 2, 2000),),
    overlay=True, scale_hint="price", plot_style=_style(value={"color": _TEAL, "width": 1.6}),
    description="End point of the least-squares straight line fitted to the last "
                "period bars.", min_bars=20,
)
def linreg(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """Rolling ordinary-least-squares end point.

    The end point of a fitted line is a fixed linear combination of the window,
    so the whole rolling regression collapses to one FIR filter rather than a
    per-bar ``polyfit``.  With ``t = 0..n-1`` across the window::

        value = mean(y) + slope * (n-1)/2
        slope = sum((t - tbar) * y) / (n * (n*n - 1) / 12)

    which expands to the weights below.
    """
    src = bars.source_array(source)
    n = int(period)
    if not _check_period(n, len(src), "Linear regression"):
        return _empty(len(src))
    t = np.arange(n, dtype="float64")
    tbar = (n - 1) / 2.0
    denom = n * (n * n - 1) / 12.0
    weights = 1.0 / n + tbar * (t - tbar) / denom
    out = _empty(len(src))
    out[n - 1:] = np.convolve(_f64(src), weights[::-1], mode="valid")
    return out


# --------------------------------------------------------------------------
# Oscillators
# --------------------------------------------------------------------------


@REGISTRY.register(
    "RSI", "Relative Strength Index", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000),),
    overlay=False, scale_hint="oscillator_0_100",
    plot_style=_style(value={"color": _PURPLE, "width": 1.6}),
    description="Wilder's RSI: 100 - 100/(1 + average gain / average loss), both "
                "averages smoothed the Wilder way. 0-100, oversold below 30.",
    min_bars=15,
)
def rsi(bars: BarSeries, period: int, source: str) -> np.ndarray:
    """Wilder's RSI.

    Two conventions worth stating because they are otherwise invisible:
    a window with losses but no gains is 0 and one with gains but no losses is
    100 (so a monotonically rising series reads exactly 100), and a window that
    is perfectly flat -- no gains *and* no losses -- reads 50.  Returning NaN
    for the flat case, which the naive 0/0 gives, would quietly switch off every
    rule mentioning RSI for the whole flat stretch.
    """
    src = bars.source_array(source)
    delta = np.diff(src, prepend=np.nan)
    gain = np.where(np.isfinite(delta), np.maximum(delta, 0.0), np.nan)
    loss = np.where(np.isfinite(delta), np.maximum(-delta, 0.0), np.nan)
    avg_gain = _rma(gain, period)
    avg_loss = _rma(loss, period)
    out = _empty(len(src))
    defined = np.isfinite(avg_gain) & np.isfinite(avg_loss)
    both_zero = defined & (avg_gain == 0.0) & (avg_loss == 0.0)
    no_loss = defined & (avg_loss == 0.0) & (avg_gain > 0.0)
    normal = defined & (avg_loss > 0.0)
    rs = np.zeros(len(src), dtype="float64")
    np.divide(avg_gain, avg_loss, out=rs, where=normal)
    out[normal] = 100.0 - 100.0 / (1.0 + rs[normal])
    out[no_loss] = 100.0
    out[both_zero] = 50.0
    return out


@REGISTRY.register(
    "STOCHRSI", "Stochastic RSI", "Oscillators",
    params=(ParamSpec("rsi_period", "RSI Period", "int", 14, 1, 2000),
            ParamSpec("stoch_period", "Stochastic Period", "int", 14, 1, 2000),
            ParamSpec("smooth_k", "%K Smoothing", "int", 3, 1, 100),
            ParamSpec("d_period", "%D Period", "int", 3, 1, 100)),
    outputs=("k", "d"), overlay=False, scale_hint="oscillator_0_100",
    plot_style=_style(k={"color": _BLUE, "width": 1.6}, d={"color": _ORANGE, "width": 1.4}),
    description="Where RSI sits inside its own recent range. Much faster and "
                "noisier than RSI itself.", min_bars=31,
)
def stoch_rsi(bars: BarSeries, rsi_period: int, stoch_period: int, smooth_k: int,
              d_period: int, source: str) -> dict[str, np.ndarray]:
    base = rsi(bars, rsi_period, source)
    hi = _rolling_max(base, stoch_period)
    lo = _rolling_min(base, stoch_period)
    rng = hi - lo
    raw = np.where(rng > 0, safe_divide(100.0 * (base - lo), rng), 50.0)
    raw = np.where(np.isfinite(hi) & np.isfinite(lo), raw, np.nan)
    k = _rolling_mean(raw, smooth_k) if smooth_k > 1 else raw
    return {"k": k, "d": _rolling_mean(k, d_period)}


@REGISTRY.register(
    "MACD", "MACD", "Oscillators",
    params=(ParamSpec("fast", "Fast EMA", "int", 12, 1, 2000),
            ParamSpec("slow", "Slow EMA", "int", 26, 1, 2000),
            ParamSpec("signal", "Signal EMA", "int", 9, 1, 2000)),
    outputs=("macd", "signal", "histogram"), overlay=False, scale_hint="zero_centred",
    plot_style=_style(macd={"color": _BLUE, "width": 1.6},
                      signal={"color": _ORANGE, "width": 1.4},
                      histogram={"color": _GREEN, "negative_color": _RED,
                                 "kind": "histogram"}),
    description="EMA(fast) - EMA(slow), its signal EMA, and the difference "
                "between the two as a histogram.", min_bars=34,
)
def macd(bars: BarSeries, fast: int, slow: int, signal: int,
         source: str) -> dict[str, np.ndarray]:
    src = bars.source_array(source)
    line = _ema(src, fast) - _ema(src, slow)
    sig = _ema(line, signal)
    return {"macd": line, "signal": sig, "histogram": line - sig}


@REGISTRY.register(
    "STOCH", "Stochastic Oscillator", "Oscillators",
    params=(ParamSpec("k_period", "%K Period", "int", 14, 1, 2000),
            ParamSpec("smooth_k", "%K Smoothing", "int", 3, 1, 100),
            ParamSpec("d_period", "%D Period", "int", 3, 1, 100)),
    outputs=("k", "d"), overlay=False, uses_source=False, scale_hint="oscillator_0_100",
    plot_style=_style(k={"color": _BLUE, "width": 1.6}, d={"color": _ORANGE, "width": 1.4}),
    description="Where the close sits inside the high-low range of the last "
                "k_period bars. %D is the moving average of %K.", min_bars=16,
)
def stoch(bars: BarSeries, k_period: int, smooth_k: int,
          d_period: int) -> dict[str, np.ndarray]:
    """%K smoothed by ``smooth_k``, %D the simple average of %K.

    A window whose high equals its low reads 50: the close is simultaneously at
    the top and the bottom of a range of zero width, so the mid-point is the
    only honest answer and it keeps the series free of NaN holes.
    """
    hi = _rolling_max(bars.high, k_period)
    lo = _rolling_min(bars.low, k_period)
    rng = hi - lo
    raw = np.where(rng > 0, safe_divide(100.0 * (bars.close - lo), rng), 50.0)
    raw = np.where(np.isfinite(hi) & np.isfinite(lo), raw, np.nan)
    k = _rolling_mean(raw, smooth_k) if smooth_k > 1 else raw
    return {"k": k, "d": _rolling_mean(k, d_period)}


@REGISTRY.register(
    "CCI", "Commodity Channel Index", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 20, 1, 2000),),
    overlay=False, uses_source=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _TEAL, "width": 1.6}),
    description="(hlc3 - SMA(hlc3)) / (0.015 * mean absolute deviation). Roughly "
                "+/-100 in a normal market.", min_bars=20,
)
def cci(bars: BarSeries, period: int) -> np.ndarray:
    """CCI on the typical price with the classic 0.015 scaling constant.

    The source is fixed to hlc3 rather than exposed as a parameter: CCI on the
    close is a different indicator with the same name, and a strategy file that
    silently defaulted to ``close`` would not match any chart.

    The deviation term is the *mean absolute* deviation from the window's own
    mean, which is not a rolling mean of ``|x - SMA|`` and so cannot be reduced
    to one cumulative sum.  It is computed as ``period`` shifted passes, which is
    cheap for the 20-bar default and needs no ``O(n*period)`` scratch array.
    """
    tp = bars.hlc3
    n = len(tp)
    if not _check_period(period, n, "CCI"):
        return _empty(n)
    mean = _rolling_mean(tp, period)
    acc = np.zeros(n, dtype="float64")
    for k in range(period):
        acc += np.abs(_shift(tp, k) - mean)
    mad = acc / float(period)
    return safe_divide(tp - mean, 0.015 * mad)


@REGISTRY.register(
    "WILLR", "Williams %R", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000),),
    overlay=False, uses_source=False, scale_hint="percent",
    plot_style=_style(value={"color": _PINK, "width": 1.6}),
    description="-100 * (highest high - close) / (highest high - lowest low). "
                "Runs from -100 (at the low) to 0 (at the high).", min_bars=14,
)
def willr(bars: BarSeries, period: int) -> np.ndarray:
    hi = _rolling_max(bars.high, period)
    lo = _rolling_min(bars.low, period)
    rng = hi - lo
    out = np.where(rng > 0, safe_divide(-100.0 * (hi - bars.close), rng), -50.0)
    return np.where(np.isfinite(hi) & np.isfinite(lo), out, np.nan)


@REGISTRY.register(
    "ROC", "Rate of Change", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 10, 1, 5000),),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _BLUE, "width": 1.6}),
    description="Percent change of the source over the period.", min_bars=11,
)
def roc(bars: BarSeries, period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    prev = _shift(src, period)
    return 100.0 * safe_divide(src - prev, prev)


@REGISTRY.register(
    "MOM", "Momentum", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 10, 1, 5000),),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _ORANGE, "width": 1.6}),
    description="Source minus its value period bars ago, in price units.", min_bars=11,
)
def mom(bars: BarSeries, period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    return _f64(src - _shift(src, period))


@REGISTRY.register(
    "RETURNS", "Returns", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 1, 1, 5000),
            ParamSpec("method", "Method", "choice", "simple", None, None, 1,
                      ("simple", "log"), "Simple percent change or log return.")),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _GREEN, "negative_color": _RED, "kind": "histogram"}),
    description="Per-bar return in percent, simple or logarithmic.", min_bars=2,
)
def returns(bars: BarSeries, period: int, method: str, source: str) -> np.ndarray:
    """Percent return over ``period`` bars.

    Log returns are also scaled by 100 so the two methods share an axis; they
    are additive across bars, which is what makes them the right choice when the
    series is fed into a further average.
    """
    src = bars.source_array(source)
    prev = _shift(src, period)
    if method == "simple":
        return 100.0 * safe_divide(src - prev, prev)
    if method == "log":
        ratio = safe_divide(src, prev)
        out = _empty(len(src))
        ok = np.isfinite(ratio) & (ratio > 0)
        out[ok] = 100.0 * np.log(ratio[ok])
        return out
    raise IndicatorError(f"'{method}' is not a return method; choose simple or log.")


@REGISTRY.register(
    "ULTOSC", "Ultimate Oscillator", "Oscillators",
    params=(ParamSpec("period1", "Fast Period", "int", 7, 1, 2000),
            ParamSpec("period2", "Middle Period", "int", 14, 1, 2000),
            ParamSpec("period3", "Slow Period", "int", 28, 1, 2000)),
    overlay=False, uses_source=False, scale_hint="oscillator_0_100",
    plot_style=_style(value={"color": _YELLOW, "width": 1.6}),
    description="Williams' weighted blend of buying pressure over three "
                "timeframes; 4:2:1 weights, 0-100.", min_bars=29,
)
def ultosc(bars: BarSeries, period1: int, period2: int, period3: int) -> np.ndarray:
    prev_close = _shift(bars.close, 1)
    true_low = np.minimum(bars.low, prev_close)
    true_high = np.maximum(bars.high, prev_close)
    bp = bars.close - true_low
    tr = true_high - true_low
    a1 = safe_divide(_rolling_sum(bp, period1), _rolling_sum(tr, period1))
    a2 = safe_divide(_rolling_sum(bp, period2), _rolling_sum(tr, period2))
    a3 = safe_divide(_rolling_sum(bp, period3), _rolling_sum(tr, period3))
    return 100.0 * (4.0 * a1 + 2.0 * a2 + a3) / 7.0


@REGISTRY.register(
    "TSI", "True Strength Index", "Oscillators",
    params=(ParamSpec("long_period", "Long Period", "int", 25, 1, 2000),
            ParamSpec("short_period", "Short Period", "int", 13, 1, 2000)),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _PURPLE, "width": 1.6}),
    description="Double-smoothed momentum divided by double-smoothed absolute "
                "momentum, times 100. Roughly -100 to +100.", min_bars=38,
)
def tsi(bars: BarSeries, long_period: int, short_period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    change = np.diff(src, prepend=np.nan)
    smooth = _ema(_ema(change, long_period), short_period)
    smooth_abs = _ema(_ema(np.abs(change), long_period), short_period)
    return 100.0 * safe_divide(smooth, smooth_abs)


@REGISTRY.register(
    "CHOP", "Choppiness Index", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 14, 2, 2000),),
    overlay=False, uses_source=False, scale_hint="oscillator_0_100",
    plot_style=_style(value={"color": _GREY, "width": 1.6}),
    description="100 * log10(sum(TR) / range) / log10(period). Above ~61 the "
                "market is ranging, below ~38 it is trending.", min_bars=15,
)
def chop(bars: BarSeries, period: int) -> np.ndarray:
    tr_sum = _rolling_sum(_true_range(bars), period)
    rng = _rolling_max(bars.high, period) - _rolling_min(bars.low, period)
    ratio = safe_divide(tr_sum, rng)
    out = _empty(len(bars))
    ok = np.isfinite(ratio) & (ratio > 0)
    out[ok] = 100.0 * np.log10(ratio[ok]) / np.log10(float(period))
    return out


@REGISTRY.register(
    "ZSCORE", "Z-Score", "Oscillators",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),),
    overlay=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _BLUE, "width": 1.6}),
    description="Standard deviations the source sits away from its own rolling "
                "mean. NaN on a window with no variation at all.", min_bars=20,
)
def zscore(bars: BarSeries, period: int, source: str) -> np.ndarray:
    src = bars.source_array(source)
    mean = _rolling_mean(src, period)
    std = _rolling_std(src, period)
    return safe_divide(src - mean, std)


@REGISTRY.register(
    "CROSS_COUNT", "Crossings in Window", "Oscillators",
    params=(ParamSpec("period", "Window", "int", 100, 2, 5000),
            ParamSpec("reference", "Reference", "choice", "sma", None, None, 1,
                      ("sma", "level"), "Cross the source's own average, or a fixed level."),
            ParamSpec("ma_period", "Average Period", "int", 20, 1, 2000),
            ParamSpec("level", "Level", "float", 0.0, -1e12, 1e12, 0.1)),
    overlay=False, uses_source=True, scale_hint="zero_centred",
    plot_style=_style(value={"color": _GREY, "width": 1.4, "kind": "histogram"}),
    description="How many times the source crossed its reference in the last "
                "window. A direct measure of how chopped-up a signal is.",
    min_bars=100,
)
def cross_count(bars: BarSeries, period: int, reference: str, ma_period: int,
                level: float, source: str) -> np.ndarray:
    """Count of sign changes of ``source - reference`` inside a rolling window.

    Two references are offered because both questions come up: crossings of a
    fixed level answer "how often did RSI cross 50", and crossings of the
    source's own moving average answer "is price trending or sawing about",
    which works for any source without the user having to know its scale.
    """
    src = bars.source_array(source)
    if reference == "sma":
        ref = _rolling_mean(src, ma_period)
    elif reference == "level":
        ref = np.full(len(src), float(level))
    else:
        raise IndicatorError(
            f"'{reference}' is not a cross reference; choose sma or level."
        )
    flags = _cross_flags(src - ref).astype("float64")
    # Bars before the reference exists are "no cross observed", not NaN, so the
    # window sum stays defined once enough bars have gone by.
    return _rolling_sum(flags, period)


# --------------------------------------------------------------------------
# Volatility
# --------------------------------------------------------------------------

_ATR_METHOD = ParamSpec("method", "Smoothing", "choice", "wilder", None, None, 1,
                        ("wilder", "ema", "sma"),
                        "Wilder is the original and the default everywhere else.")


@REGISTRY.register(
    "TRUE_RANGE", "True Range", "Volatility",
    overlay=False, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _GREY, "width": 1.2, "kind": "histogram"}),
    description="max(high-low, |high-prev close|, |low-prev close|). The first "
                "bar has no previous close, so it is simply high-low.", min_bars=1,
)
def true_range(bars: BarSeries) -> np.ndarray:
    return _true_range(bars)


@REGISTRY.register(
    "ATR", "Average True Range", "Volatility",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000), _ATR_METHOD),
    overlay=False, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _ORANGE, "width": 1.6}),
    description="Average of the true range. Wilder's smoothing by default, which "
                "is what stops and targets elsewhere in this application assume.",
    min_bars=14,
)
def atr(bars: BarSeries, period: int, method: str) -> np.ndarray:
    return _smooth(_true_range(bars), period, method)


@REGISTRY.register(
    "ATR_EMA", "Average True Range (EMA)", "Volatility",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000),
            ParamSpec("method", "Smoothing", "choice", "ema", None, None, 1,
                      ("wilder", "ema", "sma"), "Defaults to the 2/(n+1) EMA here.")),
    overlay=False, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _ORANGE, "width": 1.4, "style": "dash"}),
    description="The same average true range smoothed with a conventional EMA "
                "instead of Wilder's. Reacts about twice as fast.", min_bars=14,
)
def atr_ema(bars: BarSeries, period: int, method: str) -> np.ndarray:
    return _smooth(_true_range(bars), period, method)


@REGISTRY.register(
    "ATR_PERCENT", "ATR Percent", "Volatility",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000), _ATR_METHOD),
    overlay=False, uses_source=False, scale_hint="percent",
    plot_style=_style(value={"color": _YELLOW, "width": 1.6}),
    description="Average true range as a percent of the close, so volatility is "
                "comparable across instruments and across years.", min_bars=14,
)
def atr_percent(bars: BarSeries, period: int, method: str) -> np.ndarray:
    return 100.0 * safe_divide(_smooth(_true_range(bars), period, method), bars.close)


@REGISTRY.register(
    "STDDEV", "Standard Deviation", "Volatility",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),),
    overlay=False, scale_hint="price",
    plot_style=_style(value={"color": _TEAL, "width": 1.6}),
    description="Population standard deviation (ddof=0) of the source, matching "
                "the convention used by Bollinger Bands.", min_bars=20,
)
def stddev(bars: BarSeries, period: int, source: str) -> np.ndarray:
    return _rolling_std(bars.source_array(source), period)


@REGISTRY.register(
    "BBANDS", "Bollinger Bands", "Volatility",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),
            ParamSpec("deviation", "Deviations", "float", 2.0, 0.1, 10.0, 0.1)),
    outputs=("upper", "middle", "lower"), overlay=True, scale_hint="price",
    plot_style=_style(upper={"color": _GREY, "width": 1.2},
                      middle={"color": _BLUE, "width": 1.4, "style": "dash"},
                      lower={"color": _GREY, "width": 1.2, "fill_to": "upper",
                             "fill_color": "#4aa3ff22"}),
    description="A simple moving average with bands at a multiple of the "
                "population standard deviation.", min_bars=20,
)
def bbands(bars: BarSeries, period: int, deviation: float,
           source: str) -> dict[str, np.ndarray]:
    """Bands at ``deviation`` *population* standard deviations (``ddof=0``).

    Population rather than sample deviation: it is what TradingView,
    MetaTrader and Bollinger's own description use, and the difference at a
    20-bar period is a visible 2.6%.
    """
    src = bars.source_array(source)
    middle = _rolling_mean(src, period)
    width = float(deviation) * _rolling_std(src, period)
    return {"upper": middle + width, "middle": middle, "lower": middle - width}


@REGISTRY.register(
    "BBWIDTH", "Bollinger Band Width", "Volatility",
    params=(ParamSpec("period", "Period", "int", 20, 2, 5000),
            ParamSpec("deviation", "Deviations", "float", 2.0, 0.1, 10.0, 0.1)),
    overlay=False, scale_hint="percent",
    plot_style=_style(value={"color": _PINK, "width": 1.6}),
    description="Band width as a percent of the middle band -- the usual way to "
                "spot a volatility squeeze.", min_bars=20,
)
def bbwidth(bars: BarSeries, period: int, deviation: float, source: str) -> np.ndarray:
    b = bbands(bars, period, deviation, source)
    return 100.0 * safe_divide(b["upper"] - b["lower"], b["middle"])


@REGISTRY.register(
    "KELTNER", "Keltner Channel", "Volatility",
    params=(ParamSpec("period", "EMA Period", "int", 20, 1, 5000),
            ParamSpec("atr_period", "ATR Period", "int", 10, 1, 2000),
            ParamSpec("multiplier", "ATR Multiplier", "float", 2.0, 0.1, 20.0, 0.1)),
    outputs=("upper", "middle", "lower"), overlay=True, scale_hint="price",
    plot_style=_style(upper={"color": _ORANGE, "width": 1.2},
                      middle={"color": _ORANGE, "width": 1.4, "style": "dash"},
                      lower={"color": _ORANGE, "width": 1.2, "fill_to": "upper",
                             "fill_color": "#ff9f4322"}),
    description="An EMA with bands a multiple of the average true range away. "
                "Unlike Bollinger Bands the width follows range, not closes.",
    min_bars=20,
)
def keltner(bars: BarSeries, period: int, atr_period: int, multiplier: float,
            source: str) -> dict[str, np.ndarray]:
    middle = _ema(bars.source_array(source), period)
    band = float(multiplier) * _rma(_true_range(bars), atr_period)
    return {"upper": middle + band, "middle": middle, "lower": middle - band}


@REGISTRY.register(
    "DONCHIAN", "Donchian Channel", "Volatility",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    outputs=("upper", "middle", "lower"), overlay=True, uses_source=False,
    scale_hint="price",
    plot_style=_style(upper={"color": _GREEN, "width": 1.2},
                      middle={"color": _GREY, "width": 1.0, "style": "dot"},
                      lower={"color": _RED, "width": 1.2, "fill_to": "upper",
                             "fill_color": "#26de8118"}),
    description="Highest high and lowest low of the last period bars, and their "
                "mid-point. The channel a turtle breakout trades.", min_bars=20,
)
def donchian(bars: BarSeries, period: int) -> dict[str, np.ndarray]:
    """Channel over the last ``period`` bars **including the current one**.

    Including the current bar means the close can never be above ``upper``, so a
    breakout rule must compare against the previous bar's channel
    (``offset=1`` on the operand).  That is the honest version: excluding the
    current bar inside the indicator would hide the choice.
    """
    upper = _rolling_max(bars.high, period)
    lower = _rolling_min(bars.low, period)
    return {"upper": upper, "middle": (upper + lower) / 2.0, "lower": lower}


@REGISTRY.register(
    "HIGHEST", "Highest High", "Volatility",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    overlay=True, scale_hint="price", default_source="high",
    plot_style=_style(value={"color": _GREEN, "width": 1.2}),
    description="Rolling maximum of the source over the period, current bar "
                "included.", min_bars=20,
)
def highest(bars: BarSeries, period: int, source: str) -> np.ndarray:
    return _rolling_max(bars.source_array(source), period)


@REGISTRY.register(
    "LOWEST", "Lowest Low", "Volatility",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    overlay=True, scale_hint="price", default_source="low",
    plot_style=_style(value={"color": _RED, "width": 1.2}),
    description="Rolling minimum of the source over the period, current bar "
                "included.", min_bars=20,
)
def lowest(bars: BarSeries, period: int, source: str) -> np.ndarray:
    return _rolling_min(bars.source_array(source), period)


# --------------------------------------------------------------------------
# Trend
# --------------------------------------------------------------------------


@REGISTRY.register(
    "ADX", "Average Directional Index", "Trend",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000),
            ParamSpec("adx_period", "ADX Smoothing", "int", 14, 1, 2000)),
    outputs=("adx", "plus_di", "minus_di"), overlay=False, uses_source=False,
    scale_hint="oscillator_0_100",
    plot_style=_style(adx={"color": _YELLOW, "width": 1.8},
                      plus_di={"color": _GREEN, "width": 1.4},
                      minus_di={"color": _RED, "width": 1.4}),
    description="Wilder's trend strength. ADX above 25 says there is a trend; "
                "+DI over -DI says which way.", min_bars=28,
)
def adx(bars: BarSeries, period: int, adx_period: int) -> dict[str, np.ndarray]:
    """Wilder's directional movement system.

    Directional movement is one-sided by construction: only the larger of the
    two moves counts on any bar, and neither counts on an inside bar.  Both the
    movements and the true range are smoothed the Wilder way before the ratio is
    taken, which is what stops the DIs jumping about on a single wide bar.
    """
    n = len(bars)
    if n == 0:
        return {"adx": _empty(0), "plus_di": _empty(0), "minus_di": _empty(0)}
    high, low = bars.high, bars.low
    up_move = high - _shift(high, 1)
    down_move = _shift(low, 1) - low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    # The first bar has no previous bar, so no directional movement is defined.
    plus_dm[0] = np.nan
    minus_dm[0] = np.nan
    tr = _true_range(bars).copy()
    tr[0] = np.nan                      # keep the DM and TR warm-ups aligned
    atr_w = _rma(tr, period)
    plus_di = 100.0 * safe_divide(_rma(plus_dm, period), atr_w)
    minus_di = 100.0 * safe_divide(_rma(minus_dm, period), atr_w)
    dx = 100.0 * safe_divide(np.abs(plus_di - minus_di), plus_di + minus_di)
    # A bar with no directional movement at all leaves 0/0; the market is not
    # directional there, which is a DX of zero, not a hole in the series.
    both_zero = np.isfinite(plus_di) & np.isfinite(minus_di) & \
        (plus_di + minus_di == 0.0)
    dx[both_zero] = 0.0
    return {"adx": _rma(dx, adx_period), "plus_di": plus_di, "minus_di": minus_di}


@REGISTRY.register(
    "AROON", "Aroon", "Trend",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000),),
    outputs=("up", "down", "oscillator"), overlay=False, uses_source=False,
    scale_hint="oscillator_0_100",
    plot_style=_style(up={"color": _GREEN, "width": 1.5},
                      down={"color": _RED, "width": 1.5},
                      oscillator={"color": _GREY, "width": 1.2, "style": "dash"}),
    description="How recently the highest high and lowest low of the window "
                "happened, as a percentage. 100 means it happened on this bar.",
    min_bars=15,
)
def aroon(bars: BarSeries, period: int) -> dict[str, np.ndarray]:
    """Aroon over ``period`` bars back, i.e. a window of ``period + 1`` bars.

    The extra bar is the convention: "the highest high of the last 14 bars"
    means this bar plus the 14 before it, so a fresh high scores exactly 100.
    """
    window = int(period) + 1
    since_high = _bars_since_extreme(bars.high, window, True)
    since_low = _bars_since_extreme(bars.low, window, False)
    up = 100.0 * (period - since_high) / float(period)
    down = 100.0 * (period - since_low) / float(period)
    return {"up": up, "down": down, "oscillator": up - down}


@REGISTRY.register(
    "SUPERTREND", "SuperTrend", "Trend",
    params=(ParamSpec("period", "ATR Period", "int", 10, 1, 2000),
            ParamSpec("multiplier", "Multiplier", "float", 3.0, 0.1, 20.0, 0.1)),
    outputs=("value", "direction"), overlay=True, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _GREEN, "negative_color": _RED, "width": 2.0,
                             "colour_by": "direction"},
                      direction={"color": _GREY, "width": 1.0, "panel": "hidden"}),
    description="An ATR band that ratchets in the direction of the trend and "
                "flips when price closes through it. Direction is +1 up, -1 down.",
    min_bars=10,
)
def supertrend(bars: BarSeries, period: int, multiplier: float) -> dict[str, np.ndarray]:
    """The standard latch-the-band SuperTrend.

    Genuinely recursive: each final band is the tighter of this bar's basic band
    and the previous final band, and it is only allowed to loosen once price has
    closed through it.  One ``O(n)`` pass, no way around it.
    """
    n = len(bars)
    value = _empty(n)
    direction = _empty(n)
    if n == 0:
        return {"value": value, "direction": direction}
    atr_w = _rma(_true_range(bars), period)
    mid = bars.hl2
    basic_upper = mid + float(multiplier) * atr_w
    basic_lower = mid - float(multiplier) * atr_w
    start = _first_valid(atr_w)
    if start < 0:
        return {"value": value, "direction": direction}
    close = bars.close
    final_upper = float(basic_upper[start])
    final_lower = float(basic_lower[start])
    # Seed the direction from where the close sits relative to the mid-band
    # rather than assuming "up"; either way it settles within a bar or two.
    trend = 1 if float(close[start]) >= float(mid[start]) else -1
    value[start] = final_lower if trend > 0 else final_upper
    direction[start] = float(trend)
    for i in range(start + 1, n):
        bu = float(basic_upper[i])
        bl = float(basic_lower[i])
        prev_close = float(close[i - 1])
        final_upper = bu if (bu < final_upper or prev_close > final_upper) else final_upper
        final_lower = bl if (bl > final_lower or prev_close < final_lower) else final_lower
        c = float(close[i])
        if c > final_upper:
            trend = 1
        elif c < final_lower:
            trend = -1
        value[i] = final_lower if trend > 0 else final_upper
        direction[i] = float(trend)
    return {"value": value, "direction": direction}


@REGISTRY.register(
    "PSAR", "Parabolic SAR", "Trend",
    params=(ParamSpec("af_start", "Start Step", "float", 0.02, 0.001, 1.0, 0.001),
            ParamSpec("af_step", "Increment", "float", 0.02, 0.001, 1.0, 0.001),
            ParamSpec("af_max", "Maximum Step", "float", 0.2, 0.01, 1.0, 0.01)),
    overlay=True, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _PURPLE, "width": 1.0, "kind": "dots"}),
    description="Wilder's stop and reverse: a trailing stop that accelerates the "
                "longer a trend runs.", min_bars=2,
)
def psar(bars: BarSeries, af_start: float, af_step: float, af_max: float) -> np.ndarray:
    """Wilder's parabolic SAR.

    Recursive by definition -- today's stop depends on yesterday's stop, the
    extreme point of the current leg and an acceleration factor that only ever
    increases within a leg -- so this is one ``O(n)`` loop.  The clamp against
    the previous two bars' extremes is part of the original rule and stops the
    SAR being placed inside the current bar's range, where it would be hit
    immediately.
    """
    n = len(bars)
    out = _empty(n)
    if n < 2:
        return out
    high, low = bars.high, bars.low
    start = 1
    while start < n and not (np.isfinite(high[start]) and np.isfinite(low[start])
                             and np.isfinite(bars.close[start])
                             and np.isfinite(bars.close[start - 1])):
        start += 1
    if start >= n:
        return out
    rising = bool(bars.close[start] >= bars.close[start - 1])
    ep = float(high[start] if rising else low[start])
    sar = float(low[start - 1] if rising else high[start - 1])
    af = float(af_start)
    out[start] = sar
    for i in range(start + 1, n):
        sar = sar + af * (ep - sar)
        if rising:
            # The SAR may not enter the range of the last two bars.
            sar = min(sar, float(low[i - 1]), float(low[max(i - 2, 0)]))
            if low[i] < sar:
                rising = False
                sar = ep                     # reverse to the old extreme point
                ep = float(low[i])
                af = float(af_start)
            elif high[i] > ep:
                ep = float(high[i])
                af = min(af + float(af_step), float(af_max))
        else:
            sar = max(sar, float(high[i - 1]), float(high[max(i - 2, 0)]))
            if high[i] > sar:
                rising = True
                sar = ep
                ep = float(high[i])
                af = float(af_start)
            elif low[i] < ep:
                ep = float(low[i])
                af = min(af + float(af_step), float(af_max))
        out[i] = sar
    return out


@REGISTRY.register(
    "ELDER_RAY", "Elder Ray", "Trend",
    params=(ParamSpec("period", "EMA Period", "int", 13, 1, 2000),),
    outputs=("bull", "bear"), overlay=False, uses_source=False, scale_hint="zero_centred",
    plot_style=_style(bull={"color": _GREEN, "width": 1.4, "kind": "histogram"},
                      bear={"color": _RED, "width": 1.4, "kind": "histogram"}),
    description="High and low measured against an EMA of the close: how far "
                "buyers and sellers could push price beyond fair value.",
    min_bars=13,
)
def elder_ray(bars: BarSeries, period: int) -> dict[str, np.ndarray]:
    basis = _ema(bars.close, period)
    return {"bull": bars.high - basis, "bear": bars.low - basis}


@REGISTRY.register(
    "PIVOT_HIGH", "Pivot High", "Trend",
    params=(ParamSpec("left", "Bars Left", "int", 5, 1, 500),
            ParamSpec("right", "Bars Right", "int", 5, 1, 500),
            ParamSpec("hold", "Hold Last Level", "bool", True, None, None)),
    overlay=True, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _RED, "width": 1.2, "style": "dash"}),
    description="Price of the most recent confirmed swing high. Published on the "
                "bar that confirms it, never on the bar it happened.", min_bars=11,
)
def pivot_high(bars: BarSeries, left: int, right: int, hold: bool) -> np.ndarray:
    return _pivot(bars.high, left, right, hold, True)


@REGISTRY.register(
    "PIVOT_LOW", "Pivot Low", "Trend",
    params=(ParamSpec("left", "Bars Left", "int", 5, 1, 500),
            ParamSpec("right", "Bars Right", "int", 5, 1, 500),
            ParamSpec("hold", "Hold Last Level", "bool", True, None, None)),
    overlay=True, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _GREEN, "width": 1.2, "style": "dash"}),
    description="Price of the most recent confirmed swing low. Published on the "
                "bar that confirms it, never on the bar it happened.", min_bars=11,
)
def pivot_low(bars: BarSeries, left: int, right: int, hold: bool) -> np.ndarray:
    return _pivot(bars.low, left, right, hold, False)


def _pivot(series: np.ndarray, left: int, right: int, hold: bool,
           is_high: bool) -> np.ndarray:
    """Confirmed swing points, published ``right`` bars late.

    A bar is a pivot high when nothing in the ``left`` bars before it and
    nothing in the ``right`` bars after it traded higher.  That fact is not
    known until ``right`` bars later, so the value is written at index
    ``i + right``.  Writing it at ``i`` -- which is how pivots are usually drawn
    -- would hand a strategy the future, and this file is used by the backtest
    engine, not only by the chart.

    With ``hold`` the last confirmed level is carried forward, giving a step
    line that a rule can compare price against; without it the array is NaN
    except on confirmation bars.
    """
    n = len(series)
    out = _empty(n)
    left, right = int(left), int(right)
    window = left + right + 1
    if n < window:
        return out
    extreme = _rolling_max(series, window) if is_high else _rolling_min(series, window)
    centre = _shift(series, right)              # the candidate bar's own value
    # Strict on the left, non-strict on the right is the usual tie-break: the
    # earliest bar of an equal-high plateau is the pivot.
    is_pivot = np.isfinite(extreme) & np.isfinite(centre) & (centre == extreme)
    earlier = _rolling_max(series, left) if is_high else _rolling_min(series, left)
    earlier_excl = _shift(earlier, right + 1)   # the left bars, candidate excluded
    strict = centre > earlier_excl if is_high else centre < earlier_excl
    is_pivot &= np.isfinite(earlier_excl) & strict
    out[is_pivot] = centre[is_pivot]
    if hold:
        # Forward-fill: index of the last confirmed pivot at or before each bar.
        idx = np.where(is_pivot, np.arange(n), -1)
        idx = np.maximum.accumulate(idx)
        valid = idx >= 0
        filled = _empty(n)
        filled[valid] = out[idx[valid]]
        return filled
    return out


# --------------------------------------------------------------------------
# Volume
# --------------------------------------------------------------------------


@REGISTRY.register(
    "VOLUME", "Volume", "Volume",
    overlay=False, uses_source=False, scale_hint="volume",
    plot_style=_style(value={"color": _GREY, "kind": "histogram",
                             "up_color": _GREEN, "down_color": _RED,
                             "colour_by": "bar_direction"}),
    description="Raw traded volume for the bar.", min_bars=1,
)
def volume(bars: BarSeries) -> np.ndarray:
    return _f64(bars.volume).copy()


@REGISTRY.register(
    "VOL_SMA", "Volume Moving Average", "Volume",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    overlay=False, uses_source=False, scale_hint="volume",
    plot_style=_style(value={"color": _YELLOW, "width": 1.6}),
    description="Simple moving average of volume -- the baseline a volume spike "
                "is measured against.", min_bars=20,
)
def vol_sma(bars: BarSeries, period: int) -> np.ndarray:
    return _rolling_mean(bars.volume, period)


@REGISTRY.register(
    "RVOL", "Relative Volume", "Volume",
    params=(ParamSpec("period", "Period", "int", 20, 1, 5000),),
    overlay=False, uses_source=False, scale_hint="percent",
    plot_style=_style(value={"color": _ORANGE, "width": 1.4, "kind": "histogram"}),
    description="This bar's volume as a multiple of its own recent average. "
                "1.0 is a normal bar. NaN when the average volume is zero.",
    min_bars=20,
)
def rvol(bars: BarSeries, period: int) -> np.ndarray:
    return safe_divide(bars.volume, _rolling_mean(bars.volume, period))


@REGISTRY.register(
    "OBV", "On Balance Volume", "Volume",
    overlay=False, uses_source=False, scale_hint="volume",
    plot_style=_style(value={"color": _BLUE, "width": 1.6}),
    description="Running total of volume, added on an up close and subtracted on "
                "a down close. Starts at zero on the first bar.", min_bars=1,
)
def obv(bars: BarSeries) -> np.ndarray:
    """Cumulative signed volume.

    A cumulative sum has no closed-form warm-up, so the first bar is defined as
    zero (there is no previous close to compare against) and the series is
    meaningful only in its *shape*, never its level.
    """
    close = bars.close
    direction = np.sign(np.diff(close, prepend=close[:1]))
    signed = direction * bars.volume
    return np.cumsum(np.where(np.isfinite(signed), signed, 0.0))


@REGISTRY.register(
    "MFI", "Money Flow Index", "Volume",
    params=(ParamSpec("period", "Period", "int", 14, 1, 2000),),
    overlay=False, uses_source=False, scale_hint="oscillator_0_100",
    plot_style=_style(value={"color": _TEAL, "width": 1.6}),
    description="RSI of money flow: typical price times volume, split into "
                "up-days and down-days. 0-100.", min_bars=15,
)
def mfi(bars: BarSeries, period: int) -> np.ndarray:
    """Money Flow Index.

    Same neutral conventions as RSI: all flow positive reads 100, all negative
    reads 0, and a stretch with no flow at all (zero volume, or a perfectly flat
    typical price) reads 50 rather than leaving a NaN hole.
    """
    tp = bars.hlc3
    flow = tp * bars.volume
    change = np.diff(tp, prepend=np.nan)
    positive = np.where(np.isfinite(change), np.where(change > 0, flow, 0.0), np.nan)
    negative = np.where(np.isfinite(change), np.where(change < 0, flow, 0.0), np.nan)
    pos_sum = _rolling_sum(positive, period)
    neg_sum = _rolling_sum(negative, period)
    out = _empty(len(bars))
    defined = np.isfinite(pos_sum) & np.isfinite(neg_sum)
    normal = defined & (neg_sum > 0)
    ratio = np.zeros(len(bars), dtype="float64")
    np.divide(pos_sum, neg_sum, out=ratio, where=normal)
    out[normal] = 100.0 - 100.0 / (1.0 + ratio[normal])
    out[defined & (neg_sum == 0.0) & (pos_sum > 0.0)] = 100.0
    out[defined & (neg_sum == 0.0) & (pos_sum == 0.0)] = 50.0
    return out


@REGISTRY.register(
    "CMF", "Chaikin Money Flow", "Volume",
    params=(ParamSpec("period", "Period", "int", 20, 1, 2000),),
    overlay=False, uses_source=False, scale_hint="zero_centred",
    plot_style=_style(value={"color": _GREEN, "negative_color": _RED,
                             "kind": "histogram"}),
    description="Volume weighted by where the close sat inside each bar's range, "
                "summed over the period and divided by total volume. -1 to +1.",
    min_bars=20,
)
def cmf(bars: BarSeries, period: int) -> np.ndarray:
    rng = bars.high - bars.low
    # A bar with no range has no location information, so it contributes no
    # money flow -- but its volume still counts in the denominator, which is the
    # standard treatment and keeps a doji from inflating the reading.
    multiplier = np.where(rng > 0,
                          safe_divide((bars.close - bars.low) - (bars.high - bars.close), rng),
                          0.0)
    mfv = multiplier * bars.volume
    return safe_divide(_rolling_sum(mfv, period), _rolling_sum(bars.volume, period))


@REGISTRY.register(
    "VWAP", "Volume Weighted Average Price", "Volume",
    params=(ParamSpec("anchor", "Reset", "choice", "day", None, None, 1,
                      ("day", "week", "month"),
                      "When the running total starts again."),),
    overlay=True, uses_source=False, scale_hint="price",
    plot_style=_style(value={"color": _YELLOW, "width": 1.8}),
    description="Cumulative sum(hlc3 * volume) / sum(volume), restarting each "
                "session in the instrument's own timezone.", min_bars=1,
)
def vwap(bars: BarSeries, anchor: str) -> np.ndarray:
    """Session VWAP.

    The reset boundary is a calendar day (or week, or month) in
    ``bars.instrument.timezone``, not UTC: an instrument whose session runs to
    17:00 New York would otherwise reset in the middle of its own afternoon.
    A session in which nothing traded gives NaN rather than a division by zero,
    which is also what happens for a dataset with no volume column at all.
    """
    n = len(bars)
    if n == 0:
        return _empty(0)
    group = _session_group(bars, anchor)
    pv = _reset_cumsum(bars.hlc3 * bars.volume, group)
    v = _reset_cumsum(bars.volume, group)
    return safe_divide(pv, v)


# --------------------------------------------------------------------------
# Registration entry point
# --------------------------------------------------------------------------

#: Every key this module is contractually required to provide.  Checked by
#: :func:`register_all` so a typo in a decorator fails loudly at start-up rather
#: than when a user opens the indicator list.
REQUIRED_KEYS: tuple[str, ...] = (
    "SMA", "EMA", "WMA", "HMA", "DEMA", "TEMA", "RMA", "VWMA", "RSI", "MACD",
    "BBANDS", "ATR", "STOCH", "ADX", "VWAP", "OBV", "CCI", "MFI", "ROC", "MOM",
    "STDDEV", "KELTNER", "DONCHIAN", "SUPERTREND", "PSAR", "WILLR", "CMF",
    "AROON", "TRUE_RANGE", "ZSCORE", "LINREG", "PIVOT_HIGH", "PIVOT_LOW",
    "VOLUME", "VOL_SMA", "RETURNS", "CHOP", "ULTOSC", "TSI", "ELDER_RAY",
    "ATR_PERCENT", "HIGHEST", "LOWEST", "CROSS_COUNT",
)


def register_all() -> IndicatorRegistry:
    """Make sure the library is in :data:`REGISTRY` and hand it back.

    Registration happens at *import* time through the decorators above, so
    importing this module is enough and calling this function twice does
    nothing the second time.  It exists so that start-up code can be explicit
    about when the registry is populated, and so that the required-key check
    runs somewhere a person will see it.
    """
    missing = [k for k in REQUIRED_KEYS if not REGISTRY.has(k)]
    if missing:
        raise IndicatorError(
            "Some built-in indicators failed to register, so parts of the "
            "application will not work.",
            detail=f"Missing: {', '.join(missing)}",
        )
    return REGISTRY


# The rest of the standard set. Imported HERE, at the very bottom, so that
# `extended` can import this module's private helpers without a circular
# import: by this line everything it needs is defined. It is deliberately not
# imported by `register_all()` -- REQUIRED_KEYS must be checked against a
# registry that is already complete.
from . import extended as _extended            # noqa: E402,F401  (side effect)
from . import quant as _quant                  # noqa: E402,F401  (side effect)

register_all()
log.debug("indicator library registered %d indicators", len(REGISTRY.all()))
