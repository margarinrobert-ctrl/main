"""Data providers: the seam between "where bars come from" and everything else.

The application only ever asks a provider two questions -- "what symbols do you
have?" and "give me these bars" -- so the interface is deliberately four
methods wide.  :class:`CsvFileProvider` implements it over a folder of CSV
files and is the only provider shipped.

Adding a provider later (a broker API, a vendor download, a database) means
writing a class with the same four methods and handing an instance to whatever
is doing the fetching.  There is no registration ceremony and no base class to
inherit from: :class:`DataProvider` is a ``Protocol``, so a new provider is
compatible by having the right shape.

A provider must obey three rules, and the whole design depends on them:

1. **Return UTC.**  ``fetch`` returns a :class:`BarSeries` whose ``ts`` is
   int64 UTC nanoseconds marking each bar's OPEN, strictly ascending.
2. **Fail in the user's language.**  Anything that can go wrong is raised as a
   :class:`~tradingbacktester.core.errors.DataError` (or a subclass) whose
   ``user_message`` can be shown in a dialog unedited.
3. **Never surprise the user with the network.**  Nothing in this file, or in
   any provider shipped with this application, opens a socket.  A provider that
   did would have to say so in :meth:`describe` and be enabled deliberately.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol, Sequence, runtime_checkable

import numpy as np
import pandas as pd

from ...core.errors import DataError, InsufficientDataError, TimeframeError
from ...core.timeframe import Timeframe, infer_timeframe
from ..csv_loader import ColumnMapping, load_csv, sniff_csv
from ..instruments import InstrumentRegistry, default_instrument_for
from ..models import BarSeries, Instrument
from ..resample import resample

log = logging.getLogger(__name__)

#: Anything a user might reasonably hand to a date field.
TimeLike = datetime | date | pd.Timestamp | str | int | float | None

#: File extensions :class:`CsvFileProvider` will look inside.  Compressed files
#: are excluded because the CSV loader sniffs raw text.
CSV_SUFFIXES: tuple[str, ...] = (".csv", ".txt", ".tsv")

#: Filename words that describe the file rather than the symbol.
_NOISE_TOKENS = frozenset({
    "synthetic", "sample", "samples", "test", "testdata", "data", "bars",
    "ohlc", "ohlcv", "history", "historical", "export", "backtest",
})

_SPLIT_RE = re.compile(r"[\s_\-]+")
_TF_TOKEN_RE = re.compile(r"^\d{0,4}[A-Za-z]{1,7}$")


# ---------------------------------------------------------------------------
# The interface
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderSymbol:
    """One search hit: something a provider can be asked to fetch.

    ``timeframe`` is the *native* timeframe of the underlying data when the
    provider knows it, as a label such as ``"5m"``.  An empty string means the
    provider will work it out when asked.
    """

    symbol: str
    name: str = ""
    timeframe: str = ""
    provider: str = ""
    detail: str = ""
    """Where this came from -- a file path, an exchange code, a vendor ticker."""
    bar_estimate: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        parts = [self.symbol]
        if self.timeframe:
            parts.append(self.timeframe)
        if self.name and self.name != self.symbol:
            parts.append(f"- {self.name}")
        if self.bar_estimate:
            parts.append(f"({self.bar_estimate:,} bars)")
        return " ".join(parts)


@runtime_checkable
class DataProvider(Protocol):
    """The shape every data source must have.

    Implementations are plain classes; there is nothing to inherit.  See
    :class:`CsvFileProvider` for a worked example.
    """

    #: Short human name shown in the source picker, e.g. ``"CSV files"``.
    name: str

    def describe(self) -> str:
        """One sentence for the UI saying what this provider reads and from where."""
        ...

    def is_available(self) -> bool:
        """True when the provider can be used right now.

        Must not raise and must not be expensive: it is called to decide
        whether to grey out a menu item.
        """
        ...

    def search(self, query: str) -> list[ProviderSymbol]:
        """Symbols matching a free-text query; an empty query lists everything."""
        ...

    def fetch(self, symbol: str, timeframe: Timeframe | str | None = None,
              start: Any = None, end: Any = None) -> BarSeries:
        """Bars for one symbol.

        ``start`` and ``end`` are inclusive bounds and may be ``None``.  Raise
        :class:`~tradingbacktester.core.errors.DataError` when the symbol is
        unknown, and :class:`~tradingbacktester.core.errors.InsufficientDataError`
        when the range contains no bars.
        """
        ...


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def to_utc_ns(value: TimeLike, *, end_of_day: bool = False) -> int | None:
    """Turn anything date-like into int64 UTC nanoseconds.

    A naive value is read as UTC, because every timestamp inside the
    application is already UTC by the time it gets here.  ``end_of_day``
    pushes a bare date to 23:59:59.999999999 so that an inclusive end bound
    given as ``"2024-06-30"`` really does include that whole day.
    """
    if value is None:
        return None
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        # Bare integers are ambiguous; treat anything below year 2200 in
        # seconds as seconds, and otherwise assume nanoseconds already.
        magnitude = abs(int(value))
        if magnitude < 10 ** 11:
            return int(value) * 1_000_000_000
        if magnitude < 10 ** 14:
            return int(value) * 1_000_000
        return int(value)
    try:
        stamp = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise DataError(
            f"'{value}' is not a date this application can read.",
            detail=repr(exc)) from exc
    if stamp.tz is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    if end_of_day and isinstance(value, (str, date)) and not isinstance(value, datetime):
        if stamp == stamp.normalize():
            stamp = stamp + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return int(stamp.value)


def parse_dataset_filename(filename: str) -> tuple[str, Timeframe | None]:
    """Guess ``(symbol, timeframe)`` from a file name.

    Handles the conventions vendors and this application actually use --
    ``EURUSD_60m.csv``, ``NQ-5m.csv``, ``SYNTHETIC_SPY_1D.csv``, ``AAPL.csv`` --
    by throwing away descriptive words, treating a trailing token that parses
    as a timeframe as the timeframe, and taking the last remaining token as the
    symbol.  Returns ``(stem.upper(), None)`` when it cannot do better.
    """
    stem = Path(str(filename)).name
    for suffix in CSV_SUFFIXES:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    tokens = [t for t in _SPLIT_RE.split(stem) if t]
    if not tokens:
        return str(filename).upper(), None

    meaningful = [t for t in tokens if t.lower() not in _NOISE_TOKENS] or tokens
    timeframe: Timeframe | None = None
    if len(meaningful) > 1 and _TF_TOKEN_RE.match(meaningful[-1]):
        try:
            timeframe = Timeframe.parse(meaningful[-1])
        except TimeframeError:
            timeframe = None
        else:
            meaningful = meaningful[:-1]
    symbol = meaningful[-1] if meaningful else tokens[0]
    return symbol.upper(), timeframe


# ---------------------------------------------------------------------------
# The one shipped provider
# ---------------------------------------------------------------------------


class CsvFileProvider:
    """Reads bars out of a folder of CSV files.

    The folder is scanned, not indexed: files can be dropped in and picked up
    without restarting.  A file's symbol and timeframe are taken from its name
    (see :func:`parse_dataset_filename`) and its columns are sniffed by
    :func:`~tradingbacktester.data.csv_loader.sniff_csv`, so no configuration
    is needed for a conventionally named file.

    Parameters
    ----------
    root:
        Folder to scan.  Subfolders are included.
    registry:
        Instrument catalogue used to attach contract specifications to the
        bars.  Without one, the seeded defaults are used and an unknown symbol
        gets asset-class defaults.
    name:
        Display name, in case an application shows two of these (a samples
        folder and a downloads folder, say).
    mapping:
        Column mapping to use for every file, overriding the sniffer.  Useful
        when a whole folder comes from one vendor with an unusual layout.
    recursive:
        Scan subfolders as well.
    """

    def __init__(self, root: str | Path,
                 registry: InstrumentRegistry | None = None,
                 name: str = "CSV files",
                 mapping: ColumnMapping | None = None,
                 recursive: bool = True) -> None:
        self.root = Path(root).expanduser()
        self.registry = registry
        self.name = str(name)
        self.mapping = mapping
        self.recursive = bool(recursive)

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<CsvFileProvider {self.name!r} root={self.root}>"

    # -- interface ---------------------------------------------------------

    def describe(self) -> str:
        state = "" if self.is_available() else " (folder not found)"
        return (f"Reads OHLCV bars from CSV files in {self.root}{state}. "
                f"Nothing is downloaded and nothing leaves this computer.")

    def is_available(self) -> bool:
        """True when the folder exists.  Never raises -- the UI calls it often."""
        try:
            return self.root.is_dir()
        except OSError:  # pragma: no cover - unreadable mount point
            return False

    def search(self, query: str = "") -> list[ProviderSymbol]:
        """Every file whose symbol, timeframe or name contains ``query``."""
        needle = str(query or "").strip().lower()
        hits: list[ProviderSymbol] = []
        for path in self._files():
            symbol, timeframe = parse_dataset_filename(path.name)
            haystack = f"{symbol} {timeframe.label if timeframe else ''} {path.name}".lower()
            if needle and needle not in haystack:
                continue
            hits.append(ProviderSymbol(
                symbol=symbol,
                name=self._instrument_for(symbol).name,
                timeframe=timeframe.label if timeframe else "",
                provider=self.name,
                detail=str(path),
                bar_estimate=_estimate_rows(path),
                extra={"path": str(path)},
            ))
        hits.sort(key=lambda h: (h.symbol, h.timeframe))
        return hits

    def fetch(self, symbol: str, timeframe: Timeframe | str | None = None,
              start: Any = None, end: Any = None) -> BarSeries:
        """Load one symbol, resampling and trimming to the requested range.

        When several files match, the one whose native timeframe is closest to
        (and no coarser than) the requested timeframe wins, because building
        5-minute bars out of 1-minute bars is exact while the reverse is
        impossible.
        """
        target = self._as_timeframe(timeframe)
        path, native = self._choose_file(symbol, target)
        instrument = self._instrument_for(symbol)
        mapping = self.mapping or self._sniff(path)

        bars = load_csv(path, mapping, instrument, timeframe=native)
        if len(bars) == 0:  # pragma: no cover - load_csv raises first
            raise InsufficientDataError(f"'{path.name}' contained no usable bars.")

        # ``60m`` and ``1h`` are different Timeframe objects but the same bar,
        # so compare durations rather than identity before resampling.
        if target is not None and target.approx_seconds != bars.timeframe.approx_seconds:
            if not target.can_build_from(bars.timeframe):
                raise TimeframeError(
                    f"'{path.name}' holds {bars.timeframe.display_name} bars, "
                    f"which cannot be turned into {target.display_name} bars. "
                    f"Only longer timeframes can be built from shorter ones.")
            bars = resample(bars, target)

        start_ns = to_utc_ns(start)
        end_ns = to_utc_ns(end, end_of_day=True)
        if start_ns is not None or end_ns is not None:
            # slice_time raises InsufficientDataError with a usable message when
            # the window is empty, which is exactly what the caller wants.
            bars = bars.slice_time(start_ns, end_ns)

        bars.source = str(path)
        bars.meta.setdefault("provider", self.name)
        log.info("Fetched %s from %s", bars.describe(), path.name)
        return bars

    # -- internals ---------------------------------------------------------

    def _files(self) -> list[Path]:
        """Every candidate file under the root, sorted for a stable listing."""
        if not self.is_available():
            return []
        pattern = "**/*" if self.recursive else "*"
        try:
            found = [p for p in self.root.glob(pattern)
                     if p.is_file() and p.suffix.lower() in CSV_SUFFIXES]
        except OSError as exc:  # pragma: no cover - unreadable directory
            log.warning("The folder %s could not be listed: %r", self.root, exc)
            return []
        return sorted(found)

    def _candidates(self, symbol: str) -> list[tuple[Path, Timeframe | None]]:
        key = str(symbol).strip().upper()
        out: list[tuple[Path, Timeframe | None]] = []
        for path in self._files():
            found, timeframe = parse_dataset_filename(path.name)
            if found == key:
                out.append((path, timeframe))
        return out

    def _choose_file(self, symbol: str,
                     target: Timeframe | None) -> tuple[Path, Timeframe | None]:
        """Pick the best file for a symbol, or explain why there is not one."""
        candidates = self._candidates(symbol)
        if not candidates:
            known = sorted({s.symbol for s in self.search("")})
            hint = (f" This folder has {', '.join(known[:8])}."
                    if known else " This folder has no CSV files in it.")
            raise DataError(
                f"There is no data for '{symbol}' in {self.root}.{hint}",
                detail=f"root={self.root} known={known}")
        if target is None:
            return candidates[0]

        exact = [c for c in candidates if c[1] is not None
                 and c[1].approx_seconds == target.approx_seconds]
        if exact:
            return exact[0]
        # Coarsest source that can still build the target: fewer bars to read
        # and to aggregate, with an identical result.
        buildable = [c for c in candidates
                     if c[1] is not None and target.can_build_from(c[1])]
        if buildable:
            return max(buildable, key=lambda c: c[1].approx_seconds)
        unknown = [c for c in candidates if c[1] is None]
        if unknown:
            # No timeframe in the name: read it and find out.
            return unknown[0]
        have = ", ".join(sorted({c[1].label for c in candidates if c[1]}))
        raise TimeframeError(
            f"'{symbol}' is available at {have}, none of which can be turned "
            f"into {target.display_name} bars.",
            detail=f"root={self.root}")

    def _sniff(self, path: Path) -> ColumnMapping:
        """Work out the column layout of one file, refusing early if it cannot."""
        profile = sniff_csv(path)
        if not profile.is_usable:
            problems = "; ".join(profile.problems[:3]) or "no timestamp or price column was found"
            raise DataError(
                f"'{path.name}' does not look like an OHLCV file: {problems}.",
                detail=f"headers={profile.headers}")
        return profile.mapping

    def _instrument_for(self, symbol: str) -> Instrument:
        """Contract specification for a symbol, without writing to the catalogue."""
        key = str(symbol).strip().upper()
        if self.registry is not None:
            found = self.registry.find(key)
            if found is not None:
                return found
        seeded = default_instrument_for(key)
        if seeded is not None:
            return seeded
        # Unknown symbol: asset-class defaults are wrong for P&L but at least
        # they are consistent, and the user can fix the instrument afterwards.
        log.info("No contract specification for %s; using generic defaults", key)
        return Instrument(symbol=key)

    @staticmethod
    def _as_timeframe(timeframe: Timeframe | str | None) -> Timeframe | None:
        if timeframe is None or isinstance(timeframe, Timeframe):
            return timeframe
        return Timeframe.parse(str(timeframe))


def _estimate_rows(path: Path, sample_bytes: int = 65_536) -> int:
    """Rough row count from the average line length of the first block.

    Exact enough for "about 20,000 bars" in a list, and constant-time on a
    500 MB file, which counting the lines would not be.
    """
    try:
        size = path.stat().st_size
        if size == 0:
            return 0
        with open(path, "rb") as handle:
            chunk = handle.read(sample_bytes)
    except OSError:
        return 0
    lines = chunk.count(b"\n")
    if lines == 0:
        return 1
    average = len(chunk) / lines
    if average <= 0:  # pragma: no cover - impossible with lines > 0
        return 0
    return max(0, int(size / average) - 1)


def bars_from_frame(frame: pd.DataFrame, instrument: Instrument,
                    timeframe: Timeframe | None = None,
                    source: str = "") -> BarSeries:
    """Build a :class:`BarSeries` from a tidy DataFrame.

    Offered here because it is the one piece of plumbing every future provider
    will need: a vendor client hands back a DataFrame with a DatetimeIndex and
    OHLCV columns, and this turns it into the application's bar type without
    each provider reinventing the timezone handling.
    """
    if frame is None or len(frame) == 0:
        raise InsufficientDataError(
            f"The provider returned no bars for {instrument.symbol}.")
    lower = {str(c).lower(): c for c in frame.columns}
    missing = [c for c in ("open", "high", "low", "close") if c not in lower]
    if missing:
        raise DataError(
            f"The data for {instrument.symbol} is missing the "
            f"{', '.join(missing)} column(s).",
            detail=f"columns={list(frame.columns)}")

    if "ts" in lower:
        stamps = pd.to_datetime(frame[lower["ts"]], utc=True)
    elif "datetime" in lower:
        stamps = pd.to_datetime(frame[lower["datetime"]], utc=True)
    else:
        index = pd.DatetimeIndex(frame.index)
        stamps = pd.Series(index.tz_localize("UTC") if index.tz is None
                           else index.tz_convert("UTC"))
    ts = stamps.to_numpy(dtype="datetime64[ns]").astype("int64")

    volume = (frame[lower["volume"]].to_numpy(dtype="float64")
              if "volume" in lower else pd.Series(0.0, index=frame.index).to_numpy())
    return BarSeries.from_arrays(
        ts=ts,
        open_=frame[lower["open"]].to_numpy(dtype="float64"),
        high=frame[lower["high"]].to_numpy(dtype="float64"),
        low=frame[lower["low"]].to_numpy(dtype="float64"),
        close=frame[lower["close"]].to_numpy(dtype="float64"),
        volume=volume,
        instrument=instrument,
        timeframe=timeframe or (infer_timeframe(ts) if len(ts) >= 2 else None),
        source=source,
    )


def check_providers(providers: Sequence[DataProvider]) -> list[str]:
    """Names of the providers that are usable right now.

    A provider whose :meth:`is_available` raises is reported as unusable rather
    than being allowed to take the application down with it.
    """
    usable: list[str] = []
    for provider in providers:
        try:
            if provider.is_available():
                usable.append(provider.name)
        except Exception as exc:  # noqa: BLE001 - a third-party provider may do anything
            log.warning("Provider %r failed its availability check: %r",
                        getattr(provider, "name", provider), exc)
    return usable
