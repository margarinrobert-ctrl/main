"""Work out which column is which by reading the values, not the header names.

A header row is a claim about a file, not a proof.  Real exports arrive with
the columns in a vendor's own order, with names in another language, with a
``Volume`` column that is entirely zero sitting next to the real volume, with
the newest bar first -- and, when a mapping has been edited by hand or by a
stray mouse wheel, pointing at the wrong column altogether.

So this module decides from the data.  Two facts make that possible without
guesswork:

* a timestamp column parses as timestamps and moves in one direction;
* an OHLC quartet satisfies ``high >= max(open, close)`` and
  ``low <= min(open, close)`` on essentially every bar.

The second is the whole test.  It is a *falsifiable* statement about four
columns, which is what separates this from pattern-matching on names: a wrong
assignment fails it on the first few bars, and the right one cannot fail it.

Nothing here parses a file.  It takes the sample rows :func:`sniff_csv` has
already read and returns an ordinary :class:`~.csv_loader.ColumnMapping`, so
every path downstream -- the loader, validation, the dataset sidecar, the
import dialog -- is unchanged.  :func:`audit_mapping` is deliberately
conservative: it changes a mapping only when the current one demonstrably
fails and the replacement demonstrably passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from . import csv_loader as _csv

#: Rows examined.  Twenty prove the OHLC relation; a few hundred make the
#: open/close continuity test meaningful and still cost nothing.
MAX_ROWS = 400

#: Fraction of rows that must satisfy the OHLC relation before a quartet is
#: accepted.  Not 1.0: real files contain the occasional broken bar, and one
#: bad row must not send the detector off looking for a different answer.
OHLC_PASS = 0.97

#: Median relative difference under which two numeric columns are "the same
#: price".  Two prices of one bar differ by a fraction of a percent; a price
#: and a volume differ by orders of magnitude.
SAME_SCALE = 0.08

#: A numeric column must be at least this clean to be treated as numbers.
NUMERIC_MIN = 0.98

#: Columns considered when grouping prices.  The comparison is pairwise, so
#: this bounds the cost on a very wide file; a candle is never past here.
MAX_GROUP_COLUMNS = 40

#: Smallest median value an integral column may have and still be an epoch
#: timestamp.  1e8 seconds is 1973, and no price and few volumes reach it.
EPOCH_MIN = 1e8

_PRICE_FIELDS = ("open", "high", "low", "close")
_TRIM = str.maketrans("", "", "$€£¥₹ '’ ")


# ---------------------------------------------------------------------------
# what one column contains
# ---------------------------------------------------------------------------


@dataclass
class ColumnFacts:
    """What a sample of one column's values proves about it."""

    index: int
    name: str
    kind: str = "empty"
    """One of ``datetime``, ``time``, ``numeric``, ``text`` or ``empty``."""
    values: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype="float64"))
    texts: list[str] = field(default_factory=list)
    numeric_fraction: float = 0.0
    median: float = float("nan")
    all_zero: bool = False
    integral: bool = False
    non_negative: bool = True
    monotone: float = 0.0
    """Largest fraction of consecutive steps sharing one sign."""
    datetime_kind: str = "unknown"
    datetime_format: str | None = None

    @property
    def is_numeric(self) -> bool:
        return self.kind == "numeric"

    @property
    def is_datetime(self) -> bool:
        return self.kind == "datetime"


def to_number(text: str, decimal: str = ".", thousands: str = "") -> float:
    """Parse one cell the way the loader will, or return ``nan``.

    Currency symbols, thousands separators, a comma decimal point and
    accountancy negatives -- ``(1 234,50)`` -- all appear in exported files and
    must not make a price column look like text.
    """
    s = str(text).strip().translate(_TRIM)
    if not s:
        return float("nan")
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    if thousands:
        s = s.replace(thousands, "")
    if decimal and decimal != ".":
        s = s.replace(decimal, ".")
    try:
        value = float(s)
    except ValueError:
        return float("nan")
    return -value if negative else value


def _monotone_fraction(values: np.ndarray) -> float:
    """How one-directional a numeric column is, ignoring flat steps."""
    good = values[np.isfinite(values)]
    if good.size < 3:
        return 0.0
    steps = np.diff(good)
    moving = steps[steps != 0.0]
    if moving.size == 0:
        return 0.0
    up = float((moving > 0).sum()) / float(moving.size)
    return max(up, 1.0 - up)


def _facts_for(index: int, name: str, texts: Sequence[str],
               decimal: str, thousands: str) -> ColumnFacts:
    facts = ColumnFacts(index=index, name=str(name))
    filled = [t for t in texts if t != ""]
    facts.texts = list(filled)
    if not filled:
        return facts

    values = np.array([to_number(t, decimal, thousands) for t in filled],
                      dtype="float64")
    good = np.isfinite(values)
    facts.values = values
    facts.numeric_fraction = float(good.mean())
    numeric = facts.numeric_fraction >= NUMERIC_MIN
    if numeric:
        kept = values[good]
        facts.median = float(np.median(kept))
        facts.all_zero = bool(np.all(kept == 0.0))
        facts.integral = bool(np.all(kept == np.trunc(kept)))
        facts.non_negative = bool(np.all(kept >= 0.0))
        facts.monotone = _monotone_fraction(values)

    # A timestamp may be numeric too, so ask the datetime detector first -- but
    # hold it to a stricter standard than the loader does when it has already
    # been told which column is the date.  Left alone, an epoch test that
    # accepts "any positive number" calls every price column a timestamp.
    if _csv._looks_datelike(filled):
        kind, fmt, _ = _csv.detect_datetime_format(filled)
        if kind.startswith("epoch_"):
            plausible = (numeric and facts.integral and facts.non_negative
                         and facts.median >= EPOCH_MIN and facts.monotone >= 0.95)
            if not plausible:
                kind = "unknown"
        if kind not in ("unknown", ""):
            facts.kind = "datetime"
            facts.datetime_kind, facts.datetime_format = kind, fmt
            return facts

    if not numeric and _csv._looks_timelike(filled) \
            and _csv.detect_time_format(filled):
        facts.kind = "time"
        return facts

    facts.kind = "numeric" if numeric else "text"
    return facts


def analyse_columns(headers: Sequence[str], rows: Sequence[Sequence[str]],
                    decimal: str = ".", thousands: str = "") -> list[ColumnFacts]:
    """Describe every column of a sample, one :class:`ColumnFacts` each."""
    sample = list(rows[:MAX_ROWS])
    width = len(headers)
    for row in sample:
        width = max(width, len(row))
    out: list[ColumnFacts] = []
    for index in range(width):
        name = str(headers[index]) if index < len(headers) else ""
        texts = [str(r[index]).strip() for r in sample if index < len(r)]
        out.append(_facts_for(index, name, texts, decimal, thousands))
    return out


# ---------------------------------------------------------------------------
# the OHLC relation
# ---------------------------------------------------------------------------


def _stack(facts: Sequence[ColumnFacts], indices: Sequence[int]) -> np.ndarray | None:
    """The chosen columns as one ``(k, n)`` array, or ``None`` if unusable."""
    if not indices:
        return None
    sizes = [facts[i].values.size for i in indices]
    n = min(sizes) if sizes else 0
    if n < 2:
        return None
    return np.vstack([facts[i].values[:n] for i in indices])


def ohlc_pass_rate(open_: np.ndarray, high: np.ndarray, low: np.ndarray,
                   close: np.ndarray) -> float:
    """Fraction of bars where the four values can really be one candle.

    Rows with a missing value are left out of both halves of the fraction:
    the relation cannot be evaluated there, and counting them as failures
    would make a file with a few gaps in it look like a file whose columns are
    in the wrong order.
    """
    n = min(open_.size, high.size, low.size, close.size)
    if n == 0:
        return 0.0
    o, h, l, c = open_[:n], high[:n], low[:n], close[:n]
    finite = np.isfinite(o) & np.isfinite(h) & np.isfinite(l) & np.isfinite(c)
    testable = int(finite.sum())
    if testable < 2:
        return 0.0
    # A tolerance in the last bits of the price, so a file written to eight
    # decimal places is not failed by its own rounding.
    tol = np.maximum(np.abs(c), 1.0) * 1e-9
    body_high = np.maximum(o, c)
    body_low = np.minimum(o, c)
    good = finite & (h >= body_high - tol) & (l <= body_low + tol) & (h >= l - tol)
    return float(good.sum()) / float(testable)


def _rate_for(facts: Sequence[ColumnFacts], quad: dict[str, int]) -> float:
    order = [quad["open"], quad["high"], quad["low"], quad["close"]]
    matrix = _stack(facts, order)
    if matrix is None:
        return 0.0
    return ohlc_pass_rate(matrix[0], matrix[1], matrix[2], matrix[3])


# ---------------------------------------------------------------------------
# grouping columns that are prices of the same thing
# ---------------------------------------------------------------------------


def _same_scale(a: ColumnFacts, b: ColumnFacts) -> bool:
    n = min(a.values.size, b.values.size)
    if n == 0:
        return False
    x, y = a.values[:n], b.values[:n]
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return False
    denom = np.maximum(np.maximum(np.abs(x), np.abs(y)), 1e-12)
    return float(np.median(np.abs(x - y)[ok] / denom[ok])) <= SAME_SCALE


def price_groups(facts: Sequence[ColumnFacts]) -> list[list[int]]:
    """Numeric columns clustered into "these are prices of the same thing".

    Grouping is by *row-wise* closeness rather than by average magnitude: the
    open and the close of one bar differ by a fraction of a percent on every
    row, while a price and a volume that happen to share a magnitude do not.
    """
    usable = [f for f in facts if f.is_numeric and not f.all_zero
              and np.isfinite(f.median) and f.median != 0.0][:MAX_GROUP_COLUMNS]
    parent = {f.index: f.index for f in usable}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a_pos, a in enumerate(usable):
        for b in usable[a_pos + 1:]:
            if _same_scale(a, b):
                parent[find(b.index)] = find(a.index)

    clusters: dict[int, list[int]] = {}
    for f in usable:
        clusters.setdefault(find(f.index), []).append(f.index)
    return sorted((sorted(v) for v in clusters.values()),
                  key=lambda g: (-len(g), g[0]))


def _named(facts: Sequence[ColumnFacts], field_name: str,
           within: Sequence[int]) -> int | None:
    """The column in *within* whose header names *field_name*, if any."""
    priority = _csv._NAME_PRIORITY.get(field_name, ())
    normalised = {i: _csv._normalise(facts[i].name) for i in within}
    for candidate in priority:
        for i in within:
            if normalised[i] == candidate:
                return i
    return None


def _choose_quartet(facts: Sequence[ColumnFacts], group: Sequence[int],
                    notes: list[str]) -> list[int]:
    """Narrow a price group down to the four columns of one candle."""
    if len(group) <= 4:
        return list(group)
    by_name = [i for f in _PRICE_FIELDS
               for i in ((_named(facts, f, group),) if _named(facts, f, group)
                         is not None else ())]
    if len(set(by_name)) == 4:
        return sorted(set(by_name))
    # Vendors write the four together.  The leftmost run of four adjacent
    # columns beats an arbitrary subset of a wide bid/ask file.
    for start in range(len(group) - 3):
        window = group[start:start + 4]
        if window[-1] - window[0] == 3:
            notes.append(
                f"This file has {len(group)} price columns; the four adjacent "
                f"ones were used. Check the mapping.")
            return list(window)
    notes.append(f"This file has {len(group)} price columns; the first four "
                 f"were used. Check the mapping.")
    return list(group[:4])


def _assign_quartet(facts: Sequence[ColumnFacts], quad: Sequence[int],
                    direction: int, notes: list[str]) -> dict[str, int] | None:
    """Decide which of four price columns is open, high, low and close."""
    quad = sorted(quad)
    if len(quad) != 4:
        return None
    matrix = _stack(facts, quad)
    if matrix is None:
        return None
    with np.errstate(invalid="ignore"):
        row_high = np.nanmax(matrix, axis=0)
        row_low = np.nanmin(matrix, axis=0)
    tol = np.maximum(np.abs(row_high), 1.0) * 1e-9
    is_high = [(matrix[k] >= row_high - tol).mean() for k in range(4)]
    is_low = [(matrix[k] <= row_low + tol).mean() for k in range(4)]
    high_k, low_k = int(np.argmax(is_high)), int(np.argmax(is_low))

    if high_k == low_k or is_high[high_k] < OHLC_PASS or is_low[low_k] < OHLC_PASS:
        # Nothing is consistently the extreme of its row, so the four columns
        # are not a candle at all.  Say so rather than inventing an order.
        return None

    rest = [k for k in range(4) if k not in (high_k, low_k)]
    first, second = rest[0], rest[1]

    # Which of the two is the open?  The close of one bar and the open of the
    # next are the same trade in a continuous market, so the assignment that
    # makes consecutive bars join up is the right one.  This is what catches a
    # file written close-first, which neither the names nor the positions show.
    a, b = matrix[first], matrix[second]
    left_is_open = float(np.nanmean(np.abs(b[:-1] - a[1:])))
    left_is_close = float(np.nanmean(np.abs(a[:-1] - b[1:])))
    if direction < 0:
        # Newest first: the bar on the row below is the earlier one, so the
        # same comparison runs the other way.
        left_is_open, left_is_close = left_is_close, left_is_open
    span = float(np.nanmean(row_high - row_low))
    open_k, close_k = first, second
    # With the row order unknown the test cannot tell "close first" from
    # "newest first": both make the same two numbers join up.  Positional order
    # is the safer answer there, and it is what every vendor writes.
    if direction != 0 and np.isfinite(left_is_open) \
            and np.isfinite(left_is_close) and span > 0:
        best, other = sorted((left_is_open, left_is_close))
        decisive = best < 0.5 * span and other > 1.5 * max(best, span * 1e-6)
        if decisive and left_is_close < left_is_open:
            open_k, close_k = second, first
            notes.append(
                "The closing price is written before the opening price in this "
                "file; only that order makes consecutive bars join up.")
    return {"open": quad[open_k], "high": quad[high_k],
            "low": quad[low_k], "close": quad[close_k]}


# ---------------------------------------------------------------------------
# row order
# ---------------------------------------------------------------------------


def row_direction(facts: ColumnFacts | None) -> int:
    """``+1`` oldest first, ``-1`` newest first, ``0`` when it cannot be told."""
    if facts is None or facts.kind != "datetime" or not facts.texts:
        return 0
    if facts.datetime_kind.startswith("epoch_"):
        values = facts.values
    else:
        import pandas as pd

        series = pd.Series(facts.texts, dtype="object")
        try:
            if facts.datetime_kind == "iso":
                parsed = pd.to_datetime(series, errors="coerce", utc=True,
                                        format="ISO8601")
            else:
                parsed = pd.to_datetime(series, errors="coerce",
                                        format=facts.datetime_format)
        except Exception:                       # pragma: no cover - defensive
            return 0
        present = parsed.notna().to_numpy()
        values = np.full(len(parsed), np.nan, dtype="float64")
        if present.any():
            values[present] = parsed[present].astype("int64").to_numpy(
                dtype="float64")
    good = values[np.isfinite(values)]
    if good.size < 3:
        return 0
    steps = np.diff(good)
    moving = steps[steps != 0.0]
    if moving.size == 0:
        return 0
    up = float((moving > 0).sum()) / float(moving.size)
    if up >= 0.9:
        return 1
    if up <= 0.1:
        return -1
    return 0


# ---------------------------------------------------------------------------
# the public entry points
# ---------------------------------------------------------------------------


@dataclass
class Detection:
    """The outcome of reading a file's columns."""

    mapping: Any
    changes: list[str] = field(default_factory=list)
    """Plain sentences naming every field that was moved, and why."""
    notes: list[str] = field(default_factory=list)
    """Observations that changed nothing but the user should see."""
    ok: bool = False
    """True when the final mapping satisfies the OHLC relation."""
    pass_rate: float = 0.0
    direction: int = 0
    facts: list[ColumnFacts] = field(default_factory=list)


def _reference(facts: Sequence[ColumnFacts], index: int, has_header: bool) -> str:
    """How the loader must be told to address a column."""
    name = facts[index].name if index < len(facts) else ""
    return name if (has_header and name) else str(index)


def _label(facts: Sequence[ColumnFacts], index: int) -> str:
    name = facts[index].name if index < len(facts) else ""
    return f"'{name}'" if name else f"column {index + 1}"


def detect_mapping(headers: Sequence[str], rows: Sequence[Sequence[str]],
                   has_header: bool = True, decimal: str = ".",
                   thousands: str = "", base: Any = None) -> Detection:
    """Work the whole mapping out from the values, ignoring the header names.

    Names are used only to break ties -- to pick the volume column out of two
    equally plausible ones, or the four price columns out of a wide file.
    """
    mapping = _csv.ColumnMapping.from_dict(base.to_dict()) if base is not None \
        else _csv.ColumnMapping()
    facts = analyse_columns(headers, rows, decimal, thousands)
    result = Detection(mapping=mapping, facts=facts)

    # -- timestamp ------------------------------------------------------
    dt_index = next((f.index for f in facts if f.is_datetime), None)
    time_index = None
    if dt_index is not None:
        carries_time = (facts[dt_index].datetime_kind.startswith("epoch_")
                        or facts[dt_index].datetime_kind == "iso"
                        or any(d in (facts[dt_index].datetime_format or "")
                               for d in ("%H", "%I")))
        if not carries_time:
            following = next((f for f in facts if f.index > dt_index
                              and f.kind == "time"), None)
            if following is not None:
                time_index = following.index
    mapping.datetime = mapping.date = mapping.time = None
    if dt_index is not None:
        if time_index is not None:
            mapping.date = _reference(facts, dt_index, has_header)
            mapping.time = _reference(facts, time_index, has_header)
        else:
            mapping.datetime = _reference(facts, dt_index, has_header)
    result.direction = row_direction(facts[dt_index] if dt_index is not None else None)

    # -- prices ---------------------------------------------------------
    used = {i for i in (dt_index, time_index) if i is not None}
    groups = [g for g in price_groups(facts) if not (set(g) & used)]
    quad: dict[str, int] | None = None
    for group in groups:
        if len(group) < 4:
            continue
        chosen = _choose_quartet(facts, group, result.notes)
        quad = _assign_quartet(facts, chosen, result.direction, result.notes)
        if quad is not None:
            break
    if quad is None:
        # No candle could be proven.  Fall back to the only thing left that is
        # true of every vendor: prices are written open, high, low, close.
        free = [f.index for f in facts
                if f.is_numeric and f.index not in used and not f.all_zero]
        if len(free) >= 4:
            quad = dict(zip(_PRICE_FIELDS, free[:4]))
            result.notes.append(
                "The open, high, low and close could not be told apart from "
                "their values, so they were taken in the usual order. Check "
                "the mapping before importing.")
        elif free:
            quad = {"close": free[0]}
            result.notes.append(
                f"Only one price column was found, {_label(facts, free[0])}; it "
                f"was used as the close.")
    for field_name in _PRICE_FIELDS:
        setattr(mapping, field_name, None)
    for field_name, index in (quad or {}).items():
        setattr(mapping, field_name, _reference(facts, index, has_header))
        used.add(index)

    # -- volume ---------------------------------------------------------
    volume_index = _pick_volume(facts, used, result.notes)
    mapping.volume = (None if volume_index is None
                      else _reference(facts, volume_index, has_header))

    result.pass_rate = _rate_for(facts, quad) if quad and len(quad) == 4 else 0.0
    result.ok = bool(quad) and (len(quad) < 4 or result.pass_rate >= OHLC_PASS)
    return result


def _pick_volume(facts: Sequence[ColumnFacts], used: set[int],
                 notes: list[str], preferred: int | None = None) -> int | None:
    """The volume column: named if possible, and never an all-zero one.

    An MT5 export writes a ``Volume`` column of zeros next to the real figure
    in ``TickVolume``.  Importing the zeros is silently wrong -- every
    volume-based indicator goes flat -- so a named column that is entirely zero
    loses to a named column that is not.
    """
    free = [f for f in facts if f.is_numeric and f.index not in used
            and f.non_negative]
    if not free:
        return None
    known = _csv._NAME_PRIORITY["volume"]
    named = [f for f in free if "vol" in _csv._normalise(f.name)
             or _csv._normalise(f.name) in known]
    live_named = [f for f in named if not f.all_zero]

    if preferred is not None and any(f.index == preferred and not f.all_zero
                                     for f in free):
        return preferred
    if live_named:
        return live_named[0].index
    if preferred is not None and any(f.index == preferred for f in free):
        notes.append(f"The volume column {_label(facts, preferred)} is zero on "
                     f"every row; volume indicators will be flat.")
        return preferred
    if named:
        notes.append(f"The volume column {_label(facts, named[0].index)} is zero "
                     f"on every row; volume indicators will be flat.")
        return named[0].index
    live = [f for f in free if not f.all_zero and f.integral]
    return live[-1].index if live else None


def audit_mapping(mapping: Any, headers: Sequence[str],
                  rows: Sequence[Sequence[str]],
                  has_header: bool = True) -> Detection:
    """Check a mapping against the data and repair it if it is wrong.

    This is the conservative entry point, and the one wired into
    :func:`~.csv_loader.sniff_csv`.  A mapping that satisfies the OHLC relation
    is left exactly as it is -- header names are usually right, and second-
    guessing them would be its own bug.  Only a mapping that fails is replaced,
    and only by one that passes.

    The *mapping* is modified in place and also returned on the result.
    """
    facts = analyse_columns(headers, rows, mapping.decimal or ".",
                            mapping.thousands or "")
    names = [f.name for f in facts]
    result = Detection(mapping=mapping, facts=facts)

    def index_of(key: str | None) -> int | None:
        found = _csv._column_index(names, key)
        return found if (found is not None and 0 <= found < len(facts)) else None

    # -- is the timestamp really a timestamp? ---------------------------
    dt_key, time_key = mapping.datetime_source()
    dt_index = index_of(dt_key)
    dt_ok = dt_index is not None and facts[dt_index].kind in ("datetime", "time")
    result.direction = row_direction(
        facts[dt_index] if (dt_ok and dt_index is not None) else None)

    # -- is the candle really a candle? ---------------------------------
    current: dict[str, int | None] = {f: index_of(getattr(mapping, f))
                                      for f in _PRICE_FIELDS}
    complete = all(v is not None for v in current.values())
    close_index = current["close"]
    # "Holds prices" is a lower bar than "is a clean numeric column": a file
    # with a few blank or N/A cells is still a price file, and the loader --
    # not this audit -- is what should report the missing values.
    close_numeric = (close_index is not None
                     and facts[close_index].numeric_fraction >= 0.5)
    rate = _rate_for(facts, current) if complete else 0.0    # type: ignore[arg-type]
    result.pass_rate = rate
    price_ok = close_numeric and (rate >= OHLC_PASS if complete else True)

    reserved = {i for i in (dt_index, index_of(mapping.time)) if i is not None}

    if dt_ok and price_ok:
        result.ok = True
        _volume_audit(mapping, facts, current, reserved, has_header, result)
        _order_note(result)
        return result

    detected = detect_mapping(names, rows, has_header, mapping.decimal or ".",
                              mapping.thousands or "", base=mapping)
    fresh = detected.mapping
    result.direction = detected.direction or result.direction

    fresh_dt, _fresh_time = fresh.datetime_source()
    if not dt_ok and fresh_dt is not None:
        mapping.datetime, mapping.date, mapping.time = (
            fresh.datetime, fresh.date, fresh.time)
        target = index_of(fresh_dt)
        result.changes.append(
            f"The date column was read from the data: {_label(facts, target)} "
            f"holds the timestamps."
            if target is not None else "The date column was read from the data.")
        dt_index = target
    elif not dt_ok:
        result.notes.append(
            "No column in this file parses as a date. Choose one by hand.")

    fresh_current: dict[str, int | None] = {f: index_of(getattr(fresh, f))
                                            for f in _PRICE_FIELDS}
    fresh_complete = all(v is not None for v in fresh_current.values())
    fresh_rate = (_rate_for(facts, fresh_current)   # type: ignore[arg-type]
                  if fresh_complete else 0.0)
    # A replacement is only a repair if it is actually better.  When the data
    # yields no usable price column at all -- an unreadable number format, a
    # file that is not really a price series -- the original mapping stands and
    # the loader reports the real problem.
    if fresh.close is not None and not price_ok \
            and (fresh_rate >= OHLC_PASS or not close_numeric):
        moved = [f for f in _PRICE_FIELDS
                 if getattr(mapping, f) != getattr(fresh, f)]
        described = ", ".join(f"{f} → {_label(facts, fresh_current[f])}"
                              for f in moved if fresh_current[f] is not None)
        for field_name in _PRICE_FIELDS:
            setattr(mapping, field_name, getattr(fresh, field_name))
        if described:
            reason = ("the mapped columns did not hold prices" if not close_numeric
                      else f"the high was below the open or close on "
                           f"{(1.0 - rate) * 100:.0f}% of rows")
            result.changes.append(
                f"The price columns were matched to the data because {reason}: "
                f"{described}.")
        current, rate = fresh_current, fresh_rate
        result.pass_rate = fresh_rate
        # Only now are the detector's own observations about the price columns
        # worth repeating: they describe the mapping that was actually taken.
        result.notes.extend(detected.notes)
    elif not price_ok and complete:
        result.notes.append(
            f"The high is below the open or close on {(1.0 - rate) * 100:.0f}% of "
            f"the sampled rows, and no better arrangement of the columns was "
            f"found. Check the mapping before importing.")

    reserved = {i for i in (dt_index, index_of(mapping.time)) if i is not None}
    _volume_audit(mapping, facts, current, reserved, has_header, result)
    _order_note(result)
    result.ok = (all(v is not None for v in current.values())
                 and rate >= OHLC_PASS and dt_index is not None)
    return result


def _volume_audit(mapping: Any, facts: Sequence[ColumnFacts],
                  current: dict[str, int | None], reserved: set[int],
                  has_header: bool, result: Detection) -> None:
    """Move the volume off an all-zero column when a real one exists."""
    names = [f.name for f in facts]
    used = {i for i in current.values() if i is not None} | set(reserved)
    mapped = _csv._column_index(names, mapping.volume)
    if mapped is not None and not (0 <= mapped < len(facts)):
        mapped = None
    if mapped is not None:
        used.discard(mapped)
    chosen = _pick_volume(facts, used, result.notes, preferred=mapped)
    if chosen is None:
        if mapping.volume is not None and mapped is None:
            result.changes.append(
                "The volume column was cleared: it does not exist in this file.")
            mapping.volume = None
        return
    if mapped is not None and chosen != mapped:
        result.changes.append(
            f"Volume was moved from {_label(facts, mapped)}, which is zero on "
            f"every row, to {_label(facts, chosen)}.")
    elif mapped is None:
        result.changes.append(
            f"Volume was read from the data: {_label(facts, chosen)}.")
    mapping.volume = _reference(facts, chosen, has_header)


def _order_note(result: Detection) -> None:
    if result.direction < 0:
        result.notes.append(
            "The rows in this file are newest first; they will be sorted oldest "
            "first on import.")
