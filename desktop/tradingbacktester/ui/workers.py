"""Background workers.

Every long task -- importing a large CSV, running a backtest, sweeping an
optimisation grid -- happens on a ``QThread`` so the window keeps repainting and
the Cancel button keeps responding.  Workers never touch a widget: they emit
signals and the main thread does the drawing, which is the only arrangement Qt
supports.
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from ..core.errors import BacktesterError, CancelledError
from ..logging_setup import get_logger

log = get_logger(__name__)


class _CancelToken:
    """A thread-safe flag the worker polls and the UI sets."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def __call__(self) -> bool:
        return self._cancelled

    @property
    def cancelled(self) -> bool:
        return self._cancelled


class Worker(QObject):
    """Runs one callable on a worker thread and reports what happened.

    The callable receives ``progress`` and ``cancel`` keyword arguments when it
    accepts them, so a task that cannot report progress does not have to pretend.
    """

    progress = Signal(int, int, str)
    """current, total, message"""
    finished = Signal(object)
    failed = Signal(str, str)
    """user message, technical detail"""
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.token = _CancelToken()
        self._last_emit = 0.0

    def cancel(self) -> None:
        self.token.cancel()

    def _emit_progress(self, current: int, total: int, message: str = "") -> None:
        # Throttled: a backtest can call this per bar, and flooding the event
        # loop with signals makes the UI slower than doing the work.
        now = time.monotonic()
        if current >= total or now - self._last_emit > 0.05:
            self._last_emit = now
            self.progress.emit(int(current), int(total), message)

    def run(self) -> None:
        try:
            import inspect

            kwargs = dict(self._kwargs)
            try:
                params = inspect.signature(self._fn).parameters
            except (TypeError, ValueError):
                params = {}
            if "progress" in params:
                kwargs["progress"] = self._emit_progress
            if "cancel" in params:
                kwargs["cancel"] = self.token
            result = self._fn(*self._args, **kwargs)
        except CancelledError:
            log.info("Task cancelled by the user")
            self.cancelled.emit()
            return
        except BacktesterError as exc:
            log.warning("Task failed: %s", exc.user_message)
            self.failed.emit(exc.user_message, exc.detail or "")
            return
        except MemoryError:
            self.failed.emit(
                "The computer ran out of memory while running this task. Try a "
                "shorter date range, a coarser timeframe, or a smaller "
                "optimisation grid.",
                traceback.format_exc())
            return
        except Exception:
            detail = traceback.format_exc()
            log.exception("Unexpected failure in a background task")
            self.failed.emit(
                "Something went wrong while running this task. The details have "
                "been written to the log file.", detail)
            return
        if self.token.cancelled:
            self.cancelled.emit()
            return
        self.finished.emit(result)


class TaskRunner(QObject):
    """Owns a worker and its thread and guarantees both are cleaned up.

    Keeping a reference here matters: a ``QThread`` that goes out of scope while
    running is destroyed underneath itself and takes the process with it.
    """

    progress = Signal(int, int, str)
    finished = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()
    stateChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: Worker | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Begin a task.  Returns False if one is already running."""
        if self.busy:
            return False
        thread = QThread()
        worker = Worker(fn, *args, **kwargs)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)

        self._thread = thread
        self._worker = worker
        self.stateChanged.emit(True)
        thread.start()
        return True

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def wait(self, timeout_ms: int = 5000) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(timeout_ms)

    # -- completion ------------------------------------------------------

    def _teardown(self) -> None:
        thread, worker = self._thread, self._worker
        self._thread, self._worker = None, None
        if thread is not None:
            thread.quit()
            thread.wait(5000)
            thread.deleteLater()
        if worker is not None:
            worker.deleteLater()
        self.stateChanged.emit(False)

    def _on_finished(self, result: Any) -> None:
        self._teardown()
        self.finished.emit(result)

    def _on_failed(self, message: str, detail: str) -> None:
        self._teardown()
        self.failed.emit(message, detail)

    def _on_cancelled(self) -> None:
        self._teardown()
        self.cancelled.emit()


# --------------------------------------------------------------------------
# Task functions.  These run on the worker thread and must not touch widgets.
# --------------------------------------------------------------------------

def run_backtest_task(bars: Any, spec: Any, config: Any,
                      param_overrides: dict[str, Any] | None = None,
                      label: str = "",
                      progress: Callable[[int, int, str], None] | None = None,
                      cancel: Callable[[], bool] | None = None) -> Any:
    """Run one backtest.  Returns a
    :class:`~tradingbacktester.engine.results.BacktestResult`."""
    from ..engine.backtester import Backtester

    def report(current: int, total: int) -> None:
        if progress is not None:
            progress(current, total, f"Simulating bar {current:,} of {total:,}")

    engine = Backtester(bars, spec, config, progress=report, cancel=cancel,
                        param_overrides=param_overrides)
    result = engine.run()
    if label:
        result.label = label
    return result


def import_csv_task(path: str, mapping: Any, instrument: Any, timeframe: Any = None,
                    progress: Callable[[int, int, str], None] | None = None,
                    cancel: Callable[[], bool] | None = None) -> Any:
    """Load a CSV into a :class:`~tradingbacktester.data.models.BarSeries`."""
    from ..data.csv_loader import load_csv

    def report(current: int, total: int) -> None:
        if progress is not None:
            progress(current, total, f"Reading row {current:,} of {total:,}")
        if cancel is not None and cancel():
            raise CancelledError("Import cancelled.")

    return load_csv(path, mapping, instrument, timeframe=timeframe, progress=report)


def optimize_task(bars: Any, spec: Any, config: Any, ranges: Any,
                  max_workers: int = 0,
                  progress: Callable[[int, int, str], None] | None = None,
                  cancel: Callable[[], bool] | None = None) -> Any:
    """Sweep a parameter grid.  Returns the optimisation result set."""
    from ..optimize.runner import OptimizationRunner

    def report(done: int, total: int) -> None:
        if progress is not None:
            progress(done, total, f"Combination {done:,} of {total:,}")

    runner = OptimizationRunner(bars, spec, config, max_workers=max_workers)
    return runner.run(ranges, progress=report, cancel=cancel)
