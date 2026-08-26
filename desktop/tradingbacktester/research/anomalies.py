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
from ..finder.search import (MIN_BARS, choose_timeframe, default_costs,
                             prepare_bars, too_few_bars)
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
)


# ---------------------------------------------------------------------------
# the scan
# ---------------------------------------------------------------------------


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
            fired = np.asarray(detector.detect(working), dtype=bool)
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
        if share > _MAX_SHARE:
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
        fired = np.asarray(finding.detector.detect(working), dtype=bool) & entry_ok
        confirmed = _sampled(cache, fired & research, control_draws, seed)
        held = _score(cache, fired & ~research)
        finding.holdout_excess = held[1].excess_per_trade if held else 0.0
        finding.holdout_trades = int(held[0]["trades"]) if held else 0
        _judge(finding, confirmed)

    findings.sort(key=lambda f: (-int(f.survives_fdr), -f.excess))

    import pandas as pd

    notes = [
        f"{len(DETECTORS)} detectors were tried on each side and "
        f"{tests} of those had enough trades to score; the p-values are "
        f"corrected over all {tests}, including the side that was not "
        f"reported, because choosing the better of two is itself a search.",
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
