"""Timeframes and the rules for converting between them.

A :class:`Timeframe` is an amount of time per bar.  It is stored as a
``(multiplier, unit)`` pair rather than a raw number of seconds so that
calendar units -- days, weeks, months -- keep their meaning across DST changes
and weekends.

The only *safe* conversion is upsampling to a whole multiple: 1m bars can build
5m bars because five 1m bars fit exactly inside one 5m bar.  Going the other way
(5m -> 1m) would require inventing data and is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .errors import TimeframeError


class TimeframeUnit(str, Enum):
    """The unit of a timeframe."""

    SECOND = "s"
    MINUTE = "m"
    HOUR = "h"
    DAY = "d"
    WEEK = "w"
    MONTH = "M"

    @property
    def is_calendar(self) -> bool:
        """True for units whose length in seconds is not constant."""
        return self in (TimeframeUnit.DAY, TimeframeUnit.WEEK, TimeframeUnit.MONTH)


#: Nominal seconds per unit.  DAY/WEEK/MONTH are approximate and are used only
#: for ordering and for "is this timeframe coarser than that one" questions --
#: never for building bars, which uses calendar-aware grouping.
_UNIT_SECONDS: dict[TimeframeUnit, float] = {
    TimeframeUnit.SECOND: 1.0,
    TimeframeUnit.MINUTE: 60.0,
    TimeframeUnit.HOUR: 3600.0,
    TimeframeUnit.DAY: 86400.0,
    TimeframeUnit.WEEK: 604800.0,
    TimeframeUnit.MONTH: 2629746.0,
}


@dataclass(frozen=True, order=False)
class Timeframe:
    """A bar duration, e.g. ``Timeframe(5, TimeframeUnit.MINUTE)``."""

    multiplier: int
    unit: TimeframeUnit

    def __post_init__(self) -> None:
        if self.multiplier <= 0:
            raise TimeframeError(
                f"A timeframe multiplier must be a positive whole number, got {self.multiplier}."
            )

    # -- construction ----------------------------------------------------

    @classmethod
    def parse(cls, text: str) -> "Timeframe":
        """Parse ``"5m"``, ``"1h"``, ``"D"``, ``"1D"``, ``"4 hours"`` and friends.

        Raises
        ------
        TimeframeError
            If the string cannot be understood.
        """
        if isinstance(text, Timeframe):  # pragma: no cover - defensive
            return text
        raw = str(text).strip()
        if not raw:
            raise TimeframeError("No timeframe was given.")
        norm = raw.replace(" ", "").replace("-", "").replace("_", "")

        aliases = {
            "d": "1d", "day": "1d", "daily": "1d", "1day": "1d",
            "w": "1w", "week": "1w", "weekly": "1w", "1week": "1w",
            "mo": "1M", "month": "1M", "monthly": "1M", "1month": "1M",
            "h": "1h", "hour": "1h", "hourly": "1h",
            "min": "1m", "minute": "1m",
        }
        low = norm.lower()
        if low in aliases:
            norm = aliases[low]

        digits = ""
        idx = 0
        while idx < len(norm) and norm[idx].isdigit():
            digits += norm[idx]
            idx += 1
        suffix = norm[idx:]
        if not digits:
            digits = "1"
        if not suffix:
            # A bare number is read as minutes, which is what most vendors mean.
            suffix = "m"

        suffix_map = {
            "s": TimeframeUnit.SECOND, "sec": TimeframeUnit.SECOND,
            "secs": TimeframeUnit.SECOND, "second": TimeframeUnit.SECOND,
            "seconds": TimeframeUnit.SECOND,
            "m": TimeframeUnit.MINUTE, "min": TimeframeUnit.MINUTE,
            "mins": TimeframeUnit.MINUTE, "minute": TimeframeUnit.MINUTE,
            "minutes": TimeframeUnit.MINUTE,
            "h": TimeframeUnit.HOUR, "hr": TimeframeUnit.HOUR,
            "hrs": TimeframeUnit.HOUR, "hour": TimeframeUnit.HOUR,
            "hours": TimeframeUnit.HOUR,
            "d": TimeframeUnit.DAY, "day": TimeframeUnit.DAY, "days": TimeframeUnit.DAY,
            "w": TimeframeUnit.WEEK, "wk": TimeframeUnit.WEEK,
            "week": TimeframeUnit.WEEK, "weeks": TimeframeUnit.WEEK,
        }
        # 'M' means month, 'm' means minute -- the only case-sensitive suffix.
        if suffix == "M" or suffix.lower() in ("mo", "mon", "month", "months"):
            unit = TimeframeUnit.MONTH
        else:
            unit = suffix_map.get(suffix.lower())
        if unit is None:
            raise TimeframeError(
                f"'{raw}' is not a timeframe this application understands.",
                detail="Expected something like 1m, 5m, 15m, 30m, 1h, 4h, 1d or 1w.",
            )
        return cls(int(digits), unit)

    # -- properties ------------------------------------------------------

    @property
    def label(self) -> str:
        """Short display label, e.g. ``"5m"``, ``"1h"``, ``"1D"``."""
        if self.unit is TimeframeUnit.DAY:
            return f"{self.multiplier}D" if self.multiplier != 1 else "1D"
        if self.unit is TimeframeUnit.WEEK:
            return f"{self.multiplier}W" if self.multiplier != 1 else "1W"
        if self.unit is TimeframeUnit.MONTH:
            return f"{self.multiplier}M"
        return f"{self.multiplier}{self.unit.value}"

    @property
    def display_name(self) -> str:
        """Long display label, e.g. ``"5 minutes"``."""
        names = {
            TimeframeUnit.SECOND: "second", TimeframeUnit.MINUTE: "minute",
            TimeframeUnit.HOUR: "hour", TimeframeUnit.DAY: "day",
            TimeframeUnit.WEEK: "week", TimeframeUnit.MONTH: "month",
        }
        base = names[self.unit]
        return f"{self.multiplier} {base}" + ("s" if self.multiplier != 1 else "")

    @property
    def approx_seconds(self) -> float:
        """Approximate length in seconds; exact for sub-daily timeframes."""
        return self.multiplier * _UNIT_SECONDS[self.unit]

    @property
    def pandas_freq(self) -> str:
        """The pandas offset alias used to group bars of this timeframe."""
        mapping = {
            TimeframeUnit.SECOND: "s", TimeframeUnit.MINUTE: "min",
            TimeframeUnit.HOUR: "h", TimeframeUnit.DAY: "D",
            TimeframeUnit.WEEK: "W-MON", TimeframeUnit.MONTH: "MS",
        }
        return f"{self.multiplier}{mapping[self.unit]}"

    # -- comparison ------------------------------------------------------

    def __lt__(self, other: "Timeframe") -> bool:
        return self.approx_seconds < other.approx_seconds

    def __le__(self, other: "Timeframe") -> bool:
        return self.approx_seconds <= other.approx_seconds

    def __gt__(self, other: "Timeframe") -> bool:
        return self.approx_seconds > other.approx_seconds

    def __ge__(self, other: "Timeframe") -> bool:
        return self.approx_seconds >= other.approx_seconds

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.label

    def can_build_from(self, source: "Timeframe") -> bool:
        """True if bars of this timeframe can be built out of ``source`` bars.

        Requires the source to be strictly finer *and*, for same-unit pairs, to
        divide evenly.  Weeks are buildable from days; months from days or
        weeks; anything sub-daily must divide exactly.
        """
        if source.approx_seconds > self.approx_seconds:
            return False
        if source == self:
            return True
        if source.unit is self.unit:
            return self.multiplier % source.multiplier == 0
        # Cross-unit: allow only when the source unit divides the target unit
        # cleanly in calendar terms.
        order = [TimeframeUnit.SECOND, TimeframeUnit.MINUTE, TimeframeUnit.HOUR,
                 TimeframeUnit.DAY, TimeframeUnit.WEEK, TimeframeUnit.MONTH]
        if order.index(source.unit) > order.index(self.unit):
            return False
        if self.unit in (TimeframeUnit.WEEK, TimeframeUnit.MONTH):
            return True
        # e.g. 1h from 5m: 3600 % 300 == 0
        return self.approx_seconds % source.approx_seconds == 0


#: Timeframes offered in the UI, coarsest last.
STANDARD_TIMEFRAMES: tuple[Timeframe, ...] = (
    Timeframe(1, TimeframeUnit.MINUTE),
    Timeframe(5, TimeframeUnit.MINUTE),
    Timeframe(15, TimeframeUnit.MINUTE),
    Timeframe(30, TimeframeUnit.MINUTE),
    Timeframe(1, TimeframeUnit.HOUR),
    Timeframe(4, TimeframeUnit.HOUR),
    Timeframe(1, TimeframeUnit.DAY),
    Timeframe(1, TimeframeUnit.WEEK),
)


def infer_timeframe(timestamps_ns) -> Timeframe:
    """Infer the timeframe of a series of UTC nanosecond timestamps.

    Uses the *modal* gap between consecutive bars, which is robust to weekend
    gaps, holidays and missing bars.  Raises :class:`TimeframeError` when fewer
    than two timestamps are supplied.
    """
    import numpy as np

    ts = np.asarray(timestamps_ns, dtype="int64")
    if ts.size < 2:
        raise TimeframeError(
            "At least two bars are needed to work out the timeframe of a dataset."
        )
    diffs = np.diff(ts)
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        raise TimeframeError("Every timestamp in this dataset is identical.")
    values, counts = np.unique(diffs, return_counts=True)
    gap_ns = int(values[int(np.argmax(counts))])
    gap_s = gap_ns / 1e9
    if gap_s >= 20 * 86400:
        return Timeframe(1, TimeframeUnit.MONTH)
    if gap_s >= 5 * 86400:
        return Timeframe(max(1, round(gap_s / 604800)), TimeframeUnit.WEEK)
    if gap_s >= 86400:
        return Timeframe(max(1, round(gap_s / 86400)), TimeframeUnit.DAY)
    if gap_s >= 3600:
        return Timeframe(max(1, round(gap_s / 3600)), TimeframeUnit.HOUR)
    if gap_s >= 60:
        return Timeframe(max(1, round(gap_s / 60)), TimeframeUnit.MINUTE)
    return Timeframe(max(1, round(gap_s)), TimeframeUnit.SECOND)
