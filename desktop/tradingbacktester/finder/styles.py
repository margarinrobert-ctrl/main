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

from dataclasses import dataclass, field, replace
from typing import Any


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


#: What :func:`customise` will let a caller change, and nothing else.  A style
#: is a constraint, and the fields not listed here are the ones that stop a
#: search from becoming a different question: the templates it may use, its own
#: identity, and the note explaining what it is for.
ADJUSTABLE = ("timeframes", "stop_atr", "target_r", "max_bars", "session",
              "flat_at_session_end", "weekdays", "min_trades", "atr_period")


def customise(base: TradingStyle | str, **overrides: Any) -> TradingStyle:
    """A copy of ``base`` with some of its constraints changed.

    The point of a style is that the geometry is fixed before the search runs,
    so the optimiser cannot pick it -- but "day trading" means different hours
    on different instruments, and a user with a reason to trade 07:00-11:00 or
    to hold for a week should not have to edit the source to say so.

    What this will NOT do is let the constraint be *searched*. The overrides
    are applied once, up front, and the resulting style is reported with the
    result, so a reader can see what was fixed and what was found. Handing a
    list of sessions to a search and keeping the best would put the session
    inside the selection, which is how a calendar condition becomes a free
    lottery ticket.

    Raises
    ------
    StrategyError
        For an unknown field, one that is not adjustable, or a value that
        cannot make a usable style -- an empty geometry, a session that is not
        ``HH:MM``, a negative hold.
    """
    from ..core.errors import StrategyError

    found = base if isinstance(base, TradingStyle) else style(base)
    clean: dict[str, Any] = {}
    for name, value in overrides.items():
        # ``None`` means "leave it alone" for every field but one: for a
        # session it is the documented way to say ALL HOURS, and skipping it
        # made that the one constraint a user could not express.
        if value is None and name != "session":
            continue
        if name not in ADJUSTABLE:
            known = ", ".join(ADJUSTABLE)
            raise StrategyError(
                f"'{name}' is not something a search may be told to change. "
                f"Adjustable: {known}."
                if hasattr(found, name) else
                f"A trading style has no '{name}'. Adjustable: {known}.")
        clean[name] = value

    if "session" in clean and clean["session"] is not None:
        window = tuple(clean["session"])
        if len(window) != 2:
            raise StrategyError(
                "A session is a start and an end, for example "
                "('09:30', '16:00').")
        for part in window:
            _check_hhmm(str(part))
        clean["session"] = window

    for name in ("stop_atr", "target_r", "timeframes"):
        if name in clean:
            values = tuple(clean[name])
            if not values:
                raise StrategyError(
                    f"A search needs at least one {name.replace('_', ' ')} to "
                    f"try.")
            clean[name] = values

    for name in ("max_bars", "min_trades", "atr_period"):
        if name in clean and int(clean[name]) < 1:
            raise StrategyError(
                f"{name.replace('_', ' ')} must be at least 1.")

    if "weekdays" in clean:
        days = tuple(sorted({int(d) for d in clean["weekdays"]}))
        if not days or any(d < 0 or d > 6 for d in days):
            raise StrategyError(
                "Weekdays are numbers from 0 (Monday) to 6 (Sunday).")
        clean["weekdays"] = days

    return replace(found, **clean)


def _check_hhmm(text: str) -> None:
    from ..core.errors import StrategyError

    parts = str(text).split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        raise StrategyError(
            f"'{text}' is not a time of day. Write it as HH:MM.") from None
    if not (0 <= hour <= 24) or not (0 <= minute < 60):
        raise StrategyError(f"'{text}' is not a real time of day.")
