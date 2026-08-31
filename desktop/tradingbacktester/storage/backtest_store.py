"""Saved backtest runs: one folder per run, readable a year later.

A saved run has to survive three things that a naive ``pickle`` of the result
object does not: a new application version, a user poking at the files, and a
crash halfway through writing one.  So each run is a small folder of plain
formats:

===================  =====================================================
``meta.json``        Identity, the headline numbers, the full metrics dict,
                     the warnings, and which dataset the run used.
``config.json``      The :class:`~tradingbacktester.core.types.BacktestConfig`
                     -- costs, risk, session, exits, execution.
``strategy.json``    The strategy exactly as it was run, in the same shape
                     :class:`~tradingbacktester.strategy.spec.StrategySpec`
                     reads, so a saved run can be re-opened and re-run.
``trades.json``      Every completed trade, enums written as their values.
``curves.npz``       The per-bar equity, balance, drawdown and exposure
                     arrays, in NumPy's own format so they come back
                     bit-for-bit identical.
===================  =====================================================

**Bars are not saved.**  A year of one-minute bars is hundreds of megabytes and
it is already sitting in ``data/``; copying it into every saved run would fill a
disk for nothing.  Instead each run records the dataset id, the symbol, the
timeframe and the first and last timestamp it covered, which is enough for
:meth:`BacktestStore.load_bars` to fetch the same bars back from the dataset
repository when they are wanted.  A loaded :class:`BacktestResult` therefore has
``bars is None``, and everything in this module is written to cope with that.
The comparison view works entirely from the curves and the metrics, both of
which *are* saved, so comparing saved runs needs no bars at all; the price chart
does need them, which is why the caller is given the dataset reference.

*Atomicity.*  A run is built inside a hidden ``.<id>.partial`` folder and moved
into place with a single :func:`os.replace`.  A crash mid-save leaves a partial
folder that :meth:`BacktestStore.list` ignores and the next save cleans up --
never a half-written run in the browser.  Later edits to a single file (a
relabel) use the temp-file-then-replace dance on that one file.

*A damaged run is an entry, not an exception.*  :meth:`BacktestStore.list` never
raises for a bad folder: it returns a :class:`SavedRunMeta` with
``readable=False`` and the reason in ``problem``, so the browser can show the
run greyed out with a Delete button beside it instead of refusing to open.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

from ..config import APP_VERSION, Workspace
from ..core.errors import StorageError
from ..core.types import (
    BacktestConfig,
    CommissionMode,
    CostModel,
    ExecutionSettings,
    ExitReason,
    ExitSettings,
    IntrabarPriority,
    RiskSettings,
    SessionSettings,
    Side,
    SignalExecution,
    SizingMode,
    SlippageMode,
    SpreadMode,
    Trade,
)
from ..engine.results import BacktestResult, EquityCurves

log = logging.getLogger(__name__)

__all__ = [
    "META_FILENAME",
    "CONFIG_FILENAME",
    "STRATEGY_FILENAME",
    "TRADES_FILENAME",
    "CURVES_FILENAME",
    "NO_BARS_NOTE",
    "DatasetRef",
    "SavedRunMeta",
    "BacktestStore",
    "config_to_dict",
    "config_from_dict",
    "trade_to_dict",
    "trade_from_dict",
]

META_FILENAME = "meta.json"
CONFIG_FILENAME = "config.json"
STRATEGY_FILENAME = "strategy.json"
TRADES_FILENAME = "trades.json"
CURVES_FILENAME = "curves.npz"

#: Appended to a loaded run's warnings so the reason the chart is empty is on
#: screen rather than in this docstring.
NO_BARS_NOTE = ("The price bars are not stored with a saved run. Load the "
                "dataset it names to see the chart; the equity curve, the "
                "trades and the metrics are all here.")

_SCHEMA_VERSION = 1
_PARTIAL_SUFFIX = ".partial"
_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]")
_MAX_ID_LENGTH = 64

#: The curve arrays, in the order :class:`EquityCurves` declares them.
_CURVE_KEYS: tuple[str, ...] = ("ts", "equity", "balance", "drawdown",
                                "drawdown_pct", "exposure", "peak")

#: Enum-valued fields of the configuration blocks, by field name.  Used to turn
#: the saved strings back into enum members without hard-coding a reconstruction
#: for every block.
_ENUM_FIELDS: dict[str, type[Enum]] = {
    "sizing_mode": SizingMode,
    "commission_mode": CommissionMode,
    "spread_mode": SpreadMode,
    "slippage_mode": SlippageMode,
    "signal_execution": SignalExecution,
    "intrabar_priority": IntrabarPriority,
}

_TRADE_INT_FIELDS = ("id", "entry_bar", "entry_ts", "exit_bar", "exit_ts", "bars_held")
_TRADE_OPTIONAL_FLOATS = ("stop_loss", "take_profit", "r_multiple")


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


@dataclass
class DatasetRef:
    """Which bars a saved run was computed from.

    This is the whole reason a saved run can be small: rather than copying the
    bars, a run points back at the dataset in the library and records enough to
    recognise it (and to notice when it is no longer the same one).
    """

    dataset_id: str = ""
    dataset_name: str = ""
    symbol: str = ""
    timeframe_label: str = ""
    bar_count: int = 0
    start_ts: int = 0
    """UTC nanoseconds of the first bar simulated; ``0`` when unknown."""
    end_ts: int = 0
    """UTC nanoseconds of the last bar simulated; ``0`` when unknown."""
    source: str = ""
    """Where the bars came from -- a file path, a provider name, ``synthetic``."""
    instrument: dict[str, Any] = field(default_factory=dict)
    """The contract specification in force during the run, so a reloaded run
    still knows its point value even if the instrument has since been edited."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> "DatasetRef":
        d = dict(d or {})
        known = set(DatasetRef.__dataclass_fields__)
        clean = {k: v for k, v in d.items() if k in known}
        for key in ("bar_count", "start_ts", "end_ts"):
            clean[key] = _as_int(clean.get(key), 0)
        for key in ("dataset_id", "dataset_name", "symbol", "timeframe_label", "source"):
            clean[key] = str(clean.get(key) or "")
        inst = clean.get("instrument")
        clean["instrument"] = inst if isinstance(inst, dict) else {}
        return DatasetRef(**clean)

    def describe(self) -> str:
        """One line naming the data, for a status bar or a tooltip."""
        parts = [p for p in (self.symbol, self.timeframe_label) if p]
        head = " ".join(parts) or self.dataset_name or "unknown data"
        if self.bar_count:
            head += f", {self.bar_count:,} bars"
        span = _range_text(self.start_ts, self.end_ts)
        return f"{head} ({span})" if span else head


@dataclass
class SavedRunMeta:
    """One row of the saved-run browser.

    Everything here is read from ``meta.json`` alone, so listing a hundred runs
    opens a hundred small files and never touches a curve or a trade list.

    An entry with ``readable=False`` is a folder that could not be understood:
    ``problem`` says why, the numeric fields are zero, and the only sensible
    thing the browser can offer for it is Delete.
    """

    id: str
    label: str = ""
    strategy_name: str = ""
    instrument_symbol: str = ""
    timeframe_label: str = ""
    created_at: str = ""
    """ISO-8601 UTC timestamp of the moment the run was saved."""
    trade_count: int = 0
    net_profit: float = 0.0
    return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0

    # -- everything below is extra context, not required by the browser -----
    strategy_id: str = ""
    dataset_id: str = ""
    dataset_name: str = ""
    bar_count: int = 0
    start_ts: int = 0
    end_ts: int = 0
    duration_seconds: float = 0.0
    app_version: str = ""
    size_bytes: int = 0
    path: str = ""
    readable: bool = True
    problem: str = ""

    def date_range_text(self) -> str:
        """``2023-01-02 - 2023-12-29``, or an empty string when unknown."""
        return _range_text(self.start_ts, self.end_ts)

    def summary_line(self) -> str:
        if not self.readable:
            return f"{self.id}: unreadable ({self.problem})"
        return (f"{self.label or self.id}: {self.strategy_name} on "
                f"{self.instrument_symbol} {self.timeframe_label}, "
                f"{self.trade_count} trades, net {self.net_profit:,.2f} "
                f"({self.return_pct:.2f}%)")


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


class BacktestStore:
    """The library of saved runs under ``<workspace>/backtests``.

    Parameters
    ----------
    workspace:
        The workspace to store runs in.  A plain path is accepted as well, for
        tests and for tools that have a directory rather than a workspace.
    """

    def __init__(self, workspace: Workspace | str | Path) -> None:
        space = (workspace if isinstance(workspace, Workspace)
                 else Workspace(Path(workspace)))
        self.workspace: Workspace = space
        self.dir: Path = space.backtests

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"<BacktestStore at {self.dir}>"

    # -- locations ---------------------------------------------------------

    def path_for(self, run_id: str) -> Path:
        """The folder a run lives in, whether or not it exists."""
        return self.dir / _safe_id(run_id)

    def exists(self, run_id: str) -> bool:
        return (self.path_for(run_id) / META_FILENAME).is_file()

    # -- saving ------------------------------------------------------------

    def save(self, result: BacktestResult, label: str = "") -> str:
        """Write ``result`` to a new run folder and return its id.

        A run is always written under a *fresh* id: saving the same result twice
        under two labels gives two runs rather than silently replacing the
        first.  The id from ``result.run_id`` is reused when it is free, so the
        folder name matches the id the rest of the session is using.
        """
        if result is None:
            raise StorageError("There is no backtest result to save.")

        run_id = self._reserve_id(getattr(result, "run_id", ""))
        final = self.dir / run_id
        staging = self.dir / f".{run_id}{_PARTIAL_SUFFIX}"
        text = (str(label).strip() or str(getattr(result, "label", "")).strip()
                or str(getattr(result, "strategy_name", "")).strip() or "Backtest")

        self._prepare_dir()
        self._clear_stale_partials()
        try:
            staging.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            raise StorageError(
                f"The saved run could not be created in {self.dir}.\n\n"
                f"Check that you have permission to write to the workspace.",
                detail=repr(exc)) from exc

        try:
            meta = self._build_meta(result, run_id, text)
            _write_json(staging / META_FILENAME, meta)
            _write_json(staging / CONFIG_FILENAME,
                        {"schema": _SCHEMA_VERSION,
                         "config": config_to_dict(result.config)})
            _write_json(staging / STRATEGY_FILENAME,
                        _jsonable(result.strategy_dict or {}))
            _write_json(staging / TRADES_FILENAME,
                        {"schema": _SCHEMA_VERSION,
                         "count": len(result.trades),
                         "trades": [trade_to_dict(t) for t in result.trades]})
            _write_curves(staging / CURVES_FILENAME, result.curves)
            os.replace(staging, final)
        except StorageError:
            _remove_tree(staging)
            raise
        except OSError as exc:
            _remove_tree(staging)
            raise StorageError(
                f"The backtest '{text}' could not be saved.\n\n"
                f"Check that there is free space on the drive holding the "
                f"workspace and that you have permission to write to it.",
                detail=repr(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - a bad result must not corrupt the library
            _remove_tree(staging)
            raise StorageError(
                f"The backtest '{text}' could not be saved because part of the "
                f"result could not be written to a file.",
                detail=f"{type(exc).__name__}: {exc}") from exc

        log.info("Saved backtest '%s' as %s (%d trades)", text, run_id,
                 len(result.trades))
        return run_id

    def set_label(self, run_id: str, label: str) -> SavedRunMeta:
        """Rename a saved run in place and return its refreshed row."""
        text = str(label).strip()
        if not text:
            raise StorageError("A saved run needs a label.")
        folder = self._require_dir(run_id)
        payload = self._read_meta_file(folder)
        payload["label"] = text
        _write_json(folder / META_FILENAME, payload)
        return self._row_from_payload(folder, payload)

    # -- listing -----------------------------------------------------------

    def list(self) -> list[SavedRunMeta]:
        """Every saved run, newest first, damaged ones included.

        Never raises for a bad run folder.  It does raise
        :class:`StorageError` when the ``backtests`` folder itself exists but
        cannot be listed at all, because that is a permissions problem the user
        has to fix rather than a run to skip.
        """
        if not self.dir.exists():
            return []
        try:
            entries = sorted(self.dir.iterdir())
        except OSError as exc:
            raise StorageError(
                f"The saved runs in {self.dir} could not be listed.\n\n"
                f"Check that you have permission to read the workspace folder.",
                detail=repr(exc)) from exc

        rows: list[SavedRunMeta] = []
        for entry in entries:
            name = entry.name
            if name.startswith(".") or name.endswith(_PARTIAL_SUFFIX):
                continue  # a save that is still in flight, or was interrupted
            if not entry.is_dir():
                continue
            rows.append(self._row_for_dir(entry))
        rows.sort(key=lambda r: (r.created_at, r.id), reverse=True)
        return rows

    def load_meta(self, run_id: str) -> SavedRunMeta:
        """One run's summary row, without reading its trades or curves."""
        folder = self._require_dir(run_id)
        return self._row_for_dir(folder)

    def dataset_ref(self, run_id: str) -> DatasetRef:
        """Which bars the run used, so the caller can load them again."""
        folder = self._require_dir(run_id)
        return DatasetRef.from_dict(self._read_meta_file(folder).get("dataset"))

    # -- loading -----------------------------------------------------------

    def load(self, run_id: str) -> BacktestResult:
        """Rebuild a saved run as a usable :class:`BacktestResult`.

        Trades come back as real :class:`~tradingbacktester.core.types.Trade`
        objects with their enums restored, the curves as a real
        :class:`~tradingbacktester.engine.results.EquityCurves`, and the metrics
        exactly as they were saved.

        ``bars``, ``orders``, ``indicators`` and ``signals`` are **not** stored
        and come back empty: they are all per-bar data that can be regenerated
        by re-running the strategy against the dataset the run names.  A note
        saying so is appended to ``warnings``.
        """
        folder = self._require_dir(run_id)
        payload = self._read_meta_file(folder)
        result = BacktestResult()

        result.run_id = str(payload.get("id") or folder.name)
        result.label = str(payload.get("label") or "")
        result.strategy_name = str(payload.get("strategy_name") or "")
        result.strategy_id = str(payload.get("strategy_id") or "")
        result.instrument_symbol = str(payload.get("instrument_symbol") or "")
        result.timeframe_label = str(payload.get("timeframe_label") or "")
        result.created_at = str(payload.get("created_at") or "")
        result.duration_seconds = _as_float(payload.get("duration_seconds"), 0.0)
        result.bars_processed = _as_int(payload.get("bars_processed"), 0)
        result.rejected_orders = _as_int(payload.get("rejected_orders"), 0)
        metrics = payload.get("metrics")
        result.metrics = dict(metrics) if isinstance(metrics, dict) else {}
        params = payload.get("param_values")
        result.param_values = dict(params) if isinstance(params, dict) else {}
        warnings = payload.get("warnings")
        result.warnings = [str(w) for w in warnings] if isinstance(warnings, list) else []

        # Bars are deliberately absent.  Say so where a user will see it.
        result.bars = None
        result.warnings.append(NO_BARS_NOTE)

        result.config = self._load_config(folder, result)
        result.strategy_dict = self._load_strategy(folder, result)
        result.trades = self._load_trades(folder)
        result.curves = self._load_curves(folder)

        # The result's own net_profit is derived from the curves and the
        # starting capital; if the saved metrics disagree with them, the saved
        # metrics are the record of what the run actually produced.
        if not result.metrics:
            log.debug("Saved run %s has no metrics; the browser will show zeros",
                      result.run_id)
        return result

    def load_bars(self, run_id: str, repository: Any) -> Any:
        """Fetch the bars a saved run used back out of the dataset library.

        ``repository`` is a
        :class:`~tradingbacktester.data.repository.DatasetRepository`; it is
        taken as an argument rather than built here so this module never
        depends on the data layer being importable.
        """
        ref = self.dataset_ref(run_id)
        if not ref.dataset_id:
            raise StorageError(
                "This run does not record which dataset it used, so its bars "
                "cannot be loaded automatically. Open the dataset yourself and "
                "run the strategy again.")
        try:
            return repository.load_bars(ref.dataset_id)
        except StorageError:
            raise
        except Exception as exc:  # DataError and friends carry their own message
            message = getattr(exc, "user_message", "")
            raise StorageError(
                message or
                f"The dataset '{ref.dataset_name or ref.dataset_id}' this run "
                f"used is no longer in the workspace.",
                detail=f"{type(exc).__name__}: {exc}") from exc

    # -- deleting ----------------------------------------------------------

    def delete(self, run_id: str) -> None:
        """Remove a saved run, damaged ones included.

        Deleting a run that is already gone is not an error: the user asked for
        it not to be there, and it is not there.
        """
        folder = self.path_for(run_id)
        if not folder.exists():
            log.warning("Saved run %s was already gone", run_id)
            return
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            raise StorageError(
                f"The saved run could not be deleted from {folder}.\n\n"
                f"It may be open in another program.",
                detail=repr(exc)) from exc
        log.info("Deleted saved run %s", folder.name)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _prepare_dir(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(
                f"The saved-runs folder could not be created at {self.dir}.\n\n"
                f"Choose a different workspace location from File > Change "
                f"Workspace.",
                detail=repr(exc)) from exc

    def _clear_stale_partials(self) -> None:
        """Delete leftovers from a save that was interrupted by a crash."""
        try:
            candidates = [p for p in self.dir.iterdir()
                          if p.is_dir() and p.name.endswith(_PARTIAL_SUFFIX)]
        except OSError:
            return
        for path in candidates:
            log.info("Removing the leftovers of an interrupted save: %s", path.name)
            _remove_tree(path)

    def _reserve_id(self, preferred: str) -> str:
        """Pick a folder name that is free, preferring the result's own id."""
        candidate = _safe_id(preferred)
        if candidate and not (self.dir / candidate).exists():
            return candidate
        for _ in range(1000):
            candidate = _new_run_id()
            if not (self.dir / candidate).exists():
                return candidate
        raise StorageError(  # pragma: no cover - a thousand collisions is a broken clock
            "A new saved run could not be given a unique name.",
            detail=f"dir={self.dir}")

    def _require_dir(self, run_id: str) -> Path:
        folder = self.path_for(run_id)
        if not folder.is_dir():
            raise StorageError(
                f"The saved run '{run_id}' is no longer in the workspace.\n\n"
                f"It may have been deleted outside the application.",
                detail=f"expected {folder}")
        return folder

    def _read_meta_file(self, folder: Path) -> dict[str, Any]:
        payload = _read_json(folder / META_FILENAME, "summary", folder.name)
        if not isinstance(payload, dict):
            raise StorageError(
                f"The saved run '{folder.name}' has an unreadable summary file.",
                detail=f"{META_FILENAME} contained {type(payload).__name__}")
        return payload

    def _build_meta(self, result: BacktestResult, run_id: str,
                    label: str) -> dict[str, Any]:
        """Assemble ``meta.json``: identity, headline numbers, metrics, dataset."""
        metrics = dict(result.metrics or {})
        ref = _dataset_ref_for(result)
        net, ret, dd, pf, sharpe = _headline_numbers(result, metrics)
        return {
            "schema": _SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "id": run_id,
            "label": label,
            "created_at": _utc_now_iso(),
            "run_created_at": str(getattr(result, "created_at", "") or ""),
            "strategy_name": str(getattr(result, "strategy_name", "") or ""),
            "strategy_id": str(getattr(result, "strategy_id", "") or ""),
            "instrument_symbol": (str(getattr(result, "instrument_symbol", "") or "")
                                  or ref.symbol),
            "timeframe_label": (str(getattr(result, "timeframe_label", "") or "")
                                or ref.timeframe_label),
            "duration_seconds": float(getattr(result, "duration_seconds", 0.0) or 0.0),
            "bars_processed": int(getattr(result, "bars_processed", 0) or 0),
            "rejected_orders": int(getattr(result, "rejected_orders", 0) or 0),
            "order_count": len(getattr(result, "orders", []) or []),
            "starting_capital": float(result.config.starting_capital),
            "trade_count": len(result.trades),
            "net_profit": net,
            "return_pct": ret,
            "max_drawdown_pct": dd,
            "profit_factor": pf,
            "sharpe_ratio": sharpe,
            "metrics": _jsonable(metrics),
            "param_values": _jsonable(result.param_values or {}),
            "warnings": [str(w) for w in (result.warnings or [])],
            "dataset": ref.to_dict(),
            "curve_length": 0 if result.curves is None else len(result.curves),
        }

    def _row_for_dir(self, folder: Path) -> SavedRunMeta:
        """Read one run's summary, turning any failure into an unreadable row."""
        try:
            payload = self._read_meta_file(folder)
            return self._row_from_payload(folder, payload)
        except StorageError as exc:
            log.warning("Saved run %s could not be read: %s", folder.name,
                        exc.user_message)
            return _unreadable_row(folder, exc.user_message)
        except Exception:  # noqa: BLE001 - the browser must always open
            log.exception("Unexpected failure reading the saved run %s", folder.name)
            return _unreadable_row(folder, "This saved run could not be read.")

    def _row_from_payload(self, folder: Path, payload: dict[str, Any]) -> SavedRunMeta:
        ref = DatasetRef.from_dict(payload.get("dataset"))
        metrics = payload.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}

        def number(key: str) -> float:
            if key in payload:
                return _as_float(payload.get(key), 0.0)
            return _as_float(metrics.get(key), 0.0)

        return SavedRunMeta(
            id=str(payload.get("id") or folder.name),
            label=str(payload.get("label") or folder.name),
            strategy_name=str(payload.get("strategy_name") or ""),
            instrument_symbol=str(payload.get("instrument_symbol") or ref.symbol),
            timeframe_label=str(payload.get("timeframe_label") or ref.timeframe_label),
            created_at=str(payload.get("created_at") or _mtime_iso(folder)),
            trade_count=_as_int(payload.get("trade_count"), 0),
            net_profit=number("net_profit"),
            return_pct=number("return_pct"),
            max_drawdown_pct=number("max_drawdown_pct"),
            profit_factor=number("profit_factor"),
            sharpe_ratio=number("sharpe_ratio"),
            strategy_id=str(payload.get("strategy_id") or ""),
            dataset_id=ref.dataset_id,
            dataset_name=ref.dataset_name,
            bar_count=ref.bar_count or _as_int(payload.get("bars_processed"), 0),
            start_ts=ref.start_ts,
            end_ts=ref.end_ts,
            duration_seconds=_as_float(payload.get("duration_seconds"), 0.0),
            app_version=str(payload.get("app_version") or ""),
            size_bytes=_folder_size(folder),
            path=str(folder),
            readable=True,
        )

    def _load_config(self, folder: Path, result: BacktestResult) -> BacktestConfig:
        """Read ``config.json``, degrading to defaults rather than losing the run.

        The configuration is context: without it the trades and the curve are
        still exactly what happened.  So a damaged ``config.json`` produces a
        warning on the result instead of an error dialog.
        """
        try:
            payload = _read_json(folder / CONFIG_FILENAME, "settings", folder.name)
        except StorageError as exc:
            result.warnings.append(
                "The settings this run used could not be read, so the defaults "
                "are shown instead.")
            log.warning("Saved run %s has an unreadable %s: %s", folder.name,
                        CONFIG_FILENAME, exc.user_message)
            return BacktestConfig()
        raw = payload.get("config") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            raw = payload if isinstance(payload, dict) else {}
        try:
            return config_from_dict(raw)
        except Exception as exc:  # noqa: BLE001 - a future version's field, say
            result.warnings.append(
                "Some of the settings this run used were not understood by this "
                "version, so the defaults are shown instead.")
            log.warning("Saved run %s has settings this version cannot read: %r",
                        folder.name, exc)
            return BacktestConfig()

    def _load_strategy(self, folder: Path, result: BacktestResult) -> dict[str, Any]:
        try:
            payload = _read_json(folder / STRATEGY_FILENAME, "strategy", folder.name)
        except StorageError as exc:
            result.warnings.append(
                "The strategy definition saved with this run could not be read, "
                "so the run cannot be repeated from here.")
            log.warning("Saved run %s has an unreadable %s: %s", folder.name,
                        STRATEGY_FILENAME, exc.user_message)
            return {}
        return payload if isinstance(payload, dict) else {}

    def _load_trades(self, folder: Path) -> list[Trade]:
        payload = _read_json(folder / TRADES_FILENAME, "trade list", folder.name)
        rows = payload.get("trades") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise StorageError(
                f"The trade list of the saved run '{folder.name}' is damaged.",
                detail=f"{TRADES_FILENAME} held {type(rows).__name__}")
        trades: list[Trade] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise StorageError(
                    f"Trade {index + 1} of the saved run '{folder.name}' is damaged.",
                    detail=f"row was {type(row).__name__}")
            trades.append(trade_from_dict(row, index=index, run=folder.name))
        return trades

    def _load_curves(self, folder: Path) -> EquityCurves:
        path = folder / CURVES_FILENAME
        if not path.is_file():
            raise StorageError(
                f"The equity curve of the saved run '{folder.name}' is missing.",
                detail=f"expected {path}")
        try:
            # allow_pickle stays off: a workspace file must never be able to
            # execute code when it is opened.
            with np.load(path, allow_pickle=False) as data:
                arrays = {key: np.asarray(data[key]) for key in _CURVE_KEYS
                          if key in data.files}
        except (OSError, ValueError, EOFError) as exc:
            raise StorageError(
                f"The equity curve of the saved run '{folder.name}' could not be "
                f"read; the file is damaged.",
                detail=repr(exc)) from exc
        missing = [k for k in _CURVE_KEYS if k not in arrays]
        if missing:
            raise StorageError(
                f"The equity curve of the saved run '{folder.name}' is "
                f"incomplete.",
                detail=f"missing series: {', '.join(missing)}")
        n = len(arrays["ts"])
        for key in _CURVE_KEYS[1:]:
            if len(arrays[key]) != n:
                raise StorageError(
                    f"The equity curve of the saved run '{folder.name}' is "
                    f"inconsistent and cannot be shown.",
                    detail=f"{key} has {len(arrays[key])} points, ts has {n}")
        return EquityCurves(
            ts=np.ascontiguousarray(arrays["ts"], dtype="int64"),
            equity=np.ascontiguousarray(arrays["equity"], dtype="float64"),
            balance=np.ascontiguousarray(arrays["balance"], dtype="float64"),
            drawdown=np.ascontiguousarray(arrays["drawdown"], dtype="float64"),
            drawdown_pct=np.ascontiguousarray(arrays["drawdown_pct"], dtype="float64"),
            exposure=np.ascontiguousarray(arrays["exposure"], dtype="float64"),
            peak=np.ascontiguousarray(arrays["peak"], dtype="float64"),
        )


# ---------------------------------------------------------------------------
# Serialising the pieces
# ---------------------------------------------------------------------------


def config_to_dict(config: BacktestConfig) -> dict[str, Any]:
    """A JSON-safe view of a :class:`BacktestConfig`.

    The enum members are ``str`` subclasses, so ``asdict`` already leaves usable
    strings behind; the pass through :func:`_jsonable` is what copes with tuples
    and with NumPy scalars that have found their way into a setting.
    """
    return _jsonable(asdict(config))


def config_from_dict(d: dict[str, Any]) -> BacktestConfig:
    """Rebuild a :class:`BacktestConfig`, ignoring fields this version dropped.

    Deliberately does *not* call ``validate()``: a run that has already happened
    is a historical record, and refusing to open it because a setting is now
    considered contradictory would lose the user their result.
    """
    data = dict(d or {})
    config = BacktestConfig()
    for name in ("starting_capital", "risk_free_rate"):
        if name in data:
            setattr(config, name, _as_float(data.get(name), getattr(config, name)))
    for name in ("start_ts", "end_ts"):
        value = data.get(name)
        setattr(config, name, None if value is None else _as_int(value, 0))
    if "warmup_bars" in data:
        config.warmup_bars = _as_int(data.get("warmup_bars"), 0)
    factor = data.get("annualization_factor")
    config.annualization_factor = None if factor is None else _as_float(factor, 0.0)

    config.risk = _rebuild_block(RiskSettings, data.get("risk"))
    config.costs = _rebuild_block(CostModel, data.get("costs"))
    config.session = _rebuild_block(SessionSettings, data.get("session"))
    config.exits = _rebuild_block(ExitSettings, data.get("exits"))
    config.execution = _rebuild_block(ExecutionSettings, data.get("execution"))
    return config


def trade_to_dict(trade: Trade) -> dict[str, Any]:
    """One trade as JSON-safe data, enums written as their values."""
    return _jsonable(trade.as_dict())


def trade_from_dict(d: dict[str, Any], index: int = 0, run: str = "") -> Trade:
    """Rebuild a :class:`Trade`, restoring :class:`Side` and :class:`ExitReason`.

    An unknown enum value means the file was written by a version that knows
    something this one does not; that is reported rather than quietly mapped to
    the nearest member, because a trade filed under the wrong exit reason would
    poison every by-reason split downstream.
    """
    known = set(Trade.__dataclass_fields__)
    kwargs: dict[str, Any] = {k: v for k, v in d.items() if k in known}

    where = f"Trade {index + 1}" + (f" of the saved run '{run}'" if run else "")
    kwargs["side"] = _restore_enum(Side, d.get("side"), where, "side")
    kwargs["exit_reason"] = _restore_enum(ExitReason, d.get("exit_reason"), where,
                                          "exit reason")
    for name in _TRADE_INT_FIELDS:
        kwargs[name] = _as_int(kwargs.get(name), 0)
    for name in _TRADE_OPTIONAL_FLOATS:
        value = kwargs.get(name)
        kwargs[name] = None if value is None else _as_float(value, 0.0)
    parent = kwargs.get("parent_id")
    kwargs["parent_id"] = None if parent is None else _as_int(parent, 0)
    kwargs["tag"] = str(kwargs.get("tag") or "")
    for name in ("quantity", "entry_price", "exit_price", "gross_pnl", "commission",
                 "slippage_cost", "spread_cost", "net_pnl", "return_pct",
                 "duration_seconds", "mae", "mfe", "equity_at_entry", "equity_after"):
        kwargs[name] = _as_float(kwargs.get(name), 0.0)

    try:
        return Trade(**kwargs)
    except TypeError as exc:
        raise StorageError(f"{where} could not be read.", detail=repr(exc)) from exc


def _restore_enum(enum_cls: type[Enum], value: Any, where: str, what: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise StorageError(
            f"{where} has a {what} this version does not know ('{value}').\n\n"
            f"The run was probably saved by a newer version of the application.",
            detail=repr(exc)) from exc


def _rebuild_block(cls: type, data: Any) -> Any:
    """Rebuild one settings dataclass from a saved dict.

    Unknown keys are dropped (a setting removed in a later version) and missing
    keys keep the class default (a setting that did not exist yet), so a saved
    run opens on either side of a version change.
    """
    if not isinstance(data, dict):
        return cls()
    kwargs: dict[str, Any] = {}
    for name, spec in cls.__dataclass_fields__.items():
        if name not in data:
            continue
        value = data[name]
        enum_cls = _ENUM_FIELDS.get(name)
        if enum_cls is not None:
            try:
                value = enum_cls(value)
            except ValueError:
                log.warning("Ignoring the unknown %s value %r in a saved run",
                            name, value)
                continue
        elif isinstance(spec.default, tuple) and isinstance(value, list):
            # JSON has no tuples; weekdays and partial_exits went out as lists.
            value = tuple(tuple(v) if isinstance(v, list) else v for v in value)
        kwargs[name] = value
    return cls(**kwargs)


def _dataset_ref_for(result: BacktestResult) -> DatasetRef:
    """Work out what to record about the bars, from the bars if they are there.

    Falls back to the result's own labels and to the curve's first and last
    timestamps, so a run assembled without a :class:`BarSeries` still records a
    usable date range.
    """
    bars = getattr(result, "bars", None)
    ref = DatasetRef(
        symbol=str(getattr(result, "instrument_symbol", "") or ""),
        timeframe_label=str(getattr(result, "timeframe_label", "") or ""),
        bar_count=int(getattr(result, "bars_processed", 0) or 0),
    )
    if bars is not None:
        meta = getattr(bars, "meta", {}) or {}
        ref.dataset_id = str(meta.get("dataset_id", "") or "")
        ref.dataset_name = str(meta.get("dataset_name", "") or "")
        ref.source = str(getattr(bars, "source", "") or "")
        instrument = getattr(bars, "instrument", None)
        if instrument is not None:
            ref.symbol = ref.symbol or str(getattr(instrument, "symbol", "") or "")
            try:
                ref.instrument = _jsonable(instrument.to_dict())
            except Exception:  # noqa: BLE001 - a contract spec is not worth a failed save
                log.debug("The instrument of this run could not be recorded",
                          exc_info=True)
        timeframe = getattr(bars, "timeframe", None)
        if timeframe is not None and not ref.timeframe_label:
            ref.timeframe_label = str(getattr(timeframe, "label", "") or "")
        try:
            ref.bar_count = len(bars)
            if len(bars):
                ref.start_ts = int(bars.ts[0])
                ref.end_ts = int(bars.ts[-1])
        except (TypeError, AttributeError, IndexError):  # pragma: no cover
            log.debug("The bar range of this run could not be recorded", exc_info=True)

    curves = getattr(result, "curves", None)
    if curves is not None and len(curves):
        if not ref.start_ts:
            ref.start_ts = int(curves.ts[0])
        if not ref.end_ts:
            ref.end_ts = int(curves.ts[-1])
        if not ref.bar_count:
            ref.bar_count = len(curves)
    return ref


def _headline_numbers(result: BacktestResult,
                      metrics: dict[str, Any]) -> tuple[float, float, float, float, float]:
    """The five numbers the browser sorts on.

    They are copied to the top level of ``meta.json`` so that listing runs never
    has to understand the metrics dictionary, and they are derived from the
    result itself when a metric is absent -- which happens for a result built by
    hand, and for one saved before a metric existed.
    """
    capital = float(result.config.starting_capital) or 0.0
    net = _as_float(metrics.get("net_profit"), None)
    if net is None:
        net = float(result.net_profit)
    ret = _as_float(metrics.get("return_pct"), None)
    if ret is None:
        ret = (net / capital * 100.0) if capital else 0.0
    dd = _as_float(metrics.get("max_drawdown_pct"), None)
    if dd is None:
        dd = _derive_max_drawdown_pct(result)
    pf = _as_float(metrics.get("profit_factor"), None)
    if pf is None:
        pf = _derive_profit_factor(result)
    # Sharpe cannot be recovered from trades alone -- it needs the annualisation
    # factor the run used -- so an absent one stays absent rather than guessed.
    sharpe = _as_float(metrics.get("sharpe_ratio"), 0.0)
    return float(net), float(ret), float(dd), float(pf), float(sharpe)


def _derive_max_drawdown_pct(result: BacktestResult) -> float:
    curves = getattr(result, "curves", None)
    if curves is None or len(curves) == 0:
        return 0.0
    values = np.asarray(curves.drawdown_pct, dtype="float64")
    if values.size == 0 or not np.isfinite(values).any():
        return 0.0
    # ``drawdown_pct`` is a negative fraction; the metric is a percentage.
    return float(np.nanmin(values)) * 100.0


def _derive_profit_factor(result: BacktestResult) -> float:
    wins = sum(t.net_pnl for t in result.trades if t.net_pnl > 0.0)
    losses = -sum(t.net_pnl for t in result.trades if t.net_pnl < 0.0)
    if losses > 0.0:
        return float(wins / losses)
    return float("inf") if wins > 0.0 else 0.0


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: Any) -> None:
    """Write JSON to ``path``, flushed to disk before it is used.

    ``allow_nan`` is left on: a metric can legitimately be infinite (a profit
    factor with no losing trade) or undefined, and Python's own reader accepts
    the ``Infinity``/``NaN`` tokens it writes.  The alternative -- turning them
    into ``null`` -- would make "no losses" and "no trades" look the same.
    """
    text = json.dumps(payload, indent=2, sort_keys=False)
    _atomic_write_text(path, text)


def _read_json(path: Path, what: str, run: str = "") -> Any:
    where = f"the saved run '{run}'" if run else "this saved run"
    if not path.is_file():
        raise StorageError(
            f"The {what} of {where} is missing.",
            detail=f"expected {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise StorageError(
            f"The {what} of {where} could not be read; the file is damaged.",
            detail=f"{path}: {exc!r}") from exc


def _write_curves(path: Path, curves: EquityCurves | None) -> None:
    """Store the per-bar series as a compressed ``.npz``.

    A run with no curves is written as seven empty arrays rather than refused:
    the trades and the metrics are still worth keeping, and an empty curve
    reloads as an empty curve.
    """
    if curves is None:
        arrays = {"ts": np.empty(0, dtype="int64")}
        arrays.update({k: np.empty(0, dtype="float64") for k in _CURVE_KEYS[1:]})
    else:
        arrays = {"ts": np.ascontiguousarray(curves.ts, dtype="int64")}
        arrays.update({k: np.ascontiguousarray(getattr(curves, k), dtype="float64")
                       for k in _CURVE_KEYS[1:]})
    try:
        with open(path, "wb") as handle:
            np.savez_compressed(handle, **arrays)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise StorageError(
            "The equity curve of this run could not be written.\n\n"
            "Check that there is free space on the drive holding the workspace.",
            detail=repr(exc)) from exc


def _atomic_write_text(path: Path, text: str) -> None:
    """Temporary file in the same directory, fsync, then :func:`os.replace`."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                        dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
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
            f"Check that you have permission to write to the workspace and that "
            f"the drive is not full.",
            detail=repr(exc)) from exc


def _remove_tree(path: Path) -> None:
    """Best-effort cleanup of a staging folder; never raises."""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # noqa: BLE001 - pragma: no cover
        log.debug("Could not remove %s", path, exc_info=True)


def _folder_size(folder: Path) -> int:
    total = 0
    try:
        for path in folder.iterdir():
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0
    return total


def _unreadable_row(folder: Path, problem: str) -> SavedRunMeta:
    return SavedRunMeta(
        id=folder.name,
        label=f"Unreadable run ({folder.name})",
        created_at=_mtime_iso(folder),
        size_bytes=_folder_size(folder),
        path=str(folder),
        readable=False,
        problem=problem,
    )


def _mtime_iso(path: Path) -> str:
    try:
        stamp = path.stat().st_mtime
    except OSError:  # pragma: no cover - the caller just listed it
        return ""
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat(timespec="seconds")


def _range_text(start_ts: int, end_ts: int) -> str:
    if not start_ts or not end_ts:
        return ""
    return f"{_date_text(start_ts)} - {_date_text(end_ts)}"


def _date_text(ts: int) -> str:
    """A UTC date from nanoseconds, without pulling pandas into this module."""
    try:
        return datetime.fromtimestamp(int(ts) / 1e9, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):  # pragma: no cover - absurd timestamp
        return "?"


def _new_run_id() -> str:
    """A sortable, collision-resistant folder name."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def _safe_id(run_id: str) -> str:
    """Reduce an id to something that is safe as a folder name.

    Anything outside ``[A-Za-z0-9_-]`` is replaced, which also makes ``..`` and
    path separators impossible: an id ultimately comes from a file on disk, and
    a file on disk must never be able to steer a write out of the workspace.
    """
    token = _ID_SAFE.sub("-", str(run_id or "").strip())
    return token.strip("-")[:_MAX_ID_LENGTH]


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Convert anything a metric or a setting might hold into JSON-safe data.

    NumPy scalars are the common case -- ``np.int64`` is not a Python ``int``
    and the JSON encoder refuses it -- and the rest is defensive: this has to
    keep working when the analytics layer starts returning something new, and a
    saved run is worth more than an exact rendering of one exotic value.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value  # np.float64 is a float subclass and round-trips exactly
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    isoformat = getattr(value, "isoformat", None)  # pandas.Timestamp and friends
    if callable(isoformat):
        try:
            return str(isoformat())
        except Exception:  # noqa: BLE001 - pragma: no cover
            pass
    return str(value)


def _as_float(value: Any, default: float | None = 0.0) -> Any:
    """A float from whatever was in the file, or ``default`` when it is not one."""
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
