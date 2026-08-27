"""Market-neutral scoring, and the sub-period concentration gate.

Two statistics that ask the same awkward question from different directions:
*is this an edge, or is it exposure?*

**Market-neutral scoring.** A Sharpe ratio computed on raw account currency
cannot tell an edge from leverage. A rule that is long the index during a rising
hour earns money whether or not its entry condition means anything, and the
Sharpe rewards it either way. So every Sharpe here is reported beside the
regression of the strategy's per-session P&L on the market's own move across
**the strategy's own entry window** — not the whole session, because a rule that
only trades 09:30 to 11:00 is exposed to that hour and a half and to nothing
else.

The finding this exists for, from `docs/ib/STUDY_TURTLE_SCALP.md`: a scalp
reading a holdout Sharpe of 0.222 and a profit factor of 1.04 turned out to be
**87% beta**. Stripped of it the Sharpe was 0.032, and $16,789 of profit was
$2,147 of alpha. A matched random-entry control does not catch this, because a
random entry has a different holding profile from a breakout's — the control
read +$28 a trade where the regression said +$2.39.

**Concentration.** Split the block into five equal parts by session and ask what
share of the profit the best part carried. A strategy whose profit arrived in
one twenty-month window and nowhere else does not have an edge, it had a good
year. The lesson worth keeping is about *which block to ask on*: this gate
caught nothing on the shipped scalp because it was specified out-of-sample only,
while on the research block 20% of the sessions carried 76% of the profit and
the rest had a residual Sharpe of 0.008. **Run it on the block you are selecting
on.** A spike in time disqualifies a candidate exactly as a spike in parameter
space does.

What neither of these is: a thing to maximise. Ranking a 901,120-cell sweep on
residual Sharpe found beta 0.166 rather than 0.490, but among the survivors the
correlation between selection-block and validation-block residual Sharpe was
-0.057. Report them, rank on them if you like, and do not optimise hard against
them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from ..logging_setup import get_logger

log = get_logger(__name__)

#: Sub-periods the concentration gate splits a block into. Five is the
#: protocol's figure: enough that one good stretch stands out, few enough that
#: each part still holds a meaningful number of sessions.
CONCENTRATION_PARTS = 5

#: No single sub-period may carry more than this share of the block's P&L.
CONCENTRATION_LIMIT = 0.6

#: Above this share of the result explained by the market factor, the number is
#: worth a warning rather than a footnote.
BETA_SHARE_LIMIT = 0.5

#: Sessions per year when the span is too short to measure one.
DEFAULT_SESSIONS_PER_YEAR = 252.0

_NS_PER_YEAR = 365.25 * 24 * 3600 * 1e9


@dataclass(frozen=True)
class SessionMap:
    """Which session each bar belongs to, and what the market did in each.

    ``ordinal`` is -1 for a bar outside the tradeable window, so a market factor
    built from it measures the window and not the day around it.
    """

    ordinal: np.ndarray
    """Per-bar session index, or -1 outside the window."""
    count: int
    market: np.ndarray
    """P&L in account currency of holding one long unit across each session's
    window: the last in-window close against the first in-window open."""
    sessions_per_year: float

    def __len__(self) -> int:
        return int(self.count)


#: The session map is a pure function of the bars and the session window, and
#: costs a pandas timezone conversion of the whole series -- 106 ms on 194,000
#: bars, which is 15% of a backtest and would be paid again by every single
#: combination of an optimiser sweep, where the bars and the window never
#: change. A small bounded cache of the last few, keyed the same way
#: `finder.outcomes.wilder_atr` keys its own: the series object is held in the
#: value so an id reused after a garbage collection cannot return another
#: dataset's sessions.
_MAP_CACHE: "dict[tuple, tuple[Any, SessionMap]]" = {}
_MAP_CACHE_SIZE = 8


def _session_key(session: Any) -> tuple:
    """The fields of a session window that change the grouping."""
    if not getattr(session, "enabled", False):
        return (False,)
    return (True, str(getattr(session, "start", "")),
            str(getattr(session, "end", "")),
            str(getattr(session, "timezone", "")),
            tuple(getattr(session, "weekdays", ()) or ()))


def build_session_map(bars: Any, session: Any = None, *,
                      fallback_timezone: str = "",
                      point_value: float | None = None) -> SessionMap:
    """Group the bars into sessions and price one long unit across each window.

    The grouping follows the engine's own: the same :class:`_SessionArrays` the
    simulation uses, so a session here is the session a trade was filtered by.
    With no session filter every bar is in the window and a session is a local
    calendar day.

    Memoised -- see :data:`_MAP_CACHE`.
    """
    from ..core.types import SessionSettings

    settings_key = _session_key(session if session is not None
                                else SessionSettings())
    key = (id(bars), settings_key, fallback_timezone, point_value)
    cached = _MAP_CACHE.get(key)
    if cached is not None and cached[0] is bars:
        return cached[1]
    built = _build_session_map(bars, session, fallback_timezone, point_value)
    if len(_MAP_CACHE) >= _MAP_CACHE_SIZE:
        _MAP_CACHE.pop(next(iter(_MAP_CACHE)), None)
    _MAP_CACHE[key] = (bars, built)
    return built


def _build_session_map(bars: Any, session: Any, fallback_timezone: str,
                       point_value: float | None) -> SessionMap:
    from ..core.types import SessionSettings
    from ..engine.backtester import _SessionArrays

    n = len(bars)
    settings = session if session is not None else SessionSettings()
    timezone = (fallback_timezone
                or getattr(bars.instrument, "timezone", "") or "UTC")
    arrays = _SessionArrays.build(np.asarray(bars.ts, dtype="int64"),
                                  settings, timezone)
    in_session = np.asarray(arrays.in_session, dtype=bool)
    day_key = np.asarray(arrays.day_key, dtype="int64")
    session_last = np.asarray(arrays.session_last, dtype=bool)

    ordinal = np.full(n, -1, dtype="int64")
    if getattr(settings, "enabled", False):
        # Count session boundaries rather than calendar days: an overnight
        # window (18:00 to 17:00) spans two dates and is one session, and
        # `session_last` is where the engine itself puts the boundary.
        boundary = np.zeros(n, dtype="int64")
        boundary[1:] = np.cumsum(session_last[:-1])
        ordinal = np.where(in_session, boundary, -1)
        if in_session.any():
            # Renumber densely: a day with no in-window bars must not consume
            # an ordinal, or the market factor gains an all-zero session.
            used = np.unique(ordinal[in_session])
            remap = {int(old): index for index, old in enumerate(used)}
            ordinal = np.array([remap.get(int(v), -1) for v in ordinal],
                               dtype="int64")
    else:
        used = np.unique(day_key)
        remap = {int(k): index for index, k in enumerate(used)}
        ordinal = np.array([remap[int(k)] for k in day_key], dtype="int64")

    count = int(ordinal.max()) + 1 if n and ordinal.max() >= 0 else 0
    pv = (float(point_value) if point_value is not None
          else float(getattr(bars.instrument, "point_value", 1.0) or 1.0))
    market = _market_factor(bars, ordinal, count, pv)
    return SessionMap(ordinal=ordinal, count=count, market=market,
                      sessions_per_year=_sessions_per_year(bars, count))


def _market_factor(bars: Any, ordinal: np.ndarray, count: int,
                   point_value: float) -> np.ndarray:
    """One long unit held from the window's first open to its last close."""
    market = np.zeros(max(count, 0), dtype="float64")
    if count <= 0:
        return market
    inside = ordinal >= 0
    if not inside.any():
        return market
    index = ordinal[inside]
    opens = np.asarray(bars.open, dtype="float64")[inside]
    closes = np.asarray(bars.close, dtype="float64")[inside]
    # The bars are in order, so the first and last writes per session win.
    first_open = np.zeros(count, dtype="float64")
    last_close = np.zeros(count, dtype="float64")
    seen = np.zeros(count, dtype=bool)
    np.maximum.at(seen, index, True)
    # `index` is non-decreasing; a reverse pass leaves the first open in place
    # and a forward pass leaves the last close.
    first_open[index[::-1]] = opens[::-1]
    last_close[index] = closes
    market[seen] = (last_close[seen] - first_open[seen]) * point_value
    return market


def _sessions_per_year(bars: Any, count: int) -> float:
    """Sessions a year, measured from the data rather than assumed."""
    ts = np.asarray(getattr(bars, "ts", ()), dtype="int64")
    if count <= 1 or ts.size < 2:
        return DEFAULT_SESSIONS_PER_YEAR
    years = float(ts[-1] - ts[0]) / _NS_PER_YEAR
    if years <= 0:
        return DEFAULT_SESSIONS_PER_YEAR
    rate = count / years
    # A rate outside this range means the span or the grouping is degenerate;
    # the calendar figure is a better guess than a number built on one week.
    return rate if 1.0 <= rate <= 400.0 else DEFAULT_SESSIONS_PER_YEAR


def session_pnl(trades: Sequence[Any], session_map: SessionMap) -> np.ndarray:
    """Per-session strategy P&L, **including the sessions it did not trade**.

    Dropping flat sessions is the most common way an intraday Sharpe gets
    inflated two or three times, so the denominator here is every session in the
    block. A trade is attributed to the session it was *opened* in, which is the
    session whose market move it was exposed to.
    """
    series = np.zeros(max(session_map.count, 0), dtype="float64")
    if session_map.count <= 0:
        return series
    ordinal = session_map.ordinal
    for trade in trades or ():
        bar = int(getattr(trade, "entry_bar", -1))
        if not (0 <= bar < ordinal.size):
            continue
        index = int(ordinal[bar])
        if index < 0:
            # Opened outside the tradeable window -- possible when the session
            # filter was changed after the run. Attribute it to the nearest
            # session at or before it rather than discarding the P&L.
            earlier = ordinal[:bar + 1]
            earlier = earlier[earlier >= 0]
            if earlier.size == 0:
                continue
            index = int(earlier[-1])
        series[index] += float(getattr(trade, "net_pnl", 0.0) or 0.0)
    return series


# --------------------------------------------------------------------------
# the regression
# --------------------------------------------------------------------------

@dataclass
class NeutralStats:
    """A strategy's per-session P&L, regressed on the market's own move."""

    sessions: int
    sharpe: float
    beta: float
    alpha: float
    """Mean per-session P&L left after the market's contribution is removed."""
    correlation: float
    residual_sharpe: float
    beta_pnl_share: float
    """Fraction of the net result the market factor explains, or NaN when the
    net is ~0 -- there is no share of nothing."""
    net: float
    market_net: float
    sessions_per_year: float

    @property
    def mostly_beta(self) -> bool:
        return (math.isfinite(self.beta_pnl_share)
                and abs(self.beta_pnl_share) > BETA_SHARE_LIMIT)

    def verdict(self) -> str:
        if self.sessions < 2:
            return "too few sessions to regress anything"
        if not math.isfinite(self.beta_pnl_share):
            return ("the net result is about zero, so there is no share of it "
                    "to attribute")
        share = self.beta_pnl_share * 100.0
        if self.mostly_beta:
            return (f"{share:.0f}% of the result is the market's own move "
                    f"across this window — stripped of it the Sharpe is "
                    f"{self.residual_sharpe:.3f} against {self.sharpe:.3f}")
        if abs(self.beta) < 0.05:
            return ("essentially uncorrelated with the market across this "
                    "window, so the Sharpe is measuring the rule")
        return (f"{share:.0f}% of the result is the market's move; the "
                f"residual Sharpe is {self.residual_sharpe:.3f} against "
                f"{self.sharpe:.3f}")

    def to_dict(self) -> dict[str, Any]:
        return {"sessions": self.sessions, "sharpe": self.sharpe,
                "beta": self.beta, "alpha": self.alpha,
                "correlation": self.correlation,
                "residual_sharpe": self.residual_sharpe,
                "beta_pnl_share": self.beta_pnl_share,
                "net": self.net, "market_net": self.market_net,
                "sessions_per_year": self.sessions_per_year,
                "mostly_beta": self.mostly_beta, "verdict": self.verdict()}


def market_neutral(strategy: Sequence[float], market: Sequence[float],
                   sessions_per_year: float = DEFAULT_SESSIONS_PER_YEAR
                   ) -> NeutralStats:
    """Regress ``strategy`` on ``market``, session by session.

    Both series must cover **every** session in the block in order, zeros
    included. Everything below is a function of five running sums, so it is one
    pass over the sessions and can sit inside a sweep.
    """
    x = np.asarray(strategy, dtype="float64")
    y = np.asarray(market, dtype="float64")
    if x.size != y.size:
        raise ValueError(
            f"The strategy series has {x.size} sessions and the market series "
            f"{y.size}; they must describe the same block.")
    n = int(x.size)
    ppy = float(sessions_per_year) if sessions_per_year > 0 else DEFAULT_SESSIONS_PER_YEAR
    if n == 0:
        return NeutralStats(0, 0.0, 0.0, 0.0, 0.0, 0.0, float("nan"),
                            0.0, 0.0, ppy)

    mean_x, mean_y = float(x.mean()), float(y.mean())
    var_x = max(float((x * x).mean()) - mean_x * mean_x, 0.0)
    var_y = max(float((y * y).mean()) - mean_y * mean_y, 0.0)
    cov = float((x * y).mean()) - mean_x * mean_y

    beta = cov / var_y if var_y > 0 else 0.0
    alpha = mean_x - beta * mean_y
    residual_var = max(var_x - (cov * cov / var_y if var_y > 0 else 0.0), 0.0)
    sd_x = math.sqrt(var_x)
    root = math.sqrt(ppy)

    net = float(x.sum())
    return NeutralStats(
        sessions=n,
        sharpe=(mean_x / sd_x * root) if sd_x > 0 else 0.0,
        beta=beta,
        alpha=alpha,
        correlation=(cov / (sd_x * math.sqrt(var_y))
                     if sd_x > 0 and var_y > 0 else 0.0),
        residual_sharpe=(alpha / math.sqrt(residual_var) * root
                         if residual_var > 0 else 0.0),
        beta_pnl_share=(beta * float(y.sum()) / net
                        if abs(net) > 1e-9 else float("nan")),
        net=net, market_net=float(y.sum()), sessions_per_year=ppy)


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------

@dataclass
class Concentration:
    """How much of a block's profit came from one stretch of it."""

    share: float
    """Best sub-period's P&L over the block's total, or NaN when the total is ~0."""
    parts: list[float] = field(default_factory=list)
    best_part: int = 0
    limit: float = CONCENTRATION_LIMIT

    total: float = 0.0

    @property
    def applicable(self) -> bool:
        """The gate asks how spread out the PROFIT is.

        On a block that lost money the ratio still computes but stops meaning
        that: dividing by a negative total flips the sign, and a part that lost
        more than the block did reads as a share above one. A losing block is
        rejected on its result, not on this.
        """
        return math.isfinite(self.share) and self.total > 1e-9

    @property
    def passed(self) -> bool:
        return self.applicable and self.share <= self.limit

    def verdict(self) -> str:
        n = len(self.parts) or CONCENTRATION_PARTS
        if not math.isfinite(self.share):
            return ("the block's net is about zero, so no sub-period carried "
                    "it — there is nothing here to be spread out")
        if not self.applicable:
            return ("the block lost money, so how concentrated its profit was "
                    "is not the question to ask of it")
        if self.passed:
            return (f"the profit is spread across the block: the best of "
                    f"{n} sub-periods carried {self.share * 100:.0f}% of it, "
                    f"against the {100 / n:.0f}% an even spread would give")
        return (f"sub-period {self.best_part + 1} of {n} carried "
                f"{self.share * 100:.0f}% of the block's profit — above the "
                f"{self.limit * 100:.0f}% limit, this is one good stretch "
                f"rather than an edge")

    def to_dict(self) -> dict[str, Any]:
        return {"share": self.share, "parts": list(self.parts),
                "best_part": self.best_part, "limit": self.limit,
                "total": self.total, "applicable": self.applicable,
                "passed": self.passed, "verdict": self.verdict()}


def concentration(strategy: Sequence[float],
                  parts: int = CONCENTRATION_PARTS,
                  limit: float = CONCENTRATION_LIMIT) -> Concentration:
    """Split the sessions into equal parts and find the share the best carried.

    Run this on the block you are **selecting** on. Pointed out-of-sample it
    catches nothing: the candidate has already been chosen by then.
    """
    x = np.asarray(strategy, dtype="float64")
    parts = max(2, int(parts))
    if x.size == 0:
        return Concentration(share=float("nan"), parts=[0.0] * parts,
                             limit=limit, total=0.0)
    # np.array_split handles a session count that does not divide evenly, and
    # puts the remainder in the earlier parts rather than dropping it.
    chunks = np.array_split(x, parts)
    sums = [float(chunk.sum()) for chunk in chunks]
    total = float(x.sum())
    if abs(total) <= 1e-9:
        return Concentration(share=float("nan"), parts=sums, limit=limit,
                             total=total)
    shares = [value / total for value in sums]
    best = int(np.argmax(shares))
    return Concentration(share=float(shares[best]), parts=sums,
                         best_part=best, limit=limit, total=total)


# --------------------------------------------------------------------------
# the whole thing, from a finished run
# --------------------------------------------------------------------------

@dataclass
class NeutralReport:
    neutral: NeutralStats
    concentration: Concentration
    sessions: int
    traded_sessions: int

    def to_dict(self) -> dict[str, Any]:
        return {"neutral": self.neutral.to_dict(),
                "concentration": self.concentration.to_dict(),
                "sessions": self.sessions,
                "traded_sessions": self.traded_sessions}


def analyse(result: Any) -> NeutralReport | None:
    """Both statistics from a finished :class:`BacktestResult`.

    Returns ``None`` rather than raising when the run cannot support them --
    no bars, no trades, or a single session. A missing panel is better than a
    report that will not open.
    """
    bars = getattr(result, "bars", None)
    trades = list(getattr(result, "trades", ()) or ())
    if bars is None or len(bars) == 0 or not trades:
        return None
    try:
        config = getattr(result, "config", None)
        session_map = build_session_map(
            bars, getattr(config, "session", None),
            fallback_timezone=getattr(bars.instrument, "timezone", "") or "UTC")
        if session_map.count < 2:
            return None
        series = session_pnl(trades, session_map)
        return NeutralReport(
            neutral=market_neutral(series, session_map.market,
                                   session_map.sessions_per_year),
            concentration=concentration(series),
            sessions=session_map.count,
            traded_sessions=int(np.count_nonzero(series)))
    except Exception:                       # noqa: BLE001 - see the docstring
        log.debug("Market-neutral analysis unavailable", exc_info=True)
        return None
