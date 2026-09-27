"""Tick data: every trade, in order, and the bars built from it.

A bar is a summary. It keeps the open, the high, the low and the close and
throws away the ORDER they happened in, and order is exactly what a backtest
needs when a bar reaches both a stop and a target: bar data cannot say which
came first, so a bar-based engine has to assume (see ``IntrabarPriority``).
Tick data does not have to assume anything. With ticks attached, the engine
walks each bar's trades in sequence and fills every stop, target and resting
entry at the first trade that reaches it -- see
:meth:`tradingbacktester.engine.broker.SimulatedBroker.walk_ticks`.

Formats read
------------
* A CSV with a header naming a time column and a price column -- ``time``,
  ``timestamp``, ``datetime``, ``date`` + ``time``, MetaTrader's ``<DATE>`` +
  ``<TIME>``; ``price``, ``last``, ``trade``, ``close`` -- and optionally a
  volume (``volume``, ``size``, ``qty``) and ``bid`` / ``ask``.
* NinjaTrader's tick export: ``yyyyMMdd HHmmss fffffff;price;volume`` with no
  header (a bid/ask variant has more columns; the second is the trade).
* Headerless ``time,price[,volume]``.
* Epoch timestamps in seconds, milliseconds, microseconds or nanoseconds.

A file with bid and ask but no trade price is read at the MID, with a warning:
a stop filled at the mid is half a spread cheaper than one filled at the bid
or the ask, so costs should carry the spread.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..core.errors import DataError
from ..core.timeframe import Timeframe
from .models import BarSeries, Instrument

__all__ = ["TickSeries", "read_ticks", "bars_from_ticks", "save_ticks",
           "load_ticks", "TICK_TIMEFRAMES"]

#: Bar sizes offered when building bars from ticks.  Intraday only: a day bar
#: from ticks needs a session definition, and the bar importer already has one.
TICK_TIMEFRAMES = ("1s", "5s", "10s", "15s", "30s", "1m", "2m", "3m", "5m",
                   "10m", "15m", "30m", "1h")

_TIME_NAMES = ("timestamp", "time", "datetime", "date_time", "ts", "ny", "utc",
               "time_utc", "date time", "gmt time", "time (utc)", "local time")
_PRICE_NAMES = ("price", "last", "trade", "last_price", "lastprice", "close",
                "trade_price")
_VOLUME_NAMES = ("volume", "size", "qty", "quantity", "vol", "last_size",
                 "lastsize", "tickvolume", "tick_volume")


@dataclass
class TickSeries:
    """Trades in time order.  ``ts`` is UTC nanoseconds."""

    ts: np.ndarray
    price: np.ndarray
    volume: np.ndarray
    source: str = ""
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.ts = np.ascontiguousarray(self.ts, dtype="int64")
        self.price = np.ascontiguousarray(self.price, dtype="float64")
        self.volume = np.ascontiguousarray(self.volume, dtype="float64")
        if not (len(self.ts) == len(self.price) == len(self.volume)):
            raise DataError("Tick arrays must all be the same length.")

    def __len__(self) -> int:
        return int(self.ts.size)

    @property
    def start_ts(self) -> int:
        return int(self.ts[0]) if len(self) else 0

    @property
    def end_ts(self) -> int:
        return int(self.ts[-1]) if len(self) else 0

    def slice_time(self, start: int | None, end: int | None) -> "TickSeries":
        lo = 0 if start is None else int(np.searchsorted(self.ts, start, "left"))
        hi = len(self) if end is None else int(np.searchsorted(self.ts, end, "right"))
        return TickSeries(self.ts[lo:hi], self.price[lo:hi], self.volume[lo:hi],
                          self.source)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _open_text(path: Path):
    if str(path).lower().endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8-sig",
                                errors="replace")
    return open(path, "r", encoding="utf-8-sig", errors="replace", newline="")


def _norm(name: str) -> str:
    return str(name).strip().strip("<>").strip().lower()


_NINJA = re.compile(r"^\d{8} \d{6}( \d{1,7})?$")


def _sniff(path: Path) -> tuple[str, bool, list[str]]:
    """Delimiter, header present, first line's fields."""
    with _open_text(path) as fh:
        lines = [fh.readline() for _ in range(20)]
    lines = [l.rstrip("\r\n") for l in lines if l.strip()]
    if not lines:
        raise DataError(f"{path.name} is empty.")
    sample = "\n".join(lines)
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        for d in (";", "\t", ",", "|"):
            if d in lines[0]:
                delimiter = d
                break
    first = [f.strip() for f in lines[0].split(delimiter)]
    has_header = any(re.search(r"[A-Za-z]", f) for f in first) and not _NINJA.match(first[0])
    return delimiter, has_header, first


def _parse_times(values: pd.Series, timezone: str,
                 warnings: list[str]) -> np.ndarray:
    """Strings or epoch numbers to UTC nanoseconds."""
    from .csv_loader import _localise

    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().mean() > 0.99:
        mag = float(np.nanmedian(np.abs(numeric.to_numpy(dtype="float64"))))
        unit = ("s" if mag < 1e11 else "ms" if mag < 1e14 else
                "us" if mag < 1e17 else "ns")
        stamps = pd.to_datetime(numeric, unit=unit, utc=True)
        warnings.append(f"Timestamps read as Unix epoch {unit}, which is UTC by "
                        f"definition; the timezone setting was not applied.")
        return stamps.to_numpy(dtype="datetime64[ns]").astype("int64")
    text = values.astype(str).str.strip()
    sample = text.iloc[0] if len(text) else ""
    if _NINJA.match(sample):
        # NinjaTrader: yyyyMMdd HHmmss fffffff (100-ns ticks of the second).
        parts = text.str.split(" ", expand=True)
        base = pd.to_datetime(parts[0] + parts[1], format="%Y%m%d%H%M%S")
        if parts.shape[1] > 2:
            frac = pd.to_numeric(parts[2], errors="coerce").fillna(0).astype("int64")
            base = base + pd.to_timedelta(frac * 100, unit="ns")
        naive = pd.DatetimeIndex(base)
    else:
        naive = None
        for fmt in ("%Y.%m.%d %H:%M:%S.%f", "%Y.%m.%d %H:%M:%S",
                    "%d.%m.%Y %H:%M:%S.%f", "%d.%m.%Y %H:%M:%S",
                    "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                    "%Y%m%d %H:%M:%S.%f", "%Y%m%d %H:%M:%S",
                    "%m/%d/%Y %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S"):
            try:
                parsed = pd.to_datetime(text, format=fmt)
            except (ValueError, TypeError):
                continue
            naive = pd.DatetimeIndex(parsed)
            break
        if naive is None:
            try:
                parsed = pd.to_datetime(text, format="ISO8601")
            except (ValueError, TypeError):
                try:
                    parsed = pd.to_datetime(text, format="mixed")
                except (ValueError, TypeError) as exc:
                    raise DataError(
                        f"The timestamps could not be read (the first one is "
                        f"'{sample}').", detail=repr(exc)) from exc
            naive = pd.DatetimeIndex(parsed)
        if naive.tz is not None:
            return _utc_ns(naive.tz_convert("UTC"))
    local = _localise(naive, timezone, warnings)
    return _utc_ns(local.tz_convert("UTC"))


def _utc_ns(index: pd.DatetimeIndex) -> np.ndarray:
    """Nanoseconds since the epoch, whatever unit pandas parsed into.

    pandas 2 keeps the resolution a format implies -- microseconds for
    ``%f`` -- and ``asi8`` returns integers in THAT unit. Read as nanoseconds
    they put every tick a thousand times too early, in January 1970.
    """
    return index.as_unit("ns").asi8.copy()


def read_ticks(path: str | Path, timezone: str = "UTC") -> TickSeries:
    """Read a tick file.  Raises :class:`DataError` with a plain reason."""
    path = Path(path)
    if not path.is_file():
        raise DataError(f"There is no file at {path}.")
    delimiter, has_header, first = _sniff(path)
    warnings: list[str] = []
    frame = pd.read_csv(path, sep=delimiter, header=0 if has_header else None,
                        dtype=str, engine="c", skip_blank_lines=True,
                        encoding="utf-8-sig", compression="infer")
    if frame.empty:
        raise DataError(f"{path.name} has no rows.")
    if has_header:
        names = {_norm(c): c for c in frame.columns}
        time_col = next((names[n] for n in _TIME_NAMES if n in names), None)
        date_col = names.get("date")
        if time_col is not None and date_col is not None and time_col != date_col \
                and _norm(time_col) == "time":
            stamps = frame[date_col].astype(str) + " " + frame[time_col].astype(str)
        elif time_col is not None:
            stamps = frame[time_col]
        elif date_col is not None:
            stamps = frame[date_col]
        else:
            stamps = frame.iloc[:, 0]
        price_col = next((names[n] for n in _PRICE_NAMES if n in names), None)
        vol_col = next((names[n] for n in _VOLUME_NAMES if n in names), None)
        bid_col, ask_col = names.get("bid"), names.get("ask")
        price = (pd.to_numeric(frame[price_col], errors="coerce")
                 if price_col is not None else None)
        if price is not None and bid_col is not None and price.notna().mean() < 0.5:
            price = None          # MetaTrader writes an empty LAST on quote ticks
        if price is None:
            if bid_col is None or ask_col is None:
                raise DataError(
                    f"{path.name} has no trade price column (price, last, trade) "
                    f"and no bid and ask to take a mid from. Columns found: "
                    f"{', '.join(map(str, frame.columns))}.")
            bid = pd.to_numeric(frame[bid_col], errors="coerce")
            ask = pd.to_numeric(frame[ask_col], errors="coerce")
            price = (bid + ask) / 2.0
            warnings.append(
                "The file has quotes, not trades, so ticks are read at the MID of "
                "bid and ask. A stop filled at the mid is half a spread cheaper "
                "than one filled at the bid or ask: set the spread in the costs.")
        volume = (pd.to_numeric(frame[vol_col], errors="coerce").fillna(0.0)
                  if vol_col is not None else pd.Series(1.0, index=frame.index))
    else:
        if frame.shape[1] < 2:
            raise DataError(f"{path.name} needs at least a time and a price per row.")
        stamps = frame.iloc[:, 0]
        price = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
        volume = (pd.to_numeric(frame.iloc[:, -1], errors="coerce").fillna(0.0)
                  if frame.shape[1] >= 3 else pd.Series(1.0, index=frame.index))
    ts = _parse_times(stamps, timezone, warnings)
    price = price.to_numpy(dtype="float64")
    volume = volume.to_numpy(dtype="float64")
    keep = np.isfinite(price) & (price > 0.0) & (ts != np.iinfo("int64").min)
    dropped = int((~keep).sum())
    if dropped:
        warnings.append(f"{dropped:,} rows without a usable time or price were skipped.")
    ts, price, volume = ts[keep], price[keep], volume[keep]
    if ts.size == 0:
        raise DataError(f"No usable ticks were found in {path.name}.")
    if np.any(np.diff(ts) < 0):
        order = np.argsort(ts, kind="stable")     # keeps same-stamp trades in file order
        ts, price, volume = ts[order], price[order], volume[order]
        warnings.append("The rows were not in time order; they were sorted, keeping "
                        "trades that share a timestamp in the order the file lists them.")
    return TickSeries(ts, price, volume, source=str(path), warnings=warnings)


# ---------------------------------------------------------------------------
# Bars
# ---------------------------------------------------------------------------


def bars_from_ticks(ticks: TickSeries, timeframe: Timeframe | str,
                    instrument: Instrument) -> BarSeries:
    """Time bars from ticks: each bar holds the trades in [start, start + size).

    Bars are aligned to the UTC epoch, so a minute bar starts on the minute and
    an hour bar on the hour. Periods with no trade produce no bar.
    """
    tf = Timeframe.parse(timeframe) if isinstance(timeframe, str) else timeframe
    step = int(round(float(tf.approx_seconds) * 1e9))
    if tf.approx_seconds > 3600 or step <= 0:
        raise DataError("Bars can be built from ticks at one hour or finer.")
    if len(ticks) == 0:
        raise DataError("There are no ticks to build bars from.")
    bucket = (ticks.ts // step) * step
    starts = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    price = ticks.price
    opens = price[starts]
    highs = np.maximum.reduceat(price, starts)
    lows = np.minimum.reduceat(price, starts)
    ends = np.r_[starts[1:], price.size] - 1
    closes = price[ends]
    volume = np.add.reduceat(ticks.volume, starts)
    bars = BarSeries(ts=bucket[starts].astype("int64"), open=opens, high=highs,
                     low=lows, close=closes, volume=volume, instrument=instrument,
                     timeframe=tf, source=f"ticks:{ticks.source}")
    bars.meta["built_from_ticks"] = len(ticks)
    bars.meta["warnings"] = list(ticks.warnings)
    return bars


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def save_ticks(ticks: TickSeries, path: str | Path) -> int:
    """Write ticks as compressed NumPy arrays.  Returns the file size."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "wb") as fh:
        np.savez_compressed(fh, ts=ticks.ts, price=ticks.price, volume=ticks.volume)
    tmp.replace(path)
    return int(path.stat().st_size)


def load_ticks(path: str | Path) -> TickSeries:
    path = Path(path)
    try:
        with np.load(path) as data:
            return TickSeries(data["ts"], data["price"], data["volume"],
                              source=str(path))
    except (OSError, KeyError, ValueError) as exc:
        raise DataError(f"The tick file {path.name} could not be read.",
                        detail=repr(exc)) from exc


def tick_offsets(ticks: TickSeries, bar_ts: np.ndarray,
                 bar_seconds: float) -> np.ndarray:
    """``off[i]:off[i+1]`` are the ticks inside bar ``i``.

    A bar owns the trades from its open time up to the next bar's open -- or,
    for the last bar, up to its open plus its length. Ticks outside every bar
    belong to none.
    """
    bar_ts = np.asarray(bar_ts, dtype="int64")
    n = bar_ts.size
    off = np.empty(n + 1, dtype="int64")
    off[:n] = np.searchsorted(ticks.ts, bar_ts, side="left")
    last_end = bar_ts[-1] + int(round(bar_seconds * 1e9)) if n else 0
    off[n] = np.searchsorted(ticks.ts, last_end, side="left") if n else 0
    return off


def tick_coverage(ticks: TickSeries, bars: BarSeries,
                  off: np.ndarray) -> dict[str, Any]:
    """How well the ticks describe the bars: coverage and agreement."""
    n = len(bars)
    counts = np.diff(off)
    covered = counts > 0
    idx = np.flatnonzero(covered)
    disagree = 0
    if idx.size:
        starts = off[idx]
        p = ticks.price
        hi = np.maximum.reduceat(p, starts) if starts.size else np.empty(0)
        lo = np.minimum.reduceat(p, starts) if starts.size else np.empty(0)
        # reduceat runs to the next start; clamp the final group to its bar.
        last = idx[-1]
        seg = p[off[last]:off[last + 1]]
        hi[-1], lo[-1] = seg.max(), seg.min()
        tol = 1e-9 + 1e-9 * np.abs(np.asarray(bars.high)[idx])
        disagree = int(np.sum((np.abs(hi - np.asarray(bars.high)[idx]) > tol)
                              | (np.abs(lo - np.asarray(bars.low)[idx]) > tol)))
    return {"bars": n, "bars_with_ticks": int(covered.sum()),
            "ticks_used": int(counts.sum()), "disagree": disagree}
