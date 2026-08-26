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
from ..strategy.spec import (Compare, Const, Cross, Group, Ind,
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


def _ind(bars: BarSeries, key: str, output: str = "value", **params) -> np.ndarray:
    return REGISTRY.compute(key, bars, params)[output]


def _crossed_up(series: np.ndarray, level: np.ndarray | float) -> np.ndarray:
    """True on the bar a series finishes above a level having been below it."""
    level_arr = np.full_like(series, float(level)) if np.isscalar(level) else level
    out = np.zeros(series.shape, dtype=bool)
    ok = np.isfinite(series) & np.isfinite(level_arr)
    above = ok & (series > level_arr)
    below = np.roll(ok & (series < level_arr), 1)
    below[0] = False
    out[1:] = (above & below)[1:]
    return out


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
    out = REGISTRY.compute("BBANDS", bars,
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
    out = REGISTRY.compute("MACD", bars, {"fast": p["fast"], "slow": p["slow"],
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
    out = REGISTRY.compute("STOCH", bars, {"k_period": p["k"], "smooth_k": 3,
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


TEMPLATES: tuple[Template, ...] = (
    Template(
        key="trend_pullback", label="Trend pullback",
        description="Price pulls back to the fast average while the fast "
                    "average is on the right side of the slow one.",
        grid={"fast": (10, 20, 50), "slow": (50, 100, 200)},
        signal=_pullback_signal, build=_pullback_build,
        warmup=lambda p: int(p["slow"]) + 5),
    Template(
        key="breakout", label="Channel breakout",
        description="Close beyond the highest high (or lowest low) of the "
                    "previous N bars.",
        grid={"lookback": (10, 20, 40, 80)},
        signal=_breakout_signal, build=_breakout_build,
        warmup=lambda p: int(p["lookback"]) + 5),
    Template(
        key="rsi_reversion", label="RSI reversion",
        description="RSI turns back up through an oversold level.",
        grid={"period": (7, 14, 21), "level": (25.0, 30.0, 35.0)},
        signal=_reversion_signal, build=_reversion_build,
        warmup=lambda p: int(p["period"]) * 4),
    Template(
        key="band_reversion", label="Bollinger reversion",
        description="Close crosses back inside the lower band.",
        grid={"period": (14, 20, 30), "deviations": (2.0, 2.5)},
        signal=_band_signal, build=_band_build,
        warmup=lambda p: int(p["period"]) + 5),
    Template(
        key="macd_cross", label="MACD cross",
        description="The MACD line crosses its signal line.",
        grid={"fast": (8, 12), "slow": (21, 26), "signal": (9,)},
        signal=_macd_signal, build=_macd_build,
        warmup=lambda p: int(p["slow"]) * 3),
    Template(
        key="stoch_trend", label="Stochastic with the trend",
        description="%K crosses %D, taken only on the side of a long moving "
                    "average.",
        grid={"k": (9, 14), "trend": (100, 200)},
        signal=_stoch_signal, build=_stoch_build,
        warmup=lambda p: int(p["trend"]) + 10),
)

TEMPLATES_BY_KEY = {t.key: t for t in TEMPLATES}


def all_candidates(sides: tuple[int, ...] = (1, -1),
                   templates: tuple[str, ...] = ()) -> list[Candidate]:
    """Every candidate in the space, which is also the multiplicity of a search."""
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
            f"{template.description}\n\n"
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
    spec.costs = costs
    return spec
