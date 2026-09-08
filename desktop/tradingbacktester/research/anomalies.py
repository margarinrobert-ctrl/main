"""Finding the unusual, and then asking whether unusual pays.

Two different things get called an anomaly and they need separating, because
one is a problem with the file and the other is a property of the market.

**Data anomalies** are bad prints, frozen quotes, holiday gaps and impossible
bars. They make a backtest describe something that never happened, and they are
reported first so they can be dealt with before anything else is believed.

**Market anomalies** are real: a bar that moved four times its usual range, a
volume surge, an opening gap, a volatility collapse. These are interesting only
if something follows them, so each one is not merely counted -- it is traded.
Every detector's bars are run through the same simulation and the same matched
control the strategy search uses, and the answer is usually "nothing follows
it", which is worth knowing and is what the report says.

A detector is a boolean over bars, computed causally: whether bar *i* is
unusual is decided by bars up to *i*, never by what came after.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..core.errors import InsufficientDataError
from ..core.types import CostModel
from ..data.models import BarSeries
from ..finder.control import ControlResult, analytic_control, benjamini_hochberg, sampled_control
from ..finder.outcomes import (Geometry, OutcomeCache, build_outcomes,
                               select_sequential, session_entry_mask,
                               session_hold_limit, wilder_atr)
from ..finder.search import (MIN_BARS, check_split, choose_timeframe,
                             default_costs, prepare_bars, too_few_bars)
from ..finder.styles import TradingStyle
from .features import rolling_mean, rolling_rank

ProgressFn = Callable[[int, int, str], None]

#: A detector that fires on almost every bar is not detecting an anomaly, and
#: one that fires a handful of times cannot be judged.
_MAX_SHARE = 0.20
_MIN_EVENTS = 30


@dataclass(frozen=True)
class Detector:
    """One kind of unusual bar."""

    key: str
    label: str
    description: str
    detect: Callable[[BarSeries], np.ndarray]
    needs_session: bool = False
    """Called as ``detect(bars, session)`` rather than ``detect(bars)``.

    "The first hour of the day" means the first hour of the SESSION, not of the
    calendar day. Without the mask these detectors marked the first hour after
    local midnight -- which on a nearly-24-hour instrument is nowhere near the
    open, sits entirely outside an RTH style's window, and scored zero bars
    while looking like a detector that had simply found nothing.
    """
    family: str = "shape"
    """``shape`` for a property of the bar, ``calendar`` for a property of the
    clock.  Reported apart because they are answers to different questions and
    one of them is far easier to fool yourself with."""
    max_share: float = _MAX_SHARE
    """Above this the detector is describing the market, not an event in it.

    A calendar detector is allowed more: "Monday" is a fifth of the sample by
    construction and that is the whole point of asking about it, whereas a
    volatility spike on a fifth of all bars is not a spike.
    """


@dataclass
class AnomalyFinding:
    """One detector, and what trading it was worth."""

    detector: Detector
    count: int
    share: float
    side: int = 1
    trades: int = 0
    per_trade: float = 0.0
    excess: float = 0.0
    p_value: float = 1.0
    survives_fdr: bool = False
    control: ControlResult | None = None
    holdout_excess: float = 0.0
    holdout_trades: int = 0
    verdict: str = "not tested"
    detail: str = ""

    @property
    def key(self) -> str:
        return self.detector.key

    @property
    def label(self) -> str:
        return self.detector.label

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label,
            "description": self.detector.description,
            "count": self.count, "share": self.share,
            "side": "long" if self.side > 0 else "short",
            "trades": self.trades, "per_trade": self.per_trade,
            "excess_per_trade": self.excess, "p_value": self.p_value,
            "survives_fdr": self.survives_fdr,
            "holdout_excess_per_trade": self.holdout_excess,
            "holdout_trades": self.holdout_trades,
            "verdict": self.verdict,
        }


@dataclass
class AnomalyScan:
    """Everything one scan found."""

    symbol: str
    timeframe: str
    currency: str
    bars: int
    start: str
    end: str
    research_bars: int
    holdout_bars: int
    findings: list[AnomalyFinding] = field(default_factory=list)
    quality: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    elapsed: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol, "timeframe": self.timeframe,
            "bars": self.bars, "start": self.start, "end": self.end,
            "research_bars": self.research_bars,
            "holdout_bars": self.holdout_bars,
            "quality": list(self.quality),
            "findings": [f.to_dict() for f in self.findings],
            "notes": list(self.notes),
            "elapsed_seconds": round(self.elapsed, 2),
        }


# ---------------------------------------------------------------------------
# the detectors
# ---------------------------------------------------------------------------


def _previous(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, np.nan)
    out[1:] = values[:-1]
    return out


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    out = np.full(a.shape, np.nan)
    ok = np.isfinite(a) & np.isfinite(b) & (np.abs(b) > 1e-12)
    out[ok] = a[ok] / b[ok]
    return out


def _volatility_spike(bars: BarSeries) -> np.ndarray:
    return _ratio(wilder_atr(bars, 5), wilder_atr(bars, 50)) > 2.0


def _volatility_collapse(bars: BarSeries) -> np.ndarray:
    return _ratio(wilder_atr(bars, 5), wilder_atr(bars, 50)) < 0.5


def _range_shock(bars: BarSeries) -> np.ndarray:
    return _ratio(bars.high - bars.low, wilder_atr(bars, 14)) > 3.0


def _gap_up(bars: BarSeries) -> np.ndarray:
    return _ratio(bars.open - _previous(bars.close), wilder_atr(bars, 14)) > 1.0


def _gap_down(bars: BarSeries) -> np.ndarray:
    return _ratio(bars.open - _previous(bars.close), wilder_atr(bars, 14)) < -1.0


def _volume_surge(bars: BarSeries) -> np.ndarray:
    return _ratio(bars.volume, rolling_mean(bars.volume, 50)) > 4.0


def _volume_drought(bars: BarSeries) -> np.ndarray:
    average = rolling_mean(bars.volume, 50)
    return (_ratio(bars.volume, average) < 0.25) & (average > 0)


def _shock_up(bars: BarSeries) -> np.ndarray:
    return _ratio(bars.close - _previous(bars.close),
                  wilder_atr(bars, 14)) > 3.0


def _shock_down(bars: BarSeries) -> np.ndarray:
    return _ratio(bars.close - _previous(bars.close),
                  wilder_atr(bars, 14)) < -3.0


def _outside_bar(bars: BarSeries) -> np.ndarray:
    wide = _ratio(bars.high - bars.low, wilder_atr(bars, 14)) > 1.5
    return wide & (bars.high > _previous(bars.high)) \
        & (bars.low < _previous(bars.low))


def _inside_squeeze(bars: BarSeries) -> np.ndarray:
    inside = (bars.high <= _previous(bars.high)) & (bars.low >= _previous(bars.low))
    return inside & (rolling_rank(wilder_atr(bars, 14), 100) < 0.2)


def _stale_price(bars: BarSeries, run: int = 4) -> np.ndarray:
    same = np.zeros(bars.close.size, dtype=bool)
    same[1:] = bars.close[1:] == bars.close[:-1]
    out = np.zeros(same.size, dtype=bool)
    streak = 0
    for i, flag in enumerate(same):
        streak = streak + 1 if flag else 0
        out[i] = streak >= run - 1
    return out


def _new_extreme_high(bars: BarSeries) -> np.ndarray:
    return rolling_rank(bars.close, 200) >= 0.999


def _new_extreme_low(bars: BarSeries) -> np.ndarray:
    return rolling_rank(bars.close, 200) <= 0.001


def _thrust(bars: BarSeries) -> np.ndarray:
    body = (bars.close - bars.open)
    atr = wilder_atr(bars, 14)
    strong = _ratio(np.abs(body), atr) > 0.8
    direction = np.sign(body)
    out = np.zeros(body.size, dtype=bool)
    out[2:] = (strong[2:] & strong[1:-1] & strong[:-2]
               & (direction[2:] == direction[1:-1])
               & (direction[1:-1] == direction[:-2]))
    return out


# ---------------------------------------------------------------------------
# Calendar and session effects
#
# These are the anomalies the literature is actually about -- Monday, the turn
# of the month, January, the first and last hour -- and they need a paragraph
# of their own, because everywhere else in this project a calendar condition is
# banned outright.
#
# The ban is on letting a SEARCH pick one. Weekday and month conditions
# partition a sample five or twelve ways, and an optimiser allowed to choose
# among them is being handed a free lottery ticket: one of the five will look
# wonderful on any series, edge or no edge.
#
# Naming them in advance is the opposite activity. This list is fixed in the
# source, every entry is tested whether it looks promising or not, both sides
# are scored, all of the p-values go into one Benjamini-Hochberg correction
# together with every shape detector, and the locked block is the gate. Nothing
# is chosen; a stated list is checked. Adding a calendar family therefore makes
# every OTHER finding harder to pass, which is the correct direction and is
# reported with the result.
#
# What is deliberately absent: post-earnings drift, index-inclusion effects and
# anything else needing fundamentals or a second instrument. This application
# has one OHLCV series, and a detector that pretends otherwise would be
# measuring nothing.
# ---------------------------------------------------------------------------


def _local(bars: BarSeries):
    """Bar timestamps in the instrument's own timezone, as a pandas index.

    In the instrument's zone rather than UTC because "Monday" and "the first
    hour" are facts about the exchange's clock, and a New York session that
    starts at 13:30 UTC in summer starts at 14:30 in winter.
    """
    import pandas as pd

    index = pd.DatetimeIndex(pd.to_datetime(bars.ts, utc=True))
    zone = getattr(bars.instrument, "timezone", "") or "UTC"
    try:
        return index.tz_convert(zone)
    except Exception:                   # noqa: BLE001 - a bad zone is a label
        return index                    # problem, not a reason to fail the scan


def _weekday(day: int) -> Callable[[BarSeries], np.ndarray]:
    def detect(bars: BarSeries) -> np.ndarray:
        return np.asarray(_local(bars).dayofweek == day, dtype=bool)
    return detect


def _month(month: int) -> Callable[[BarSeries], np.ndarray]:
    def detect(bars: BarSeries) -> np.ndarray:
        return np.asarray(_local(bars).month == month, dtype=bool)
    return detect


def _turn_of_month(bars: BarSeries) -> np.ndarray:
    """The first three trading days of a month, and its last weekday.

    Both halves have to be knowable at the time, and the obvious way to write
    this is not. Taking the month's last trading day as "the last date this
    file has for that month" reads the whole month before deciding about its
    first bar -- so truncating the series changes the answer, and on the final
    month in a file it marks whatever day the data happens to stop on. The
    causality test caught exactly that.

    So: the first three trading days are COUNTED as they arrive, and the last
    day is the last **weekday** of the calendar month, which is knowable years
    ahead. A holiday on that Friday makes the real last session the Thursday
    and this fires a day late; that is a known and stated inaccuracy rather
    than a peek at the future.
    """
    import pandas as pd

    n = len(bars)
    out = np.zeros(n, dtype=bool)
    if not n:
        return out
    local = _local(bars)
    dates = local.normalize()
    month_key = (np.asarray(local.year, dtype="int64") * 100
                 + np.asarray(local.month, dtype="int64"))
    date_key = month_key * 100 + np.asarray(local.day, dtype="int64")

    new_date = np.empty(n, dtype=bool)
    new_date[0] = True
    new_date[1:] = date_key[1:] != date_key[:-1]
    new_month = np.empty(n, dtype=bool)
    new_month[0] = True
    new_month[1:] = month_key[1:] != month_key[:-1]

    # How many distinct dates of THIS month have been seen at or before each
    # bar -- a running count, so it never reads forward.
    seq = np.cumsum(new_date)
    before = np.maximum.accumulate(np.where(new_month, seq - 1, 0))
    ordinal = seq - before

    # The last weekday of the calendar month: step back from month end over a
    # Saturday (dayofweek 5) or Sunday (6).
    month_end = dates + pd.offsets.MonthEnd(0)
    back = np.maximum(0, np.asarray(month_end.dayofweek, dtype="int64") - 4)
    last_weekday = month_end - pd.to_timedelta(back, unit="D")

    out = (ordinal <= 3) | (dates.to_numpy() == last_weekday.to_numpy())
    return np.asarray(out, dtype=bool)


def _session_days(bars: BarSeries, session: np.ndarray):
    """``(minutes, [indices of each day's tradeable bars])`` in local time.

    Only the bars the style may actually trade, grouped by local date. Grouping
    every bar instead makes "the first hour of the day" the hour after local
    midnight, which for an instrument trading nearly around the clock is not
    the open and is not in anybody's session.
    """
    local = _local(bars)
    minutes = (np.asarray(local.hour, dtype="int64") * 60
               + np.asarray(local.minute, dtype="int64"))
    day_key = (np.asarray(local.year, dtype="int64") * 10000
               + np.asarray(local.month, dtype="int64") * 100
               + np.asarray(local.day, dtype="int64"))
    eligible = np.flatnonzero(np.asarray(session, dtype=bool))
    days: list[np.ndarray] = []
    if eligible.size:
        keys = day_key[eligible]
        change = np.empty(eligible.size, dtype=bool)
        change[0] = True
        change[1:] = keys[1:] != keys[:-1]
        starts = np.flatnonzero(change)
        for lo, hi in zip(starts, np.append(starts[1:], eligible.size)):
            days.append(eligible[lo:hi])
    return minutes, days


def _first_hour(bars: BarSeries, session: np.ndarray) -> np.ndarray:
    """Bars in the first hour after the session's own first bar of the day."""
    minutes, days = _session_days(bars, session)
    out = np.zeros(len(bars), dtype=bool)
    for index in days:
        out[index] = minutes[index] < minutes[index[0]] + 60
    return out


def _last_hour(bars: BarSeries, session: np.ndarray) -> np.ndarray:
    """The hour before the close, using the PREVIOUS day's close to say when.

    Taking today's own last bar is the obvious way to write this and it is
    look-ahead: at 14:00 you do not know that 16:00 will be the final bar, and
    on the last day in the file you never find out. Truncating the series then
    changes the answer for bars that were already decided -- which is exactly
    what the causality test measures, and how this one was caught.

    Yesterday's close is known today, which is also what a trader actually
    knows. On a half-day the reference is an hour or two late and this fires on
    nothing; that is the conservative direction and is better than a detector
    that cannot be traded.
    """
    minutes, days = _session_days(bars, session)
    out = np.zeros(len(bars), dtype=bool)
    previous_close: int | None = None
    for index in days:
        if previous_close is not None:
            out[index] = minutes[index] > previous_close - 60
        previous_close = int(minutes[index[-1]])
    return out


def _after_long_break(bars: BarSeries, session: np.ndarray) -> np.ndarray:
    """The first tradeable bar after a gap far longer than the usual one.

    A holiday, a weekend, or a data outage -- the detector cannot tell which,
    and says so. Measured against the median spacing of the bars this style can
    actually trade, rather than of every bar in the file: on a session-limited
    style the overnight gap is the usual case, and against the 24-hour spacing
    every single session open would look like a holiday.
    """
    out = np.zeros(len(bars), dtype=bool)
    eligible = np.flatnonzero(np.asarray(session, dtype=bool))
    if eligible.size < 3:
        return out
    ts = np.asarray(bars.ts, dtype="int64")[eligible]
    steps = np.diff(ts)
    usual = float(np.median(steps))
    if usual <= 0:
        return out
    out[eligible[1:]] = steps > usual * 4.0
    return out


def _round_number(bars: BarSeries) -> np.ndarray:
    """Close within a tenth of an ATR of a round level.

    The level is the round number appropriate to the price -- 100s for an
    index in the tens of thousands, 0.01 for a currency pair -- taken from the
    price's own magnitude rather than hard-coded, so it is not an assumption
    about which instrument this is.
    """
    close = np.asarray(bars.close, dtype="float64")
    atr = wilder_atr(bars, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        magnitude = np.power(10.0, np.floor(np.log10(np.abs(close))) - 2.0)
    step = np.where(np.isfinite(magnitude) & (magnitude > 0), magnitude * 10.0,
                    np.nan)
    distance = np.abs(close - np.round(close / step) * step)
    return np.asarray(np.isfinite(distance) & np.isfinite(atr) & (atr > 0)
                      & (distance < atr * 0.1), dtype=bool)


CALENDAR_DETECTORS: tuple[Detector, ...] = (
    Detector("monday", "Monday",
             "The weekend effect: the best-known calendar anomaly there is, "
             "and the one most often found to have decayed.",
             _weekday(0), family="calendar", max_share=0.30),
    Detector("friday", "Friday",
             "The other end of the week, tested for the same reason.",
             _weekday(4), family="calendar", max_share=0.30),
    Detector("turn_of_month", "Turn of the month",
             "The last trading day of a month and the first three of the "
             "next, counted in trading days actually present in this file.",
             _turn_of_month, family="calendar", max_share=0.35),
    Detector("january", "January",
             "The January effect, on whatever instrument this is.",
             _month(1), family="calendar", max_share=0.20),
    Detector("first_hour", "First hour of the day",
             "The hour after the session's own first bar. Where the "
             "overnight news gets priced.",
             _first_hour, needs_session=True, family="calendar",
             max_share=0.35),
    Detector("last_hour", "Last hour of the day",
             "The hour before the session's own last bar, where the "
             "rebalancing happens.",
             _last_hour, needs_session=True, family="calendar",
             max_share=0.35),
    Detector("after_long_break", "First bar after a long break",
             "A gap more than four times this series' usual one -- a "
             "weekend, a holiday or a data outage, and the detector cannot "
             "tell which.",
             _after_long_break, needs_session=True,
             family="calendar", max_share=0.30),
    Detector("round_number", "At a round number",
             "The close sits within a tenth of an ATR of a round level, "
             "scaled to the price's own magnitude.",
             _round_number, family="calendar", max_share=0.30),
)


DETECTORS: tuple[Detector, ...] = (
    Detector("volatility_spike", "Volatility spike",
             "ATR over five bars is more than twice ATR over fifty: the "
             "market has just started moving much faster than it was.",
             _volatility_spike),
    Detector("volatility_collapse", "Volatility collapse",
             "Short-term ATR has fallen below half the long-term one.",
             _volatility_collapse),
    Detector("range_shock", "Range shock",
             "A bar three times the average range.", _range_shock),
    Detector("gap_up", "Gap up",
             "The bar opened more than one ATR above the previous close.",
             _gap_up),
    Detector("gap_down", "Gap down",
             "The bar opened more than one ATR below the previous close.",
             _gap_down),
    Detector("volume_surge", "Volume surge",
             "Four times the fifty-bar average volume.", _volume_surge),
    Detector("volume_drought", "Volume drought",
             "A quarter of the fifty-bar average volume.", _volume_drought),
    Detector("shock_up", "Price shock up",
             "The close jumped more than three ATRs from the last one.",
             _shock_up),
    Detector("shock_down", "Price shock down",
             "The close fell more than three ATRs from the last one.",
             _shock_down),
    Detector("outside_bar", "Wide outside bar",
             "A bar that engulfed the previous one and was half again as "
             "wide as usual.", _outside_bar),
    Detector("inside_squeeze", "Inside bar in a squeeze",
             "An inside bar while volatility sits in the bottom fifth of its "
             "own range.", _inside_squeeze),
    Detector("stale_price", "Frozen price",
             "Four or more consecutive bars closing at exactly the same "
             "price. Usually a data problem, occasionally a real halt.",
             _stale_price),
    Detector("new_extreme_high", "New 200-bar high",
             "The close is the highest of the last two hundred bars.",
             _new_extreme_high),
    Detector("new_extreme_low", "New 200-bar low",
             "The close is the lowest of the last two hundred bars.",
             _new_extreme_low),
    Detector("thrust", "Three-bar thrust",
             "Three consecutive bars closing the same way, each with a body "
             "over eight tenths of an ATR.", _thrust),
) + CALENDAR_DETECTORS


# ---------------------------------------------------------------------------
# the scan
# ---------------------------------------------------------------------------


def _fire(detector: Detector, bars: BarSeries,
          session: np.ndarray) -> np.ndarray:
    """Run one detector, giving it the session mask if it asked for one."""
    if detector.needs_session:
        return detector.detect(bars, session)
    return detector.detect(bars)


def scan(bars: BarSeries, style: TradingStyle, *, timeframe: str = "",
         costs: CostModel | None = None, research_fraction: float = 0.65,
         control_draws: int = 1000, alpha: float = 0.10, seed: int = 0,
         progress: ProgressFn | None = None) -> AnomalyScan:
    """Find unusual bars, then measure whether trading after them pays."""
    started = time.time()
    timeframe = timeframe or choose_timeframe(bars, style)
    working = prepare_bars(bars, timeframe)
    n = len(working)
    if n < MIN_BARS:
        raise InsufficientDataError(
            too_few_bars("An anomaly scan", bars, working, timeframe))

    instrument = working.instrument
    timezone = getattr(instrument, "timezone", "UTC") or "UTC"
    costs = costs if costs is not None else default_costs(instrument)

    quality = _data_quality(working)

    stop_atr = style.stop_atr[len(style.stop_atr) // 2]
    target_r = style.target_r[len(style.target_r) // 2]
    hold_limit = None
    if style.session is not None and style.flat_at_session_end:
        hold_limit = session_hold_limit(working, timezone, style.session[0],
                                        style.session[1], style.max_bars,
                                        style.weekdays)
    entry_ok = session_entry_mask(
        working, timezone,
        style.session[0] if style.session else None,
        style.session[1] if style.session else None, style.weekdays,
        style.flat_at_session_end)

    eligible = int(entry_ok.sum())
    caches = {
        side: build_outcomes(working,
                             Geometry(side, stop_atr, target_r, style.max_bars,
                                      style.atr_period), costs, hold_limit,
                             detail=False)
        for side in (1, -1)
    }

    split = int(n * float(research_fraction))
    check_split(n, split, style.max_bars, "An anomaly scan")
    research = np.zeros(n, dtype=bool)
    research[:split] = True

    findings: list[AnomalyFinding] = []
    #: Every (detector, side) pair that was actually scored. This is the
    #: multiplicity, and it is what the correction divides by.
    attempts: list[tuple[AnomalyFinding, int, ControlResult, dict]] = []
    for index, detector in enumerate(DETECTORS):
        if progress is not None:
            progress(index, len(DETECTORS), f"Scanning for {detector.label}")
        try:
            fired = np.asarray(_fire(detector, working, entry_ok), dtype=bool)
        except Exception:                   # pragma: no cover - defensive
            from ..logging_setup import get_logger

            get_logger(__name__).exception("Detector %s failed", detector.key)
            continue
        fired &= entry_ok
        count = int(fired.sum())
        # Against the bars it could have fired on, not against every bar in the
        # file: for a session-limited style three quarters of the series was
        # never eligible, and dividing by all of it makes a detector that fires
        # on most of the session look rare.
        share = count / max(1, eligible)
        finding = AnomalyFinding(detector=detector, count=count, share=share)

        if count < _MIN_EVENTS:
            finding.verdict = f"too rare to judge ({count} bars)"
            findings.append(finding)
            continue
        if share > detector.max_share:
            finding.verdict = (f"fires on {share * 100:.0f}% of bars, which is "
                               f"not an anomaly")
            findings.append(finding)
            continue

        # Both sides are scored and both p-values go into the correction. It
        # is tempting to keep only the better side and correct over the
        # detectors alone, but taking the best of two is itself a search, and
        # not counting it halves the multiplicity twice over.
        sides = []
        for side in (1, -1):
            scored = _score(caches[side], fired & research)
            if scored is not None:
                sides.append((side, scored[1], scored[0]))
        if not sides:
            finding.verdict = "not enough trades after these bars to judge"
            findings.append(finding)
            continue

        for side, control, summary in sides:
            attempts.append((finding, side, control, summary))
        side, control, summary = max(
            sides, key=lambda item: item[1].excess_per_trade)
        finding.side = side
        finding.control = control
        finding.trades = int(summary["trades"])
        finding.per_trade = float(summary["per_trade"])
        finding.excess = control.excess_per_trade
        finding.p_value = control.p_value
        findings.append(finding)

    tests = len(attempts)
    if attempts:
        survives = benjamini_hochberg([c.p_value for _f, _s, c, _u in attempts],
                                      alpha)
        for (finding, side, _control, _summary), ok in zip(attempts, survives):
            if ok and side == finding.side:
                finding.survives_fdr = True
    scored = [f for f in findings if f.control is not None]

    for finding in scored:
        if not finding.survives_fdr:
            finding.verdict = "nothing follows it"
            finding.detail = ""
            continue
        cache = caches[finding.side]
        fired = np.asarray(_fire(finding.detector, working, entry_ok),
                           dtype=bool) & entry_ok
        confirmed = _sampled(cache, fired & research, control_draws, seed)
        held = _score(cache, fired & ~research)
        finding.holdout_excess = held[1].excess_per_trade if held else 0.0
        finding.holdout_trades = int(held[0]["trades"]) if held else 0
        _judge(finding, confirmed)

    findings.sort(key=lambda f: (-int(f.survives_fdr), -f.excess))

    import pandas as pd

    notes = [
        f"{len(DETECTORS)} detectors were tried on both sides — "
        f"{len(DETECTORS) * 2} tests — and {tests} of those had enough trades "
        f"to score. The p-values are corrected over all {tests}, including "
        f"each side that was not reported, because choosing the better of two "
        f"is itself a search.",
        f"{sum(1 for d in DETECTORS if d.family == 'calendar')} of the "
        f"detectors are calendar effects. Everywhere else in this application "
        f"a calendar condition is banned, because an optimiser allowed to "
        f"choose among five weekdays is being handed a free lottery ticket. "
        f"Naming them in advance is the opposite: this list is fixed in the "
        f"source, every entry is tested whether it looks promising or not, and "
        f"including them makes every other finding here harder to pass.",
        "Each detector is scored against random entries at the same times of "
        "day with the same geometry and costs, so 'it happened during a "
        "profitable hour' does not count as an edge.",
        f"Anomalies were selected on the first "
        f"{research_fraction * 100:.0f}% of the data; the rest is a check, not "
        f"a score.",
        f"'Share' is against the {eligible:,} bars a detector could fire on "
        f"for this style, not against every bar in the file.",
        "An unusual bar is not a trading signal until something reliably "
        "follows it. Most of the rows above are the market being unusual and "
        "then carrying on as before.",
    ]

    return AnomalyScan(
        symbol=getattr(instrument, "symbol", "?"), timeframe=timeframe,
        currency=getattr(instrument, "currency", "USD"), bars=n,
        start=str(pd.Timestamp(working.ts[0], tz="UTC").date()),
        end=str(pd.Timestamp(working.ts[-1], tz="UTC").date()),
        research_bars=split, holdout_bars=n - split,
        findings=findings, quality=quality, notes=notes,
        elapsed=time.time() - started)


def _score(cache: OutcomeCache, mask: np.ndarray):
    kept = select_sequential(cache, mask)
    if int(kept.sum()) < _MIN_EVENTS:
        return None
    pool = cache.valid & _block_of(mask)
    control = analytic_control(cache.minute_of_day[pool], cache.net_cash[pool],
                               cache.minute_of_day[kept], cache.net_cash[kept])
    return cache.summary(kept), control


def _sampled(cache: OutcomeCache, mask: np.ndarray, draws: int,
             seed: int) -> ControlResult:
    kept = select_sequential(cache, mask)
    pool = cache.valid & _block_of(mask)
    return sampled_control(cache.minute_of_day[pool], cache.net_cash[pool],
                           cache.minute_of_day[kept], cache.net_cash[kept],
                           draws=draws, seed=seed)


def _block_of(mask: np.ndarray) -> np.ndarray:
    """The contiguous block a mask lives in, so the control draws from it.

    A control for a research-block result must draw research-block bars; using
    the whole series would compare the anomaly against a period it was never
    measured in.
    """
    where = np.flatnonzero(mask)
    block = np.zeros(mask.size, dtype=bool)
    if where.size == 0:
        return block
    block[where[0]:where[-1] + 1] = True
    return block


def _judge(finding: AnomalyFinding, confirmed: ControlResult) -> None:
    way = "long" if finding.side > 0 else "short"
    concerns = []
    if confirmed.p_value > 0.10:
        concerns.append("the sampled control disagrees")
    if finding.holdout_trades < _MIN_EVENTS:
        concerns.append("too few in the locked block to confirm")
    elif finding.holdout_excess <= 0:
        concerns.append("it did not survive the locked block")

    if concerns:
        finding.verdict = "does not hold up"
        finding.detail = (f"{finding.label}: {way} looked worth "
                          f"{finding.excess:+,.2f} a trade on research, but "
                          + "; ".join(concerns) + ".")
        return
    finding.verdict = "worth a look"
    finding.detail = (
        f"{finding.label}: going {way} after these bars beat a matched "
        f"control by {finding.excess:+,.2f} per trade over {finding.trades:,} "
        f"trades, and by {finding.holdout_excess:+,.2f} over "
        f"{finding.holdout_trades:,} trades on the locked block.")


def _data_quality(bars: BarSeries) -> list[str]:
    """The file's own problems, which are not market anomalies."""
    from ..data.validation import validate_bars

    try:
        report = validate_bars(bars)
    except Exception:                       # pragma: no cover - defensive
        return []
    return [issue.format_line() for issue in report.sorted_issues()[:10]]
