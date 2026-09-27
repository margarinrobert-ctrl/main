"""The strategies that ship with the application.

Seven complete, runnable strategies, each one built out of the same declarative
pieces a user gets in the strategy editor.  They exist for three reasons: the
application has something to run on first launch, every part of the rule
language has a worked example, and the parameters are wired through ``"$name"``
references so the optimiser has something to sweep the moment it is opened.

None of these is a recommendation.  They are textbook structures on textbook
defaults; the honest expectation for any of them, on any real instrument, after
costs, is a loss.  What they demonstrate is the *machinery* — crossings,
thresholds, offsets, channel breakouts, session windows, multi-output indicators
and ATR-based exits.

Every factory returns a fresh :class:`StrategySpec` with a stable ``id``, so
re-seeding a workspace updates the same file instead of piling up duplicates,
and every one passes :meth:`StrategySpec.validate` without raising.
"""

from __future__ import annotations

import logging
from typing import Callable

from ..core.types import (CostModel, ExecutionSettings, ExitSettings,
                          RiskSettings, SessionSettings)
from ..indicators.base import ParamSpec
from .spec import (Compare, Const, Cross, Group, Ind, IndicatorSlot, Param,
                   Price, SessionWindow, StrategySpec)

log = logging.getLogger(__name__)

__all__ = ["BUILTIN_STRATEGIES", "builtin_specs", "get_builtin",
           "ema_cross_rsi", "rsi_mean_reversion", "bollinger_breakout",
           "macd_trend", "donchian_breakout", "opening_range_momentum",
           "supertrend_follower"]

_AUTHOR = "Trading Backtester"


def _risk(allow_long: bool = True, allow_short: bool = True) -> RiskSettings:
    """Standard risk block: the application defaults, plus the allowed sides.

    Sizing is left at one unit per trade on purpose.  It is the only mode that
    produces a trade on every instrument -- risk-percent sizing rounds down to
    zero contracts on a futures symbol with a $100,000 account -- and the Risk
    panel is where a user changes it once they know what they are trading.
    """
    return RiskSettings(allow_long=allow_long, allow_short=allow_short)


# --------------------------------------------------------------------------
# 1. The specification's worked example
# --------------------------------------------------------------------------


def ema_cross_rsi() -> StrategySpec:
    """EMA 20 crosses above EMA 50 with RSI above 50; stop 1.5 ATR, target 3 ATR.

    This is the example from the specification, expressed exactly: two moving
    averages for the crossing and an oscillator as a filter, so the entry needs
    both a trigger and a condition.  Long only, because that is how the example
    is written.
    """
    spec = StrategySpec(
        id="bi-ema-rsi", name="EMA Cross + RSI", author=_AUTHOR,
        tags=["built-in", "trend"],
        description=(
            "Buys when the fast EMA crosses above the slow EMA while RSI is above "
            "its level, and sells when the fast EMA crosses back below. The RSI "
            "filter is there to skip crossings that happen with no momentum "
            "behind them. Protective stop at 1.5 ATR, target at 3 ATR."),
        params=[
            ParamSpec("ema_fast", "Fast EMA", "int", 20, 2, 400, 1,
                      help="Period of the fast exponential moving average."),
            ParamSpec("ema_slow", "Slow EMA", "int", 50, 3, 1000, 1,
                      help="Period of the slow exponential moving average."),
            ParamSpec("rsi_period", "RSI Period", "int", 14, 2, 200, 1,
                      help="Look-back of the RSI filter."),
            ParamSpec("rsi_level", "RSI Level", "float", 50.0, 1.0, 99.0, 1.0,
                      help="RSI must be above this for a long entry."),
        ],
        indicators=[
            IndicatorSlot("emaFast", "EMA", {"period": "$ema_fast"}, "close",
                          label="EMA Fast"),
            IndicatorSlot("emaSlow", "EMA", {"period": "$ema_slow"}, "close",
                          label="EMA Slow"),
            IndicatorSlot("rsi", "RSI", {"period": "$rsi_period"}, "close"),
        ],
        entry_long=Group("AND", [
            Cross(Ind("emaFast"), "above", Ind("emaSlow")),
            Compare(Ind("rsi"), ">", Param("rsi_level")),
        ]),
        exit_long=Cross(Ind("emaFast"), "below", Ind("emaSlow")),
        risk=_risk(allow_short=False),
        exits=ExitSettings(
            stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=1.5,
            take_profit_enabled=True, take_profit_mode="atr", take_profit_value=3.0,
            atr_period=14),
        execution=ExecutionSettings(),
        session=SessionSettings(),
        costs=CostModel(),
    )
    return spec


# --------------------------------------------------------------------------
# 2. Mean reversion
# --------------------------------------------------------------------------


def rsi_mean_reversion() -> StrategySpec:
    """Buy an oversold RSI turning up, in the direction of the long trend.

    The entry is a *crossing* out of oversold rather than the oversold reading
    itself: an RSI below 30 can stay below 30 for a hundred bars, and buying the
    reading buys every one of them.  The moving-average filter is what stops the
    strategy buying dips in a market that is simply falling.
    """
    return StrategySpec(
        id="bi-rsi-mr", name="RSI Mean Reversion", author=_AUTHOR,
        tags=["built-in", "mean reversion"],
        description=(
            "Buys when RSI crosses back up through the oversold level while price "
            "is above its long moving average, and sells short on the mirror "
            "condition. Trades are closed when RSI returns to the middle, on a "
            "2.5 ATR stop, or after the time stop, whichever comes first."),
        params=[
            ParamSpec("rsi_period", "RSI Period", "int", 14, 2, 200, 1,
                      help="Look-back of the RSI."),
            ParamSpec("oversold", "Oversold Level", "float", 30.0, 1.0, 49.0, 1.0,
                      help="RSI crossing up through this level opens a long."),
            ParamSpec("overbought", "Overbought Level", "float", 70.0, 51.0, 99.0, 1.0,
                      help="RSI crossing down through this level opens a short."),
            ParamSpec("exit_level", "Exit Level", "float", 50.0, 2.0, 98.0, 1.0,
                      help="RSI returning to this level closes the trade."),
            ParamSpec("trend_period", "Trend Filter", "int", 200, 5, 2000, 5,
                      help="Period of the moving average that decides which side "
                           "may be traded."),
        ],
        indicators=[
            IndicatorSlot("rsi", "RSI", {"period": "$rsi_period"}, "close"),
            IndicatorSlot("trend", "SMA", {"period": "$trend_period"}, "close",
                          label="Trend SMA"),
        ],
        entry_long=Group("AND", [
            Cross(Ind("rsi"), "above", Param("oversold")),
            Compare(Price("close"), ">", Ind("trend")),
        ]),
        exit_long=Cross(Ind("rsi"), "above", Param("exit_level")),
        entry_short=Group("AND", [
            Cross(Ind("rsi"), "below", Param("overbought")),
            Compare(Price("close"), "<", Ind("trend")),
        ]),
        exit_short=Cross(Ind("rsi"), "below", Param("exit_level")),
        risk=_risk(),
        exits=ExitSettings(
            stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=2.5,
            atr_period=14, max_bars_in_trade=20),
        execution=ExecutionSettings(),
        session=SessionSettings(),
        costs=CostModel(),
    )


# --------------------------------------------------------------------------
# 3. Volatility breakout
# --------------------------------------------------------------------------


def bollinger_breakout() -> StrategySpec:
    """Trade closes outside the Bollinger bands, exit back at the middle band.

    The opposite reading of the same indicator to :func:`rsi_mean_reversion`:
    here a close outside the band is treated as the start of a move rather than
    an extreme to fade.  Both readings are defensible and both are here so the
    two can be compared on the same data.
    """
    return StrategySpec(
        id="bi-bbands", name="Bollinger Breakout", author=_AUTHOR,
        tags=["built-in", "breakout"],
        description=(
            "Buys a close crossing above the upper Bollinger band and shorts a "
            "close crossing below the lower band, taking the move back to the "
            "middle band as the exit. Stop at 2 ATR, target at 4 ATR."),
        params=[
            ParamSpec("bb_period", "Bollinger Period", "int", 20, 3, 500, 1,
                      help="Look-back of the moving average and the deviation."),
            ParamSpec("bb_dev", "Deviations", "float", 2.0, 0.5, 5.0, 0.1,
                      help="Band width in standard deviations."),
        ],
        indicators=[
            IndicatorSlot("bb", "BBANDS",
                          {"period": "$bb_period", "deviation": "$bb_dev"},
                          "close", label="Bollinger"),
        ],
        entry_long=Cross(Price("close"), "above", Ind("bb", "upper")),
        exit_long=Cross(Price("close"), "below", Ind("bb", "middle")),
        entry_short=Cross(Price("close"), "below", Ind("bb", "lower")),
        exit_short=Cross(Price("close"), "above", Ind("bb", "middle")),
        risk=_risk(),
        exits=ExitSettings(
            stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=2.0,
            take_profit_enabled=True, take_profit_mode="atr", take_profit_value=4.0,
            atr_period=14),
        execution=ExecutionSettings(),
        session=SessionSettings(),
        costs=CostModel(),
    )


# --------------------------------------------------------------------------
# 4. Trend following on a multi-output indicator
# --------------------------------------------------------------------------


def macd_trend() -> StrategySpec:
    """MACD signal-line crossings, filtered by a long EMA, held with a trail.

    Shows a multi-output indicator (``macd``, ``signal``, ``histogram``) and a
    trailing stop that only starts once the trade is 1 R in front, which is the
    usual way of letting a trend run without giving back the whole move.
    """
    return StrategySpec(
        id="bi-macd", name="MACD Trend", author=_AUTHOR,
        tags=["built-in", "trend"],
        description=(
            "Buys when the MACD line crosses above its signal line while price is "
            "above the trend EMA, and mirrors that for shorts. Exits on the "
            "opposite crossing, a 2 ATR stop, or a 3 ATR trailing stop that "
            "activates once the trade is 1 R in profit."),
        params=[
            ParamSpec("macd_fast", "MACD Fast", "int", 12, 2, 200, 1,
                      help="Fast EMA period inside the MACD."),
            ParamSpec("macd_slow", "MACD Slow", "int", 26, 3, 400, 1,
                      help="Slow EMA period inside the MACD."),
            ParamSpec("macd_signal", "Signal Period", "int", 9, 1, 100, 1,
                      help="EMA period of the signal line."),
            ParamSpec("trend_period", "Trend EMA", "int", 200, 5, 2000, 5,
                      help="Period of the EMA that decides which side may be traded."),
        ],
        indicators=[
            IndicatorSlot("macd", "MACD",
                          {"fast": "$macd_fast", "slow": "$macd_slow",
                           "signal": "$macd_signal"}, "close", label="MACD"),
            IndicatorSlot("trend", "EMA", {"period": "$trend_period"}, "close",
                          label="Trend EMA"),
        ],
        entry_long=Group("AND", [
            Cross(Ind("macd", "macd"), "above", Ind("macd", "signal")),
            Compare(Price("close"), ">", Ind("trend")),
        ]),
        exit_long=Cross(Ind("macd", "macd"), "below", Ind("macd", "signal")),
        entry_short=Group("AND", [
            Cross(Ind("macd", "macd"), "below", Ind("macd", "signal")),
            Compare(Price("close"), "<", Ind("trend")),
        ]),
        exit_short=Cross(Ind("macd", "macd"), "above", Ind("macd", "signal")),
        risk=_risk(),
        exits=ExitSettings(
            stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=2.0,
            trailing_enabled=True, trailing_mode="atr", trailing_value=3.0,
            trailing_activate_at_r=1.0, atr_period=14),
        execution=ExecutionSettings(),
        session=SessionSettings(),
        costs=CostModel(),
    )


# --------------------------------------------------------------------------
# 5. Channel breakout -- the offset example
# --------------------------------------------------------------------------


def donchian_breakout() -> StrategySpec:
    """Turtle-style channel breakout with a shorter channel as the exit.

    The one strategy that *needs* operand offsets.  A Donchian channel includes
    the current bar, so the close can never be above ``upper`` on the bar that
    makes the high; the rule therefore compares against ``upper[1]``, the
    channel as it stood before this bar existed.  Getting this wrong is the
    classic silent look-ahead in a breakout backtest.
    """
    return StrategySpec(
        id="bi-donchian", name="Donchian Channel Breakout", author=_AUTHOR,
        tags=["built-in", "breakout"],
        description=(
            "Buys a close above the previous bar's highest high of the entry "
            "channel and shorts a close below its lowest low, exiting on the "
            "opposite edge of a shorter channel. The channel is read one bar back "
            "because the current bar's own high is part of it. Stop at 2 ATR."),
        params=[
            ParamSpec("entry_channel", "Entry Channel", "int", 20, 2, 500, 1,
                      help="Bars in the breakout channel."),
            ParamSpec("exit_channel", "Exit Channel", "int", 10, 2, 500, 1,
                      help="Bars in the shorter channel used to exit."),
        ],
        indicators=[
            IndicatorSlot("entryChan", "DONCHIAN", {"period": "$entry_channel"},
                          "close", label="Entry Channel"),
            IndicatorSlot("exitChan", "DONCHIAN", {"period": "$exit_channel"},
                          "close", label="Exit Channel"),
        ],
        entry_long=Cross(Price("close"), "above", Ind("entryChan", "upper", 1)),
        exit_long=Cross(Price("close"), "below", Ind("exitChan", "lower", 1)),
        entry_short=Cross(Price("close"), "below", Ind("entryChan", "lower", 1)),
        exit_short=Cross(Price("close"), "above", Ind("exitChan", "upper", 1)),
        risk=_risk(),
        exits=ExitSettings(
            stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=2.0,
            atr_period=14),
        execution=ExecutionSettings(),
        session=SessionSettings(),
        costs=CostModel(),
    )


# --------------------------------------------------------------------------
# 6. Session-aware intraday
# --------------------------------------------------------------------------


def opening_range_momentum() -> StrategySpec:
    """Break of the recent range, taken only in the late morning in New York.

    The session example.  Two filters are at work and they are deliberately
    different things: the strategy's own ``session`` block says when a position
    may be open at all (and flattens at the close), while the ``SessionWindow``
    condition inside the entry rule narrows *entries* to the part of the day the
    idea is about.

    ``rangeHigh``/``rangeLow`` are a rolling proxy for the opening range rather
    than the literal first N bars of the day: the highest high of the previous
    ``range_bars`` bars, read one bar back so the breakout bar is not part of
    the range it is breaking. On a 5-minute chart with the default of six bars
    that is a half-hour range, which is the usual reading of the idea.
    """
    return StrategySpec(
        id="bi-openrange", name="Opening Range Momentum", author=_AUTHOR,
        tags=["built-in", "intraday", "session"],
        description=(
            "Intraday only. Buys a close above the high of the last few bars and "
            "shorts a close below their low, but only between 09:45 and 11:30 New "
            "York time, and flattens at the session close. Stop 1.5 ATR, target "
            "2.5 ATR, and a time stop after 24 bars. Meant for intraday data: on "
            "daily bars the session filter will exclude everything."),
        params=[
            ParamSpec("range_bars", "Range Bars", "int", 6, 1, 200, 1,
                      help="How many bars form the range that has to be broken."),
        ],
        indicators=[
            IndicatorSlot("rangeHigh", "HIGHEST", {"period": "$range_bars"}, "high",
                          label="Range High"),
            IndicatorSlot("rangeLow", "LOWEST", {"period": "$range_bars"}, "low",
                          label="Range Low"),
        ],
        entry_long=Group("AND", [
            Cross(Price("close"), "above", Ind("rangeHigh", "value", 1)),
            SessionWindow("09:45", "11:30", "America/New_York", (0, 1, 2, 3, 4)),
        ]),
        exit_long=Cross(Price("close"), "below", Ind("rangeLow", "value", 1)),
        entry_short=Group("AND", [
            Cross(Price("close"), "below", Ind("rangeLow", "value", 1)),
            SessionWindow("09:45", "11:30", "America/New_York", (0, 1, 2, 3, 4)),
        ]),
        exit_short=Cross(Price("close"), "above", Ind("rangeHigh", "value", 1)),
        risk=_risk(),
        exits=ExitSettings(
            stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=1.5,
            take_profit_enabled=True, take_profit_mode="atr", take_profit_value=2.5,
            atr_period=14, max_bars_in_trade=24),
        execution=ExecutionSettings(),
        session=SessionSettings(enabled=True, start="09:30", end="16:00",
                                timezone="America/New_York",
                                weekdays=(0, 1, 2, 3, 4),
                                flat_at_session_end=True),
        costs=CostModel(),
    )


# --------------------------------------------------------------------------
# 7. Regime-filtered trend following
# --------------------------------------------------------------------------


def supertrend_follower() -> StrategySpec:
    """Follow SuperTrend flips, but only when ADX says there is a trend.

    ``direction`` is +1 or -1, so "the trend flipped up" is written as the
    direction crossing above zero -- a crossing on a two-valued series, which is
    exactly a state change and never fires twice for the same flip.
    """
    return StrategySpec(
        id="bi-supertrnd", name="SuperTrend Follower", author=_AUTHOR,
        tags=["built-in", "trend"],
        description=(
            "Goes long when SuperTrend flips up and short when it flips down, but "
            "only while ADX is above its threshold, so the strategy sits out the "
            "sideways stretches where a band-flip system whipsaws. The opposite "
            "flip is the exit; a 3 ATR stop is the backstop and the stop moves to "
            "break-even at 1 R."),
        params=[
            ParamSpec("st_period", "SuperTrend ATR", "int", 10, 2, 200, 1,
                      help="ATR period inside SuperTrend."),
            ParamSpec("st_mult", "SuperTrend Multiplier", "float", 3.0, 0.5, 10.0, 0.1,
                      help="How many ATRs wide the band sits."),
            ParamSpec("adx_period", "ADX Period", "int", 14, 2, 200, 1,
                      help="Look-back of the ADX trend-strength filter."),
            ParamSpec("adx_min", "Minimum ADX", "float", 20.0, 0.0, 60.0, 1.0,
                      help="ADX must be above this for an entry. Around 25 is the "
                           "conventional 'trending' reading."),
        ],
        indicators=[
            IndicatorSlot("st", "SUPERTREND",
                          {"period": "$st_period", "multiplier": "$st_mult"},
                          "close", label="SuperTrend"),
            IndicatorSlot("adx", "ADX",
                          {"period": "$adx_period", "adx_period": "$adx_period"},
                          "close", label="ADX"),
        ],
        entry_long=Group("AND", [
            Cross(Ind("st", "direction"), "above", Const(0.0)),
            Compare(Ind("adx", "adx"), ">", Param("adx_min")),
        ]),
        exit_long=Cross(Ind("st", "direction"), "below", Const(0.0)),
        entry_short=Group("AND", [
            Cross(Ind("st", "direction"), "below", Const(0.0)),
            Compare(Ind("adx", "adx"), ">", Param("adx_min")),
        ]),
        exit_short=Cross(Ind("st", "direction"), "above", Const(0.0)),
        risk=_risk(),
        exits=ExitSettings(
            stop_loss_enabled=True, stop_loss_mode="atr", stop_loss_value=3.0,
            breakeven_at_r=1.0, atr_period=14),
        execution=ExecutionSettings(),
        session=SessionSettings(),
        costs=CostModel(),
    )


#: Display name -> factory.  Ordered: the specification's worked example first,
#: because the application loads the first entry when nothing else is chosen.
BUILTIN_STRATEGIES: dict[str, Callable[[], StrategySpec]] = {
    "EMA Cross + RSI": ema_cross_rsi,
    "RSI Mean Reversion": rsi_mean_reversion,
    "Bollinger Breakout": bollinger_breakout,
    "MACD Trend": macd_trend,
    "Donchian Channel Breakout": donchian_breakout,
    "Opening Range Momentum": opening_range_momentum,
    "SuperTrend Follower": supertrend_follower,
}


def builtin_specs() -> list[StrategySpec]:
    """A fresh :class:`StrategySpec` for every built-in, in display order."""
    return [factory() for factory in BUILTIN_STRATEGIES.values()]


def get_builtin(name: str) -> StrategySpec:
    """One built-in strategy by display name.

    Raises :class:`~tradingbacktester.core.errors.StrategyError` rather than
    ``KeyError`` so a mistyped name reaches the user as a readable message.
    """
    from ..core.errors import StrategyError

    factory = BUILTIN_STRATEGIES.get(name)
    if factory is None:
        raise StrategyError(
            f"There is no built-in strategy called '{name}'. The built-in "
            f"strategies are: {', '.join(BUILTIN_STRATEGIES)}.")
    return factory()
