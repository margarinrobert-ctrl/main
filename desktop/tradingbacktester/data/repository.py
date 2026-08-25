"""The dataset library: imported bars stored on disk with an index over them.

A user imports a CSV once and then expects to pick the dataset out of a list
for the rest of the year, so imported bars are copied into the workspace in a
fast binary form and the original file is never depended on again.

Three decisions worth explaining:

*Format.*  Parquet when ``pyarrow`` can be imported, gzip-compressed CSV
otherwise.  Parquet is roughly ten times faster to read and half the size, but
it is a heavy optional dependency and a frozen build might not carry it; the
CSV fallback means a workspace written by one build is always readable by the
other, because the format is recorded per dataset rather than assumed.

*Atomicity.*  Every write goes to a temporary file in the destination directory
and is then moved into place with :func:`os.replace`.  A power cut during an
import leaves either the old file or the new one, never a half-written one, and
the index is written the same way.

*The index is a cache, not the truth.*  Each dataset also gets a small
``<id>.meta.json`` sidecar.  If ``index.json`` is lost or damaged the library
can be rebuilt by scanning the folder, and a dataset copied in from another
machine is adopted on the next :meth:`DatasetRepository.refresh`.  Conversely
an index row whose data file has been deleted from underneath us is dropped
with a warning rather than raising: a missing file is the user's doing, and the
application's job is to notice, not to fall over.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from ..config import Workspace
from ..core.errors import DataError, InsufficientDataError, StorageError, TimeframeError
from ..core.timeframe import Timeframe
from .models import BarSeries, Instrument

log = logging.getLogger(__name__)

#: Name of the index inside the workspace data directory.
INDEX_FILENAME = "index.json"

#: Columns of a stored dataset file, in order.
_COLUMNS: tuple[str, ...] = ("ts", "open", "high", "low", "close", "volume")

_SCHEMA_VERSION = 1
_ID_LENGTH = 12
_HASH_CHUNK = 1 << 20

#: Cached answer to "can we write parquet?".  ``None`` means "not asked yet";
#: the check is deferred so importing this module never pulls in pyarrow.
_parquet_ok: bool | None = None


def parquet_available() -> bool:
    """True when parquet files can be written and read on this installation.

    Both halves are checked at once because a pyarrow that imports but cannot
    round-trip a frame is worse than no pyarrow at all -- it would produce a
    library of files that cannot be opened.
    """
    global _parquet_ok
    if _parquet_ok is None:
        try:
            import pyarrow  # noqa: F401
            import pyarrow.parquet  # noqa: F401

            _parquet_ok = True
            log.debug("pyarrow is available; datasets will be stored as parquet")
        except Exception as exc:  # ImportError, but a broken build can raise others
            _parquet_ok = False
            log.info("pyarrow is not available (%s); datasets will be stored as "
                     "gzip-compressed CSV", exc)
    return _parquet_ok


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@dataclass
class DatasetMeta:
    """What the library knows about one stored dataset without opening it.

    ``checksum`` is the SHA-256 of the raw bytes of the *stored* file, taken
    after it was written.  It detects a file that has been truncated, swapped
    or corrupted in place; it is deliberately not a hash of the bar values, so
    it can be verified without decoding anything.
    """

    id: str
    name: str
    symbol: str
    timeframe: str
    """Timeframe label, e.g. ``"5m"`` -- parse with :meth:`Timeframe.parse`."""
    bar_count: int = 0
    start_ts: int = 0
    end_ts: int = 0
    source_path: str = ""
    """Where the bars were imported from; informational only."""
    imported_at: str = ""
    """ISO-8601 UTC timestamp of the import."""
    checksum: str = ""
    notes: str = ""
    filename: str = ""
    """Data file name, relative to the workspace data directory."""
    storage_format: str = "parquet"
    """``parquet`` or ``csv.gz``."""
    file_size: int = 0
    instrument: dict[str, Any] = field(default_factory=dict)
    """Full contract specification, so bars reload with the right point value
    even if the instrument has since been renamed or deleted from the catalogue."""
    import_warnings: list[str] = field(default_factory=list)
    """Caveats the loader raised at import time -- a derived low, a missing
    volume column, dropped rows.  Stored with the dataset because a user loads
    it from the library many times and imports it once, and a caveat that
    disappears after the first session is a caveat nobody acts on."""

    # -- convenience -------------------------------------------------------

    @property
    def start(self) -> pd.Timestamp | None:
        return pd.Timestamp(self.start_ts, tz="UTC") if self.bar_count else None

    @property
    def end(self) -> pd.Timestamp | None:
        return pd.Timestamp(self.end_ts, tz="UTC") if self.bar_count else None

    def timeframe_obj(self) -> Timeframe:
        """The stored timeframe as a :class:`Timeframe`.

        Falls back to inferring one from the label rather than raising, because
        a metadata row is not worth losing a dataset over.
        """
        try:
            return Timeframe.parse(self.timeframe)
        except TimeframeError:
            log.warning("Dataset %s has an unreadable timeframe %r; treating it "
                        "as 1 day", self.id, self.timeframe)
            return Timeframe.parse("1d")

    def instrument_obj(self) -> Instrument:
        """The stored contract specification, or a sane default for the symbol."""
        if self.instrument:
            try:
                return Instrument.from_dict(self.instrument)
            except (DataError, TypeError, ValueError) as exc:
                log.warning("Dataset %s has an unreadable instrument record (%s); "
                            "falling back to defaults for %s", self.id, exc, self.symbol)
        from .instruments import default_instrument_for

        seeded = default_instrument_for(self.symbol)
        return seeded if seeded is not None else Instrument(symbol=self.symbol or "UNKNOWN")

    def describe(self) -> str:
        """One line for a list widget or a log message."""
        if not self.bar_count:
            return f"{self.name} ({self.symbol} {self.timeframe}): empty"
        return (f"{self.name} ({self.symbol} {self.timeframe}): "
                f"{self.bar_count:,} bars, "
                f"{pd.Timestamp(self.start_ts, tz='UTC'):%Y-%m-%d} to "
                f"{pd.Timestamp(self.end_ts, tz='UTC'):%Y-%m-%d}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetMeta":
        known = set(cls.__dataclass_fields__)
        payload = {k: v for k, v in dict(data).items() if k in known}
        if not payload.get("id"):
            raise ValueError("a dataset record needs an id")
        payload.setdefault("name", str(payload["id"]))
        payload.setdefault("symbol", "")
        payload.setdefault("timeframe", "1d")
        # Older or hand-edited rows may carry numbers as strings.
        for key in ("bar_count", "start_ts", "end_ts", "file_size"):
            if key in payload and payload[key] is not None:
                payload[key] = int(payload[key])
        if not isinstance(payload.get("instrument", {}), dict):
            payload["instrument"] = {}
        return cls(**payload)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class DatasetRepository:
    """The library of imported datasets living under ``workspace/data``.

    Every mutating method persists immediately: there is no "save the library"
    step for the user to forget.  All public methods are safe to call from a
    worker thread; a single lock serialises index updates, which is enough
    because the expensive part -- reading a data file -- does not touch the
    index.
    """

    def __init__(self, workspace: Workspace | str | Path) -> None:
        self.workspace = workspace if isinstance(workspace, Workspace) else Workspace(Path(workspace))
        self.dir: Path = self.workspace.data
        self.index_path: Path = self.dir / INDEX_FILENAME
        self._items: dict[str, DatasetMeta] = {}
        self._lock = threading.RLock()
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(
                f"The data folder could not be created at {self.dir}.\n\n"
                f"Choose a different workspace from File > Change Workspace.",
                detail=repr(exc),
            ) from exc
        self._load_index()

    # -- container behaviour ---------------------------------------------

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[DatasetMeta]:
        return iter(self.list())

    def __contains__(self, dataset_id: object) -> bool:
        return str(dataset_id) in self._items

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<DatasetRepository {len(self._items)} datasets at {self.dir}>"

    # -- queries -----------------------------------------------------------

    def list(self) -> list[DatasetMeta]:
        """Every dataset whose file is still on disk, newest import first.

        Rows whose data file has gone missing are dropped here rather than
        being returned and then failing to open: the list a user sees should
        only contain datasets they can actually load.
        """
        with self._lock:
            self._prune_missing()
            return sorted(self._items.values(),
                          key=lambda m: (m.imported_at, m.name), reverse=True)

    def get(self, dataset_id: str) -> DatasetMeta:
        """Metadata for one dataset.

        Raises
        ------
        DataError
            If the id is unknown or its file has been deleted.
        """
        key = str(dataset_id)
        with self._lock:
            meta = self._items.get(key)
            if meta is None:
                raise DataError(
                    "That dataset is no longer in the library. It may have been "
                    "removed since this window was opened.",
                    detail=f"id={key!r} known={sorted(self._items)}")
            if not self.path_for(meta).exists():
                self._drop(key, "its data file is missing")
                raise DataError(
                    f"The data file for '{meta.name}' is missing from the "
                    f"workspace, so it has been removed from the library. "
                    f"Import it again to restore it.",
                    detail=f"expected {self.path_for(meta)}")
            return meta

    def exists(self, dataset_id: str) -> bool:
        with self._lock:
            meta = self._items.get(str(dataset_id))
            return meta is not None and self.path_for(meta).exists()

    def find_by_symbol(self, symbol: str,
                       timeframe: Timeframe | str | None = None) -> list[DatasetMeta]:
        """Every dataset for a symbol, optionally filtered to one timeframe."""
        key = str(symbol).strip().upper()
        label = None
        if timeframe is not None:
            label = (timeframe.label if isinstance(timeframe, Timeframe)
                     else Timeframe.parse(str(timeframe)).label)
        return [m for m in self.list()
                if m.symbol.upper() == key and (label is None or m.timeframe == label)]

    def path_for(self, meta: DatasetMeta | str) -> Path:
        """Absolute path of a dataset's data file.

        Accepts either the metadata object or a bare dataset id, because most
        callers are holding an id from a combo box rather than the record.
        """
        if isinstance(meta, str):
            meta = self.get(meta)
        return self.dir / (meta.filename or f"{meta.id}.{meta.storage_format}")

    def sidecar_for(self, meta: DatasetMeta | str) -> Path:
        """Absolute path of a dataset's metadata sidecar."""
        dataset_id = meta if isinstance(meta, str) else meta.id
        return self.dir / f"{dataset_id}.meta.json"

    def total_bars(self) -> int:
        return sum(m.bar_count for m in self.list())

    # -- loading -----------------------------------------------------------

    def load_bars(self, dataset_id: str) -> BarSeries:
        """Read a stored dataset back into a :class:`BarSeries`.

        Raises
        ------
        DataError
            If the file is missing, unreadable, or does not hold the columns a
            dataset is supposed to have.
        """
        meta = self.get(dataset_id)
        path = self.path_for(meta)
        frame = _read_frame(path, meta.storage_format)

        missing = [c for c in _COLUMNS if c not in frame.columns]
        if missing:
            raise DataError(
                f"The stored file for '{meta.name}' is missing the "
                f"{', '.join(missing)} column(s) and cannot be read. "
                f"Import the original data again.",
                detail=f"path={path} columns={list(frame.columns)}")

        try:
            ts = np.ascontiguousarray(frame["ts"].to_numpy(), dtype="int64")
            cols = {name: np.ascontiguousarray(frame[name].to_numpy(), dtype="float64")
                    for name in ("open", "high", "low", "close", "volume")}
        except (TypeError, ValueError) as exc:
            raise DataError(
                f"The stored file for '{meta.name}' holds values that are not "
                f"numbers and cannot be read.",
                detail=f"path={path} {exc!r}") from exc

        bars = BarSeries(
            ts=ts, open=cols["open"], high=cols["high"], low=cols["low"],
            close=cols["close"], volume=cols["volume"],
            instrument=meta.instrument_obj(), timeframe=meta.timeframe_obj(),
            source=meta.source_path or str(path),
            meta={"dataset_id": meta.id, "dataset_name": meta.name,
                  "imported_at": meta.imported_at, "notes": meta.notes,
                  # Replayed so the quality report repeats the import caveats
                  # every time the dataset is opened, not only on the day it
                  # was imported.
                  "warnings": list(meta.import_warnings)},
        )
        log.debug("Loaded dataset %s (%d bars) from %s", meta.id, len(bars), path)
        return bars

    def verify(self, dataset_id: str) -> bool:
        """Re-hash a dataset's file and compare it with the stored checksum.

        Returns ``True`` when they match or when no checksum was recorded.
        """
        meta = self.get(dataset_id)
        if not meta.checksum:
            return True
        actual = _sha256_file(self.path_for(meta))
        if actual != meta.checksum:
            log.warning("Checksum mismatch for dataset %s (%s): stored %s, actual %s",
                        meta.id, meta.name, meta.checksum[:12], actual[:12])
            return False
        return True

    # -- mutation ----------------------------------------------------------

    def add_from_bars(self, bars: BarSeries, name: str = "",
                      source_path: str = "", notes: str = "") -> DatasetMeta:
        """Copy a loaded :class:`BarSeries` into the library.

        Parameters
        ----------
        bars:
            The bars to store.  Must not be empty.
        name:
            Display name.  Defaults to ``"SYMBOL TIMEFRAME"``.
        source_path:
            Where the bars came from, recorded for the user's benefit.
        notes:
            Free text shown alongside the dataset.

        Returns
        -------
        DatasetMeta
            The row that was added to the index.
        """
        if bars is None or len(bars) == 0:
            raise InsufficientDataError(
                "There are no bars to save, so nothing was added to the library.")

        symbol = bars.instrument.symbol
        label = bars.timeframe.label
        display = str(name).strip() or f"{symbol} {label}"
        dataset_id = self._new_id()
        fmt = "parquet" if parquet_available() else "csv.gz"
        filename = f"{_slug(display or symbol)}-{dataset_id}.{fmt}"
        path = self.dir / filename

        frame = pd.DataFrame({
            "ts": np.asarray(bars.ts, dtype="int64"),
            "open": bars.open, "high": bars.high, "low": bars.low,
            "close": bars.close, "volume": bars.volume,
        }, columns=list(_COLUMNS))
        import_warnings = [str(w) for w in (bars.meta.get("warnings") or ())]

        _write_frame(frame, path, fmt)
        try:
            checksum = _sha256_file(path)
            size = path.stat().st_size
        except OSError as exc:  # pragma: no cover - the write just succeeded
            raise StorageError(
                f"'{display}' was written to the library but could not be read "
                f"back to verify it.", detail=repr(exc)) from exc

        meta = DatasetMeta(
            id=dataset_id, name=display, symbol=symbol, timeframe=label,
            bar_count=len(bars), start_ts=int(bars.ts[0]), end_ts=int(bars.ts[-1]),
            source_path=str(source_path or bars.source or ""),
            imported_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            checksum=checksum, notes=str(notes), filename=filename,
            storage_format=fmt, file_size=int(size),
            instrument=bars.instrument.to_dict(),
            import_warnings=import_warnings,
        )
        with self._lock:
            self._items[meta.id] = meta
            self._write_sidecar(meta)
            self._save_index()
        log.info("Added dataset %s: %s", meta.id, meta.describe())
        return meta

    def remove(self, dataset_id: str) -> None:
        """Delete a dataset and its file from the workspace.

        A file that has already gone is not an error -- the outcome the user
        asked for is the outcome they get.
        """
        with self._lock:
            meta = self._items.get(str(dataset_id))
            if meta is None:
                raise DataError("That dataset is not in the library, so there is "
                                "nothing to remove.")
            for target in (self.path_for(meta), self.sidecar_for(meta)):
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
                except OSError as exc:
                    raise StorageError(
                        f"'{meta.name}' could not be deleted.\n\n"
                        f"The file may be open in another program.",
                        detail=f"{target}: {exc!r}") from exc
            del self._items[meta.id]
            self._save_index()
        log.info("Removed dataset %s (%s)", meta.id, meta.name)

    def rename(self, dataset_id: str, name: str) -> DatasetMeta:
        """Change a dataset's display name.  The file on disk keeps its name."""
        clean = str(name).strip()
        if not clean:
            raise DataError("A dataset needs a name.")
        with self._lock:
            meta = self.get(dataset_id)
            meta.name = clean
            self._write_sidecar(meta)
            self._save_index()
            return meta

    def set_notes(self, dataset_id: str, notes: str) -> DatasetMeta:
        """Replace a dataset's free-text notes."""
        with self._lock:
            meta = self.get(dataset_id)
            meta.notes = str(notes)
            self._write_sidecar(meta)
            self._save_index()
            return meta

    def refresh(self) -> list[DatasetMeta]:
        """Re-read the index, drop vanished datasets and adopt new files.

        Called when the user has been editing the workspace folder behind the
        application's back -- copying a dataset in from another machine, or
        deleting one to free space.
        """
        with self._lock:
            self._load_index()
            self._adopt_orphans()
            self._prune_missing()
            self._save_index()
            return self.list()

    # -- index persistence -------------------------------------------------

    def _load_index(self) -> None:
        """Read ``index.json``, rebuilding from sidecars if it is unusable."""
        if not self.index_path.exists():
            self._items = {}
            self._adopt_orphans()
            if self._items:
                log.info("No dataset index at %s; recovered %d dataset(s) from "
                         "their sidecar files", self.index_path, len(self._items))
                self._save_index()
            return

        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            log.error("The dataset index at %s could not be read (%s); it will be "
                      "rebuilt from the files in that folder", self.index_path, exc)
            self._quarantine_index()
            self._items = {}
            self._adopt_orphans()
            self._save_index()
            return

        records = payload.get("datasets") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            log.error("The dataset index at %s is not in the expected shape; it "
                      "will be rebuilt", self.index_path)
            self._quarantine_index()
            self._items = {}
            self._adopt_orphans()
            self._save_index()
            return

        items: dict[str, DatasetMeta] = {}
        skipped = 0
        for record in records:
            if not isinstance(record, dict):
                skipped += 1
                continue
            try:
                meta = DatasetMeta.from_dict(record)
            except (TypeError, ValueError, KeyError) as exc:
                skipped += 1
                log.warning("Skipping unreadable dataset record %r: %s", record, exc)
                continue
            items[meta.id] = meta
        if skipped:
            log.warning("%d dataset record(s) in %s could not be read and were "
                        "ignored", skipped, self.index_path)
        self._items = items

    def _save_index(self) -> None:
        payload = {
            "schema": _SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "datasets": [m.to_dict() for m in self._items.values()],
        }
        _atomic_write_text(self.index_path, json.dumps(payload, indent=2))

    def _write_sidecar(self, meta: DatasetMeta) -> None:
        """Mirror one row next to its data file so the index can be rebuilt."""
        try:
            _atomic_write_text(self.sidecar_for(meta), json.dumps(meta.to_dict(), indent=2))
        except StorageError as exc:
            # The sidecar is a recovery aid; losing it must not fail an import.
            log.warning("Could not write the sidecar for dataset %s: %s", meta.id, exc)

    def _quarantine_index(self) -> None:
        broken = self.index_path.with_suffix(".json.corrupt")
        try:
            if broken.exists():
                broken.unlink()
            self.index_path.replace(broken)
        except OSError as exc:  # pragma: no cover - unusual filesystem state
            log.warning("The damaged index could not be moved aside: %r", exc)

    def _drop(self, dataset_id: str, why: str) -> None:
        """Forget one dataset, tidying its sidecar, and persist the change."""
        meta = self._items.pop(dataset_id, None)
        if meta is None:  # pragma: no cover - defensive
            return
        log.warning("Dropping dataset %s ('%s') from the library because %s",
                    meta.id, meta.name, why)
        try:
            self.sidecar_for(meta).unlink()
        except OSError:
            pass
        self._save_index()

    def _prune_missing(self) -> None:
        """Drop index rows whose data file is no longer on disk."""
        gone = [key for key, meta in self._items.items()
                if not self.path_for(meta).exists()]
        for key in gone:
            self._drop(key, "its data file is no longer on disk")

    def _adopt_orphans(self) -> None:
        """Pick up datasets present on disk but absent from the index."""
        try:
            sidecars = sorted(self.dir.glob("*.meta.json"))
        except OSError as exc:  # pragma: no cover - unreadable directory
            log.warning("The data folder %s could not be listed: %r", self.dir, exc)
            return
        for sidecar in sidecars:
            try:
                meta = DatasetMeta.from_dict(
                    json.loads(sidecar.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                log.warning("Ignoring unreadable dataset sidecar %s: %s", sidecar.name, exc)
                continue
            if meta.id in self._items:
                continue
            if not self.path_for(meta).exists():
                # A sidecar without its data file is litter from a failed
                # import or a half-finished manual delete.
                log.warning("Ignoring sidecar %s: its data file %s is missing",
                            sidecar.name, meta.filename)
                continue
            log.info("Adopted dataset %s ('%s') found in the data folder",
                     meta.id, meta.name)
            self._items[meta.id] = meta

    def _new_id(self) -> str:
        """A short, collision-free identifier that is safe in a filename."""
        while True:
            candidate = uuid.uuid4().hex[:_ID_LENGTH]
            if candidate not in self._items:
                return candidate


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    """A filesystem-safe fragment of a dataset name, for a browsable data folder."""
    out = []
    for ch in str(text).strip():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_.":
            out.append("-")
    slug = "".join(out).strip("-").replace("--", "-")[:48]
    return slug or "dataset"


def _write_frame(frame: pd.DataFrame, path: Path, fmt: str) -> None:
    """Write a dataset file atomically in the requested format."""
    tmp: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                        dir=str(path.parent))
        os.close(fd)
        tmp = Path(tmp_name)
        if fmt == "parquet":
            frame.to_parquet(tmp, engine="pyarrow", index=False, compression="snappy")
        else:
            # ``lineterminator`` keeps the bytes -- and therefore the checksum --
            # identical on Windows and POSIX for the same input.
            frame.to_csv(tmp, index=False, compression="gzip", lineterminator="\n")
        os.replace(tmp, path)
        tmp = None
    except (OSError, ValueError, ImportError) as exc:
        raise StorageError(
            f"The dataset could not be written to {path.parent}.\n\n"
            f"Check that there is free space and that you have permission to "
            f"write to that folder.",
            detail=f"{path}: {exc!r}") from exc
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass


def _read_frame(path: Path, fmt: str) -> pd.DataFrame:
    """Read a dataset file, tolerating a format label that disagrees with reality."""
    if not path.exists():
        raise DataError(
            f"The data file {path.name} is missing from the workspace.",
            detail=str(path))
    actual = fmt
    if path.suffix == ".parquet":
        actual = "parquet"
    elif path.name.endswith(".csv.gz"):
        actual = "csv.gz"
    try:
        if actual == "parquet":
            if not parquet_available():
                raise DataError(
                    f"'{path.name}' is stored as parquet, which needs the "
                    f"'pyarrow' package. Install pyarrow, or import the original "
                    f"data again to store it as CSV.",
                    detail=str(path))
            return pd.read_parquet(path, engine="pyarrow")
        # ``float_precision="round_trip"`` is what makes the CSV fallback
        # lossless.  pandas' default parser is fast but not correctly rounded,
        # so a price can come back one unit in the last place away from the
        # value that was written, and a reloaded dataset would then produce a
        # backtest that disagrees with the freshly imported one.
        return pd.read_csv(path, compression="gzip", float_precision="round_trip")
    except DataError:
        raise
    except (OSError, ValueError, EOFError, ImportError) as exc:
        raise DataError(
            f"'{path.name}' could not be read. The file may be damaged or "
            f"incomplete; import the original data again.",
            detail=f"{path}: {exc!r}") from exc


def _sha256_file(path: Path) -> str:
    """SHA-256 of a file's raw bytes, read in chunks so size does not matter."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            while True:
                chunk = handle.read(_HASH_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise StorageError(
            f"{path.name} could not be read to check it.", detail=repr(exc)) from exc
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text via a temporary file in the same directory, then rename."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                        dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                # fsync before the rename is what actually makes the write
                # survive a power cut, rather than merely a crashed process.
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise StorageError(
            f"The file {path.name} could not be saved to {path.parent}.\n\n"
            f"Check that the folder exists and that you have permission to "
            f"write to it.",
            detail=repr(exc)) from exc


def copy_into_workspace(repo: DatasetRepository, source: Path) -> Path:
    """Copy an arbitrary file into the workspace data folder, keeping its name.

    Used by the import dialog when the user asks to keep a copy of the original
    CSV alongside the converted dataset.  Returns the destination path.
    """
    src = Path(source).expanduser()
    dest = repo.dir / src.name
    counter = 1
    while dest.exists():
        dest = repo.dir / f"{src.stem}-{counter}{src.suffix}"
        counter += 1
    try:
        shutil.copy2(src, dest)
    except OSError as exc:
        raise StorageError(
            f"'{src.name}' could not be copied into the workspace.",
            detail=repr(exc)) from exc
    return dest
