"""Engineered features: what a bar looks like, in units that travel.

Two rules decide everything in this file.

**Scale-free.** A feature measured in price points cannot be compared across
instruments, across years, or even across a volatility regime -- "the close is
40 points above the average" means something different on the Dow at 18,000
than at 44,000. So distances are divided by ATR, sizes by their own rolling
average, and levels turned into z-scores or percentiles. A feature that cannot
be made scale-free is not included.

**Causal.** Every value at bar *i* is computed from bars up to and including
*i*, and never from *i+1*. Rolling statistics use only the past; a percentile
rank is against the trailing window, not the whole series. This is checked by
a test that truncates the series and asserts the earlier values do not move --
the same test the indicator library gets, for the same reason: a look-ahead
here would produce a beautiful, entirely fictional result.

Roughly eighty features in seven families. That is a large multiplicity, which
is why :mod:`.study` corrects for it and reports how many of them are really
independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator

import numpy as np

from ..data.models import BarSeries
from ..indicators.base import REGISTRY

_EPS = 1e-12


@dataclass(frozen=True)
class Feature:
    """One named, scale-free, causal series derived from the bars."""

    name: str
    family: str
    description: str
    compute: Callable[[BarSeries], np.ndarray]
    warmup: int = 0

    def values(self, bars: BarSeries) -> np.ndarray:
        out = np.asarray(self.compute(bars), dtype="float64")
        if self.warmup > 0:
            out = out.copy()
            out[:min(self.warmup, out.size)] = np.nan
        return out


# ---------------------------------------------------------------------------
# primitives
# ---------------------------------------------------------------------------


def _ind(bars: BarSeries, key: str, **params) -> dict[str, np.ndarray]:
    return REGISTRY.compute(key, bars, params)


def _atr(bars: BarSeries, period: int = 14) -> np.ndarray:
    from ..finder.outcomes import wilder_atr

    return wilder_atr(bars, period)


def _safe(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Divide, giving NaN rather than infinity where the denominator vanishes."""
    denominator = np.asarray(denominator, dtype="float64")
    out = np.full(numerator.shape, np.nan)
    ok = np.isfinite(denominator) & (np.abs(denominator) > _EPS) \
        & np.isfinite(numerator)
    out[ok] = numerator[ok] / denominator[ok]
    return out


def rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing mean including the current bar; NaN until the window fills."""
    values = np.asarray(values, dtype="float64")
    n = values.size
    out = np.full(n, np.nan)
    if window <= 0 or n < window:
        return out
    filled = np.nan_to_num(values, nan=0.0)
    counted = np.isfinite(values).astype("float64")
    csum = np.concatenate(([0.0], np.cumsum(filled)))
    ccount = np.concatenate(([0.0], np.cumsum(counted)))
    total = csum[window:] - csum[:-window]
    count = ccount[window:] - ccount[:-window]
    out[window - 1:] = np.where(count > 0, total / np.maximum(count, 1.0), np.nan)
    return out


def rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing standard deviation, population form, including the current bar."""
    values = np.asarray(values, dtype="float64")
    mean = rolling_mean(values, window)
    mean_square = rolling_mean(values * values, window)
    variance = mean_square - mean * mean
    return np.sqrt(np.maximum(variance, 0.0))


def rolling_rank(values: np.ndarray, window: int) -> np.ndarray:
    """Where the current value sits in its own trailing window, 0 to 1.

    A percentile against the *past* only.  Ranking against the whole series is
    the classic way to leak the future into a feature and it is invisible in
    the output.
    """
    values = np.asarray(values, dtype="float64")
    n = values.size
    out = np.full(n, np.nan)
    if window < 2 or n < window:
        return out
    from numpy.lib.stride_tricks import sliding_window_view

    view = sliding_window_view(values, window)
    current = view[:, -1][:, None]
    valid = np.isfinite(view)
    below = np.sum((view < current) & valid, axis=1)
    count = np.sum(valid, axis=1)
    ranked = np.where(count > 1, below / np.maximum(count - 1, 1), np.nan)
    out[window - 1:] = np.where(np.isfinite(values[window - 1:]), ranked, np.nan)
    return out


def zscore(values: np.ndarray, window: int) -> np.ndarray:
    """Trailing z-score: how unusual this value is against its own recent past."""
    mean = rolling_mean(values, window)
    spread = rolling_std(values, window)
    return _safe(np.asarray(values, dtype="float64") - mean, spread)


# ---------------------------------------------------------------------------
# the families
# ---------------------------------------------------------------------------


def _trend(bars: BarSeries) -> Iterator[Feature]:
    for period in (20, 50, 200):
        def distance(b: BarSeries, p: int = period) -> np.ndarray:
            ema = _ind(b, "EMA", period=p)["value"]
            return _safe(b.close - ema, _atr(b))

        yield Feature(f"close_vs_ema{period}_atr", "trend",
                      f"How far the close is above the {period} EMA, in ATRs.",
                      distance, warmup=period + 14)

        def slope(b: BarSeries, p: int = period) -> np.ndarray:
            ema = _ind(b, "EMA", period=p)["value"]
            change = np.full(ema.shape, np.nan)
            change[5:] = ema[5:] - ema[:-5]
            return _safe(change, _atr(b))

        yield Feature(f"ema{period}_slope_atr", "trend",
                      f"Five-bar change in the {period} EMA, in ATRs.",
                      slope, warmup=period + 20)

    for fast, slow in ((20, 50), (50, 200)):
        def spread(b: BarSeries, f: int = fast, s: int = slow) -> np.ndarray:
            return _safe(_ind(b, "EMA", period=f)["value"]
                         - _ind(b, "EMA", period=s)["value"], _atr(b))

        yield Feature(f"ema{fast}_minus_ema{slow}_atr", "trend",
                      f"Gap between the {fast} and {slow} EMAs, in ATRs.",
                      spread, warmup=slow + 14)

    for period in (14, 28):
        yield Feature(f"adx{period}", "trend",
                      f"ADX over {period} bars: how directional the market is.",
                      lambda b, p=period: _ind(b, "ADX", period=p,
                                               adx_period=p)["adx"],
                      warmup=period * 3)

    for period in (14, 25):
        yield Feature(f"aroon_osc{period}", "trend",
                      f"Aroon oscillator over {period} bars.",
                      lambda b, p=period: _ind(b, "AROON", period=p)["oscillator"],
                      warmup=period + 5)


def _momentum(bars: BarSeries) -> Iterator[Feature]:
    for period in (5, 10, 20, 60):
        def roc(b: BarSeries, p: int = period) -> np.ndarray:
            change = np.full(b.close.shape, np.nan)
            change[p:] = b.close[p:] - b.close[:-p]
            return _safe(change, _atr(b) * np.sqrt(p))

        yield Feature(f"return{period}_atr", "momentum",
                      f"Return over {period} bars, in ATRs scaled by root time.",
                      roc, warmup=period + 14)

    for period in (7, 14, 21):
        yield Feature(f"rsi{period}", "momentum",
                      f"RSI over {period} bars.",
                      lambda b, p=period: _ind(b, "RSI", period=p)["value"],
                      warmup=period * 4)
        yield Feature(f"rsi{period}_z50", "momentum",
                      f"RSI({period}) as a z-score of its own last 50 values.",
                      lambda b, p=period: zscore(_ind(b, "RSI", period=p)["value"], 50),
                      warmup=period * 4 + 50)

    yield Feature("macd_hist_atr", "momentum",
                  "MACD histogram, in ATRs, so it is comparable across regimes.",
                  lambda b: _safe(_ind(b, "MACD", fast=12, slow=26,
                                       signal=9)["histogram"], _atr(b)),
                  warmup=90)

    for period in (9, 14):
        yield Feature(f"stoch_k{period}", "momentum",
                      f"Stochastic %K over {period} bars.",
                      lambda b, p=period: _ind(b, "STOCH", k_period=p, smooth_k=3,
                                               d_period=3)["k"],
                      warmup=period + 10)

    def streak(b: BarSeries) -> np.ndarray:
        direction = np.sign(np.diff(b.close, prepend=b.close[0]))
        out = np.zeros(direction.size)
        run = 0.0
        previous = 0.0
        for i, d in enumerate(direction):
            run = run + d if d == previous and d != 0 else d
            previous = d
            out[i] = run
        return out

    yield Feature("close_streak", "momentum",
                  "Consecutive bars closing the same way, signed.", streak,
                  warmup=2)


def _volatility(bars: BarSeries) -> Iterator[Feature]:
    for fast, slow in ((5, 50), (14, 100)):
        yield Feature(f"atr{fast}_over_atr{slow}", "volatility",
                      f"ATR({fast}) divided by ATR({slow}): is volatility "
                      f"expanding or contracting?",
                      lambda b, f=fast, s=slow: _safe(_atr(b, f), _atr(b, s)),
                      warmup=slow + 10)

    yield Feature("range_over_atr", "volatility",
                  "This bar's range against the average one.",
                  lambda b: _safe(b.high - b.low, _atr(b)), warmup=20)

    for window in (50, 200):
        yield Feature(f"atr_rank{window}", "volatility",
                      f"Where ATR sits in its own last {window} bars, 0 to 1.",
                      lambda b, w=window: rolling_rank(_atr(b), w),
                      warmup=window + 14)

    yield Feature("bb_width_rank100", "volatility",
                  "Bollinger band width against its own last 100 bars.",
                  lambda b: rolling_rank(_ind(b, "BBWIDTH", period=20,
                                              deviation=2.0)["value"], 100),
                  warmup=130)

    def parkinson(b: BarSeries) -> np.ndarray:
        with np.errstate(divide="ignore", invalid="ignore"):
            log_range = np.log(np.maximum(b.high, _EPS) / np.maximum(b.low, _EPS))
        return _safe(log_range, rolling_mean(log_range, 50))

    yield Feature("parkinson_ratio50", "volatility",
                  "High-low log range against its own fifty-bar average.",
                  parkinson, warmup=60)


def _shape(bars: BarSeries) -> Iterator[Feature]:
    yield Feature("close_position_in_bar", "shape",
                  "Where the close sits between the low and the high, 0 to 1.",
                  lambda b: _safe(b.close - b.low, b.high - b.low), warmup=1)
    yield Feature("body_over_range", "shape",
                  "Body size as a fraction of the whole bar.",
                  lambda b: _safe(np.abs(b.close - b.open), b.high - b.low),
                  warmup=1)
    yield Feature("upper_wick_fraction", "shape",
                  "Upper shadow as a fraction of the bar.",
                  lambda b: _safe(b.high - np.maximum(b.open, b.close),
                                  b.high - b.low), warmup=1)
    yield Feature("lower_wick_fraction", "shape",
                  "Lower shadow as a fraction of the bar.",
                  lambda b: _safe(np.minimum(b.open, b.close) - b.low,
                                  b.high - b.low), warmup=1)

    def gap(b: BarSeries) -> np.ndarray:
        previous = np.full(b.open.shape, np.nan)
        previous[1:] = b.close[:-1]
        return _safe(b.open - previous, _atr(b))

    yield Feature("gap_atr", "shape",
                  "Opening gap from the previous close, in ATRs.", gap,
                  warmup=20)

    def overlap(b: BarSeries) -> np.ndarray:
        previous_high = np.full(b.high.shape, np.nan)
        previous_low = np.full(b.low.shape, np.nan)
        previous_high[1:] = b.high[:-1]
        previous_low[1:] = b.low[:-1]
        shared = (np.minimum(b.high, previous_high)
                  - np.maximum(b.low, previous_low))
        return _safe(shared, b.high - b.low)

    yield Feature("overlap_with_previous", "shape",
                  "How much of this bar overlaps the last one; negative is a gap.",
                  overlap, warmup=2)


def _volume(bars: BarSeries) -> Iterator[Feature]:
    for window in (20, 100):
        yield Feature(f"volume_over_mean{window}", "volume",
                      f"Volume against its own {window}-bar average.",
                      lambda b, w=window: _safe(b.volume,
                                                rolling_mean(b.volume, w)),
                      warmup=window + 5)
        yield Feature(f"volume_z{window}", "volume",
                      f"Volume as a z-score of its last {window} bars.",
                      lambda b, w=window: zscore(b.volume, w),
                      warmup=window + 5)

    def effort(b: BarSeries) -> np.ndarray:
        move = np.abs(b.close - b.open)
        return _safe(_safe(move, _atr(b)), _safe(b.volume,
                                                 rolling_mean(b.volume, 50)))

    yield Feature("move_per_unit_volume", "volume",
                  "How far price moved for the volume it took; low means "
                  "effort without result.", effort, warmup=70)

    yield Feature("obv_slope_z100", "volume",
                  "Twenty-bar change in on-balance volume, as a z-score.",
                  lambda b: zscore(np.diff(_ind(b, "OBV")["value"],
                                           prepend=np.nan), 100), warmup=130)


def _reversion(bars: BarSeries) -> Iterator[Feature]:
    for window in (20, 50):
        yield Feature(f"close_z{window}", "reversion",
                      f"Close as a z-score of its own last {window} closes.",
                      lambda b, w=window: zscore(b.close, w), warmup=window + 5)
        yield Feature(f"close_rank{window}", "reversion",
                      f"Where the close sits in its last {window} bars, 0 to 1.",
                      lambda b, w=window: rolling_rank(b.close, w),
                      warmup=window + 5)

    for period in (20, 55):
        def channel(b: BarSeries, p: int = period) -> np.ndarray:
            out = _ind(b, "DONCHIAN", period=p)
            width = out["upper"] - out["lower"]
            return _safe(b.close - out["middle"], width * 0.5)

        yield Feature(f"donchian_position{period}", "reversion",
                      f"Position inside the {period}-bar channel, -1 to +1.",
                      channel, warmup=period + 5)

    yield Feature("cci20", "reversion",
                  "Commodity channel index over 20 bars.",
                  lambda b: _ind(b, "CCI", period=20)["value"], warmup=40)


def _session(bars: BarSeries) -> Iterator[Feature]:
    def since_open(b: BarSeries) -> np.ndarray:
        import pandas as pd

        index = pd.DatetimeIndex(pd.to_datetime(b.ts, utc=True))
        try:
            local = index.tz_convert(getattr(b.instrument, "timezone", "UTC"))
        except Exception:                   # pragma: no cover - bad tz name
            local = index
        day = (local.year * 10_000 + local.month * 100 + local.day).to_numpy()
        out = np.zeros(day.size, dtype="float64")
        count = 0
        previous = None
        for i, key in enumerate(day):
            count = 0 if key != previous else count + 1
            previous = key
            out[i] = count
        return out

    yield Feature("bars_since_day_open", "session",
                  "How far into the local day this bar is. Reported for "
                  "context; time of day is priced into every control, so an "
                  "edge that is only this is not an edge.",
                  since_open, warmup=1)

    def range_vs_time_of_day(b: BarSeries) -> np.ndarray:
        """This bar's range against what that minute of the day usually does."""
        minutes = ((np.asarray(b.ts, dtype="int64") // 60_000_000_000) % 1440)
        span = b.high - b.low
        out = np.full(span.shape, np.nan)
        for minute in np.unique(minutes):
            where = np.flatnonzero(minutes == minute)
            if where.size < 20:
                continue
            values = span[where]
            # Expanding mean of the PAST only, so the comparison is causal.
            csum = np.concatenate(([0.0], np.cumsum(np.nan_to_num(values))))
            counts = np.arange(values.size)
            past_mean = np.where(counts > 0, csum[:-1] / np.maximum(counts, 1),
                                 np.nan)
            out[where] = _safe(values, past_mean)
        return out

    yield Feature("range_vs_this_minute", "session",
                  "Bar range against what this minute of the day normally "
                  "produces, using only earlier days.", range_vs_time_of_day,
                  warmup=1)


_FAMILIES = (_trend, _momentum, _volatility, _shape, _volume, _reversion,
             _session)


def all_features() -> list[Feature]:
    """Every feature, in family order.  The length is the multiplicity."""
    out: list[Feature] = []
    for family in _FAMILIES:
        out.extend(family(None))            # type: ignore[arg-type]
    return out


def compute_matrix(bars: BarSeries, features: list[Feature] | None = None
                   ) -> tuple[np.ndarray, list[Feature]]:
    """``(values, features)`` where *values* is ``(bars, features)`` float64."""
    features = features if features is not None else all_features()
    matrix = np.full((len(bars), len(features)), np.nan)
    failed: list[str] = []
    for column, feature in enumerate(features):
        try:
            matrix[:, column] = feature.values(bars)
        except Exception as exc:            # pragma: no cover - defensive
            from ..logging_setup import get_logger

            get_logger(__name__).warning("Feature %s could not be computed: %s",
                                         feature.name, exc)
            failed.append(feature.name)
    if failed:
        # Not raised: one broken indicator should not stop a study of eighty
        # features.  It is reported, because a column of NaN that nobody
        # mentions looks exactly like a feature that predicts nothing.
        kept = [f for f in features if f.name not in set(failed)]
        keep_columns = [i for i, f in enumerate(features)
                        if f.name not in set(failed)]
        return matrix[:, keep_columns], kept
    return matrix, features
