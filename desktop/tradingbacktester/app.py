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
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from .config import APP_DISPLAY_NAME, APP_ORG, APP_VERSION, AppSettings
from .logging_setup import configure_logging, get_logger, install_excepthook


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


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point used by ``python -m tradingbacktester`` and by the frozen exe."""
    # Harmless when already called from run.py, and required when someone
    # invokes main() directly from a frozen build.
    multiprocessing.freeze_support()
    args = list(argv if argv is not None else sys.argv)
    if "--self-test" in args:
        return self_test()
    if "--version" in args:
        print(f"{APP_DISPLAY_NAME} {APP_VERSION}")
        return 0
    app = create_application(args)

    settings = AppSettings.load()
    try:
        # bootstrap creates the folder tree, seeds the instrument catalogue and
        # the sample datasets, and writes the workspace README.  Doing it here
        # rather than in the window means a workspace that cannot be written is
        # reported before any UI exists to be broken by it.
        from .storage.workspace import bootstrap

        workspace = bootstrap(settings)
        log_file = configure_logging(workspace.logs, settings.log_level,
                                     console=not _is_frozen())
    except Exception as exc:  # The workspace is unusable; say so and stop.
        from .ui.theme import apply_theme
        from .ui.widgets.common import show_error

        apply_theme(app)
        show_error(None, exc, "Cannot Start")
        return 2

    log = get_logger(__name__)
    log.info("%s %s starting", APP_DISPLAY_NAME, APP_VERSION)
    log.info("Workspace: %s", workspace.root)

    from .ui.theme import apply_theme
    from .ui.icons import app_icon

    apply_theme(app)
    app.setWindowIcon(app_icon(256))

    from .ui.main_window import MainWindow

    window = MainWindow(settings, workspace, log_file)

    def report(message: str, detail: str) -> None:
        from .ui.widgets.common import ErrorDialog

        ErrorDialog("Unexpected Error", message, detail, window).exec()

    install_excepthook(report)
    window.show()
    return app.exec()


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
