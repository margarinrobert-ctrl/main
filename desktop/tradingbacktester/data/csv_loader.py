"""Reading OHLCV bars out of a CSV file.

This is the module a user meets first and the one most likely to be handed a
file nobody anticipated, so it is deliberately forgiving about *shape* and
deliberately strict about *values*.  It will work out the encoding, the
delimiter, whether there is a header row, which column is which and how the
timestamps are written; but once it has decided, a price it cannot parse is an
error that names the line rather than a silently dropped bar.

The two halves of the job are separate on purpose:

``sniff_csv`` looks at the start and the end of the file and *guesses*.  It
never raises -- an unreadable file comes back as a profile with a populated
``problems`` list -- because the import dialog needs something to show even for
a file that cannot be loaded.

``load_csv`` takes the (possibly user-corrected) :class:`ColumnMapping` and
does the real work, raising :class:`CsvImportError` with a plain-language
message whenever it cannot continue.

Timestamps come out as int64 UTC nanoseconds marking each bar's OPEN.  Input
that carries a UTC offset is converted; input without one is interpreted in
``mapping.timezone`` and then converted.  Daylight-saving transitions are
resolved rather than raised on, and are reported as warnings on the returned
``BarSeries.meta``.
"""

from __future__ import annotations

import codecs
import csv
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd

from ..core.errors import CsvImportError
from ..core.timeframe import Timeframe, TimeframeUnit, infer_timeframe
from .models import BarSeries, Instrument

log = logging.getLogger(__name__)

#: ``progress(rows_done, rows_total)``.  Called about 100 times for one pass
#: over the file, and starts again from zero on the rare file that needs a
#: second, more tolerant pass.
ProgressFn = Callable[[int, int], None]

#: Delimiters worth guessing between.  Space-separated files are not supported
#: because a space is also a legitimate part of a datetime.
DELIMITERS: tuple[str, ...] = (",", ";", "\t", "|")

_PROBE_BYTES = 262_144
_MAX_SAMPLE_ROWS = 5000
_MAX_FORMAT_SAMPLES = 250
_PROGRESS_STEPS = 100
#: A datetime shape fitting this share of the samples is accepted straight away.
_FORMAT_MATCH_STRONG = 0.9
#: Below this share nothing is accepted, however much better it is than the rest.
_FORMAT_MATCH_MIN = 0.5
_MIN_CHUNK_ROWS = 50_000

_FIELDS = ("datetime", "date", "time", "open", "high", "low", "close", "volume")
_PRICE_FIELDS = ("open", "high", "low", "close")

_DIGITS_RE = re.compile(r"^\d+$")
_NUMBER_RE = re.compile(r"^\d+(\.\d+)?$")
_ISO_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}([T ]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|z|[+-]\d{2}:?\d{2})?$"
)
_OFFSET_RE = re.compile(r"(Z|z|[+-]\d{2}:?\d{2})$")
_DMY_RE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")
_NUMERICISH_RE = re.compile(r"^[\s$€£¥₹+\-(]*\d[\d\s.,'’]*\)?\s*$")


def _normalise(name: object) -> str:
    """Reduce a header name to lowercase alphanumerics so matching is forgiving."""
    text = str(name).strip().lstrip("\ufeff").lower()
    return re.sub(r"[^a-z0-9]", "", text)


# Candidate header names per field, in *preference* order: "close" must beat
# "adj close", and "volume" must beat "volume from".
_NAME_PRIORITY: dict[str, tuple[str, ...]] = {
    "datetime": (
        "datetime", "dateandtime", "datetimeutc", "timestamp", "timestamputc",
        "timestampms", "unixtimestamp", "unixtime", "unix", "epochtime", "epoch",
        "opentime", "opentimestamp", "bartime", "barstart", "starttime",
        "gmttime", "localtime", "utc", "dt", "ts",
    ),
    # The tail of each list is the same word in the languages a European data
    # vendor is most likely to export in.  They are last so an English name
    # always wins, and they cost nothing when they do not appear.
    "date": ("date", "tradedate", "tradingday", "businessdate", "day", "dates",
             "datum", "fecha", "dato", "data"),
    "time": ("time", "timeofday", "bartime", "times", "hourminute",
             "zeit", "uhrzeit", "hora", "ora", "tijd"),
    "open": ("open", "openprice", "opn", "o", "first", "openingprice"),
    "high": ("high", "highprice", "hi", "h", "max", "maxprice"),
    "low": ("low", "lowprice", "lo", "l", "min", "minprice"),
    "close": (
        "close", "closeprice", "closingprice", "last", "lastprice", "settle",
        "settlement", "c", "price", "adjclose", "adjustedclose",
    ),
    "volume": (
        "volume", "vol", "totalvolume", "tickvolume", "realvolume", "tickvol",
        "quantity", "qty", "contracts", "shares", "size", "v", "volumefrom",
        "basevolume", "tradedvolume", "volumen", "umsatz",
    ),
}

#: Every name that proves a row is a header rather than data.
_ALL_KNOWN_NAMES: frozenset[str] = frozenset(
    n for names in _NAME_PRIORITY.values() for n in names
)

# Datetime formats tried in order.  ISO 8601 is handled separately by pandas'
# dedicated parser, so this list is only the non-ISO shapes.
_DATE_ONLY_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d",
    "%d-%b-%Y", "%d %b %Y", "%b %d %Y", "%d-%B-%Y", "%B %d %Y", "%d %B %Y",
)


def _ambiguous_date_formats(day_first: bool) -> tuple[str, ...]:
    """``nn?nn?yyyy`` candidates, best guess first.

    Order only decides files where nothing proves which number is the day, so
    the tie-break follows the convention of the separator: a dot or a dash
    between numbers is European and means day first, while a slash follows
    whatever the file or the user said.  Anything that spans more than twelve
    days proves itself later, in :func:`_verify_day_order`.
    """
    out: list[str] = []
    for sep in ("/", ".", "-"):
        prefer_day = day_first or sep in (".", "-")
        for year in ("%Y", "%y"):
            dmy = f"%d{sep}%m{sep}{year}"
            mdy = f"%m{sep}%d{sep}{year}"
            out.extend((dmy, mdy) if prefer_day else (mdy, dmy))
    return tuple(out)

_TIME_SUFFIXES: tuple[str, ...] = (
    " %H:%M:%S.%f", " %H:%M:%S", " %H:%M", " %H%M%S", " %H%M",
    " %I:%M:%S %p", " %I:%M %p", "T%H:%M:%S", "",
)


@dataclass
class ColumnMapping:
    """Which column of a CSV holds which field, and how to read its values.

    ``datetime`` and (``date`` + ``time``) are alternatives: set one or the
    other.  Column references may be a header name or a 0-based column index
    written as a string, which is what a headerless file gets.

    The parsing knobs (``delimiter``, ``has_header``, ``encoding``,
    ``comment_char``, ``skip_rows``) are optional.  Leaving them ``None`` makes
    :func:`load_csv` sniff the file for them, so a mapping built by hand from
    header names alone is enough to load a file.
    """

    datetime: str | None = None
    date: str | None = None
    time: str | None = None
    open: str | None = None
    high: str | None = None
    low: str | None = None
    close: str | None = None
    volume: str | None = None

    datetime_format: str | None = None
    """``strftime`` pattern, ``"ISO8601"``, or one of ``epoch_s|epoch_ms|epoch_us|epoch_ns``."""
    time_format: str | None = None
    """Format of a separate time column; inferred when ``None``."""
    timezone: str = "UTC"
    """Timezone that *naive* timestamps in the file are expressed in."""
    decimal: str = "."
    thousands: str = ""
    dayfirst: bool = False

    delimiter: str | None = None
    has_header: bool | None = None
    encoding: str | None = None
    comment_char: str | None = None
    skip_rows: int = 0

    def datetime_source(self) -> tuple[str | None, str | None]:
        """Return ``(datetime_column, time_column)`` after resolving the aliases.

        A file with only a ``date`` column that actually contains a full
        timestamp is very common, so ``date`` alone is promoted to the datetime
        column rather than being rejected.
        """
        if self.datetime:
            return self.datetime, (self.time if self.date is None else None)
        if self.date and self.time:
            return self.date, self.time
        if self.date:
            return self.date, None
        if self.time:
            return self.time, None
        return None, None

    def to_dict(self) -> dict[str, Any]:
        """Plain dictionary for saving alongside an imported dataset."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColumnMapping":
        """Rebuild a mapping, ignoring keys from a newer or older version."""
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in dict(data).items() if k in known})


@dataclass
class CsvProfile:
    """Everything :func:`sniff_csv` could work out about a file.

    ``problems`` is the honest part: anything the sniffer had to guess, could
    not determine, or actively disliked ends up there as one plain sentence the
    import dialog can show verbatim.
    """

    path: str
    encoding: str = "utf-8"
    delimiter: str = ","
    has_header: bool = True
    comment_char: str | None = None
    skip_rows: int = 0
    headers: list[str] = field(default_factory=list)
    column_count: int = 0
    sample_rows: list[list[str]] = field(default_factory=list)
    file_size: int = 0
    row_estimate: int = 0
    mapping: ColumnMapping = field(default_factory=ColumnMapping)
    datetime_format: str | None = None
    datetime_kind: str = "unknown"
    """One of ``iso``, ``format``, ``epoch_s|ms|us|ns``, ``date_time`` or ``unknown``."""
    dayfirst: bool = False
    dayfirst_proven: bool = False
    decimal: str = "."
    thousands: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def is_usable(self) -> bool:
        """True when this file could be imported exactly as the profile describes.

        Requires a timestamp column whose format was actually recognised and a
        closing price; a mapping that merely points at columns is not enough,
        because pointing at the wrong ones is the usual failure.
        """
        dt_col, _ = self.mapping.datetime_source()
        return (dt_col is not None and self.mapping.close is not None
                and self.datetime_kind not in ("unknown", ""))

    def describe(self) -> str:
        """One short paragraph for the import dialog."""
        delim = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}.get(
            self.delimiter, repr(self.delimiter))
        head = "with a header row" if self.has_header else "with no header row"
        return (f"{delim}-separated, {head}, {self.column_count} columns, "
                f"about {self.row_estimate:,} rows, {self.encoding} encoding")

    def to_dict(self) -> dict[str, Any]:
        """Plain dictionary for the import dialog and the log."""
        d = asdict(self)
        d["mapping"] = self.mapping.to_dict()
        d["is_usable"] = self.is_usable
        return d


# ---------------------------------------------------------------------------
# probing the raw bytes
# ---------------------------------------------------------------------------


def _decode(raw: bytes, partial_tail: bool = False) -> tuple[str, str]:
    """Decode a chunk of a text file, returning ``(text, encoding_name)``.

    UTF-8 with or without a BOM covers almost everything; latin-1 is the
    fallback because it can decode any byte sequence, which means a file with
    one stray byte still imports instead of failing at byte 4,000,000.
    """
    if raw.startswith(codecs.BOM_UTF8):
        return raw[len(codecs.BOM_UTF8):].decode("utf-8", errors="replace"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        if partial_tail:
            # A tail chunk usually starts mid-character; that alone must not
            # push the whole file onto latin-1.
            try:
                return raw.decode("utf-8", errors="replace"), "utf-8"
            except Exception:  # pragma: no cover - decode with replace cannot fail
                pass
        return raw.decode("latin-1"), "latin-1"


def _probe(path: Path) -> tuple[str, str, str]:
    """Read the head and the tail of a file.  Returns ``(head, tail, encoding)``.

    The tail matters for date-order detection: the first 256 KB of a 1-minute
    file may cover only three days, which is not enough to prove whether
    ``05/01`` means the fifth of January or the first of May.  The last 256 KB
    almost always contains a day number above twelve.
    """
    size = path.stat().st_size
    with path.open("rb") as fh:
        head_raw = fh.read(_PROBE_BYTES)
        tail_raw = b""
        if size > _PROBE_BYTES + 4096:
            fh.seek(size - _PROBE_BYTES)
            tail_raw = fh.read(_PROBE_BYTES)
    head, encoding = _decode(head_raw)
    tail = ""
    if tail_raw:
        tail, _ = _decode(tail_raw, partial_tail=True)
        # The first line of the tail is almost certainly cut in half.
        nl = tail.find("\n")
        tail = tail[nl + 1:] if nl >= 0 else ""
    return head, tail, encoding


def _text_lines(text: str) -> list[str]:
    """Split into lines, dropping the final partial line and any blank ones."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and not text.endswith("\n"):
        lines = lines[:-1]
    return lines


def _strip_noise(lines: Sequence[str], comment_char: str | None) -> list[str]:
    """Drop blank and comment lines, the way pandas will when it reads the file."""
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if comment_char and stripped.startswith(comment_char):
            continue
        out.append(line)
    return out


def _detect_comment_char(lines: Sequence[str]) -> str | None:
    """``#`` is treated as a comment marker only when a line actually starts with it.

    pandas' ``comment`` option truncates a line at the character wherever it
    appears, so enabling it unconditionally would corrupt any file with a ``#``
    inside a field.
    """
    for line in lines[:50]:
        if line.lstrip().startswith("#"):
            return "#"
    return None


def _parse_rows(lines: Sequence[str], delimiter: str) -> list[list[str]]:
    """Parse sample lines with the csv module so quoted fields survive."""
    try:
        return [row for row in csv.reader(list(lines), delimiter=delimiter) if row]
    except csv.Error:
        return [line.split(delimiter) for line in lines]


def _modal(values: Iterable[int]) -> int:
    """The most common value, ties broken by the larger one."""
    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        return 0
    return max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _sniff_delimiter(lines: Sequence[str]) -> str:
    """Pick the delimiter that splits the sample into the most consistent grid.

    Scored on consistency first and field count second, so a file whose fields
    happen to contain semicolons still comes out comma-separated.
    """
    best: tuple[float, float, int, str] | None = None
    sample = list(lines[:30])
    for delim in DELIMITERS:
        rows = _parse_rows(sample, delim)
        counts = [len(r) for r in rows]
        if not counts:
            continue
        modal = _modal(counts)
        if modal < 2:
            continue
        consistency = sum(1 for c in counts if c == modal) / len(counts)
        score = (1.0 if consistency >= 0.9 else 0.0, consistency, modal, delim)
        if best is None or score > best:
            best = score
    # A single-column file, or something that is not a table at all, keeps the
    # comma: one column is one column whatever the separator is said to be.
    return "," if best is None else best[3]


def _looks_numeric(token: str) -> bool:
    """True for anything a person would read as a number, symbols and all."""
    text = token.strip().strip('"').strip()
    if not text:
        return False
    return bool(_NUMERICISH_RE.match(text))


def _detect_header(rows: Sequence[Sequence[str]]) -> bool:
    """True when the first row names columns rather than holding data."""
    if not rows:
        return False
    first = [str(c) for c in rows[0]]
    if any(_normalise(c) in _ALL_KNOWN_NAMES for c in first):
        return True
    if len(rows) > 1:
        numeric_first = sum(_looks_numeric(c) for c in first)
        numeric_next = sum(_looks_numeric(c) for c in rows[1])
        if numeric_first == 0 and numeric_next > 0:
            return True
    return False


def _detect_preamble(rows: Sequence[Sequence[str]]) -> int:
    """Number of leading rows that are not part of the table.

    Only a *narrow* leading row -- a title line with no delimiters at all -- is
    treated as preamble, because guessing more aggressively than that has a
    real chance of eating the header.
    """
    if len(rows) < 3:
        return 0
    modal = _modal(len(r) for r in rows)
    if modal < 3:
        return 0
    skip = 0
    for row in rows:
        # Only a row with no delimiters at all counts as preamble.  Anything
        # wider than that could be the header, and eating the header is worse
        # than leaving a junk line for the date parser to reject.
        if len(row) > 1:
            break
        skip += 1
    return skip if skip < len(rows) - 1 else 0


# ---------------------------------------------------------------------------
# datetime shape detection
# ---------------------------------------------------------------------------


def _clean_samples(values: Iterable[Any], limit: int = _MAX_FORMAT_SAMPLES) -> list[str]:
    """Up to ``limit`` usable sample strings, spread across the whole input.

    Spreading rather than taking the first N matters: the first few hundred
    rows of a 1-minute file cover a single day, which can never prove whether
    ``05/01`` is the fifth of January or the first of May.
    """
    seq = list(values)
    if len(seq) > limit:
        seq = seq[:: max(1, len(seq) // limit)]
    out: list[str] = []
    for v in seq:
        if v is None:
            continue
        text = str(v).strip().strip('"').strip()
        if text and text.lower() not in ("nan", "nat", "null", "none", "-"):
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _day_month_proof(samples: Sequence[str]) -> tuple[bool, bool]:
    """``(day_first_proved, month_first_proved)`` for ``nn/nn/yyyy`` style dates.

    Proof is a number above twelve in a position where only a day can live.  A
    file that proves both is internally inconsistent, which is worth its own
    error message rather than a shrug.
    """
    day_first = month_first = False
    for text in samples:
        m = _DMY_RE.match(text)
        if not m:
            continue
        first, second = int(m.group(1)), int(m.group(2))
        if first > 12 and second <= 12:
            day_first = True
        elif second > 12 and first <= 12:
            month_first = True
    return day_first, month_first


def _dayfirst_evidence(samples: Sequence[str]) -> bool | None:
    """``True`` if the data proves day-first, ``False`` if month-first, else ``None``."""
    day_first, month_first = _day_month_proof(samples)
    if day_first and not month_first:
        return True
    if month_first and not day_first:
        return False
    return None


def _format_match_fraction(samples: Sequence[str], fmt: str) -> float:
    """Share of samples that parse under ``fmt``."""
    if not samples:
        return 0.0
    try:
        parsed = pd.to_datetime(pd.Series(samples, dtype="object"),
                                format=fmt, errors="coerce")
    except (ValueError, TypeError, OverflowError, pd.errors.OutOfBoundsDatetime):
        return 0.0
    return float(parsed.notna().mean())


def _matching(samples: Sequence[str], pattern: re.Pattern[str]) -> list[str]:
    """The samples that match a pattern, for share-of-column tests."""
    return [v for v in samples if pattern.match(v)]


def _epoch_kind(samples: Sequence[str]) -> str | None:
    """Classify a numeric column as an epoch, by magnitude.

    Vendor stamps such as ``20230102`` and ``20230102093000`` are digits too and
    are checked *before* this function is reached, because ``20230102093000``
    would otherwise look like plausible epoch milliseconds.
    """
    try:
        values = [float(s) for s in samples]
    except ValueError:
        return None
    if not values:
        return None
    mid = float(np.median(np.asarray(values, dtype="float64")))
    if mid <= 0:
        return None
    if mid < 1e11:
        return "epoch_s"
    if mid < 1e14:
        return "epoch_ms"
    if mid < 1e17:
        return "epoch_us"
    if mid < 1e20:
        return "epoch_ns"
    return None


def _digit_shape(values: Sequence[str]) -> tuple[str, str | None] | None:
    """Classify a numeric datetime column: vendor stamp first, then epoch."""
    if not values:
        return None
    whole = _matching(values, _DIGITS_RE)
    if len(whole) == len(values):
        widths = {len(v) for v in whole}
        century = all(v[:2] in ("19", "20") for v in whole)
        if century and widths <= {8}:
            return "format", "%Y%m%d"
        if century and widths <= {12}:
            return "format", "%Y%m%d%H%M"
        if century and widths <= {14}:
            return "format", "%Y%m%d%H%M%S"
    kind = _epoch_kind(values)
    return (kind, None) if kind else None


def detect_datetime_format(samples: Sequence[str],
                           dayfirst: bool = False) -> tuple[str, str | None, bool | None]:
    """Work out how a datetime column is written.

    Returns ``(kind, format, dayfirst_evidence)`` where *kind* is one of
    ``iso``, ``format``, ``epoch_s``, ``epoch_ms``, ``epoch_us``, ``epoch_ns``
    or ``unknown``, and *format* is a ``strftime`` pattern for kind ``format``.

    A shape that fits nearly every sample is taken immediately.  Otherwise every
    candidate is scored and the best one wins, provided it fits at least half
    the samples: files with a repeated header part-way through, or a "Total"
    line at the end, are common enough that demanding unanimity would reject
    them outright.  Scoring also settles ``05/01`` versus ``01/05`` on its own,
    because the right way round parses strictly more rows than the wrong one.
    """
    vals = _clean_samples(samples)
    if not vals:
        return "unknown", None, None

    evidence = _dayfirst_evidence(vals)
    strong = _FORMAT_MATCH_STRONG * len(vals)

    digits = _matching(vals, _NUMBER_RE)
    if len(digits) >= strong:
        shape = _digit_shape(digits)
        return (shape[0], shape[1], None) if shape else ("unknown", None, None)
    if len(_matching(vals, _ISO_RE)) >= strong:
        return "iso", None, evidence

    order = _ambiguous_date_formats(
        evidence if evidence is not None else bool(dayfirst))
    best_format: str | None = None
    best_score = 0.0
    for date_fmt in _DATE_ONLY_FORMATS + order:
        for suffix in _TIME_SUFFIXES:
            candidate = date_fmt + suffix
            score = _format_match_fraction(vals, candidate)
            if score > best_score + 1e-9:
                best_format, best_score = candidate, score
            if best_score >= 0.999:
                break
        if best_score >= 0.999:
            break

    iso_score = float(len(_matching(vals, _ISO_RE))) / len(vals)
    if iso_score > best_score:
        best_format, best_score = "ISO8601", iso_score
    digit_score = float(len(digits)) / len(vals)
    if digit_score > best_score and digit_score >= _FORMAT_MATCH_MIN:
        shape = _digit_shape(digits)
        if shape:
            return shape[0], shape[1], None
    if best_format == "ISO8601" and best_score >= _FORMAT_MATCH_MIN:
        return "iso", None, evidence
    if best_format and best_score >= _FORMAT_MATCH_MIN:
        return "format", best_format, evidence
    return "unknown", None, evidence


def detect_time_format(samples: Sequence[str]) -> str | None:
    """Work out how a separate time-of-day column is written."""
    vals = _clean_samples(samples)
    if not vals:
        return None
    need = _FORMAT_MATCH_MIN * len(vals)
    # Same majority rule as the date formats above, for the same reason.
    patterns = (
        (r"^\d{1,2}:\d{2}:\d{2}\.\d+$", "%H:%M:%S.%f"),
        (r"^\d{1,2}:\d{2}:\d{2}$", "%H:%M:%S"),
        (r"^\d{1,2}:\d{2}$", "%H:%M"),
        (r"(?i)^\d{1,2}:\d{2}:\d{2}\s*[ap]\.?m\.?$", "%I:%M:%S %p"),
        (r"(?i)^\d{1,2}:\d{2}\s*[ap]\.?m\.?$", "%I:%M %p"),
    )
    for pattern, fmt in patterns:
        if len(_matching(vals, re.compile(pattern))) >= need:
            return fmt
    digits = _matching(vals, _DIGITS_RE)
    if len(digits) >= need:
        return "%H%M%S" if max(len(v) for v in digits) > 4 else "%H%M"
    return None


def _detect_number_format(samples: Sequence[str]) -> tuple[str, str]:
    """Guess ``(decimal, thousands)`` from sample price text."""
    vals = _clean_samples(samples, limit=200)
    euro = sum(1 for v in vals if re.match(r"^-?\d{1,3}(\.\d{3})+(,\d+)?$", v))
    euro += sum(1 for v in vals if re.match(r"^-?\d+,\d+$", v) and "." not in v)
    anglo = sum(1 for v in vals if re.match(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$", v))
    if euro > anglo and euro > 0:
        has_dot_groups = any(re.match(r"^-?\d{1,3}(\.\d{3})+", v) for v in vals)
        return ",", ("." if has_dot_groups else "")
    if anglo > 0:
        return ".", ","
    return ".", ""


# ---------------------------------------------------------------------------
# column mapping
# ---------------------------------------------------------------------------


def guess_mapping(headers: Sequence[str]) -> ColumnMapping:
    """Map header names onto fields, by preference order rather than by guesswork.

    Matching is on lowercase alphanumerics, so ``"Open Price"``, ``"open_price"``
    and ``"OPENPRICE"`` are the same name.  Preference order is what stops
    ``"Adj Close"`` from being chosen over ``"Close"``.
    """
    names = [str(h) for h in headers]
    norm = [_normalise(h) for h in names]
    used: set[int] = set()

    def pick(field_name: str) -> str | None:
        for candidate in _NAME_PRIORITY[field_name]:
            for i, n in enumerate(norm):
                if n == candidate and i not in used:
                    used.add(i)
                    return names[i]
        return None

    mapping = ColumnMapping()
    dt = pick("datetime")
    date_col = pick("date")
    time_col = pick("time")
    if dt is not None:
        mapping.datetime = dt
    elif date_col is not None and time_col is not None:
        mapping.date, mapping.time = date_col, time_col
    elif date_col is not None:
        mapping.datetime = date_col
    elif time_col is not None:
        mapping.datetime = time_col

    for f in ("open", "high", "low", "close", "volume"):
        setattr(mapping, f, pick(f))
    return mapping


def _positional_mapping(rows: Sequence[Sequence[str]], column_count: int) -> ColumnMapping:
    """Map a headerless file by position, using the conventional OHLCV order."""
    mapping = ColumnMapping()
    if column_count <= 0:
        return mapping
    sample = rows[0] if rows else []

    def cell(i: int) -> str:
        return str(sample[i]).strip() if i < len(sample) else ""

    time_like = bool(re.match(r"^\d{1,2}:\d{2}", cell(1))) or (
        bool(_DIGITS_RE.match(cell(1))) and len(cell(1)) in (4, 6)
        and not _looks_like_date(cell(1))
    )
    if column_count >= 6 and time_like:
        mapping.date, mapping.time = "0", "1"
        start = 2
    else:
        mapping.datetime = "0"
        start = 1
    remaining = column_count - start
    order = ["open", "high", "low", "close", "volume"]
    if remaining == 1:
        mapping.close = str(start)
        return mapping
    for offset, name in enumerate(order):
        idx = start + offset
        if idx >= column_count:
            break
        setattr(mapping, name, str(idx))
    return mapping


def _looks_like_date(text: str) -> bool:
    """True for a bare ``20230102`` vendor date, which a time column never is."""
    return bool(_DIGITS_RE.match(text)) and len(text) == 8 and text[:2] in ("19", "20")


_DATE_CHARS_RE = re.compile(r"^[A-Za-z\d\s:/.\-+,]+$")
_TIME_LIKE_RE = re.compile(r"^\d{1,2}:\d{2}")
_CONTENT_SCAN_COLUMNS = 10
_CONTENT_SCAN_SAMPLES = 40


def _looks_datelike(samples: Sequence[str]) -> bool:
    """Cheap filter before the expensive format scan.

    A price column must be rejected in microseconds, not by trying a hundred
    datetime formats against it, so anything that is not either a long number or
    a string of date punctuation is discarded first.
    """
    if not samples:
        return False
    hits = 0
    for text in samples:
        if not _DATE_CHARS_RE.match(text):
            continue
        if _DIGITS_RE.match(text):
            if len(text) < 8:
                continue
        elif not any(ch in text for ch in "-/.:T"):
            continue
        hits += 1
    return hits >= _FORMAT_MATCH_STRONG * len(samples)


def _looks_timelike(samples: Sequence[str]) -> bool:
    """True for a column of times of day, ``09:30`` or ``093000`` style."""
    if not samples:
        return False
    hits = 0
    for text in samples:
        if _TIME_LIKE_RE.match(text):
            hits += 1
        elif _DIGITS_RE.match(text) and len(text) in (4, 6) and int(text) <= 235959:
            hits += 1
    return hits >= _FORMAT_MATCH_STRONG * len(samples)


def _fill_missing_by_position(mapping: ColumnMapping, headers: Sequence[str],
                              rows: Sequence[Sequence[str]],
                              has_header: bool) -> list[str]:
    """Fill unmapped price fields from the leftover columns, in OHLCV order.

    Exports in other languages routinely name the timestamp column something
    recognisable and the price columns something that is not.  Every vendor on
    earth still writes the prices in open, high, low, close, volume order, so
    the leftover numeric columns can be assigned in that order.  Returns the
    field names that were filled, for the profile's problem list.
    """
    if mapping.close is not None:
        return []

    def key(i: int) -> str:
        return headers[i] if has_header else str(i)

    used: set[int] = set()
    rightmost_time = -1
    for field_name in _FIELDS:
        idx = _column_index([str(h) for h in headers], getattr(mapping, field_name))
        if idx is None:
            continue
        used.add(idx)
        if field_name in ("datetime", "date", "time"):
            rightmost_time = max(rightmost_time, idx)

    free: list[int] = []
    for i in range(len(headers)):
        if i in used or i <= rightmost_time:
            continue
        samples = _column_samples(rows, i)[:_CONTENT_SCAN_SAMPLES]
        if samples and all(_looks_numeric(v) for v in samples):
            free.append(i)

    filled: list[str] = []
    for field_name in ("open", "high", "low", "close", "volume"):
        if getattr(mapping, field_name) is not None:
            continue
        if not free:
            break
        setattr(mapping, field_name, key(free.pop(0)))
        filled.append(field_name)
    if mapping.close is None:
        # Nothing usable was found; undo so the caller reports the real problem
        # rather than a half-invented mapping.
        for field_name in filled:
            setattr(mapping, field_name, None)
        return []
    return filled


def _find_datetime_by_content(headers: Sequence[str], rows: Sequence[Sequence[str]],
                              has_header: bool) -> tuple[str | None, str | None]:
    """Look for a datetime column by reading values, when no header name matched.

    This is what rescues a file whose columns are named in another language.
    Only the leftmost few columns are examined: a timestamp is never the
    fortieth field, and scanning every column of a wide file would cost more
    than the import.
    """
    def key(i: int) -> str:
        return headers[i] if has_header else str(i)

    limit = min(len(headers), _CONTENT_SCAN_COLUMNS)
    for i in range(limit):
        samples = _column_samples(rows, i)[:_CONTENT_SCAN_SAMPLES]
        if not _looks_datelike(samples):
            continue
        kind, fmt, _ = detect_datetime_format(samples)
        if kind == "unknown":
            continue
        time_key: str | None = None
        carries_time = kind.startswith("epoch_") or any(
            d in (fmt or "") for d in ("%H", "%I")) or kind == "iso"
        if not carries_time and i + 1 < len(headers):
            following = _column_samples(rows, i + 1)[:_CONTENT_SCAN_SAMPLES]
            if _looks_timelike(following) and detect_time_format(following):
                time_key = key(i + 1)
        return key(i), time_key
    return None, None


def _column_index(headers: Sequence[str], key: str | None) -> int | None:
    """Index of a mapping reference within a header list, or ``None``."""
    if key is None or str(key) == "":
        return None
    text = str(key)
    if text in headers:
        return headers.index(text)
    norm = _normalise(text)
    for i, h in enumerate(headers):
        if _normalise(h) == norm:
            return i
    try:
        idx = int(text)
    except ValueError:
        return None
    return idx if 0 <= idx < len(headers) else None


def _column_samples(rows: Sequence[Sequence[str]], index: int | None) -> list[str]:
    """Every sample value of one column of the parsed sample rows."""
    if index is None:
        return []
    return [str(r[index]) for r in rows if index < len(r)]


# ---------------------------------------------------------------------------
# sniffing
# ---------------------------------------------------------------------------


def sniff_csv(path: str | Path) -> CsvProfile:
    """Inspect a CSV and guess how to read it.  Never raises.

    Anything that could not be determined -- or that was determined but is worth
    a second look, such as an ambiguous ``05/01/2023`` -- is appended to
    ``profile.problems`` in plain language.
    """
    profile = CsvProfile(path=str(path))
    try:
        p = Path(path)
        if not p.exists():
            profile.problems.append("This file does not exist.")
            return profile
        if p.is_dir():
            profile.problems.append("This is a folder, not a CSV file.")
            return profile
        profile.file_size = p.stat().st_size
        if profile.file_size == 0:
            profile.problems.append("This file is empty.")
            return profile

        head, tail, encoding = _probe(p)
        profile.encoding = encoding
        if encoding == "latin-1":
            profile.problems.append(
                "This file is not valid UTF-8; it was read as Latin-1, so unusual "
                "characters in text columns may look wrong."
            )

        raw_lines = _text_lines(head)
        if not raw_lines:
            profile.problems.append("This file has no complete lines of text.")
            return profile

        profile.comment_char = _detect_comment_char(raw_lines)
        lines = _strip_noise(raw_lines, profile.comment_char)
        if not lines:
            profile.problems.append("Every line in this file is blank or a comment.")
            return profile

        delimiter = _sniff_delimiter(lines)
        profile.delimiter = delimiter
        rows = _parse_rows(lines[:_MAX_SAMPLE_ROWS], delimiter)
        if not rows:
            profile.problems.append("This file could not be split into columns.")
            return profile

        skip = _detect_preamble(rows)
        if skip:
            # skip_rows counts physical lines, which is what pandas skips.
            physical = 0
            wanted = skip
            for line in raw_lines:
                physical += 1
                if line.strip() and not (profile.comment_char
                                         and line.strip().startswith(profile.comment_char)):
                    wanted -= 1
                    if wanted == 0:
                        break
            profile.skip_rows = physical
            rows = rows[skip:]
            profile.problems.append(
                f"The first {skip} line(s) do not look like part of the table and "
                f"will be skipped."
            )

        profile.has_header = _detect_header(rows)
        if profile.has_header:
            profile.headers = [str(c).strip().lstrip("\ufeff") for c in rows[0]]
            data_rows = rows[1:]
        else:
            width = _modal(len(r) for r in rows)
            profile.headers = [f"Column {i + 1}" for i in range(width)]
            data_rows = rows
            profile.problems.append(
                "No header row was found, so columns were matched by position "
                "(datetime, open, high, low, close, volume)."
            )
        profile.column_count = len(profile.headers)
        profile.sample_rows = [[str(c) for c in r] for r in data_rows[:20]]

        tail_rows: list[list[str]] = []
        if tail:
            tail_lines = _strip_noise(_text_lines(tail), profile.comment_char)
            tail_rows = [r for r in _parse_rows(tail_lines[-_MAX_SAMPLE_ROWS:], delimiter)
                         if len(r) == profile.column_count]

        mapping = (guess_mapping(profile.headers) if profile.has_header
                   else _positional_mapping(data_rows, profile.column_count))
        if not any(mapping.datetime_source()):
            found, found_time = _find_datetime_by_content(
                profile.headers, data_rows, profile.has_header)
            if found is not None:
                mapping.datetime, mapping.time = found, found_time
                profile.problems.append(
                    f"The column '{found}' was used for the date because its "
                    f"values look like dates; no column name matched.")
        if profile.has_header:
            filled = _fill_missing_by_position(mapping, profile.headers, data_rows,
                                               True)
            if filled:
                profile.problems.append(
                    "These columns were matched by position because their names "
                    "were not recognised: " + ", ".join(filled) +
                    ". Check the mapping before importing.")
        mapping.delimiter = delimiter
        mapping.has_header = profile.has_header
        mapping.encoding = encoding
        mapping.comment_char = profile.comment_char
        mapping.skip_rows = profile.skip_rows

        dt_key, time_key = mapping.datetime_source()
        dt_index = _column_index(profile.headers, dt_key)
        time_index = _column_index(profile.headers, time_key)
        samples = _column_samples(data_rows, dt_index) + _column_samples(tail_rows, dt_index)
        kind, fmt, evidence = detect_datetime_format(samples)
        profile.datetime_kind = kind
        profile.dayfirst_proven = evidence is not None
        profile.dayfirst = bool(evidence)
        mapping.dayfirst = profile.dayfirst

        if kind == "iso":
            mapping.datetime_format = "ISO8601"
        elif kind.startswith("epoch_"):
            mapping.datetime_format = kind
        elif kind == "format":
            mapping.datetime_format = fmt
        else:
            mapping.datetime_format = None
        profile.datetime_format = mapping.datetime_format

        if time_index is not None:
            time_samples = (_column_samples(data_rows, time_index)
                            + _column_samples(tail_rows, time_index))
            mapping.time_format = detect_time_format(time_samples)
            profile.datetime_kind = "date_time"
            if mapping.time_format is None:
                profile.problems.append(
                    "The time column's format could not be recognised; check the "
                    "column mapping before importing."
                )

        if dt_index is None:
            profile.problems.append(
                "No date or timestamp column was recognised. Choose one by hand "
                "in the column mapping."
            )
        elif kind == "unknown":
            profile.problems.append(
                "The date format could not be recognised. Set it by hand in the "
                "column mapping, for example %d/%m/%Y %H:%M."
            )
        elif fmt and ("%d/" in fmt or "%m/" in fmt or "%d." in fmt or "%d-" in fmt) \
                and evidence is None:
            profile.problems.append(
                "Dates like 05/01/2023 are ambiguous in this file and were read as "
                f"{'day/month' if profile.dayfirst else 'month/day'}. Change the "
                "'day first' setting if that is wrong."
            )

        price_index = next((i for i in (_column_index(profile.headers, mapping.close),
                                        _column_index(profile.headers, mapping.open))
                            if i is not None), None)
        price_samples = _column_samples(data_rows, price_index)
        decimal, thousands = _detect_number_format(price_samples)
        profile.decimal, profile.thousands = decimal, thousands
        mapping.decimal, mapping.thousands = decimal, thousands

        missing = [f for f in _PRICE_FIELDS if getattr(mapping, f) is None]
        if "close" in missing:
            profile.problems.append(
                "No closing-price column was recognised. Choose one by hand in the "
                "column mapping."
            )
        elif missing:
            profile.problems.append(
                "These columns were not found and will be filled from the close "
                "price: " + ", ".join(missing) + "."
            )
        if mapping.volume is None:
            profile.problems.append(
                "No volume column was found; volume will be imported as zero."
            )

        # Row estimate from the average line length: good enough for a progress
        # bar and far cheaper than counting 2,000,000 lines up front.
        used = _strip_noise(raw_lines, profile.comment_char)
        avg = max(1.0, sum(len(l) + 1 for l in used) / max(1, len(used)))
        profile.row_estimate = max(len(data_rows),
                                   int((profile.file_size - profile.skip_rows) / avg))
        profile.mapping = mapping
    except Exception as exc:  # noqa: BLE001 - the sniffer must never raise
        log.exception("sniff_csv failed for %s", path)
        profile.problems.append(
            "This file could not be examined automatically. You can still set the "
            "columns by hand."
        )
        profile.problems.append(f"Technical detail: {exc!r}")
    return profile


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def _complete_mapping(path: Path, mapping: ColumnMapping) -> ColumnMapping:
    """Fill in any parsing knob the caller left as ``None`` by sniffing the file.

    This is what lets a mapping built purely from header names -- the obvious
    thing to write in a script -- load a semicolon-separated Latin-1 file with a
    comment banner at the top.
    """
    filled = ColumnMapping.from_dict(mapping.to_dict())
    needs = (filled.delimiter is None or filled.has_header is None
             or filled.encoding is None)
    if not needs:
        return filled
    profile = sniff_csv(path)
    if filled.delimiter is None:
        filled.delimiter = profile.delimiter
    if filled.has_header is None:
        filled.has_header = profile.has_header
    if filled.encoding is None:
        filled.encoding = profile.encoding
    if filled.comment_char is None:
        filled.comment_char = profile.comment_char
    if not filled.skip_rows:
        filled.skip_rows = profile.skip_rows
    return filled


def _read_kwargs(mapping: ColumnMapping) -> dict[str, Any]:
    """The ``read_csv`` arguments that describe the file's shape, not its values."""
    kwargs: dict[str, Any] = {
        "sep": mapping.delimiter or ",",
        "header": 0 if mapping.has_header else None,
        "encoding": mapping.encoding or "utf-8",
        "skip_blank_lines": True,
        "engine": "c",
    }
    if mapping.comment_char:
        kwargs["comment"] = mapping.comment_char
    if mapping.skip_rows:
        kwargs["skiprows"] = int(mapping.skip_rows)
    return kwargs


def _read_labels(path: Path, mapping: ColumnMapping) -> list[Any]:
    """The column labels pandas will produce for this file."""
    kwargs = _read_kwargs(mapping)
    try:
        if mapping.has_header:
            head = pd.read_csv(path, nrows=0, **kwargs)
            return [c for c in head.columns]
        head = pd.read_csv(path, nrows=1, **kwargs)
        return list(range(len(head.columns)))
    except pd.errors.EmptyDataError as exc:
        raise CsvImportError(
            f"'{path.name}' contains no data rows.", detail=repr(exc)) from exc
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError, OSError) as exc:
        raise CsvImportError(
            f"The first line of '{path.name}' could not be read. Check that this "
            f"is a text CSV file and that the delimiter is right.",
            detail=repr(exc),
        ) from exc


def _resolve_columns(labels: Sequence[Any], mapping: ColumnMapping) -> dict[str, Any]:
    """Turn mapping references into real pandas column labels."""
    names = [str(c) for c in labels]
    resolved: dict[str, Any] = {}
    dt_key, time_key = mapping.datetime_source()
    wanted = {"datetime": dt_key, "time": time_key}
    for f in ("open", "high", "low", "close", "volume"):
        wanted[f] = getattr(mapping, f)

    for field_name, key in wanted.items():
        if key is None or str(key) == "":
            continue
        idx = _column_index(names, key)
        if idx is None or idx >= len(labels):
            available = ", ".join(names[:20]) + ("..." if len(names) > 20 else "")
            raise CsvImportError(
                f"The column '{key}' chosen for {field_name} is not in this file.\n\n"
                f"Columns found: {available}",
                detail=f"labels={names}",
            )
        resolved[field_name] = labels[idx]

    if "datetime" not in resolved:
        raise CsvImportError(
            "No date or timestamp column was chosen, so these rows cannot be "
            "placed in time. Pick the column holding the bar's date in the "
            "column mapping."
        )
    if "close" not in resolved:
        raise CsvImportError(
            "No closing-price column was chosen. Pick the column holding each "
            "bar's closing price in the column mapping."
        )
    if "time" in resolved and resolved["time"] == resolved["datetime"]:
        raise CsvImportError(
            "The date column and the time column are the same column. Either "
            "clear the time column or choose a different one."
        )
    return resolved


def _estimate_rows(path: Path, mapping: ColumnMapping) -> int:
    """Cheap row estimate for the progress bar, from the average line length.

    Counting 2,000,000 lines exactly would mean reading the file twice; the
    progress bar does not need that kind of accuracy, and the final callback
    reports the true count anyway.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            chunk = fh.read(65_536)
        lines = [l for l in chunk.split(b"\n") if l.strip()]
        if len(lines) < 2:
            return 1
        avg = max(1.0, sum(len(l) + 1 for l in lines[:-1]) / max(1, len(lines) - 1))
        return max(1, int(size / avg))
    except OSError:
        return 1


def _read_table(path: Path, mapping: ColumnMapping, cols: dict[str, Any],
                progress: ProgressFn | None) -> pd.DataFrame:
    """Read just the mapped columns, as fast as the file allows.

    The first attempt declares ``float64`` for the price columns so the C parser
    converts them itself.  A file with currency symbols, stray spaces or an
    unexpected decimal separator makes that raise, and the second attempt reads
    everything as text for the slower vectorised clean-up path.
    """
    usecols: list[Any] = []
    for label in cols.values():
        if label not in usecols:
            usecols.append(label)
    text_fields = {cols[f] for f in ("datetime", "time") if f in cols}
    numeric_fields = [cols[f] for f in ("open", "high", "low", "close", "volume")
                      if f in cols]

    strict_dtype: dict[Any, str] = {c: "str" for c in text_fields}
    for c in numeric_fields:
        strict_dtype.setdefault(c, "float64")
    loose_dtype: dict[Any, str] = {c: "str" for c in usecols}

    encoding = mapping.encoding or "utf-8"
    attempts: list[tuple[dict[Any, str], str]] = [
        (strict_dtype, encoding), (loose_dtype, encoding)]
    if encoding != "latin-1":
        attempts.append((loose_dtype, "latin-1"))

    total = _estimate_rows(path, mapping) if progress is not None else 0
    last_error: Exception | None = None
    for dtype, enc in attempts:
        kwargs = _read_kwargs(mapping)
        kwargs["encoding"] = enc
        kwargs["usecols"] = usecols
        kwargs["dtype"] = dtype
        if mapping.decimal and mapping.decimal != ".":
            kwargs["decimal"] = mapping.decimal
        if mapping.thousands:
            kwargs["thousands"] = mapping.thousands
        try:
            if progress is None:
                frame = pd.read_csv(path, **kwargs)
                return frame.reset_index(drop=True)
            step = max(_MIN_CHUNK_ROWS, -(-total // _PROGRESS_STEPS))
            frames: list[pd.DataFrame] = []
            done = 0
            progress(0, max(total, 1))
            with pd.read_csv(path, chunksize=step, **kwargs) as reader:
                for chunk in reader:
                    frames.append(chunk)
                    done += len(chunk)
                    progress(done, max(total, done))
            if not frames:
                raise pd.errors.EmptyDataError("no rows")
            frame = (frames[0] if len(frames) == 1
                     else pd.concat(frames, ignore_index=True))
            return frame.reset_index(drop=True)
        except pd.errors.EmptyDataError as exc:
            raise CsvImportError(
                f"'{path.name}' contains no data rows.", detail=repr(exc)) from exc
        except pd.errors.ParserError as exc:
            raise CsvImportError(
                _bad_line_message(path, mapping, str(exc)), detail=repr(exc)) from exc
        except (ValueError, UnicodeDecodeError) as exc:
            # Fall through to the tolerant attempt; if that fails too the last
            # error is reported.
            last_error = exc
            log.debug("csv read attempt failed for %s: %r", path, exc)
            continue
        except OSError as exc:
            raise CsvImportError(
                f"'{path.name}' could not be read from disk.", detail=repr(exc)) from exc
    raise CsvImportError(
        f"'{path.name}' could not be parsed as a CSV file. Check the delimiter, "
        f"the header row and the column mapping.",
        detail=repr(last_error),
    )


def _bad_line_message(path: Path, mapping: ColumnMapping, parser_message: str) -> str:
    """Turn pandas' tokenizer complaint into something a person can act on."""
    m = re.search(r"line (\d+)", parser_message)
    if not m:
        return (f"'{path.name}' has a line that does not match the rest of the "
                f"file. Check for an extra or missing delimiter.")
    lineno = int(m.group(1))
    raw = _raw_line(path, mapping, lineno)
    extra = f"\n\nLine {lineno}: {raw}" if raw else ""
    return (f"Line {lineno} of '{path.name}' has a different number of columns "
            f"from the rest of the file. Check for an extra or missing "
            f"delimiter, or a quote that is never closed.{extra}")


def _raw_line(path: Path, mapping: ColumnMapping, lineno: int) -> str:
    """Read one physical line, for an error message only."""
    try:
        with path.open("r", encoding=mapping.encoding or "utf-8",
                       errors="replace", newline="") as fh:
            for i, raw in enumerate(fh, start=1):
                if i == lineno:
                    return raw.rstrip("\r\n")[:300]
    except OSError:  # pragma: no cover - the file was readable a moment ago
        pass
    return ""


def _locate_source_line(path: Path, mapping: ColumnMapping,
                        data_row: int) -> tuple[int, str]:
    """Physical line number and text of a 0-based *data* row.

    Iterating the file in Python is acceptable here because this only ever runs
    while building an error message, never on the loading path.
    """
    comment = mapping.comment_char
    skip = int(mapping.skip_rows or 0)
    header_pending = bool(mapping.has_header)
    index = 0
    try:
        with path.open("r", encoding=mapping.encoding or "utf-8",
                       errors="replace", newline="") as fh:
            for lineno, raw in enumerate(fh, start=1):
                if lineno <= skip:
                    continue
                stripped = raw.strip()
                if not stripped:
                    continue
                if comment and stripped.startswith(comment):
                    continue
                if header_pending:
                    header_pending = False
                    continue
                if index == data_row:
                    return lineno, raw.rstrip("\r\n")[:300]
                index += 1
    except OSError:  # pragma: no cover
        pass
    return -1, ""


def _as_float(series: pd.Series) -> np.ndarray:
    """Contiguous float64 view of a Series, with any missing value as NaN."""
    try:
        arr = series.to_numpy(dtype="float64", na_value=np.nan)
    except (TypeError, ValueError):
        arr = np.asarray(series.astype("float64"), dtype="float64")
    return np.ascontiguousarray(arr, dtype="float64")


def _clean_numeric(series: pd.Series, decimal: str, thousands: str) -> np.ndarray:
    """Vectorised rescue of price text: currency symbols, spaces, group separators.

    Everything here is a whole-column string operation.  Iterating a million
    cells in Python to strip a dollar sign would cost more than the rest of the
    import put together.
    """
    text = series.astype("str").str.strip()
    negative = np.asarray(text.str.startswith("(").fillna(False), dtype=bool)
    cleaned = text.str.replace("[\\s\u00a0\u202f\u2007]", "", regex=True)
    cleaned = cleaned.str.replace(r"[^0-9eE+\-.,']", "", regex=True)
    cleaned = cleaned.str.replace("'", "", regex=False)  # Swiss group separator
    if thousands:
        cleaned = cleaned.str.replace(thousands, "", regex=False)
    if decimal == ",":
        cleaned = cleaned.str.replace(",", ".", regex=False)
    elif not thousands:
        # A comma that survived a dot-decimal file can only be a group separator.
        cleaned = cleaned.str.replace(",", "", regex=False)
    values = _as_float(pd.to_numeric(cleaned, errors="coerce"))
    if negative.any():
        values = np.where(negative, -np.abs(values), values)
    return values


def _column_values(df: pd.DataFrame, label: Any, mapping: ColumnMapping) -> np.ndarray:
    """One column as float64, taking the fast path when pandas already parsed it."""
    series = df[label]
    if pd.api.types.is_numeric_dtype(series):
        return _as_float(series)
    return _clean_numeric(series, mapping.decimal, mapping.thousands)


def _bad_value_error(path: Path, mapping: ColumnMapping, field_name: str,
                     label: Any, data_row: int) -> CsvImportError:
    """Build the error for an unreadable number, quoting the line it is on."""
    lineno, text = _locate_source_line(path, mapping, data_row)
    where = f"line {lineno}" if lineno > 0 else f"data row {data_row + 1}"
    quoted = f"\n\n{text}" if text else ""
    return CsvImportError(
        f"The {field_name} value on {where} of '{path.name}' is not a number.{quoted}\n\n"
        f"Column '{label}'. If this file writes numbers as 1.234,56 rather than "
        f"1,234.56, set the decimal separator to a comma in the import options.",
        detail=f"field={field_name} label={label!r} row={data_row}",
    )


def _sample_texts(series: pd.Series, limit: int = _MAX_FORMAT_SAMPLES) -> list[str]:
    """Head and tail sample of a column, as plain strings."""
    n = len(series)
    if n == 0:
        return []
    if n <= 2 * limit:
        values = series.tolist()
    else:
        values = series.iloc[:limit].tolist() + series.iloc[-limit:].tolist()
    return _clean_samples(values, limit=2 * limit)


def _spread_sample(series: pd.Series, limit: int = 20_000) -> pd.Series:
    """An evenly spaced subsample spanning the whole column."""
    n = len(series)
    if n <= limit:
        return series
    return series.iloc[:: max(1, n // limit)]


def _swap_day_month(fmt: str) -> str:
    """Swap the first ``%d`` and ``%m`` of a format, leaving the time part alone."""
    return (fmt.replace("%d", "\x00", 1).replace("%m", "%d", 1)
            .replace("\x00", "%m", 1))


def _verify_day_order(series: pd.Series, fmt: str, path: Path,
                      mapping: ColumnMapping) -> tuple[str, str | None]:
    """Confirm a guessed ``d/m`` or ``m/d`` format against the whole column.

    The head of a 1-minute file may cover three days, which cannot prove which
    number is the day.  A sample spread across the entire file almost always
    contains a day above twelve, which settles it.
    """
    if not (fmt.startswith("%d") or fmt.startswith("%m")):
        return fmt, None
    sample = _spread_sample(series).astype("str")
    parts = sample.str.extract(r"^\s*(\d{1,2})[/.\-](\d{1,2})")
    first = pd.to_numeric(parts[0], errors="coerce")
    second = pd.to_numeric(parts[1], errors="coerce")
    day_first = bool((first > 12).any())
    month_first = bool((second > 12).any())
    log.debug("day order evidence for %s: day=%s month=%s", path.name,
              day_first, month_first)
    if day_first and month_first:
        raise CsvImportError(
            f"The dates in '{path.name}' are not consistent: some have a day "
            f"number in the first position and others in the second. Fix the "
            f"file, or set the date format by hand in the import options.",
            detail=f"format={fmt}",
        )
    if day_first and fmt.startswith("%m"):
        return _swap_day_month(fmt), "Dates were read as day/month."
    if month_first and fmt.startswith("%d"):
        return _swap_day_month(fmt), "Dates were read as month/day."
    if not day_first and not month_first:
        order = "day/month" if fmt.startswith("%d") else "month/day"
        return fmt, (f"Every date in this file could be read either way; they were "
                     f"read as {order}.")
    return fmt, None


_EPOCH_FACTOR: dict[str, int] = {
    "epoch_s": 1_000_000_000, "epoch_ms": 1_000_000,
    "epoch_us": 1_000, "epoch_ns": 1,
}


def _epoch_to_ns(series: pd.Series, kind: str, path: Path) -> np.ndarray:
    """Convert an epoch column to int64 UTC nanoseconds."""
    numeric = pd.to_numeric(series.astype("str").str.strip(), errors="coerce")
    factor = _EPOCH_FACTOR[kind]
    values = _as_float(numeric)
    bad = ~np.isfinite(values)
    scaled = np.where(bad, 0.0, values) * float(factor)
    if scaled.size and float(np.max(np.abs(scaled))) > 9.2e18:
        raise CsvImportError(
            f"The timestamps in '{path.name}' are outside the range this "
            f"application can represent (years 1678 to 2262).",
            detail=f"kind={kind}",
        )
    if pd.api.types.is_integer_dtype(numeric):
        # Integer maths keeps full precision for nanosecond stamps, which a
        # float64 cannot represent exactly beyond about 2^53.
        out = numeric.to_numpy(dtype="int64") * np.int64(factor)
    else:
        # Same problem for a fractional epoch: scale the whole and the
        # fractional part separately so a whole second stays a whole second.
        safe = np.where(bad, 0.0, values)
        whole = np.floor(safe)
        out = (whole.astype("int64") * np.int64(factor)
               + np.rint((safe - whole) * float(factor)).astype("int64"))
    out = np.where(bad, np.iinfo(np.int64).min, out)
    return out.astype("int64")


def _normalise_time_text(series: pd.Series, time_format: str) -> pd.Series:
    """Zero-pad a bare numeric time column so ``930`` reads as ``09:30``."""
    text = series.astype("str").str.strip()
    if time_format == "%H%M":
        return text.str.zfill(4)
    if time_format == "%H%M%S":
        return text.str.zfill(6)
    return text


def _localise(naive: pd.DatetimeIndex, timezone: str,
              warnings: list[str]) -> pd.DatetimeIndex:
    """Attach ``timezone`` to naive timestamps, surviving the clock changes.

    Twice a year a local wall clock either repeats an hour or skips one.  Real
    exports contain both.  Refusing to import the file over it would be
    useless, so the repeated hour is resolved in reading order where possible
    and the skipped hour is pushed forward, with a warning either way.
    """
    if timezone.upper() == "UTC":
        return naive.tz_localize("UTC")
    try:
        return naive.tz_localize(timezone)
    except ValueError:
        pass
    try:
        localized = naive.tz_localize(timezone, ambiguous="infer",
                                      nonexistent="shift_forward")
        warnings.append(
            f"Some timestamps fall in a daylight-saving change in {timezone}; "
            f"they were resolved from the order of the rows.")
        return localized
    except (ValueError, pd.errors.OutOfBoundsDatetime):
        localized = naive.tz_localize(timezone, ambiguous=True,
                                      nonexistent="shift_forward")
        warnings.append(
            f"Some timestamps are ambiguous or do not exist in {timezone} because "
            f"of a daylight-saving change. Repeated times were read as the first "
            f"(summer-time) reading and skipped times were moved forward.")
        return localized


def _to_utc_ns(index: pd.DatetimeIndex, path: Path) -> np.ndarray:
    """A tz-aware index as int64 UTC nanoseconds, refusing dates it cannot hold."""
    try:
        utc = index.tz_convert("UTC").tz_localize(None)
        return utc.to_numpy(dtype="datetime64[ns]").astype("int64")
    except (pd.errors.OutOfBoundsDatetime, OverflowError, ValueError) as exc:
        raise CsvImportError(
            f"'{path.name}' contains a date outside the range this application "
            f"can represent (years 1678 to 2262).",
            detail=repr(exc),
        ) from exc


def _build_timestamps(df: pd.DataFrame, mapping: ColumnMapping, cols: dict[str, Any],
                      path: Path, warnings: list[str]) -> np.ndarray:
    """Turn the mapped date (and time) columns into int64 UTC nanoseconds.

    Rows whose timestamp cannot be read come back as ``np.iinfo(int64).min``;
    the caller drops them and warns.  That is deliberate: a trailing "Total:"
    row is common enough that it must not fail an otherwise good import, while
    an unreadable *price* is a genuine error.
    """
    series = df[cols["datetime"]]
    if pd.api.types.is_numeric_dtype(series):
        series = series.astype("str")
    samples = _sample_texts(series)
    if not samples:
        raise CsvImportError(
            f"The date column of '{path.name}' is empty.",
            detail=f"column={cols['datetime']!r}")

    fmt = mapping.datetime_format
    auto = fmt is None
    if auto:
        kind, detected, _ = detect_datetime_format(samples, dayfirst=mapping.dayfirst)
        if kind == "unknown":
            day_proof, month_proof = _day_month_proof(samples)
            if day_proof and month_proof:
                raise CsvImportError(
                    f"The dates in '{path.name}' are not consistent: some are "
                    f"written day/month and others month/day, so they cannot all "
                    f"be read the same way.\n\nExample values: {samples[0]!r} and "
                    f"{samples[-1]!r}",
                    detail=f"column={cols['datetime']!r}")
            raise CsvImportError(
                f"The date format used in '{path.name}' was not recognised.\n\n"
                f"Example value: {samples[0]!r}\n\n"
                f"Set the date format by hand in the import options, for example "
                f"%d/%m/%Y %H:%M.",
                detail=f"column={cols['datetime']!r}")
        fmt = "ISO8601" if kind == "iso" else (detected or kind)

    if fmt in _EPOCH_FACTOR:
        if "time" in cols:
            warnings.append(
                "The timestamp column already carries a time of day, so the "
                "separate time column was ignored.")
        return _epoch_to_ns(series, fmt, path)

    text = series.astype("str").str.strip()
    if fmt != "ISO8601" and auto:
        fmt, note = _verify_day_order(text, fmt, path, mapping)
        if note:
            warnings.append(note)

    has_time_directive = any(d in fmt for d in ("%H", "%I")) or fmt == "ISO8601"
    if "time" in cols:
        if has_time_directive and fmt != "ISO8601":
            warnings.append(
                "The date column already carries a time of day, so the separate "
                "time column was ignored.")
        elif has_time_directive and fmt == "ISO8601" and any(
                len(s) > 10 for s in samples):
            warnings.append(
                "The date column already carries a time of day, so the separate "
                "time column was ignored.")
        else:
            time_series = df[cols["time"]]
            if pd.api.types.is_numeric_dtype(time_series):
                time_series = time_series.round().astype("int64").astype("str")
            time_format = mapping.time_format or detect_time_format(
                _sample_texts(time_series))
            if time_format is None:
                raise CsvImportError(
                    f"The time column of '{path.name}' was not recognised.\n\n"
                    f"Example value: "
                    f"{(_sample_texts(time_series) or ['(empty)'])[0]!r}\n\n"
                    f"Set the time format by hand in the import options, for "
                    f"example %H:%M:%S.",
                    detail=f"column={cols['time']!r}")
            if fmt == "ISO8601":
                fmt = "%Y-%m-%d"
            text = text + " " + _normalise_time_text(time_series, time_format)
            fmt = fmt + " " + time_format

    tz_aware = fmt == "ISO8601" and any(_OFFSET_RE.search(s) for s in samples)
    tz_aware = tz_aware or "%z" in fmt or "%Z" in fmt
    try:
        if fmt == "ISO8601":
            parsed = pd.to_datetime(text, format="ISO8601", utc=tz_aware,
                                    errors="coerce")
        else:
            parsed = pd.to_datetime(text, format=fmt, utc=tz_aware, errors="coerce")
    except (ValueError, TypeError, pd.errors.OutOfBoundsDatetime) as exc:
        raise CsvImportError(
            f"The dates in '{path.name}' could not be read with the format "
            f"'{fmt}'.\n\nExample value: {samples[0]!r}",
            detail=repr(exc),
        ) from exc

    good = parsed.notna()
    if not bool(good.any()):
        raise CsvImportError(
            f"Not one date in '{path.name}' could be read with the format "
            f"'{fmt}'.\n\nExample value: {samples[0]!r}\n\nCheck the date column "
            f"and the date format in the import options.",
            detail=f"column={cols['datetime']!r}")

    index = pd.DatetimeIndex(parsed)
    if tz_aware:
        utc_index = index
    else:
        placeholder = index[good.to_numpy()][0]
        filled = pd.DatetimeIndex(parsed.fillna(placeholder))
        utc_index = _localise(filled, mapping.timezone, warnings)
    stamps = _to_utc_ns(pd.DatetimeIndex(utc_index), path)
    stamps = np.where(good.to_numpy(), stamps, np.iinfo(np.int64).min)
    return stamps.astype("int64")


def _check_timezone(name: str) -> None:
    """Fail early and clearly on a timezone name pandas would reject later."""
    if not name:
        raise CsvImportError("No timezone was given for this file's timestamps.")
    if name.upper() == "UTC":
        return
    try:
        pd.Timestamp("2020-01-01").tz_localize(name)
    except Exception as exc:  # noqa: BLE001 - any failure means the name is unusable
        raise CsvImportError(
            f"'{name}' is not a timezone this computer knows about. Use a name "
            f"like UTC, America/New_York or Europe/London.",
            detail=repr(exc),
        ) from exc


def load_csv(path: str | Path, mapping: ColumnMapping, instrument: Instrument,
             timeframe: Timeframe | None = None,
             progress: ProgressFn | None = None) -> BarSeries:
    """Load OHLCV bars from a CSV file.

    Parameters
    ----------
    path:
        The file to read.
    mapping:
        Which column is which.  Parsing knobs left as ``None`` are sniffed.
    instrument:
        The instrument these bars belong to.
    timeframe:
        Bar duration.  Inferred from the modal gap between bars when omitted.
    progress:
        ``progress(rows_done, rows_total)``, called at most about 100 times.

    Returns
    -------
    BarSeries
        Sorted strictly ascending by timestamp.  ``meta["warnings"]`` lists
        everything that was assumed, repaired or skipped, in plain language.

    Raises
    ------
    CsvImportError
        With a message naming the offending line and column.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise CsvImportError(f"There is no file at {p}.")
    if p.is_dir():
        raise CsvImportError(f"{p} is a folder, not a CSV file.")
    try:
        size = p.stat().st_size
    except OSError as exc:
        raise CsvImportError(f"{p} could not be opened.", detail=repr(exc)) from exc
    if size == 0:
        raise CsvImportError(f"'{p.name}' is empty.")

    warnings: list[str] = []
    active = _complete_mapping(p, mapping)
    _check_timezone(active.timezone)
    labels = _read_labels(p, active)
    cols = _resolve_columns(labels, active)
    frame = _read_table(p, active, cols, progress)
    raw_rows = len(frame)
    if raw_rows == 0:
        raise CsvImportError(f"'{p.name}' has a header but no data rows.")

    stamps = _build_timestamps(frame, active, cols, p, warnings)
    keep = stamps != np.iinfo(np.int64).min
    origin = np.arange(raw_rows, dtype="int64")
    if not bool(keep.all()):
        dropped = int((~keep).sum())
        first_bad = int(origin[~keep][0])
        lineno, text = _locate_source_line(p, active, first_bad)
        where = f"line {lineno}" if lineno > 0 else f"data row {first_bad + 1}"
        warnings.append(
            f"{dropped:,} row(s) had a date that could not be read and were "
            f"skipped; the first was on {where}: {text[:120]!r}")
        frame = frame.loc[keep].reset_index(drop=True)
        stamps = stamps[keep]
        origin = origin[keep]
    if stamps.size == 0:
        raise CsvImportError(
            f"Every row of '{p.name}' had an unreadable date, so there is "
            f"nothing to import.")

    close = _column_values(frame, cols["close"], active)
    bad = ~np.isfinite(close)
    if bad.any():
        raise _bad_value_error(p, active, "close price", cols["close"],
                               int(origin[bad][0]))

    prices: dict[str, np.ndarray] = {"close": close}
    for name in ("open", "high", "low"):
        if name in cols:
            values = _column_values(frame, cols[name], active)
            bad = ~np.isfinite(values)
            if bad.any():
                raise _bad_value_error(p, active, f"{name} price", cols[name],
                                       int(origin[bad][0]))
            prices[name] = values
    if "open" not in prices:
        prices["open"] = close.copy()
        warnings.append("This file has no opening price; the closing price was "
                        "used for the open of every bar.")
    if "high" not in prices:
        prices["high"] = np.maximum(prices["open"], close)
        warnings.append("This file has no high price; the higher of the open and "
                        "the close was used.")
    if "low" not in prices:
        prices["low"] = np.minimum(prices["open"], close)
        warnings.append("This file has no low price; the lower of the open and "
                        "the close was used.")

    if "volume" in cols:
        volume = _column_values(frame, cols["volume"], active)
        missing = ~np.isfinite(volume)
        if missing.any():
            warnings.append(f"{int(missing.sum()):,} row(s) had no volume; those "
                            f"bars were imported with a volume of zero.")
            volume = np.where(missing, 0.0, volume)
    else:
        volume = np.zeros(stamps.size, dtype="float64")
        warnings.append("This file has no volume column; every bar was imported "
                        "with a volume of zero.")

    if stamps.size > 1 and bool(np.any(np.diff(stamps) < 0)):
        order = np.argsort(stamps, kind="stable")
        stamps = stamps[order]
        origin = origin[order]
        for key in prices:
            prices[key] = prices[key][order]
        volume = volume[order]
        warnings.append("The rows in this file were not in date order; they were "
                        "sorted oldest first.")

    if stamps.size > 1:
        duplicate = np.zeros(stamps.size, dtype=bool)
        duplicate[:-1] = stamps[1:] == stamps[:-1]
        if duplicate.any():
            # Keep the LAST row of each repeated timestamp: vendors that revise a
            # bar append the corrected copy.
            survives = ~duplicate
            count = int(duplicate.sum())
            first = int(origin[duplicate][0])
            lineno, _ = _locate_source_line(p, active, first)
            where = f"line {lineno}" if lineno > 0 else f"data row {first + 1}"
            stamps = stamps[survives]
            origin = origin[survives]
            for key in prices:
                prices[key] = prices[key][survives]
            volume = volume[survives]
            warnings.append(
                f"{count:,} row(s) repeated a timestamp that had already been "
                f"seen; the last row for each was kept (first repeat on {where}).")

    resolved_tf = timeframe
    if resolved_tf is None:
        resolved_tf = (infer_timeframe(stamps) if stamps.size >= 2
                       else Timeframe(1, TimeframeUnit.DAY))
        if stamps.size < 2:
            warnings.append("There is only one bar in this file, so its timeframe "
                            "could not be worked out; it was recorded as 1 day.")
    elif stamps.size >= 2:
        inferred = infer_timeframe(stamps)
        if inferred.approx_seconds != resolved_tf.approx_seconds:
            warnings.append(
                f"These bars were imported as {resolved_tf.label} but the gaps "
                f"between them look like {inferred.label}.")

    bars = BarSeries(
        ts=stamps, open=prices["open"], high=prices["high"], low=prices["low"],
        close=prices["close"], volume=volume, instrument=instrument,
        timeframe=resolved_tf, source=str(p),
        meta={
            "warnings": warnings,
            "source_path": str(p),
            "rows_read": raw_rows,
            "rows_kept": int(stamps.size),
            "encoding": active.encoding,
            "delimiter": active.delimiter,
            "timezone": active.timezone,
            "datetime_format": active.datetime_format,
            "column_mapping": active.to_dict(),
        },
    )
    if progress is not None:
        progress(int(stamps.size), int(stamps.size))
    for message in warnings:
        log.warning("%s: %s", p.name, message)
    log.info("Loaded %s bars from %s (%s)", f"{len(bars):,}", p.name,
             resolved_tf.label)
    return bars
