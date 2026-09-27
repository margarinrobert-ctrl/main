"""Checking a bar series for the things that quietly ruin a backtest.

The checks here are deliberately split into *errors* -- data the engine cannot
run on without producing nonsense, such as a bar whose high is below its low --
and *warnings* or *information*, which are worth knowing but do not stop a run.
A user should be able to read the report and know exactly what to do next.

The gap check is the fiddly one.  Every intraday dataset has gaps: overnight,
over the weekend, over holidays.  Reporting those would bury the one gap that
matters, so a gap is only counted when the missing slots are ones the dataset
*does* fill in other weeks.  The trading week is learned from the data itself
rather than assumed, which means it works for a 24/5 FX file, a 09:30-16:00
equity file and a 24/7 crypto file without being told which is which.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..core.errors import DataError
from .models import BarSeries

log = logging.getLogger(__name__)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
_SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

#: A move this many robust standard deviations from the median is almost always
#: a decimal point in the wrong place rather than a real trade.
EXTREME_SIGMA = 20.0

#: Bars of identical closing price in a row before it is worth mentioning.
CONSTANT_RUN_BARS = 10

#: Above this share of missing bars a gap report becomes a warning.
GAP_WARNING_FRACTION = 0.01

_NS_PER_WEEK = 604_800_000_000_000
_NS_PER_HOUR = 3_600_000_000_000
# 1970-01-05 was a Monday; weekly slot maths is anchored there so slot 0 is
# Monday 00:00 UTC.
_MONDAY_ANCHOR_NS = 4 * 86_400 * 1_000_000_000
_MAX_WEEKLY_SLOTS = 5_000_000


def _stamp(ts_ns: int | np.integer) -> str:
    """Format a UTC nanosecond timestamp for a message, without pandas."""
    try:
        text = str(np.datetime64(int(ts_ns), "ns"))
    except (ValueError, OverflowError):  # pragma: no cover - defensive
        return str(ts_ns)
    return text.replace("T", " ").rstrip("0").rstrip(".") if "." in text else \
        text.replace("T", " ")


@dataclass(frozen=True)
class DataIssue:
    """One finding about a dataset.

    ``count`` is how many bars are affected, ``example_index`` the first of
    them and ``example_text`` a human-readable rendering of that bar so the
    user can go and look at it in the file.
    """

    severity: str
    code: str
    message: str
    count: int = 1
    example_index: int | None = None
    example_text: str = ""

    @property
    def is_error(self) -> bool:
        """True when this issue makes a backtest on the data meaningless."""
        return self.severity == SEVERITY_ERROR

    def format_line(self) -> str:
        """One line of the text report."""
        label = self.severity.upper()
        where = ""
        if self.example_index is not None:
            where = f" (first at bar {self.example_index:,}"
            where += f": {self.example_text})" if self.example_text else ")"
        elif self.example_text:
            where = f" ({self.example_text})"
        return f"{label}: {self.message}{where}"

    def to_dict(self) -> dict[str, Any]:
        """Plain dictionary, for the report file and the log."""
        return {"severity": self.severity, "code": self.code,
                "message": self.message, "count": self.count,
                "example_index": self.example_index,
                "example_text": self.example_text}


@dataclass
class DataQualityReport:
    """The result of :func:`validate_bars`."""

    bar_count: int = 0
    issues: list[DataIssue] = field(default_factory=list)
    symbol: str = ""
    timeframe: str = ""
    start_text: str = ""
    end_text: str = ""

    def add(self, severity: str, code: str, message: str, count: int = 1,
            example_index: int | None = None, example_text: str = "") -> DataIssue:
        """Record one finding and return it."""
        issue = DataIssue(severity=severity, code=code, message=message,
                          count=int(count), example_index=example_index,
                          example_text=example_text)
        self.issues.append(issue)
        return issue

    @property
    def errors(self) -> list[DataIssue]:
        """Findings that make the data unusable as it stands."""
        return [i for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[DataIssue]:
        """Findings worth reading before trusting a result."""
        return [i for i in self.issues if i.severity == SEVERITY_WARNING]

    @property
    def infos(self) -> list[DataIssue]:
        """Findings that are simply worth knowing, including what cleaning did."""
        return [i for i in self.issues if i.severity == SEVERITY_INFO]

    @property
    def is_usable(self) -> bool:
        """True when nothing found would make a backtest meaningless."""
        return not self.errors

    def sorted_issues(self) -> list[DataIssue]:
        """Issues worst-first, which is the order a dialog should show them in."""
        return sorted(self.issues,
                      key=lambda i: (_SEVERITY_ORDER.get(i.severity, 3), -i.count))

    def summary_text(self) -> str:
        """A short plain-text report suitable for a dialog or the log."""
        head = f"{self.bar_count:,} bars"
        if self.symbol:
            head = f"{self.symbol} {self.timeframe}: {head}"
        if self.start_text and self.end_text:
            head += f", {self.start_text} to {self.end_text} UTC"
        counts = (f"{len(self.errors)} problem(s), {len(self.warnings)} warning(s), "
                  f"{len(self.infos)} note(s)")
        lines = [head, counts]
        if not self.issues:
            lines.append("Nothing to report: this dataset looks clean.")
        else:
            lines.extend(issue.format_line() for issue in self.sorted_issues())
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Plain dictionary for saving a report next to an imported dataset."""
        return {
            "bar_count": self.bar_count, "symbol": self.symbol,
            "timeframe": self.timeframe, "start": self.start_text,
            "end": self.end_text, "is_usable": self.is_usable,
            "error_count": len(self.errors), "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.sorted_issues()],
        }


def _first_true(mask: np.ndarray) -> int | None:
    """Index of the first flagged bar, or ``None`` when nothing is flagged."""
    idx = np.flatnonzero(mask)
    return int(idx[0]) if idx.size else None


def _describe_bar(bars: BarSeries, index: int) -> str:
    """One bar written out, so a user can find it in the original file."""
    inst = bars.instrument
    return (f"{_stamp(bars.ts[index])} "
            f"O={inst.format_price(float(bars.open[index]))} "
            f"H={inst.format_price(float(bars.high[index]))} "
            f"L={inst.format_price(float(bars.low[index]))} "
            f"C={inst.format_price(float(bars.close[index]))}")


def _modal_step(ts: np.ndarray) -> int:
    """Most common positive gap between consecutive bars, in nanoseconds."""
    diffs = np.diff(ts)
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        return 0
    values, counts = np.unique(diffs, return_counts=True)
    return int(values[int(np.argmax(counts))])


def _active_slot_table(ts: np.ndarray, step: int) -> tuple[np.ndarray, int, int, bool]:
    """Build the weekly template of slots this dataset actually fills.

    Returns ``(prefix_counts, slots_per_week, slot_ns, exact)``.  ``prefix_counts``
    is an exclusive cumulative sum of the active flags so the number of active
    slots in any range can be answered in constant time -- which is what makes
    the gap scan a vectorised expression instead of a loop over gaps.
    """
    exact = step > 0 and _NS_PER_WEEK % step == 0 and _NS_PER_WEEK // step <= _MAX_WEEKLY_SLOTS
    slot_ns = step if exact else _NS_PER_HOUR
    slots = int(_NS_PER_WEEK // slot_ns)
    active = np.zeros(slots, dtype=bool)
    positions = ((ts - _MONDAY_ANCHOR_NS) // slot_ns) % slots
    active[positions.astype("int64")] = True
    prefix = np.concatenate(([0], np.cumsum(active.astype("int64"))))
    return prefix, slots, slot_ns, exact


def _active_before(slot_index: np.ndarray, prefix: np.ndarray, slots: int) -> np.ndarray:
    """Number of active slots strictly before each global slot index."""
    whole = slot_index // slots
    rest = slot_index % slots
    return whole * int(prefix[slots]) + prefix[rest.astype("int64")]


def _check_gaps(bars: BarSeries, report: DataQualityReport) -> None:
    """Count bars missing from slots this dataset fills in other weeks."""
    ts = bars.ts
    if ts.size < 3:
        return
    step = _modal_step(ts)
    if step <= 0:
        return
    prefix, slots, slot_ns, exact = _active_slot_table(ts, step)
    slot_index = (ts - _MONDAY_ANCHOR_NS) // slot_ns
    before = _active_before(slot_index, prefix, slots)
    # Active slots strictly between consecutive bars: everything the dataset
    # fills in other weeks but did not fill here.
    missing = before[1:] - before[:-1] - 1
    np.maximum(missing, 0, out=missing)
    if not exact:
        # Hour-resolution template: scale hours back to bars.
        missing = (missing * (slot_ns / step)).round().astype("int64")
    holes = np.flatnonzero(missing > 0)
    if holes.size == 0:
        return
    total = int(missing[holes].sum())
    worst = int(holes[int(np.argmax(missing[holes]))])
    fraction = total / max(1, total + ts.size)
    severity = SEVERITY_WARNING if fraction >= GAP_WARNING_FRACTION else SEVERITY_INFO
    approx = "" if exact else " (estimated)"
    report.add(
        severity, "gaps",
        f"{holes.size:,} gap(s) inside the trading week, {total:,} bar(s) "
        f"missing in total{approx}",
        count=holes.size, example_index=worst,
        example_text=(f"{int(missing[worst]):,} bars missing between "
                      f"{_stamp(ts[worst])} and {_stamp(ts[worst + 1])}"),
    )


def _check_finite(bars: BarSeries, report: DataQualityReport) -> None:
    """Missing or infinite values in any column."""
    for name in ("open", "high", "low", "close", "volume"):
        values = getattr(bars, name)
        bad = ~np.isfinite(values)
        if not bad.any():
            continue
        idx = _first_true(bad)
        nan_count = int(np.isnan(values).sum())
        kind = "missing" if nan_count == int(bad.sum()) else "missing or infinite"
        report.add(
            SEVERITY_ERROR, f"non_finite_{name}",
            f"{int(bad.sum()):,} bar(s) have a {kind} {name} value",
            count=int(bad.sum()), example_index=idx,
            example_text=_stamp(bars.ts[idx]) if idx is not None else "",
        )


def _check_timestamps(bars: BarSeries, report: DataQualityReport) -> None:
    """Repeated and backwards timestamps, both of which break bar indexing."""
    ts = bars.ts
    if ts.size < 2:
        return
    diffs = np.diff(ts)
    duplicates = diffs == 0
    if duplicates.any():
        idx = _first_true(duplicates)
        report.add(
            SEVERITY_ERROR, "duplicate_timestamps",
            f"{int(duplicates.sum()):,} bar(s) repeat a timestamp already used",
            count=int(duplicates.sum()), example_index=idx,
            example_text=_stamp(ts[idx]) if idx is not None else "",
        )
    backwards = diffs < 0
    if backwards.any():
        idx = _first_true(backwards)
        report.add(
            SEVERITY_ERROR, "unsorted_timestamps",
            f"{int(backwards.sum()):,} bar(s) go backwards in time",
            count=int(backwards.sum()), example_index=idx,
            example_text=(f"{_stamp(ts[idx])} is followed by {_stamp(ts[idx + 1])}"
                          if idx is not None else ""),
        )


def _ohlc_tolerance(values: np.ndarray) -> np.ndarray:
    """Comparison slack that scales with price, so rounding is not an error."""
    return 1e-9 * np.maximum(1.0, np.abs(values))


def _check_ohlc(bars: BarSeries, report: DataQualityReport) -> None:
    """Impossible bar geometry: a high under the low, a body outside the range."""
    o, h, l, c = bars.open, bars.high, bars.low, bars.close
    finite = np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
    tol = _ohlc_tolerance(c)

    checks = (
        ("high_below_low", h < l - tol, "have a high below their low"),
        ("high_below_body", h < np.maximum(o, c) - tol,
         "have a high below their open or close"),
        ("low_above_body", l > np.minimum(o, c) + tol,
         "have a low above their open or close"),
    )
    for code, raw_mask, wording in checks:
        mask = raw_mask & finite
        if not mask.any():
            continue
        idx = _first_true(mask)
        report.add(
            SEVERITY_ERROR, code,
            f"{int(mask.sum()):,} bar(s) {wording}",
            count=int(mask.sum()), example_index=idx,
            example_text=_describe_bar(bars, idx) if idx is not None else "",
        )

    non_positive = finite & ((o <= 0) | (h <= 0) | (l <= 0) | (c <= 0))
    if non_positive.any():
        idx = _first_true(non_positive)
        report.add(
            SEVERITY_ERROR, "non_positive_price",
            f"{int(non_positive.sum()):,} bar(s) have a price of zero or less",
            count=int(non_positive.sum()), example_index=idx,
            example_text=_describe_bar(bars, idx) if idx is not None else "",
        )


def _check_volume(bars: BarSeries, report: DataQualityReport) -> None:
    """Negative, zero and entirely absent volume."""
    volume = bars.volume
    finite = np.isfinite(volume)
    negative = finite & (volume < 0)
    if negative.any():
        idx = _first_true(negative)
        # A warning rather than an error: volume plays no part in the profit and
        # loss of a trade, so a backtest on these bars is still meaningful --
        # only volume-based indicators are affected.
        report.add(
            SEVERITY_WARNING, "negative_volume",
            f"{int(negative.sum()):,} bar(s) have a negative volume, which is "
            f"impossible; volume indicators will be wrong on those bars",
            count=int(negative.sum()), example_index=idx,
            example_text=_stamp(bars.ts[idx]) if idx is not None else "",
        )
    zero = finite & (volume == 0)
    zero_count = int(zero.sum())
    if zero_count == volume.size and volume.size:
        report.add(
            SEVERITY_INFO, "no_volume",
            "This dataset has no volume: every bar is zero. Volume-based "
            "indicators will be flat.",
            count=zero_count, example_index=0,
        )
    elif zero_count:
        idx = _first_true(zero)
        severity = (SEVERITY_WARNING if zero_count > 0.05 * volume.size
                    else SEVERITY_INFO)
        report.add(
            severity, "zero_volume",
            f"{zero_count:,} bar(s) have zero volume",
            count=zero_count, example_index=idx,
            example_text=_stamp(bars.ts[idx]) if idx is not None else "",
        )


def _check_constant_runs(bars: BarSeries, report: DataQualityReport) -> None:
    """Long stretches of an unchanged close, which usually means a stale feed."""
    close = bars.close
    if close.size < CONSTANT_RUN_BARS + 1:
        return
    # Run boundaries: every index where the close changes ends a run.
    changed = np.flatnonzero(np.diff(close) != 0)
    edges = np.concatenate(([-1], changed, [close.size - 1]))
    lengths = np.diff(edges)
    long_runs = np.flatnonzero(lengths >= CONSTANT_RUN_BARS)
    if long_runs.size == 0:
        return
    longest = int(long_runs[int(np.argmax(lengths[long_runs]))])
    start = int(edges[longest]) + 1
    report.add(
        SEVERITY_WARNING, "constant_price",
        f"{long_runs.size:,} run(s) of {CONSTANT_RUN_BARS} or more bars with an "
        f"unchanged closing price; the longest is {int(lengths[longest]):,} bars",
        count=int(long_runs.size), example_index=start,
        example_text=_stamp(bars.ts[start]),
    )


def _check_extreme_returns(bars: BarSeries, report: DataQualityReport) -> None:
    """Bar-to-bar moves far outside the usual range: bad prices, not real ones."""
    close = bars.close
    if close.size < 32:
        return
    previous = close[:-1]
    valid = np.isfinite(previous) & (previous > 0) & np.isfinite(close[1:])
    if valid.sum() < 30:
        return
    returns = np.zeros(previous.size, dtype="float64")
    np.divide(close[1:] - previous, previous, out=returns, where=valid)
    sample = returns[valid]
    median = float(np.median(sample))
    # A median absolute deviation is used rather than a standard deviation
    # because one 1000% "return" from a bad decimal point inflates a standard
    # deviation enough to hide itself.
    mad = float(np.median(np.abs(sample - median)))
    sigma = mad * 1.4826
    if sigma <= 0:
        sigma = float(np.std(sample))
    if sigma <= 0:
        return
    extreme = valid & (np.abs(returns - median) > EXTREME_SIGMA * sigma)
    if not extreme.any():
        return
    positions = np.flatnonzero(extreme) + 1
    worst = int(positions[int(np.argmax(np.abs(returns[positions - 1] - median)))])
    move = float(returns[worst - 1]) * 100.0
    report.add(
        SEVERITY_WARNING, "extreme_return",
        f"{positions.size:,} bar(s) move more than {EXTREME_SIGMA:g} standard "
        f"deviations from the usual bar-to-bar change, which usually means a bad "
        f"price rather than a real move",
        count=int(positions.size), example_index=worst,
        example_text=f"{_stamp(bars.ts[worst])} moved {move:+.2f}%",
    )


def _check_import_warnings(bars: BarSeries, report: DataQualityReport) -> None:
    """Carry the loader's caveats into the quality report.

    A CSV with no low column is imported with the low derived from the body,
    which narrows every bar's range and would make stop-loss testing
    systematically optimistic.  The loader records that in ``bars.meta``; if the
    report did not repeat it, the only place the user could see it would be the
    log file, which is not where anyone looks before running a backtest.
    """
    for message in bars.meta.get("warnings", ()) or ():
        text = str(message)
        derived = ("derived" in text.lower() or "was used" in text.lower())
        report.add(SEVERITY_WARNING if derived else SEVERITY_INFO,
                   "import_warning", text, count=len(bars))


def validate_bars(bars: BarSeries) -> DataQualityReport:
    """Check a bar series and describe everything wrong with it.

    Never raises for bad *data*; the whole point is to report rather than fail.
    A :class:`DataError` is only raised when the argument is not a bar series
    at all.
    """
    if not isinstance(bars, BarSeries):
        raise DataError("There is no dataset to check.",
                        detail=f"got {type(bars).__name__}")
    report = DataQualityReport(bar_count=len(bars),
                               symbol=bars.instrument.symbol,
                               timeframe=bars.timeframe.label)
    if bars.is_empty:
        report.add(SEVERITY_ERROR, "empty", "This dataset contains no bars.",
                   count=0)
        return report
    report.start_text = _stamp(bars.ts[0])
    report.end_text = _stamp(bars.ts[-1])

    _check_import_warnings(bars, report)
    _check_finite(bars, report)
    _check_timestamps(bars, report)
    _check_ohlc(bars, report)
    _check_volume(bars, report)
    _check_gaps(bars, report)
    _check_constant_runs(bars, report)
    _check_extreme_returns(bars, report)

    if len(bars) < 100:
        report.add(SEVERITY_WARNING, "few_bars",
                   f"Only {len(bars):,} bars: most indicators and every "
                   f"performance statistic need far more than this to mean "
                   f"anything.", count=len(bars))
    log.debug("validated %s: %d issue(s)", bars.instrument.symbol, len(report.issues))
    return report


def clean_bars(bars: BarSeries, drop_duplicates: bool = True, sort: bool = True,
               drop_invalid_ohlc: bool = False) -> tuple[BarSeries, DataQualityReport]:
    """Repair what can be repaired and report what is left.

    Sorting and de-duplicating are safe: they change the order of rows, not the
    data.  Dropping bars with impossible OHLC relationships is off by default
    because it silently deletes market data, which the user should choose to do
    knowingly.

    The returned report describes the *cleaned* series, with what was removed
    listed first as information.
    """
    if not isinstance(bars, BarSeries):
        raise DataError("There is no dataset to clean.",
                        detail=f"got {type(bars).__name__}")
    actions: list[DataIssue] = []
    if bars.is_empty:
        return bars, validate_bars(bars)

    order = np.arange(len(bars), dtype="int64")
    ts = bars.ts
    if sort and bool(np.any(np.diff(ts) < 0)):
        order = np.argsort(ts, kind="stable")
        actions.append(DataIssue(SEVERITY_INFO, "sorted",
                                 "The bars were not in date order and were sorted "
                                 "oldest first.", count=len(bars)))
    ts = bars.ts[order]

    if drop_duplicates and ts.size > 1:
        repeated = np.zeros(ts.size, dtype=bool)
        repeated[:-1] = ts[1:] == ts[:-1]
        if repeated.any():
            # Keep the last row of each repeated timestamp: a revised bar is
            # appended after the one it replaces.
            actions.append(DataIssue(
                SEVERITY_INFO, "deduplicated",
                f"{int(repeated.sum()):,} bar(s) repeated a timestamp and were "
                f"removed, keeping the last of each.", count=int(repeated.sum()),
                example_index=int(np.flatnonzero(repeated)[0]),
                example_text=_stamp(ts[int(np.flatnonzero(repeated)[0])])))
            order = order[~repeated]

    if drop_invalid_ohlc:
        o, h = bars.open[order], bars.high[order]
        l, c = bars.low[order], bars.close[order]
        finite = (np.isfinite(o) & np.isfinite(h) & np.isfinite(l)
                  & np.isfinite(c) & np.isfinite(bars.volume[order]))
        tol = _ohlc_tolerance(np.where(np.isfinite(c), c, 0.0))
        with np.errstate(invalid="ignore"):
            sane = (finite & (h >= l - tol) & (h >= np.maximum(o, c) - tol)
                    & (l <= np.minimum(o, c) + tol)
                    & (o > 0) & (h > 0) & (l > 0) & (c > 0))
        removed = int((~sane).sum())
        if removed:
            first = int(np.flatnonzero(~sane)[0])
            actions.append(DataIssue(
                SEVERITY_INFO, "dropped_invalid",
                f"{removed:,} bar(s) with impossible or missing prices were "
                f"removed.", count=removed, example_index=first,
                example_text=_stamp(bars.ts[order][first])))
            order = order[sane]

    cleaned = BarSeries(
        ts=bars.ts[order], open=bars.open[order], high=bars.high[order],
        low=bars.low[order], close=bars.close[order], volume=bars.volume[order],
        instrument=bars.instrument, timeframe=bars.timeframe, source=bars.source,
        meta=dict(bars.meta),
    )
    report = validate_bars(cleaned)
    report.issues = actions + report.issues
    if cleaned.is_empty:
        report.add(SEVERITY_ERROR, "empty_after_clean",
                   "Cleaning removed every bar in this dataset.", count=0)
    log.info("cleaned %s: %d bars in, %d out", bars.instrument.symbol,
             len(bars), len(cleaned))
    return cleaned, report
