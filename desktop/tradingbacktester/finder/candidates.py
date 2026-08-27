"""The entry rules a search is allowed to consider.

Six families, each a shape that traders actually use and that can be written
down as a rule: trend pullback, breakout, mean reversion, momentum, a moving
average cross, and a stochastic cross taken only with the trend. Every one is
parameterised over a small grid.

The grids are deliberately small. The number of combinations a search looks at
is the number of chances it had to be lucky, and it is reported with every
result for exactly that reason -- a search over a million rules will always
find something that looks wonderful and usually means nothing. Six families
with a few periods each is a few hundred, which is a multiplicity that can be
corrected for honestly.

Two properties every template here must have:

* **Causal.** A rule is evaluated on the close of bar *i* using only bars up to
  and including *i*. Indicators come from the same registry the engine uses, so
  the rule that gets exported is the rule that was tested.
* **Expressible.** Each template can emit a real
  :class:`~..strategy.spec.StrategySpec`, so anything found can be opened in
  the editor, re-run through the engine, charted and exported to Pine. A search
  that produced a number but not a strategy would be useless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

import numpy as np

from ..core.types import ExitSettings, SessionSettings
from ..data.models import BarSeries
from ..indicators.base import REGISTRY
from ..strategy.spec import (Compare, Const, Cross, ExprOperand, Group, Ind,
                             IndicatorSlot, Price, State, StrategySpec)


@dataclass
class Candidate:
    """One entry rule with its parameters fixed."""

    template: str
    params: dict[str, Any]
    side: int
    """``+1`` long, ``-1`` short."""

    @property
    def side_label(self) -> str:
        return "long" if self.side > 0 else "short"

    def describe(self) -> str:
        bits = ", ".join(f"{k} {v}" for k, v in self.params.items())
        return f"{self.template} ({bits}) {self.side_label}"

    def key(self) -> tuple:
        return (self.template, tuple(sorted(self.params.items())), self.side)


@dataclass
class Template:
    """A family of entry rules, and how to turn one into a strategy."""

    key: str
    label: str
    description: str
    grid: dict[str, tuple]
    signal: Callable[[BarSeries, dict, int], np.ndarray]
    build: Callable[[dict, int], tuple[list[IndicatorSlot], Any]]
    """``(params, side) -> (indicator slots, entry condition)``."""
    warmup: Callable[[dict], int]
    """Bars this family needs before its rule means anything.

    Reported for the record, and deliberately NOT used to mask the signals:
    :func:`warmup_for` takes the warm-up from the same indicator registry the
    engine takes it from, because the search's job is to measure the strategy
    the user will actually run. Skipping more bars here than the engine skips
    would make the search describe a strategy nobody can reproduce. If one of
    these declarations is right, the fix belongs in the indicator's own
    ``min_bars`` -- where the engine will honour it too.
    """
    short_description: str = ""
    """How the rule reads on the short side, when that is not a rephrasing.
    A short RSI-reversion candidate crosses DOWN through an overbought level;
    describing it as "turns back up through an oversold level" puts a sentence
    in the saved strategy file that contradicts the rule inside it."""

    def describe(self, side: int) -> str:
        if side < 0 and self.short_description:
            return self.short_description
        return self.description

    def candidates(self, sides: tuple[int, ...]) -> Iterator[Candidate]:
        keys = list(self.grid)

        def walk(index: int, chosen: dict) -> Iterator[dict]:
            if index == len(keys):
                yield dict(chosen)
                return
            name = keys[index]
            for value in self.grid[name]:
                chosen[name] = value
                yield from walk(index + 1, chosen)

        for combo in walk(0, {}):
            if not self._sane(combo):
                continue
            for side in sides:
                yield Candidate(self.key, combo, side)

    @staticmethod
    def _sane(params: dict) -> bool:
        fast, slow = params.get("fast"), params.get("slow")
        if fast is not None and slow is not None and fast >= slow:
            return False
        return True


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


#: Indicator results, keyed by the series identity and the exact parameters.
#:
#: A search asks 130 candidates for their signals and they overlap heavily: on
#: the shipped grid that is 188 indicator computations of only 34 distinct
#: things, with EMA(100) and EMA(200) each computed sixteen times over the same
#: half-million bars. Nothing about that was wrong, only wasteful -- 5.5x
#: wasteful, on the single most expensive step in the whole search.
#:
#: The key holds the series OBJECT, not its id, so a BarSeries that has been
#: garbage-collected cannot let a later one with a recycled id read its
#: neighbour's numbers. Bounded, because a long session resamples and mirrors
#: and slices, and an unbounded cache of half-million-point arrays is a leak
#: with a polite name.
_CACHE_LIMIT = 256
_INDICATOR_CACHE: "dict[tuple, tuple[BarSeries, dict[str, np.ndarray]]]" = {}


def clear_indicator_cache() -> None:
    """Forget every memoised indicator. Only the tests need this."""
    _INDICATOR_CACHE.clear()


def _compute(bars: BarSeries, key: str, params: dict) -> dict[str, np.ndarray]:
    """``REGISTRY.compute``, memoised per series and parameter set."""
    signature = (id(bars), key, tuple(sorted(params.items())))
    hit = _INDICATOR_CACHE.get(signature)
    if hit is not None and hit[0] is bars:
        return hit[1]
    out = REGISTRY.compute(key, bars, params)
    if len(_INDICATOR_CACHE) >= _CACHE_LIMIT:
        _INDICATOR_CACHE.pop(next(iter(_INDICATOR_CACHE)), None)
    _INDICATOR_CACHE[signature] = (bars, out)
    return out


def _ind(bars: BarSeries, key: str, output: str = "value", **params) -> np.ndarray:
    return _compute(bars, key, params)[output]


def _crossed_up(series: np.ndarray, level: np.ndarray | float) -> np.ndarray:
    """True on the bar a series finishes above a level, not having been above it.

    The previous bar must be at or below the level -- **not** strictly below.
    That is the engine's rule (``strategy/rules.py::_cross``), and the fast path
    is only worth having if it is the engine.

    Requiring the previous bar to be strictly below silently drops every
    crossing that began from an exact touch. On a bounded oscillator those are
    not rare: %K and %D sit together at 100 whenever price closes at the top of
    its range, so a stochastic cross out of that state was never counted here
    and always counted by the engine. It cost 10 trades in 3,614 on one
    5-minute candidate -- invisible, because the outcome arithmetic agreed to
    the last cent on every trade the two did share.
    """
    level_arr = np.full_like(series, float(level)) if np.isscalar(level) else level
    out = np.zeros(series.shape, dtype=bool)
    finite = np.isfinite(series) & np.isfinite(level_arr)
    # Bar 0 has no previous bar, so no crossing can be observed there.
    pair_finite = np.zeros(series.shape, dtype=bool)
    pair_finite[1:] = finite[1:] & finite[:-1]
    out[1:] = (series[1:] > level_arr[1:]) & (series[:-1] <= level_arr[:-1])
    return out & pair_finite


def _crossed_down(series: np.ndarray, level: np.ndarray | float) -> np.ndarray:
    level_arr = np.full_like(series, float(level)) if np.isscalar(level) else level
    return _crossed_up(-series, -level_arr)


def _directional(up: np.ndarray, down: np.ndarray, side: int) -> np.ndarray:
    return up if side > 0 else down


def _rolling_extreme(values: np.ndarray, window: int, highest: bool) -> np.ndarray:
    """Extreme of the *previous* ``window`` bars -- never including this one."""
    n = values.size
    out = np.full(n, np.nan)
    if window <= 0 or n <= window:
        return out
    from numpy.lib.stride_tricks import sliding_window_view

    view = sliding_window_view(values, window)
    agg = view.max(axis=1) if highest else view.min(axis=1)
    out[window:] = agg[:-1]
    return out


# ---------------------------------------------------------------------------
# the templates
# ---------------------------------------------------------------------------


def _pullback_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    fast = _ind(bars, "EMA", period=p["fast"])
    slow = _ind(bars, "EMA", period=p["slow"])
    close = bars.close
    if side > 0:
        trend = fast > slow
        return trend & _crossed_up(close, fast)
    trend = fast < slow
    return trend & _crossed_down(close, fast)


def _pullback_build(p: dict, side: int):
    slots = [IndicatorSlot("emaFast", "EMA", {"period": p["fast"]}),
             IndicatorSlot("emaSlow", "EMA", {"period": p["slow"]})]
    trend = Compare(Ind("emaFast"), ">" if side > 0 else "<", Ind("emaSlow"))
    touch = Cross(Price("close"), "above" if side > 0 else "below", Ind("emaFast"))
    return slots, Group("and", [trend, touch])


def _breakout_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    window = int(p["lookback"])
    if side > 0:
        prior = _rolling_extreme(bars.high, window, True)
        return np.isfinite(prior) & (bars.close > prior)
    prior = _rolling_extreme(bars.low, window, False)
    return np.isfinite(prior) & (bars.close < prior)


def _breakout_build(p: dict, side: int):
    slots = [IndicatorSlot("channel", "DONCHIAN", {"period": p["lookback"]})]
    output = "upper" if side > 0 else "lower"
    cond = Compare(Price("close"), ">" if side > 0 else "<",
                   Ind("channel", output, offset=1))
    return slots, cond


def _reversion_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    rsi = _ind(bars, "RSI", period=p["period"])
    if side > 0:
        return _crossed_up(rsi, float(p["level"]))
    return _crossed_down(rsi, 100.0 - float(p["level"]))


def _reversion_build(p: dict, side: int):
    slots = [IndicatorSlot("rsi", "RSI", {"period": p["period"]})]
    level = float(p["level"]) if side > 0 else 100.0 - float(p["level"])
    cond = Cross(Ind("rsi"), "above" if side > 0 else "below", Const(level))
    return slots, cond


def _band_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    out = _compute(bars, "BBANDS",
                           {"period": p["period"], "deviation": p["deviations"]})
    band = out["lower"] if side > 0 else out["upper"]
    return (_crossed_up(bars.close, band) if side > 0
            else _crossed_down(bars.close, band))


def _band_build(p: dict, side: int):
    slots = [IndicatorSlot("bb", "BBANDS",
                           {"period": p["period"], "deviation": p["deviations"]})]
    output = "lower" if side > 0 else "upper"
    cond = Cross(Price("close"), "above" if side > 0 else "below",
                 Ind("bb", output))
    return slots, cond


def _macd_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    out = _compute(bars, "MACD", {"fast": p["fast"], "slow": p["slow"],
                                          "signal": p["signal"]})
    line, sig = out["macd"], out["signal"]
    return (_crossed_up(line, sig) if side > 0 else _crossed_down(line, sig))


def _macd_build(p: dict, side: int):
    slots = [IndicatorSlot("macd", "MACD", {"fast": p["fast"], "slow": p["slow"],
                                            "signal": p["signal"]})]
    cond = Cross(Ind("macd", "macd"), "above" if side > 0 else "below",
                 Ind("macd", "signal"))
    return slots, cond


def _stoch_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    out = _compute(bars, "STOCH", {"k_period": p["k"], "smooth_k": 3,
                                           "d_period": 3})
    k, d = out["k"], out["d"]
    trend = _ind(bars, "EMA", period=p["trend"])
    cross = _crossed_up(k, d) if side > 0 else _crossed_down(k, d)
    with_trend = (bars.close > trend) if side > 0 else (bars.close < trend)
    return cross & np.isfinite(trend) & with_trend


def _stoch_build(p: dict, side: int):
    slots = [IndicatorSlot("stoch", "STOCH",
                           {"k_period": p["k"], "smooth_k": 3, "d_period": 3}),
             IndicatorSlot("emaTrend", "EMA", {"period": p["trend"]})]
    cross = Cross(Ind("stoch", "k"), "above" if side > 0 else "below",
                  Ind("stoch", "d"))
    trend = Compare(Price("close"), ">" if side > 0 else "<", Ind("emaTrend"))
    return slots, Group("and", [cross, trend])


def _structure_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    """Market structure: price takes out the last confirmed swing point.

    Not the same rule as the channel breakout, and the difference is the point.
    A Donchian break is "higher than anything in the last N bars", which fires
    on any drift to a new extreme. This fires only when price closes through
    the last *pivot* -- a level the market turned at and other people are
    watching -- and the pivot is published ``right`` bars after it happened, so
    the level was knowable before the close that breaks it.
    """
    left = right = int(p["swing"])
    level = _compute(
        bars, "PIVOT_HIGH" if side > 0 else "PIVOT_LOW",
        {"left": left, "right": right, "hold": True})["value"]
    trend = _ind(bars, "EMA", period=p["trend"])
    with_trend = (bars.close > trend) if side > 0 else (bars.close < trend)
    cross = (_crossed_up(bars.close, level) if side > 0
             else _crossed_down(bars.close, level))
    return cross & np.isfinite(trend) & with_trend


def _structure_build(p: dict, side: int):
    left = right = int(p["swing"])
    slots = [IndicatorSlot("pivot", "PIVOT_HIGH" if side > 0 else "PIVOT_LOW",
                           {"left": left, "right": right, "hold": True}),
             IndicatorSlot("emaTrend", "EMA", {"period": p["trend"]})]
    cross = Cross(Price("close"), "above" if side > 0 else "below",
                  Ind("pivot"))
    trend = Compare(Price("close"), ">" if side > 0 else "<", Ind("emaTrend"))
    return slots, Group("and", [cross, trend])


def _momentum_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    """Rate of change crosses a threshold: momentum with no average in it.

    Every other family here reads a moving average somewhere, so they all share
    a failure mode -- a market that chops around a mean. This one asks only
    whether the last N bars moved, and by how much.
    """
    roc = _ind(bars, "ROC", period=p["period"])
    level = float(p["level"])
    return (_crossed_up(roc, level) if side > 0
            else _crossed_down(roc, -level))


def _momentum_build(p: dict, side: int):
    slots = [IndicatorSlot("roc", "ROC", {"period": p["period"]})]
    level = float(p["level"]) if side > 0 else -float(p["level"])
    return slots, Cross(Ind("roc"), "above" if side > 0 else "below",
                        Const(level))


def _squeeze_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    """Volatility compresses, then price leaves the band it compressed into.

    Two conditions the other families never combine: band width BELOW a
    threshold on the previous bar, and a close through the band on this one.
    The compression is read one bar back on purpose -- the bar that expands is
    not a bar that was quiet.
    """
    width = _compute(
        bars, "BBWIDTH", {"period": p["period"], "deviation": 2.0})["value"]
    out = _compute(bars, "BBANDS",
                   {"period": p["period"], "deviation": 2.0})
    quiet = np.zeros(width.shape, dtype=bool)
    quiet[1:] = np.isfinite(width[:-1]) & (width[:-1] < float(p["max_width"]))
    band = out["upper"] if side > 0 else out["lower"]
    breakout = (_crossed_up(bars.close, band) if side > 0
                else _crossed_down(bars.close, band))
    return quiet & breakout


def _squeeze_build(p: dict, side: int):
    slots = [IndicatorSlot("bbw", "BBWIDTH",
                           {"period": p["period"], "deviation": 2.0}),
             IndicatorSlot("bb", "BBANDS",
                           {"period": p["period"], "deviation": 2.0})]
    quiet = Compare(Ind("bbw", offset=1), "<", Const(float(p["max_width"])))
    breakout = Cross(Price("close"), "above" if side > 0 else "below",
                     Ind("bb", "upper" if side > 0 else "lower"))
    return slots, Group("and", [quiet, breakout])


def _range_signal(bars: BarSeries, p: dict, side: int) -> np.ndarray:
    """A bar whose range dwarfs the recent average, closing in its direction.

    Range expansion is the one shape here that reads the CURRENT bar's own
    size rather than a level. The average it is measured against is taken one
    bar back, so the expanding bar is not part of what it is being compared to.
    """
    tr = _compute(bars, "TRUE_RANGE", {})["value"]
    # ATR with its default method, and the SAME indicator the spec below emits:
    # the fast path and the engine must read one series, not two that agree
    # most of the time.
    avg = _ind(bars, "ATR", period=p["period"])
    prior = np.full(avg.shape, np.nan)
    prior[1:] = avg[:-1]
    big = np.isfinite(prior) & (prior > 0) & (tr > prior * float(p["multiple"]))
    direction = (bars.close > bars.open) if side > 0 else (bars.close < bars.open)
    return big & direction


def _range_build(p: dict, side: int):
    slots = [IndicatorSlot("tr", "TRUE_RANGE", {}),
             IndicatorSlot("atr", "ATR", {"period": p["period"]})]
    big = Compare(Ind("tr"), ">",
                  ExprOperand("*", Ind("atr", offset=1),
                              Const(float(p["multiple"]))))
    direction = Compare(Price("close"), ">" if side > 0 else "<", Price("open"))
    return slots, Group("and", [big, direction])


TEMPLATES: tuple[Template, ...] = (
    Template(
        key="trend_pullback", label="Trend pullback",
        description="Price pulls back up to the fast average while the fast "
                    "average is above the slow one.",
        short_description="Price pulls back down to the fast average while the "
                          "fast average is below the slow one.",
        grid={"fast": (10, 20, 50), "slow": (50, 100, 200)},
        signal=_pullback_signal, build=_pullback_build,
        warmup=lambda p: int(p["slow"]) + 5),
    Template(
        key="breakout", label="Channel breakout",
        description="Close beyond the highest high of the previous N bars.",
        short_description="Close below the lowest low of the previous N bars.",
        grid={"lookback": (10, 20, 40, 80)},
        signal=_breakout_signal, build=_breakout_build,
        warmup=lambda p: int(p["lookback"]) + 5),
    Template(
        key="rsi_reversion", label="RSI reversion",
        description="RSI turns back up through an oversold level.",
        short_description="RSI turns back down through an overbought level.",
        grid={"period": (7, 14, 21), "level": (25.0, 30.0, 35.0)},
        signal=_reversion_signal, build=_reversion_build,
        warmup=lambda p: int(p["period"]) * 4),
    Template(
        key="band_reversion", label="Bollinger reversion",
        description="Close crosses back inside the lower band.",
        short_description="Close crosses back inside the upper band.",
        grid={"period": (14, 20, 30), "deviations": (2.0, 2.5)},
        signal=_band_signal, build=_band_build,
        warmup=lambda p: int(p["period"]) + 5),
    Template(
        key="macd_cross", label="MACD cross",
        description="The MACD line crosses above its signal line.",
        short_description="The MACD line crosses below its signal line.",
        grid={"fast": (8, 12), "slow": (21, 26), "signal": (9,)},
        signal=_macd_signal, build=_macd_build,
        warmup=lambda p: int(p["slow"]) * 3),
    Template(
        key="stoch_trend", label="Stochastic with the trend",
        description="%K crosses above %D, taken only above a long moving "
                    "average.",
        short_description="%K crosses below %D, taken only below a long moving "
                          "average.",
        grid={"k": (9, 14), "trend": (100, 200)},
        signal=_stoch_signal, build=_stoch_build,
        warmup=lambda p: int(p["trend"]) + 10),
    Template(
        key="structure_break", label="Break of structure",
        description="Close takes out the last confirmed swing high, above a "
                    "long moving average.",
        short_description="Close takes out the last confirmed swing low, below "
                          "a long moving average.",
        grid={"swing": (3, 5, 8), "trend": (50, 100, 200)},
        signal=_structure_signal, build=_structure_build,
        warmup=lambda p: int(p["trend"]) + int(p["swing"]) * 2 + 5),
    Template(
        key="momentum", label="Rate-of-change momentum",
        description="Rate of change crosses up through a positive threshold.",
        short_description="Rate of change crosses down through a negative "
                          "threshold.",
        grid={"period": (5, 10, 20), "level": (0.25, 0.5, 1.0)},
        signal=_momentum_signal, build=_momentum_build,
        warmup=lambda p: int(p["period"]) + 5),
    Template(
        key="squeeze", label="Volatility squeeze",
        description="Bands were narrow, and price closes out through the "
                    "upper one.",
        short_description="Bands were narrow, and price closes out through the "
                          "lower one.",
        grid={"period": (20, 30), "max_width": (1.0, 1.5, 2.0)},
        signal=_squeeze_signal, build=_squeeze_build,
        warmup=lambda p: int(p["period"]) + 5),
    Template(
        key="range_expansion", label="Range expansion",
        description="A bar far larger than the recent average, closing up.",
        short_description="A bar far larger than the recent average, closing "
                          "down.",
        grid={"period": (14, 20), "multiple": (1.5, 2.0, 3.0)},
        signal=_range_signal, build=_range_build,
        warmup=lambda p: int(p["period"]) + 5),
)

TEMPLATES_BY_KEY = {t.key: t for t in TEMPLATES}


def all_candidates(sides: tuple[int, ...] = (1, -1),
                   templates: tuple[str, ...] = ()) -> list[Candidate]:
    """Every candidate in the space, which is also the multiplicity of a search.

    An unknown family name is refused by name rather than raising a KeyError
    three frames down: a typo in a filter that silently searched everything
    would report a multiplicity the user did not choose, and one that crashed
    would do it after the data had already been loaded.
    """
    unknown = [k for k in templates if k not in TEMPLATES_BY_KEY]
    if unknown:
        from ..core.errors import StrategyError

        raise StrategyError(
            f"{'These are not entry-rule families' if len(unknown) > 1 else 'That is not an entry-rule family'}"
            f": {', '.join(unknown)}. Choose from: "
            f"{', '.join(t.key for t in TEMPLATES)}.")
    chosen = ([TEMPLATES_BY_KEY[k] for k in templates] if templates
              else list(TEMPLATES))
    out: list[Candidate] = []
    for template in chosen:
        out.extend(template.candidates(sides))
    return out


def warmup_for(candidate: Candidate, atr_period: int = 14) -> int:
    """Bars the engine would refuse to trade on, for this candidate.

    Taken from the same place the engine takes it -- the indicator registry's
    own declared warm-up -- so the fast search skips exactly the bars a real
    run would skip. Without it the search scores trades on an EMA that has
    seen four bars, and then wonders why the engine disagrees.
    """
    from ..indicators.base import REGISTRY

    template = TEMPLATES_BY_KEY[candidate.template]
    slots, _ = template.build(candidate.params, candidate.side)
    need = 1
    # From the registry, which is where the engine gets it. See Template.warmup
    # for why the family's own declaration is not used here.
    for slot in slots:
        definition = REGISTRY.get(slot.indicator)
        need = max(need, definition.warmup(
            definition.coerce_params(slot.params)))
    return int(max(need, int(atr_period))) + 1


def signals_for(bars: BarSeries, candidate: Candidate,
                warmup: int = 0) -> np.ndarray:
    """The entry mask for one candidate, evaluated on bar closes."""
    template = TEMPLATES_BY_KEY[candidate.template]
    mask = np.asarray(template.signal(bars, candidate.params, candidate.side),
                      dtype=bool)
    if warmup > 0:
        mask[:min(int(warmup), mask.size)] = False
    return mask


def build_spec(candidate: Candidate, style, timeframe: str,
               stop_atr: float, target_r: float, costs, name: str = "",
               instrument_timezone: str = "America/New_York") -> StrategySpec:
    """Turn a found candidate into a real, runnable, saveable strategy."""
    template = TEMPLATES_BY_KEY[candidate.template]
    slots, condition = template.build(candidate.params, candidate.side)

    spec = StrategySpec(
        name=name or f"{template.label} {candidate.side_label} {timeframe}",
        description=(
            f"{template.describe(candidate.side)}\n\n"
            f"Found by the strategy finder on {timeframe} bars in the "
            f"{style.label.lower()} style. Historical analysis of one sample; "
            f"not a prediction."),
        tags=["found", style.key, candidate.side_label],
        indicators=list(slots),
    )
    if candidate.side > 0:
        spec.entry_long = condition
    else:
        spec.entry_short = condition

    spec.exits = ExitSettings(
        stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=stop_atr,
        take_profit_enabled=True, take_profit_mode="r_multiple",
        take_profit_value=target_r,
        atr_period=style.atr_period, max_bars_in_trade=style.max_bars,
    )
    if style.session is not None:
        spec.session = SessionSettings(
            enabled=True, start=style.session[0], end=style.session[1],
            timezone=instrument_timezone, weekdays=tuple(style.weekdays),
            flat_at_session_end=style.flat_at_session_end)
    elif len(style.weekdays) < 7:
        # A style with no time window still has a weekday constraint, and the
        # search applies it. Leaving it off the spec meant the shipped strategy
        # traded bars the search never counted -- Sunday evening, when an index
        # CFD reopens -- so it could not reproduce the result it was found by:
        # four extra trades in 152 on one swing candidate, and the difference
        # went the strategy's way. ``start == end`` is the engine's own
        # spelling of a 24-hour session, so this adds the weekday filter and
        # nothing else.
        spec.session = SessionSettings(
            enabled=True, start="00:00", end="00:00",
            timezone=instrument_timezone, weekdays=tuple(style.weekdays),
            flat_at_session_end=False)
    spec.costs = costs
    return spec
