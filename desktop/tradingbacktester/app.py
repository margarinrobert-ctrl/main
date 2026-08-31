"""Application bootstrap.

Creates the workspace, configures logging, installs the theme and the
last-resort exception handler, then opens the main window.  Everything that can
fail during start-up fails *visibly*: a broken workspace path or an unreadable
settings file produces a dialog explaining what to do, not a silent exit.
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path
from typing import Any, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from .config import APP_DISPLAY_NAME, APP_ORG, APP_VERSION, AppSettings
from .logging_setup import (breadcrumb, configure_logging, get_logger,
                            install_excepthook, startup_log_path)


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    """Create the QApplication with the settings that must precede any widget."""
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(list(argv if argv is not None else sys.argv))
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(APP_VERSION)
    return app


def self_test() -> int:
    """Verify a build end to end without opening a window.

    Generates sample data, compiles a built-in strategy, runs a backtest and
    checks the metrics came out.  The Windows build script runs the frozen
    ``TradingBacktester.exe --self-test`` and refuses to package a build that
    fails, which catches the classic PyInstaller failure where an import that
    works from source is missing from the bundle.
    """
    import os
    import tempfile
    import time

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_application([])
    checks: list[str] = []
    try:
        from .core.timeframe import Timeframe
        from .core.types import BacktestConfig
        from .data.sample import generate_sample_data
        from .indicators.registry import REGISTRY
        from .strategy.builtin import BUILTIN_STRATEGIES
        from .engine.backtester import Backtester
        from .ui.main_window import MainWindow  # import-only: catches missing Qt bits

        checks.append(f"indicators registered: {len(REGISTRY.all())}")
        bars = generate_sample_data("SYNTH", Timeframe.parse("1h"),
                                    n_bars=3000, seed=11)
        checks.append(f"sample bars: {len(bars)}")
        name, factory = next(iter(BUILTIN_STRATEGIES.items()))
        spec = factory()
        spec.validate()
        checks.append(f"strategy compiled: {name}")
        result = Backtester(bars, spec, BacktestConfig()).run()
        checks.append(f"backtest trades: {result.trade_count}")
        assert result.metrics, "the backtest produced no metrics"
        assert result.curves is not None and len(result.curves) == len(bars)
        with tempfile.TemporaryDirectory() as tmp:
            from .reports.csv_export import export_trades_csv

            out = export_trades_csv(result, f"{tmp}/trades.csv")
            checks.append(f"trade export: {out}")
        checks.append(f"main window class: {MainWindow.__name__}")

        # Importing the class is not the same as starting the application, and
        # the difference is exactly where a frozen build fails: it can pass an
        # import-only self-test and still show a white window that never
        # paints. So build the window, run the first-run seeding the way a real
        # launch does, and pump the event loop -- under a wall-clock budget, so
        # a hang fails the build instead of hanging it.
        from .config import AppSettings
        from .storage.workspace import bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            settings = AppSettings()
            settings.workspace_dir = f"{tmp}/workspace"
            workspace = bootstrap(settings)
            started = time.monotonic()
            window = MainWindow(settings, workspace, None)
            window.resize(1280, 800)
            window.show()
            app.processEvents()
            window._first_run()
            for _ in range(20):
                app.processEvents()
            elapsed = time.monotonic() - started
            datasets = [m.name for m in window.datasets.list()]
            window.close()
            app.processEvents()
            if elapsed > SELF_TEST_STARTUP_BUDGET:
                raise AssertionError(
                    f"the window took {elapsed:.1f}s to become usable, over "
                    f"the {SELF_TEST_STARTUP_BUDGET:.0f}s budget -- a launch "
                    f"this slow is what a user reports as a freeze")
            if not datasets:
                raise AssertionError(
                    "the first run seeded no datasets, so the application "
                    "would open on an empty library")
            checks.append(f"window started in {elapsed:.1f}s")
            checks.append(f"datasets seeded: {len(datasets)}")

            # The seeded datasets are small, and that is exactly the blind spot
            # a white-screen report lived in: the chart used to do work
            # proportional to the FILE, so everything passed until a user
            # opened a large dataset and the window stopped painting.  Chart one
            # here, in the packaged binary, under its own budget.
            from .core.timeframe import Timeframe as _Tf

            big = generate_sample_data("BIG", _Tf.parse("5m"),
                                       n_bars=SELF_TEST_LARGE_BARS, seed=5)
            meta = window.datasets.add_from_bars(big, name="SELF-TEST BIG 5m")
            window.on_dataset_changed(meta.id)
            app.processEvents()
            if window._view_bars is None:
                raise AssertionError(
                    f"charting {len(big):,} bars produced no view")
            # Named explicitly, because the two indicator shapes that stalled
            # are a band (Bollinger's shaded channel) and a histogram (MACD's).
            # A strategy drawing plain lines exercises neither, which is how the
            # defect passed every previous self-test.
            for wanted in SELF_TEST_HEAVY_STRATEGIES:
                spec = next((s for s in window.strategies.list()
                             if s.name == wanted), None)
                if spec is None:
                    continue
                started = time.monotonic()
                window.on_strategy_selected(spec.id)
                app.processEvents()
                charted = time.monotonic() - started
                if charted > SELF_TEST_CHART_BUDGET:
                    raise AssertionError(
                        f"drawing '{wanted}' over {len(big):,} bars took "
                        f"{charted:.1f}s, over the "
                        f"{SELF_TEST_CHART_BUDGET:.0f}s budget -- this is the "
                        f"white unresponsive window a user reports as a freeze")
                checks.append(f"{wanted} over {len(big):,} bars: {charted:.1f}s")
            window.datasets.remove(meta.id)
    except Exception as exc:
        print("SELF-TEST FAILED")
        for line in checks:
            print("  ok:", line)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        app.quit()
    print("SELF-TEST PASSED")
    for line in checks:
        print("  ok:", line)
    return 0


#: A frozen build that takes longer than this to put a usable window on screen
#: is one a user reports as a freeze, whatever it is doing. Generous enough for
#: a cold cache and a virus scanner reading every file for the first time.
SELF_TEST_STARTUP_BUDGET = 45.0

#: How many bars the self-test charts.  Matched to the shipped US30 5-minute
#: file (581,195 bars), because that is the scale the freeze was reported at and
#: a smaller sample hides it: the same defect that costs 3.5s here costs 1.4s at
#: 200,000 bars, which would have passed.
SELF_TEST_LARGE_BARS = 500_000

#: Drawing one of those strategies over that dataset.  Measured at this scale:
#: 0.2s with the chart clipping to the view, 3.5s without.  Two seconds sits
#: between the two, so the gate fails on the defect and has ten times the
#: headroom on a working build.
SELF_TEST_CHART_BUDGET = 2.0

#: The built-ins whose drawing used to scale with the file: a shaded band and a
#: signed histogram.
SELF_TEST_HEAVY_STRATEGIES = ("Bollinger Breakout", "MACD Trend")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by ``python -m tradingbacktester`` and by the frozen exe."""
    # Harmless when already called from run.py, and required when someone
    # invokes main() directly from a frozen build.
    multiprocessing.freeze_support()
    args = list(argv if argv is not None else sys.argv)
    if "--self-test" in args:
        return self_test()
    # A real launch on the real platform plugin, which `--self-test` cannot be:
    # it forces the offscreen platform, so it proves the packaging and the
    # Python path and says nothing about the window system. This one starts
    # normally, holds the window open briefly and exits 0 -- so CI can exercise
    # the display path that a white-screen report lives in.
    smoke = "--smoke-test" in args
    if "--version" in args:
        print(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        return 0
    # Breadcrumbs from the first line, to a fixed path that does not depend on
    # the workspace. Until now the log was only opened AFTER the workspace was
    # built, so a launch that stalled before that left nothing to read at all —
    # which is the position a "it shows a white screen" report starts from.
    breadcrumb(f"--- {APP_DISPLAY_NAME} {APP_VERSION} starting "
               f"({'frozen' if _is_frozen() else 'source'}) ---")
    app = create_application(args)
    breadcrumb("Qt application created")

    from .ui.theme import apply_theme

    # Enumerates every installed font, which is the first heavy Qt call and a
    # plausible place for a machine-specific stall.
    breadcrumb("applying the theme (enumerating fonts)")
    apply_theme(app)
    breadcrumb("theme applied")

    # Something on screen BEFORE the workspace is built. Seeding it writes the
    # instrument catalogue and generates the sample datasets, which is under a
    # second here and can be many times that on a first launch where a virus
    # scanner reads every file as it appears. Until now nothing was shown for
    # the whole of it, and a launch that shows nothing is indistinguishable
    # from one that has hung -- which is what "a white screen, not responding"
    # is a report of.
    splash = _splash(app)
    settings = AppSettings.load()
    try:
        # bootstrap creates the folder tree, seeds the instrument catalogue and
        # the sample datasets, and writes the workspace README.  Doing it here
        # rather than in the window means a workspace that cannot be written is
        # reported before any UI exists to be broken by it.
        from .storage.workspace import bootstrap

        _say(app, splash, "Preparing your workspace…")
        breadcrumb("building the workspace")
        workspace = bootstrap(settings)
        breadcrumb(f"workspace ready at {workspace.root}")
        _say(app, splash, "Starting up…")
        log_file = configure_logging(workspace.logs, settings.log_level,
                                     console=not _is_frozen())
    except Exception as exc:  # The workspace is unusable; say so and stop.
        from .ui.widgets.common import show_error

        _close_splash(splash, None)
        show_error(None, exc, "Cannot Start")
        return 2

    log = get_logger(__name__)
    log.info("%s %s starting", APP_DISPLAY_NAME, APP_VERSION)
    log.info("Workspace: %s", workspace.root)

    from .ui.icons import app_icon

    app.setWindowIcon(app_icon(256))

    _say(app, splash, "Opening the window…")
    breadcrumb("building the main window")
    from .ui.main_window import MainWindow

    window = MainWindow(settings, workspace, log_file)
    breadcrumb("main window built")

    def report(message: str, detail: str) -> None:
        from .ui.widgets.common import ErrorDialog

        ErrorDialog("Unexpected Error", message, detail, window).exec()

    install_excepthook(report)
    window.show()
    # Held until the window is up, so there is never a moment with nothing on
    # screen; `finish` also raises the window above the splash on Windows.
    _close_splash(splash, window)
    breadcrumb("window shown, entering the event loop")
    log.info("Start-up breadcrumbs: %s", startup_log_path())
    if smoke:
        return _smoke(app, window)
    code = app.exec()
    breadcrumb(f"exited cleanly with code {code}")
    return code


#: How long `--smoke-test` holds the window open. Long enough for a first paint
#: and the first-run seeding on a slow machine, short enough for CI.
SMOKE_SECONDS = 20.0


def _smoke(app: QApplication, window: Any) -> int:
    """Hold a real window open briefly, then report whether it painted.

    The point is the platform plugin: `--self-test` forces the offscreen one,
    so it cannot tell a working window system from a broken one. This runs on
    whatever the machine actually uses.
    """
    import time

    deadline = time.monotonic() + SMOKE_SECONDS
    painted = False
    while time.monotonic() < deadline:
        app.processEvents()
        if not painted and window.isVisible() and window.width() > 0:
            painted = True
            breadcrumb(f"window is visible at {window.width()}x{window.height()}")
        time.sleep(0.05)
    breadcrumb(f"smoke test finished, painted={painted}")
    print(f"SMOKE TEST {'PASSED' if painted else 'FAILED'}")
    print(f"  platform: {app.platformName()}")
    print(f"  window:   {window.width()}x{window.height()} "
          f"visible={window.isVisible()}")
    print(f"  breadcrumbs: {startup_log_path()}")
    window.close()
    app.processEvents()
    return 0 if painted else 1


# --------------------------------------------------------------------------
# the splash
# --------------------------------------------------------------------------

def _splash(app: QApplication) -> Any:
    """A small window saying the application is starting.

    Never fatal: a splash that cannot be created is not a reason to fail a
    launch, so every failure here returns ``None`` and the caller carries on
    without one.
    """
    try:
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QSplashScreen

        from .ui.icons import app_icon
        from .ui.theme import PALETTE

        pixmap = QPixmap(420, 160)
        pixmap.fill(QColor(PALETTE.panel_bg))
        painter = QPainter(pixmap)
        try:
            painter.setPen(QColor(PALETTE.border_strong))
            painter.drawRect(0, 0, pixmap.width() - 1, pixmap.height() - 1)
            app_icon(64).paint(painter, 24, 30, 64, 64)
            painter.setPen(QColor(PALETTE.text))
            font = painter.font()
            font.setPointSize(15)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(108, 62, APP_DISPLAY_NAME)
            painter.setPen(QColor(PALETTE.text_muted))
            small = painter.font()
            small.setPointSize(9)
            small.setBold(False)
            painter.setFont(small)
            painter.drawText(108, 84, f"Version {APP_VERSION}")
        finally:
            painter.end()

        splash = QSplashScreen(pixmap)
        splash.show()
        app.processEvents()
        return splash
    except Exception:                       # noqa: BLE001 - see the docstring
        return None


def _say(app: QApplication, splash: Any, message: str) -> None:
    """Put a line on the splash and let it paint."""
    if splash is not None:
        try:
            from PySide6.QtCore import Qt

            from .ui.theme import PALETTE

            splash.showMessage(
                f"  {message}",
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                QColor(PALETTE.text_dim))
        except Exception:                   # noqa: BLE001 - cosmetic only
            pass
    app.processEvents()


def _close_splash(splash: Any, window: Any) -> None:
    if splash is None:
        return
    try:
        if window is not None:
            splash.finish(window)
        else:
            splash.close()
    except Exception:                       # noqa: BLE001 - cosmetic only
        pass


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
