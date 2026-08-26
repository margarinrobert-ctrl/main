"""Trading styles: the geometry a search is allowed to look in.

A style is not a preference, it is a constraint. "Scalping" means small stops,
short holds and the busy part of the session; "position trading" means daily
bars and stops wide enough to sit through a week. Fixing that up front is what
keeps a search honest: without it the optimiser is free to wander into whatever
hold time happened to suit the sample, and hold time is the single easiest
thing to overfit.

Each style therefore pins the bar size, the stop and target geometry, the
maximum time in a trade and the session window. What the search is left to
find is the *entry rule* -- which is the only part a person actually means when
they say they want a strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TradingStyle:
    """One way of trading, expressed as the geometry a candidate must fit."""

    key: str
    label: str
    summary: str
    timeframes: tuple[str, ...]
    """Bar sizes this style makes sense on, best first."""
    stop_atr: tuple[float, ...]
    """Stop distances to try, in multiples of ATR."""
    target_r: tuple[float, ...]
    """Target distances to try, in multiples of the stop (R)."""
    max_bars: int
    """Hardest limit on time in a trade, in bars."""
    session: tuple[str, str] | None = None
    """``(start, end)`` in the instrument's timezone, or ``None`` for all hours."""
    flat_at_session_end: bool = False
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    min_trades: int = 100
    """Below this a result is noise, whatever it says. See METRICS.md."""
    atr_period: int = 14
    notes: str = ""

    def geometries(self) -> list[tuple[float, float]]:
        """Every ``(stop_atr, target_r)`` pair this style allows."""
        return [(s, t) for s in self.stop_atr for t in self.target_r]

    def describe(self) -> str:
        window = (f"{self.session[0]}-{self.session[1]}" if self.session
                  else "all hours")
        return (f"{', '.join(self.timeframes)} bars · {window} · stop "
                f"{min(self.stop_atr):g}-{max(self.stop_atr):g}x ATR · target "
                f"{min(self.target_r):g}-{max(self.target_r):g}R · at most "
                f"{self.max_bars} bars in a trade")


#: New York cash session, where an index actually trades.
_RTH = ("09:30", "16:00")

STYLES: tuple[TradingStyle, ...] = (
    TradingStyle(
        key="scalp",
        label="Scalping",
        summary="Minutes in the market, small stops, only the busiest hours.",
        timeframes=("1m", "5m"),
        stop_atr=(0.5, 0.75, 1.0),
        target_r=(1.0, 1.5, 2.0),
        max_bars=12,
        session=("09:30", "11:30"),
        flat_at_session_end=True,
        min_trades=200,
        notes="The first two hours of the New York session. Costs dominate at "
              "this size: a two-point spread against a ten-point target is a "
              "fifth of the trade, so a scalp has to be right far more often "
              "than a swing to break even.",
    ),
    TradingStyle(
        key="intraday",
        label="Day trading",
        summary="Hours in the market, flat by the close, no overnight risk.",
        timeframes=("5m", "15m", "30m"),
        stop_atr=(1.0, 1.5, 2.0),
        target_r=(1.0, 1.5, 2.0, 3.0),
        max_bars=48,
        session=_RTH,
        flat_at_session_end=True,
        min_trades=100,
        notes="Entries inside the New York cash session and everything closed "
              "at the bell, so no position is exposed to a gap.",
    ),
    TradingStyle(
        key="swing",
        label="Swing trading",
        summary="Days in the market, wide stops, gaps accepted.",
        timeframes=("1h", "4h"),
        stop_atr=(1.5, 2.0, 3.0),
        target_r=(1.5, 2.0, 3.0),
        max_bars=60,
        session=None,
        flat_at_session_end=False,
        min_trades=60,
        notes="Positions are held overnight, so an opening gap can jump the "
              "stop. The simulation fills those at the open, not at the stop "
              "price, which is what really happens.",
    ),
    TradingStyle(
        key="position",
        label="Position trading",
        summary="Weeks in the market on daily bars.",
        timeframes=("1D",),
        stop_atr=(2.0, 3.0, 4.0),
        target_r=(2.0, 3.0, 4.0),
        max_bars=40,
        session=None,
        flat_at_session_end=False,
        min_trades=40,
        notes="Forty daily bars is two months. On this timeframe a decade of "
              "history is only a few hundred trades, so the honest verdict is "
              "usually 'not enough evidence'.",
    ),
)

STYLES_BY_KEY: dict[str, TradingStyle] = {s.key: s for s in STYLES}


def style(key: str) -> TradingStyle:
    """Look a style up by key, or raise with the list of valid ones."""
    found = STYLES_BY_KEY.get(str(key).strip().lower())
    if found is None:
        from ..core.errors import StrategyError

        raise StrategyError(
            f"'{key}' is not a trading style. Choose one of: "
            f"{', '.join(s.key for s in STYLES)}.")
    return found
