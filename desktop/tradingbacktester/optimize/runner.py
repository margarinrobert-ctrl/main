"""Running a parameter sweep, in parallel, cancellably.

The unit of work is one backtest of one parameter combination.  Combinations
are independent, so the sweep is embarrassingly parallel and the runner hands
them to a :class:`~concurrent.futures.ProcessPoolExecutor`: a backtest is
CPU-bound Python and NumPy, and only separate processes escape the GIL.

Three practical constraints shaped the design.

*Processes are not always available.*  A frozen PyInstaller build on Windows can
fail to spawn workers, and some locked-down environments have no usable shared
semaphores at all.  Every process failure falls back to a thread pool and the
sweep finishes -- more slowly, but it finishes.

*The worker must be picklable.*  Windows spawns rather than forks, so the worker
is a module-level function and the bars, strategy and configuration travel once
per worker process through the pool initialiser instead of once per combination.

*One bad combination must not lose the sweep.*  A combination whose parameters
make the strategy uncompilable records its error on its own row and the rest of
the grid continues.
"""

from __future__ import annotations

import concurrent.futures
import math
import os
import sys
import threading
import time
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import numpy as np

from ..core.errors import BacktesterError
from ..logging_setup import get_logger
from .grid import DEFAULT_MAX_COMBINATIONS, ParameterRange, build_grid

log = get_logger(__name__)

try:
    # Imported defensively: a stripped-down or sandboxed Python can be built
    # without working shared semaphores, and then merely importing these raises.
    # The optimiser still works in that case -- on threads.
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool

    PROCESSES_AVAILABLE = True
except Exception as _mp_exc:  # noqa: BLE001 - genuinely anything can go wrong here
    multiprocessing = None  # type: ignore[assignment]
    ProcessPoolExecutor = None  # type: ignore[assignment]

    class BrokenProcessPool(Exception):  # type: ignore[no-redef]
        """Placeholder so the except clauses below stay valid without processes."""

    PROCESSES_AVAILABLE = False
    log.warning("Multiprocessing is unavailable (%r); optimisation will use "
                "threads.", _mp_exc)

ProgressFn = Callable[[int, int], None]
CancelFn = Callable[[], bool]

#: Below this many combinations the pool costs more than it saves: starting
#: worker processes and shipping the bars to them is seconds of work, and a
#: handful of backtests is usually less than that.
MIN_COMBINATIONS_FOR_POOL = 6

#: Seconds to wait for the first worker process to answer before giving up on
#: processes.  Spawning a child that imports NumPy and pandas is not instant,
#: but it is not thirty seconds either.
POOL_STARTUP_TIMEOUT = 30.0

#: Hard ceiling on worker processes.  More than this and the memory cost of one
#: copy of the bar series per worker starts to matter on an ordinary desktop.
MAX_WORKER_PROCESSES = 8

#: Futures kept in flight per worker.  Enough that no worker ever waits for the
#: parent to submit, small enough that cancelling does not have to reap a
#: hundred thousand queued futures.
_QUEUE_DEPTH = 3

#: How long to block waiting for a completed future before looking at the
#: cancel token again.  A quarter of a second is imperceptible to the user and
#: costs nothing.
_POLL_SECONDS = 0.25

#: Rough per-process start-up cost (interpreter, NumPy import, unpickling the
#: bars) used only by :meth:`OptimizationRunner.estimate_runtime`.
_POOL_STARTUP_SECONDS = 1.5
_PER_WORKER_STARTUP_SECONDS = 0.35

#: Parallel work never scales perfectly; the estimate is padded by this factor.
_PARALLEL_INEFFICIENCY = 1.15

_FREEZE_SUPPORT_DONE = False

# Set in each worker process by :func:`_init_worker`.  The parent process never
# reads it: the thread fallback passes its arguments explicitly instead, so two
# sweeps running in one process cannot tread on each other.
_WORKER_STATE: dict[str, Any] = {}


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------


@dataclass
class OptimizationRow:
    """One parameter combination and what it produced."""

    params: dict[str, Any]
    metrics: dict[str, Any] = field(default_factory=dict)
    trade_count: int = 0
    error: str | None = None
    """Plain-language reason this combination produced nothing, or ``None``."""
    index: int = 0
    """Position in the grid, so a table can restore the original order."""
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None

    def value(self, metric: str) -> float:
        """The value of ``metric`` for this row, as a float.

        Returns NaN when the metric is missing or not a number, which is how a
        failed combination sorts to the bottom of every ranking.  The derived
        ``return_drawdown_ratio`` is computed here rather than stored so it is
        always consistent with the two metrics it comes from.
        """
        if metric == "return_drawdown_ratio":
            return self._return_drawdown_ratio()
        raw = self.metrics.get(metric)
        if isinstance(raw, bool) or raw is None:
            return float("nan")
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float("nan")

    def _return_drawdown_ratio(self) -> float:
        """Return divided by the depth of the worst drawdown it had to survive.

        Infinite when a profitable run never drew down at all -- rare, real, and
        deliberately not clamped, because hiding it would make a one-trade run
        look like a good one.
        """
        ret = self.value("return_pct")
        dd = abs(self.value("max_drawdown_pct"))
        if math.isnan(ret) or math.isnan(dd):
            return float("nan")
        if dd <= 0.0:
            return float("inf") if ret > 0 else 0.0
        return ret / dd

    def label(self) -> str:
        """``"fast=10, slow=50"`` -- how the row names itself in a table."""
        return ", ".join(f"{k}={_format_value(v)}" for k, v in self.params.items())

    def to_dict(self) -> dict[str, Any]:
        return {"params": dict(self.params), "metrics": dict(self.metrics),
                "trade_count": self.trade_count, "error": self.error,
                "index": self.index, "elapsed_seconds": self.elapsed_seconds}


@dataclass
class OptimizationResults:
    """Everything a sweep produced, in grid order."""

    rows: list[OptimizationRow] = field(default_factory=list)
    ranges: list[ParameterRange] = field(default_factory=list)
    metric_names: list[str] = field(default_factory=list)
    """Numeric metric keys present on at least one successful row, sorted."""
    elapsed_seconds: float = 0.0
    completed: int = 0
    failed: int = 0
    cancelled: bool = False
    total_combinations: int = 0
    """Size of the grid, which exceeds ``len(rows)`` after a cancellation."""
    used_processes: bool = False
    worker_count: int = 1
    warnings: list[str] = field(default_factory=list)

    @property
    def param_names(self) -> list[str]:
        return [r.name for r in self.ranges]

    def successful(self) -> list[OptimizationRow]:
        return [r for r in self.rows if r.ok]

    def errors(self) -> list[OptimizationRow]:
        return [r for r in self.rows if not r.ok]

    def row_for(self, params: dict[str, Any]) -> OptimizationRow | None:
        """The row whose parameters match ``params`` exactly, if it ran."""
        key = _key(params, self.param_names)
        for row in self.rows:
            if _key(row.params, self.param_names) == key:
                return row
        return None

    def best(self, metric: str, minimum_trades: int = 0,
             maximise: bool = True) -> OptimizationRow | None:
        from .ranking import rank

        ranked = rank(self, metric, minimum_trades=minimum_trades, maximise=maximise)
        return ranked[0] if ranked else None

    def summary_line(self) -> str:
        parts = [f"{self.completed:,} of {self.total_combinations:,} combinations"]
        if self.failed:
            parts.append(f"{self.failed:,} failed")
        if self.cancelled:
            parts.append("cancelled")
        parts.append(f"{self.elapsed_seconds:.1f}s")
        kind = "process" if self.used_processes else "thread"
        if self.worker_count != 1:
            kind += "es" if self.used_processes else "s"
        parts.append(f"{self.worker_count} {kind}")
        return ", ".join(parts)


# --------------------------------------------------------------------------
# The worker
# --------------------------------------------------------------------------


def _init_worker(bars: Any, spec: Any, config: Any) -> None:
    """Pool initialiser: hold the shared inputs in the child process.

    Sent once per worker instead of once per combination, which for a 2 M-bar
    series is the difference between a sweep that runs and one that spends all
    its time pickling.
    """
    import logging

    _WORKER_STATE["bars"] = bars
    _WORKER_STATE["spec"] = spec
    _WORKER_STATE["config"] = config
    # A spawned child has no handlers, and Python would otherwise print
    # "No handlers could be found" style warnings to a console that, in a
    # windowed build, does not exist.
    logging.getLogger("tradingbacktester").addHandler(logging.NullHandler())


def _evaluate_pooled(job: tuple[int, dict[str, Any]]) -> dict[str, Any]:
    """Process-pool entry point.  Reads the inputs stashed by the initialiser."""
    index, params = job
    return evaluate_combination(_WORKER_STATE["bars"], _WORKER_STATE["spec"],
                                _WORKER_STATE["config"], index, params)


def evaluate_combination(bars: Any, spec: Any, config: Any, index: int,
                         params: dict[str, Any]) -> dict[str, Any]:
    """Backtest one combination and return a picklable payload.

    Never raises: a combination that cannot run is reported as a row with an
    ``error`` so the rest of the sweep survives it.  The payload is a plain
    dictionary rather than an :class:`OptimizationRow` so that unpickling in the
    parent cannot depend on this module's class definition matching the child's.
    """
    started = time.perf_counter()
    metrics: dict[str, Any] = {}
    trade_count = 0
    error: str | None = None
    try:
        from ..engine.backtester import Backtester

        engine = Backtester(bars, spec, config, param_overrides=dict(params))
        result = engine.run()
        metrics = _sanitise_metrics(getattr(result, "metrics", {}) or {})
        trade_count = int(len(getattr(result, "trades", ()) or ()))
    except BacktesterError as exc:
        error = exc.user_message
    except MemoryError:
        error = "Ran out of memory on this combination."
    except Exception as exc:  # noqa: BLE001 - one bad combination must not kill the sweep
        error = f"{type(exc).__name__}: {exc}"
    if error is not None:
        log.debug("Combination %d (%s) failed: %s", index, params, error)
    return {"index": index, "params": dict(params), "metrics": metrics,
            "trade_count": trade_count, "error": error,
            "elapsed": time.perf_counter() - started}


def _sanitise_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Make a metric dictionary cheap and safe to send between processes.

    NumPy scalars become Python numbers (so the parent never has to import the
    same NumPy build to compare them) and per-bar arrays are dropped: they are
    megabytes each, the optimiser only ranks scalars, and the equity curve of a
    rejected combination is of no interest.
    """
    out: dict[str, Any] = {}
    for key, value in metrics.items():
        if isinstance(value, np.generic):
            out[key] = value.item()
        elif isinstance(value, np.ndarray):
            continue
        elif isinstance(value, (int, float, bool, str, type(None))):
            out[key] = value
        elif isinstance(value, dict):
            out[key] = {str(k): (v.item() if isinstance(v, np.generic) else v)
                        for k, v in value.items()
                        if isinstance(v, (int, float, bool, str, np.generic, type(None)))}
        elif isinstance(value, (list, tuple)):
            out[key] = [v.item() if isinstance(v, np.generic) else v for v in value
                        if isinstance(v, (int, float, bool, str, np.generic, type(None)))]
    return out


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def resolve_worker_count(max_workers: int = 0) -> int:
    """Turn the ``max_workers`` argument into a real worker count.

    ``0`` means "decide for me": one fewer than the machine's cores so the user
    interface still gets a core to repaint with, capped at
    :data:`MAX_WORKER_PROCESSES`.
    """
    if max_workers and max_workers > 0:
        return int(max_workers)
    try:
        cores = os.cpu_count() or 1
    except NotImplementedError:  # pragma: no cover - platform specific
        cores = 1
    return max(1, min(cores - 1, MAX_WORKER_PROCESSES))


def ensure_freeze_support() -> None:
    """Call :func:`multiprocessing.freeze_support` once, in the parent only.

    A frozen Windows executable that spawns a worker re-runs the executable with
    ``--multiprocessing-fork``; without ``freeze_support`` that second copy
    starts the *application* again, and the user gets an unbounded fan of
    windows.  It is a no-op everywhere else, which is why calling it defensively
    costs nothing.  The main-process guard keeps it from re-entering inside a
    worker that is already running its own bootstrap.
    """
    global _FREEZE_SUPPORT_DONE
    if _FREEZE_SUPPORT_DONE or not PROCESSES_AVAILABLE:
        return
    _FREEZE_SUPPORT_DONE = True
    try:
        if multiprocessing.current_process().name != "MainProcess":
            return
        multiprocessing.freeze_support()
    except Exception as exc:  # noqa: BLE001 - never let this stop a sweep
        log.debug("freeze_support() was not available: %r", exc)


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _key(params: dict[str, Any], names: Sequence[str]) -> tuple[Any, ...]:
    """A hashable identity for a combination, in a fixed parameter order."""
    if names:
        return tuple(params.get(n) for n in names)
    return tuple(sorted(params.items()))


class _PoolFailure(Exception):
    """Internal: the process pool died; these jobs still need running."""

    def __init__(self, remaining: list[tuple[int, dict[str, Any]]], reason: str) -> None:
        super().__init__(reason)
        self.remaining = remaining
        self.reason = reason


# --------------------------------------------------------------------------
# The runner
# --------------------------------------------------------------------------


class OptimizationRunner:
    """Runs a grid of backtests over one bar series and one strategy.

    Parameters
    ----------
    bars:
        The :class:`~tradingbacktester.data.models.BarSeries` to sweep over.
    spec:
        The :class:`~tradingbacktester.strategy.spec.StrategySpec`; every
        combination overrides its parameters and leaves everything else alone.
    config:
        The :class:`~tradingbacktester.core.types.BacktestConfig` shared by
        every combination -- costs, sizing and session settings must be
        identical or the results are not comparable.
    max_workers:
        ``0`` selects ``min(cpu_count - 1, 8)``; ``1`` runs everything in this
        process, which is also what happens for a grid too small to be worth a
        pool.
    """

    def __init__(self, bars: Any, spec: Any, config: Any,
                 max_workers: int = 0) -> None:
        self.bars = bars
        self.spec = spec
        self.config = config
        self.max_workers = resolve_worker_count(max_workers)
        self.max_combinations = DEFAULT_MAX_COMBINATIONS
        ensure_freeze_support()

    # -- planning --------------------------------------------------------

    def build(self, ranges: Sequence[ParameterRange]) -> list[dict[str, Any]]:
        """The validated grid these ranges describe."""
        return build_grid(self.spec, ranges, maximum=self.max_combinations)

    def estimate_runtime(self, ranges: Sequence[ParameterRange]) -> float:
        """Seconds the sweep is likely to take, from one timed trial run.

        One combination from the middle of the grid is backtested here and now,
        and the measurement is scaled by the grid size, the worker count and a
        parallel-inefficiency pad.  It is an order-of-magnitude guide for the
        dialog's warning, not a promise: combinations that trade more take
        longer, and the first run of any process pool pays for its own start-up.
        """
        grid = self.build(ranges)
        total = len(grid)
        if total == 0:
            return 0.0
        # A combination that fails costs almost nothing, and timing a failure
        # would promise a sweep far faster than it will be; try a couple of
        # others before giving up on getting a real measurement.
        candidates = [grid[total // 2]]
        if total > 1:
            candidates.append(grid[0])
        if total > 2:
            candidates.append(grid[-1])
        per_run = 0.0
        for params in candidates:
            payload = evaluate_combination(self.bars, self.spec, self.config, 0, params)
            per_run = max(per_run, float(payload["elapsed"]))
            if payload["error"] is None:
                break
        else:
            log.warning("Every trial combination failed; the runtime estimate "
                        "is unreliable.")
        workers = self._planned_workers(total)
        overhead = 0.0
        if workers > 1:
            overhead = _POOL_STARTUP_SECONDS + _PER_WORKER_STARTUP_SECONDS * workers
        return per_run * total / workers * _PARALLEL_INEFFICIENCY + overhead

    def _planned_workers(self, total: int) -> int:
        if self.max_workers <= 1 or total < MIN_COMBINATIONS_FOR_POOL:
            return 1
        return max(1, min(self.max_workers, total))

    # -- running ---------------------------------------------------------

    def run(self, ranges: Sequence[ParameterRange],
            progress: ProgressFn | None = None,
            cancel: CancelFn | None = None) -> OptimizationResults:
        """Backtest every combination and collect the rows.

        ``progress`` is called with ``(completed, total)``; ``cancel`` is polled
        between completed combinations and, when it returns True, pending work
        is cancelled and the partial results are returned with
        ``cancelled=True`` set.
        """
        started = time.perf_counter()
        grid = self.build(ranges)
        total = len(grid)
        results = OptimizationResults(
            ranges=list(ranges), total_combinations=total,
            worker_count=self._planned_workers(total))
        if progress is not None:
            progress(0, total)
        if total == 0:  # pragma: no cover - build_grid refuses an empty grid
            return results

        rows: dict[int, OptimizationRow] = {}

        def absorb(payload: dict[str, Any]) -> None:
            row = OptimizationRow(
                params=payload["params"], metrics=payload["metrics"],
                trade_count=int(payload["trade_count"]), error=payload["error"],
                index=int(payload["index"]),
                elapsed_seconds=float(payload["elapsed"]))
            rows[row.index] = row
            if progress is not None:
                progress(len(rows), total)

        jobs: list[tuple[int, dict[str, Any]]] = list(enumerate(grid))
        workers = results.worker_count
        cancelled = False

        if workers > 1 and PROCESSES_AVAILABLE:
            remaining, cancelled, broke = self._run_with_processes(
                jobs, workers, absorb, cancel)
            results.used_processes = not broke
            if broke:
                results.warnings.append(
                    "Worker processes could not be used for this sweep, so it "
                    "ran on threads instead. It will have taken longer than "
                    "usual, but the results are the same.")
                if remaining and not cancelled:
                    cancelled = self._run_with_threads(remaining, workers, absorb, cancel)
        elif workers > 1:
            cancelled = self._run_with_threads(jobs, workers, absorb, cancel)
            results.warnings.append(
                "This build cannot start worker processes, so the sweep ran on "
                "threads. It will have taken longer than usual.")
        else:
            cancelled = self._run_sequentially(jobs, absorb, cancel)
            results.worker_count = 1

        results.rows = [rows[i] for i in sorted(rows)]
        results.completed = sum(1 for r in results.rows if r.ok)
        results.failed = sum(1 for r in results.rows if not r.ok)
        results.cancelled = cancelled
        results.metric_names = _collect_metric_names(results.rows)
        results.elapsed_seconds = time.perf_counter() - started
        if results.rows and results.completed == 0:
            # Every combination failing is nearly always one cause, not N; say
            # what it was rather than leaving a table of identical red cells.
            first = next(r.error for r in results.rows if r.error)
            results.warnings.append(
                f"No combination produced a result. The first failure said: {first}")
        log.info("Optimisation finished: %s", results.summary_line())
        return results

    # -- execution strategies --------------------------------------------

    def _run_sequentially(self, jobs: list[tuple[int, dict[str, Any]]],
                          absorb: Callable[[dict[str, Any]], None],
                          cancel: CancelFn | None) -> bool:
        """Run in this process.  Returns True if the user cancelled."""
        for index, params in jobs:
            if cancel is not None and cancel():
                return True
            absorb(evaluate_combination(self.bars, self.spec, self.config,
                                        index, params))
        # Deliberately not re-checking the token here: every combination ran, so
        # the sweep was not cancelled even if the user clicked as it finished.
        return False

    def _run_with_processes(self, jobs: list[tuple[int, dict[str, Any]]],
                            workers: int,
                            absorb: Callable[[dict[str, Any]], None],
                            cancel: CancelFn | None
                            ) -> tuple[list[tuple[int, dict[str, Any]]], bool, bool]:
        """Run on a process pool.

        Returns ``(remaining_jobs, cancelled, pool_broke)``.  ``pool_broke`` is
        True when processes turned out to be unusable, which is the caller's cue
        to finish the job on threads.
        """
        if not spawn_can_reimport_main():
            log.info("This process has no importable __main__, so spawned workers "
                     "cannot start; running the sweep on threads instead.")
            return jobs, False, True

        context = _start_context()
        try:
            executor = ProcessPoolExecutor(
                max_workers=workers, mp_context=context,
                initializer=_init_worker,
                initargs=(self.bars, self.spec, self.config))
        except (OSError, ValueError, ImportError, RuntimeError,
                NotImplementedError) as exc:
            log.warning("Could not start worker processes (%r); using threads.", exc)
            return jobs, False, True

        if not _probe_pool(executor, POOL_STARTUP_TIMEOUT):
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:             # pragma: no cover - best effort
                pass
            return jobs, False, True
        try:
            with executor:
                cancelled = self._pump(executor, jobs, _evaluate_pooled, absorb, cancel)
            return [], cancelled, False
        except _PoolFailure as exc:
            log.warning("The worker pool stopped responding (%s); the remaining "
                        "%d combinations will run on threads.",
                        exc.reason, len(exc.remaining))
            return exc.remaining, False, True

    def _run_with_threads(self, jobs: list[tuple[int, dict[str, Any]]], workers: int,
                          absorb: Callable[[dict[str, Any]], None],
                          cancel: CancelFn | None) -> bool:
        """Fallback path: a thread pool in this process.  True if cancelled.

        NumPy releases the GIL for most of the array work a backtest does, so
        threads are not as useless here as they sound -- but they are slower
        than processes, and the caller says so in a warning.
        """
        bars, spec, config = self.bars, self.spec, self.config

        def work(job: tuple[int, dict[str, Any]]) -> dict[str, Any]:
            return evaluate_combination(bars, spec, config, job[0], job[1])

        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="optimise") as executor:
            try:
                return self._pump(executor, jobs, work, absorb, cancel)
            except _PoolFailure as exc:  # pragma: no cover - threads do not break
                log.error("The thread pool failed: %s", exc.reason)
                return False

    def _pump(self, executor: Executor, jobs: list[tuple[int, dict[str, Any]]],
              work: Callable[[tuple[int, dict[str, Any]]], dict[str, Any]],
              absorb: Callable[[dict[str, Any]], None],
              cancel: CancelFn | None) -> bool:
        """Feed ``jobs`` to ``executor``, absorbing results as they land.

        Only a bounded number of futures is in flight at once: submitting a
        hundred thousand up front would make cancellation slow and hold every
        parameter dictionary in the pool's queue for the whole run.
        """
        pending: list[tuple[int, dict[str, Any]]] = list(jobs)
        cursor = 0
        futures: dict[Future, tuple[int, dict[str, Any]]] = {}
        depth = max(1, self.max_workers) * _QUEUE_DEPTH

        def submit_next() -> bool:
            nonlocal cursor
            if cursor >= len(pending):
                return False
            job = pending[cursor]
            cursor += 1
            futures[executor.submit(work, job)] = job
            return True

        for _ in range(depth):
            if not submit_next():
                break

        while futures:
            done, _not_done = concurrent.futures.wait(
                list(futures), timeout=_POLL_SECONDS,
                return_when=concurrent.futures.FIRST_COMPLETED)
            if cancel is not None and cancel():
                self._abandon(futures)
                return True
            for future in done:
                job = futures.pop(future, None)
                if job is None:  # pragma: no cover - defensive
                    continue
                try:
                    payload = future.result()
                except BrokenProcessPool as exc:
                    remaining = list(futures.values()) + [job] + pending[cursor:]
                    self._abandon(futures)
                    raise _PoolFailure(remaining, repr(exc)) from exc
                except concurrent.futures.CancelledError:  # pragma: no cover
                    continue
                except Exception as exc:  # noqa: BLE001 - the worker swallows its own
                    payload = {"index": job[0], "params": job[1], "metrics": {},
                               "trade_count": 0, "elapsed": 0.0,
                               "error": f"{type(exc).__name__}: {exc}"}
                absorb(payload)
                submit_next()
        return False

    @staticmethod
    def _abandon(futures: dict[Future, tuple[int, dict[str, Any]]]) -> None:
        """Cancel everything still queued so a cancel really does stop work.

        A future already running in a worker cannot be interrupted; cancelling
        the queue means at most ``worker_count`` more backtests finish, which is
        a fraction of a second each.
        """
        for future in list(futures):
            future.cancel()
        futures.clear()


def spawn_can_reimport_main() -> bool:
    """Can a spawned child re-import ``__main__``?

    ``spawn`` starts a child by re-importing the parent's ``__main__`` module.
    When the program was started from stdin, from ``-c``, or from an embedded
    interpreter, there is no file to import: the child dies with
    ``FileNotFoundError`` and the parent blocks forever inside ``submit`` waiting
    for a worker that will never arrive.  A hung Optimise dialog with a dead
    Cancel button is far worse than a slower thread pool, so this is checked
    before a pool is created rather than discovered afterwards.
    """
    main = sys.modules.get("__main__")
    if main is None:
        return False
    if getattr(main, "__spec__", None) is not None:
        return True                       # started with -m, always re-importable
    path = getattr(main, "__file__", None)
    if not path:
        return False                      # interactive, -c, or stdin
    try:
        return os.path.isfile(path)
    except (OSError, TypeError):          # pragma: no cover - defensive
        return False


def _probe_pool(executor: Any, timeout: float) -> bool:
    """Confirm the pool can actually run something, within ``timeout`` seconds.

    ``ProcessPoolExecutor`` starts its workers lazily inside ``submit``, so a
    pool that cannot start does not fail until the first job -- and it fails by
    blocking.  The probe therefore runs on a daemon thread: if it has not come
    back in time the pool is abandoned rather than waited on, and the caller
    falls back to threads.
    """
    outcome: dict[str, Any] = {}

    def attempt() -> None:
        try:
            outcome["value"] = executor.submit(_worker_alive).result(timeout)
        except BaseException as exc:      # noqa: BLE001 - any failure means "no"
            outcome["error"] = exc

    thread = threading.Thread(target=attempt, name="pool-probe", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        log.warning("The worker pool did not start within %.1fs; using threads.",
                    timeout)
        return False
    if "error" in outcome:
        log.warning("The worker pool failed its start-up check (%r); using threads.",
                    outcome["error"])
        return False
    return outcome.get("value") is True


def _worker_alive() -> bool:
    """Trivial task used to prove a worker process is running."""
    return True


def _start_context() -> Any:
    """The multiprocessing context to spawn workers with.

    ``spawn`` everywhere: it is the only method Windows has, so using it on
    every platform means the packaged application behaves exactly like the
    development one.  ``fork`` would also copy a process that is already running
    a Qt event loop and several threads into the child, which is a documented
    way to deadlock on a lock held by a thread that does not exist any more.
    """
    try:
        return multiprocessing.get_context("spawn")
    except (ValueError, RuntimeError):  # pragma: no cover - platform specific
        return multiprocessing.get_context()


def _collect_metric_names(rows: Iterable[OptimizationRow]) -> list[str]:
    """Every numeric metric any successful row reported, plus the derived one."""
    names: set[str] = set()
    for row in rows:
        if not row.ok:
            continue
        for key, value in row.metrics.items():
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                names.add(key)
    if "return_pct" in names and "max_drawdown_pct" in names:
        names.add("return_drawdown_ratio")
    return sorted(names)
