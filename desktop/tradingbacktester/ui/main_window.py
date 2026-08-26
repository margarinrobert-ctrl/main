"""The main window: menus, toolbar, docks and the wiring between them.

Layout follows the shape of a trading terminal rather than a form-filling
application: configuration down the left, the chart in the middle, statistics on
the right, and the blotter along the bottom.  Every dock is movable and the
geometry is remembered between sessions.

The window itself holds no business logic.  It reads panels, calls into the
engine on a worker thread, and hands the result to the views.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QFrame,
                               QHBoxLayout, QLabel, QMainWindow, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QStatusBar,
                               QTabWidget, QToolBar, QVBoxLayout, QWidget)

from ..config import APP_DISPLAY_NAME, APP_VERSION, AppSettings, Workspace
from ..core.errors import BacktesterError, InsufficientDataError
from ..core.timeframe import Timeframe
from ..engine.results import BacktestResult
from ..logging_setup import get_logger
from ..strategy.spec import StrategySpec
from .icons import icon
from .theme import PALETTE, Fonts, currency_symbol, money, pct
from .widgets.chart_widget import ChartWidget
from .widgets.common import (Card, ask_text, confirm, show_error, show_info,
                             show_warning)
from .widgets.data_panel import DataPanel
from .widgets.equity_widget import EquityWidget
from .widgets.periodic_table import DrawdownTable, PeriodicReturnsTable
from .widgets.risk_panel import RiskPanel
from .widgets.stats_panel import StatsPanel
from .widgets.strategy_panel import StrategyPanel
from .widgets.trade_table import TradeTableWidget
from .workers import TaskRunner, import_csv_task, run_backtest_task

log = get_logger(__name__)


class MainWindow(QMainWindow):
    """The application window."""

    def __init__(self, settings: AppSettings, workspace: Workspace,
                 log_file: Path | None = None) -> None:
        super().__init__()
        self.settings = settings
        self.workspace = workspace
        self.log_file = log_file

        self._bars: Any = None                # source bars, as imported
        self._view_bars: Any = None           # after timeframe + date range
        self._quality: Any = None
        self._spec: StrategySpec | None = None
        self._result: BacktestResult | None = None
        self._saved_results: list[BacktestResult] = []
        self._runner = TaskRunner(self)
        self._dirty_strategy = False

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1680, 980)
        self.setMinimumSize(1180, 720)
        self.setDockOptions(QMainWindow.DockOption.AllowNestedDocks |
                            QMainWindow.DockOption.AllowTabbedDocks |
                            QMainWindow.DockOption.AnimatedDocks)

        self._build_services()
        self._build_actions()
        self._build_toolbar()
        self._build_menus()
        self._build_central()
        self._build_docks()
        self._build_statusbar()
        self._connect()
        self._restore_geometry()
        QTimer.singleShot(0, self._first_run)

    # ------------------------------------------------------------------
    # Set-up
    # ------------------------------------------------------------------

    def _build_services(self) -> None:
        from ..data.instruments import InstrumentRegistry
        from ..data.repository import DatasetRepository
        from ..storage.backtest_store import BacktestStore
        from ..strategy.storage import StrategyStore

        self.instruments = InstrumentRegistry(self.workspace.settings / "instruments.json")
        self.datasets = DatasetRepository(self.workspace)
        self.strategies = StrategyStore(self.workspace)
        self.backtests = BacktestStore(self.workspace)

    def _build_actions(self) -> None:
        def act(name: str, text: str, ico: str = "", shortcut: str = "",
                tip: str = "", slot=None, checkable: bool = False) -> QAction:
            a = QAction(text, self)
            if ico:
                a.setIcon(icon(ico, 18))
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(tip or text)
            a.setStatusTip(tip or text)
            a.setCheckable(checkable)
            if slot is not None:
                a.triggered.connect(slot)
            setattr(self, f"act_{name}", a)
            return a

        act("import", "Import CSV…", "import", "Ctrl+I",
            "Import an OHLCV CSV file", self.on_import_csv)
        act("sample", "Load Sample Data", "database", "",
            "Load the bundled synthetic dataset", self.on_load_sample)
        act("shipped", "Import Shipped Market Data…", "database", "",
            "Import the real market data that came with the application",
            self.on_load_shipped)
        act("datasets", "Manage Datasets…", "database", "Ctrl+D",
            "Rename or remove imported datasets", self.on_manage_datasets)
        act("instruments", "Instruments…", "settings", "",
            "Edit instrument contract specifications", self.on_instruments)
        act("quality", "Data Quality Report…", "warning", "",
            "Show the validation report for the loaded dataset", self.on_quality)

        act("new_strategy", "New Strategy", "plus", "Ctrl+N",
            "Create a strategy", self.on_new_strategy)
        act("edit_strategy", "Edit Strategy…", "strategy", "Ctrl+E",
            "Edit the entry and exit rules", self.on_edit_strategy)
        act("save_strategy", "Save Strategy", "save", "Ctrl+S",
            "Save the current strategy", self.on_save_strategy)
        act("duplicate_strategy", "Duplicate Strategy", "copy", "",
            "Copy the current strategy", self.on_duplicate_strategy)
        act("rename_strategy", "Rename Strategy…", "rename", "",
            "Rename the current strategy", self.on_rename_strategy)
        act("delete_strategy", "Delete Strategy", "trash", "",
            "Delete the current strategy", self.on_delete_strategy)
        act("import_strategy", "Import Strategy…", "import", "",
            "Load a strategy from a JSON file", self.on_import_strategy)
        act("export_strategy", "Export Strategy…", "export", "",
            "Save the current strategy to a JSON file", self.on_export_strategy)

        act("find", "Find Strategies…", "search", "Ctrl+F",
            "Search this data for entry rules that beat a matched random "
            "control", self.on_find_strategies)

        act("run", "Run Backtest", "run", "F5",
            "Run the backtest", self.on_run_backtest)
        act("cancel", "Cancel", "stop", "Esc",
            "Cancel the running task", self.on_cancel)
        self.act_cancel.setEnabled(False)
        act("save_run", "Save Backtest", "save", "Ctrl+Shift+S",
            "Keep this run so it can be compared later", self.on_save_run)
        act("browse_runs", "Saved Backtests…", "layers", "Ctrl+B",
            "Open a saved run", self.on_browse_runs)
        act("compare", "Compare Runs…", "compare", "Ctrl+K",
            "Compare saved backtests side by side", self.on_compare)
        act("optimize", "Optimise Parameters…", "optimize", "Ctrl+O",
            "Sweep a parameter grid over historical data", self.on_optimize)
        act("montecarlo", "Monte Carlo…", "shield", "Ctrl+M",
            "Resample this run's trades to see the range of paths they could "
            "have produced", self.on_monte_carlo)
        act("mirror", "Mirror-Market Test…", "compare", "",
            "Run this strategy again on a market with the same volatility and "
            "the opposite drift", self.on_mirror_test)

        act("export_trades", "Export Trades to CSV…", "export", "",
            "Save the trade list", self.on_export_trades)
        act("export_equity", "Export Equity Curve to CSV…", "export", "",
            "Save the equity and drawdown series", self.on_export_equity)
        act("export_report", "Export HTML Report…", "report", "Ctrl+R",
            "Save a full backtest report", self.on_export_report)
        act("export_pdf", "Export PDF Report…", "report", "",
            "Save a printable backtest report", self.on_export_pdf)

        # Connected to `toggled` rather than `triggered` so the mode follows the
        # checkbox however it was changed -- including from restored settings.
        act("simple", "Simple Mode", "", "",
            "Hide the optimiser, comparison and risk panels. Everything still "
            "works; there is just less of it on screen.",
            None, checkable=True)
        self.act_simple.toggled.connect(self.on_toggle_simple)
        act("start_here", "Show Start Here", "", "",
            "Bring back the three-step guide in the configuration panel",
            self.on_show_start_here)

        act("workspace", "Change Workspace Folder…", "workspace", "",
            "Choose where data, strategies and results are stored",
            self.on_change_workspace)
        act("open_workspace", "Open Workspace Folder", "folder-open", "",
            "Show the workspace in the file manager", self.on_open_workspace)
        act("open_log", "Open Log File", "report", "",
            "Show the application log", self.on_open_log)
        act("assumptions", "Backtesting Assumptions", "info", "",
            "How orders, costs and fills are simulated", self.on_assumptions)
        act("metrics_help", "Metric Definitions", "info", "",
            "What every statistic means and how it is computed", self.on_metrics_help)
        act("about", "About", "info", "", "About this application", self.on_about)
        act("quit", "Exit", "close", "Ctrl+Q", "Close the application", self.close)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setObjectName("toolbar_main")   # required by saveState/restoreState
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self.toolbar = tb

        tb.addAction(self.act_import)
        tb.addAction(self.act_sample)
        tb.addSeparator()
        tb.addAction(self.act_new_strategy)
        tb.addAction(self.act_edit_strategy)
        tb.addAction(self.act_save_strategy)
        tb.addSeparator()

        self.run_button = QPushButton("  RUN BACKTEST")
        self.run_button.setObjectName("Primary")
        self.run_button.setIcon(icon("run", 16, "#ffffff"))
        self.run_button.setMinimumHeight(28)
        self.run_button.setMinimumWidth(160)
        self.run_button.setShortcut(QKeySequence("F5"))
        self.run_button.clicked.connect(self.on_run_backtest)
        tb.addWidget(self.run_button)

        self.cancel_button = QPushButton("  Cancel")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.setIcon(icon("stop", 15, "#ffffff"))
        self.cancel_button.setMinimumHeight(28)
        self.cancel_button.clicked.connect(self.on_cancel)
        self.cancel_button.hide()
        tb.addWidget(self.cancel_button)

        self.find_button = QPushButton("  Find Strategies")
        self.find_button.setIcon(icon("search", 15))
        self.find_button.setMinimumHeight(28)
        self.find_button.setToolTip(self.act_find.toolTip())
        self.find_button.clicked.connect(self.on_find_strategies)
        tb.addWidget(self.find_button)

        tb.addSeparator()
        # Kept so Simple Mode can take them off the toolbar rather than merely
        # disabling them: a greyed-out button still has to be understood.
        self._advanced_toolbar = [tb.addAction(self.act_optimize),
                                  tb.addAction(self.act_compare)]
        tb.addAction(self.act_save_run)
        tb.addSeparator()
        tb.addAction(self.act_export_report)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)

        self.headline = QLabel("")
        self.headline.setFont(Fonts.numeric(10, bold=True))
        self.headline.setStyleSheet("background: transparent; padding-right: 8px;")
        tb.addWidget(self.headline)

    def _build_menus(self) -> None:
        bar = self.menuBar()

        m = bar.addMenu("&File")
        m.addAction(self.act_import)
        m.addAction(self.act_sample)
        m.addAction(self.act_datasets)
        m.addSeparator()
        m.addAction(self.act_import_strategy)
        m.addAction(self.act_export_strategy)
        m.addSeparator()
        m.addAction(self.act_export_trades)
        m.addAction(self.act_export_equity)
        m.addAction(self.act_export_report)
        m.addAction(self.act_export_pdf)
        m.addSeparator()
        m.addAction(self.act_workspace)
        m.addAction(self.act_open_workspace)
        m.addSeparator()
        m.addAction(self.act_quit)

        m = bar.addMenu("&Data")
        m.addAction(self.act_import)
        m.addAction(self.act_shipped)
        m.addAction(self.act_datasets)
        m.addAction(self.act_quality)
        m.addSeparator()
        m.addAction(self.act_instruments)

        m = bar.addMenu("&Strategy")
        for a in (self.act_new_strategy, self.act_edit_strategy, self.act_save_strategy,
                  self.act_duplicate_strategy, self.act_rename_strategy,
                  self.act_delete_strategy):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_import_strategy)
        m.addAction(self.act_export_strategy)

        m = bar.addMenu("&Backtest")
        m.addAction(self.act_find)
        m.addSeparator()
        m.addAction(self.act_run)
        m.addAction(self.act_cancel)
        m.addSeparator()
        m.addAction(self.act_save_run)
        m.addAction(self.act_browse_runs)
        m.addAction(self.act_compare)
        m.addSeparator()
        m.addAction(self.act_optimize)
        m.addAction(self.act_montecarlo)
        m.addAction(self.act_mirror)

        self.view_menu = bar.addMenu("&View")
        self.view_menu.addAction(self.act_simple)
        self.view_menu.addAction(self.act_start_here)
        self.view_menu.addSeparator()

        m = bar.addMenu("&Help")
        m.addAction(self.act_assumptions)
        m.addAction(self.act_metrics_help)
        m.addAction(self.act_open_log)
        m.addSeparator()
        m.addAction(self.act_about)

    def _build_central(self) -> None:
        from .widgets.comparison_view import ComparisonView

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.chart = ChartWidget()
        self.tabs.addTab(self.chart, icon("candles", 15), "Chart")

        self.equity = EquityWidget()
        self.tabs.addTab(self.equity, icon("line-chart", 15), "Equity")

        self.monthly = PeriodicReturnsTable()
        monthly_wrap = QWidget()
        wl = QVBoxLayout(monthly_wrap)
        wl.setContentsMargins(8, 8, 8, 8)
        wl.addWidget(self.monthly)
        self.tabs.addTab(monthly_wrap, icon("calendar", 15), "Periodic Returns")

        self.comparison = ComparisonView()
        self.tabs.addTab(self.comparison, icon("compare", 15), "Comparison")

        self.setCentralWidget(self.tabs)

    def _build_docks(self) -> None:
        # -- left: configuration -----------------------------------------
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(7, 7, 5, 7)
        ll.setSpacing(7)

        from .widgets.start_here import StartHere

        self.start_here = StartHere()
        self.start_here.importRequested.connect(self.on_import_csv)
        self.start_here.findRequested.connect(self.on_find_strategies)
        self.start_here.dismissed.connect(self._on_start_here_dismissed)
        ll.addWidget(self.start_here)

        self.data_panel = DataPanel()
        self.strategy_panel = StrategyPanel()
        self.risk_panel = RiskPanel()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 0, 5, 0)
        il.setSpacing(7)
        il.addWidget(self.data_panel)
        il.addWidget(self.strategy_panel)
        il.addWidget(self.risk_panel)
        il.addStretch(1)
        scroll.setWidget(inner)
        ll.addWidget(scroll, 1)

        run_row = QHBoxLayout()
        run_row.setSpacing(6)
        self.run_button_left = QPushButton("  RUN BACKTEST")
        self.run_button_left.setObjectName("Primary")
        self.run_button_left.setIcon(icon("run", 16, "#ffffff"))
        self.run_button_left.setMinimumHeight(34)
        self.run_button_left.clicked.connect(self.on_run_backtest)
        run_row.addWidget(self.run_button_left, 1)
        ll.addLayout(run_row)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        self.progress.hide()
        ll.addWidget(self.progress)

        self.left_dock = QDockWidget("Configuration", self)
        self.left_dock.setObjectName("dock_config")
        self.left_dock.setWidget(left)
        self.left_dock.setMinimumWidth(330)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)

        # -- right: statistics -------------------------------------------
        self.stats = StatsPanel()
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(5, 7, 7, 7)
        rl.addWidget(self.stats)
        self.right_dock = QDockWidget("Performance", self)
        self.right_dock.setObjectName("dock_stats")
        self.right_dock.setWidget(right)
        self.right_dock.setMinimumWidth(310)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)

        # -- bottom: blotter ---------------------------------------------
        self.bottom_tabs = QTabWidget()
        self.bottom_tabs.setDocumentMode(True)
        self.trade_table = TradeTableWidget()
        self.bottom_tabs.addTab(self.trade_table, icon("table", 15), "Trades")
        self.drawdowns = DrawdownTable()
        dd_wrap = QWidget()
        dl = QVBoxLayout(dd_wrap)
        dl.setContentsMargins(8, 8, 8, 8)
        dl.addWidget(self.drawdowns)
        self.bottom_tabs.addTab(dd_wrap, icon("arrow-down", 15), "Drawdowns")

        from .widgets.log_view import LogView

        self.log_view = LogView(self.log_file)
        self.bottom_tabs.addTab(self.log_view, icon("report", 15), "Log")

        self.bottom_dock = QDockWidget("Trades", self)
        self.bottom_dock.setObjectName("dock_trades")
        self.bottom_dock.setWidget(self.bottom_tabs)
        self.bottom_dock.setMinimumHeight(180)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.bottom_dock)

        self.act_simple.blockSignals(True)
        self.act_simple.setChecked(bool(getattr(self.settings, "simple_mode", True)))
        self.act_simple.blockSignals(False)
        self._apply_simple_mode(self.act_simple.isChecked())
        if not getattr(self.settings, "show_start_here", True):
            self.start_here.hide()

        for dock in (self.left_dock, self.right_dock, self.bottom_dock):
            self.view_menu.addAction(dock.toggleViewAction())
        self.view_menu.addSeparator()
        reset = QAction("Reset Layout", self)
        reset.triggered.connect(self.on_reset_layout)
        self.view_menu.addAction(reset)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.status_message = QLabel("Ready")
        self.status_message.setFont(Fonts.body(9))
        sb.addWidget(self.status_message, 1)

        self.status_data = QLabel("")
        self.status_data.setFont(Fonts.numeric(8))
        self.status_data.setStyleSheet(f"color:{PALETTE.text_muted};")
        sb.addPermanentWidget(self.status_data)

        self.status_workspace = QLabel(str(self.workspace.root))
        self.status_workspace.setFont(Fonts.numeric(8))
        self.status_workspace.setStyleSheet(f"color:{PALETTE.text_muted};")
        self.status_workspace.setToolTip(
            "Everything this application writes lives here. Nothing is sent "
            "anywhere else.")
        sb.addPermanentWidget(self.status_workspace)

    def _connect(self) -> None:
        self.data_panel.set_repository(self.datasets)
        self.strategy_panel.set_store(self.strategies)

        self.data_panel.datasetChanged.connect(self.on_dataset_changed)
        self.data_panel.timeframeChanged.connect(self.on_view_changed)
        self.data_panel.rangeChanged.connect(self.on_view_changed)
        self.data_panel.importRequested.connect(self.on_import_csv)
        self.data_panel.sampleRequested.connect(self.on_load_sample)
        self.data_panel.instrumentsRequested.connect(self.on_instruments)
        self.data_panel.qualityRequested.connect(self.on_quality)
        self.data_panel.manageRequested.connect(self.on_manage_datasets)

        self.strategy_panel.strategySelected.connect(self.on_strategy_selected)
        self.strategy_panel.parametersChanged.connect(self.on_parameters_changed)
        self.strategy_panel.newRequested.connect(self.on_new_strategy)
        self.strategy_panel.editRequested.connect(self.on_edit_strategy)
        self.strategy_panel.duplicateRequested.connect(self.on_duplicate_strategy)
        self.strategy_panel.renameRequested.connect(self.on_rename_strategy)
        self.strategy_panel.deleteRequested.connect(self.on_delete_strategy)
        self.strategy_panel.importRequested.connect(self.on_import_strategy)
        self.strategy_panel.exportRequested.connect(self.on_export_strategy)
        self.strategy_panel.saveRequested.connect(self.on_save_strategy)

        self.risk_panel.changed.connect(self._mark_config_dirty)

        self.chart.tradeClicked.connect(self.on_chart_trade_clicked)
        self.chart.barHovered.connect(self.equity.set_cursor_bar)
        self.trade_table.tradeSelected.connect(self.on_table_trade_selected)
        self.trade_table.exportRequested.connect(self.on_export_trades)

        self._runner.progress.connect(self.on_progress)
        self._runner.finished.connect(self.on_task_finished)
        self._runner.failed.connect(self.on_task_failed)
        self._runner.cancelled.connect(self.on_task_cancelled)
        self._runner.stateChanged.connect(self.on_task_state)

    # ------------------------------------------------------------------
    # Start-up
    # ------------------------------------------------------------------

    def _first_run(self) -> None:
        """Seed the workspace and restore the last session's selection."""
        try:
            from ..strategy.builtin import BUILTIN_STRATEGIES

            seeded = self.strategies.seed_builtins(BUILTIN_STRATEGIES)
            if seeded:
                log.info("Seeded %d built-in strategies", len(seeded))
        except BacktesterError as exc:
            show_warning(self, "Workspace", exc.user_message, exc.detail or "")
        except Exception:
            log.exception("Strategy seeding failed")

        if not self.datasets.list():
            # A first run with an empty library opens on nothing at all, which
            # tells a new user nothing about what the application does.  Real
            # market data is imported first, so the first thing on screen is a
            # real chart; the synthetic samples follow, and every surface that
            # shows them says they are not real data.
            try:
                self._import_bundled_datasets(self.STARTUP_IMPORT_LIMIT)
            except Exception:
                log.exception("Importing the shipped market data failed")
            try:
                self._import_sample_datasets()
            except Exception:
                log.exception("Importing the sample datasets failed")

        self.data_panel.refresh_datasets(self.settings.last_dataset
                                         or self._preferred_dataset())
        self.strategy_panel.refresh(self.settings.last_strategy or None)
        self._update_actions()
        self._update_start_here()
        if self._bars is None:
            self.status("Import a CSV, or press Sample to load the bundled "
                        "synthetic dataset.")

    #: Shipped files larger than this are not imported at start-up.  Half a
    #: million bars takes twenty seconds to parse, and a first launch that
    #: hangs for twenty seconds is a worse introduction than a smaller chart.
    STARTUP_IMPORT_LIMIT = 1_000_000

    def _preferred_dataset(self) -> str | None:
        """Which dataset to open on when the user has not chosen one yet.

        Real market data before synthetic: the first chart someone sees should
        be a real instrument, and the samples exist for when there is nothing
        else, not as the default.
        """
        from ..data.bundled import BUNDLED

        shipped = {d.name for d in BUNDLED}
        rows = self.datasets.list()
        real = [m for m in rows if m.name in shipped]
        if real:
            # The longest one: a four-hundred-bar daily series is real, but it
            # is not enough to show what the application does.
            return max(real, key=lambda m: int(getattr(m, "bar_count", 0) or 0)).id
        return rows[0].id if rows else None

    def _import_bundled_datasets(self, limit: int | None = None,
                                 progress: Any = None) -> list[Any]:
        """Import the real market data that ships with the application.

        Skips anything already in the library, so it is safe on every launch.
        *limit* caps the file size considered, which is how start-up stays
        quick; ``None`` imports everything and is what the menu item uses.
        """
        from ..data.bundled import available
        from ..data.csv_loader import load_csv, sniff_csv

        existing = {m.name for m in self.datasets.list()}
        added: list[Any] = []
        pending = [d for d in available() if d.name not in existing
                   and (limit is None or d.path().stat().st_size <= limit)]
        for index, dataset in enumerate(pending):
            if progress is not None:
                progress(index, len(pending), f"Importing {dataset.name}")
            try:
                instrument = self.instruments.ensure(dataset.symbol,
                                                     dataset.asset_class)
                profile = sniff_csv(str(dataset.path()))
                bars = load_csv(str(dataset.path()), profile.mapping, instrument)
                meta = self.datasets.add_from_bars(
                    bars, name=dataset.name, source_path=str(dataset.path()),
                    notes=dataset.description)
                added.append(meta)
                log.info("Imported shipped dataset %s (%d bars)", dataset.name,
                         len(bars))
            except BacktesterError as exc:
                log.warning("Could not import %s: %s", dataset.name,
                            exc.user_message)
        if added:
            try:
                self.instruments.save()
            except BacktesterError:
                log.warning("Could not save the instrument catalogue")
        if progress is not None:
            progress(len(pending), len(pending), "")
        return added

    def _import_sample_datasets(self) -> list[Any]:
        """Load every bundled sample CSV into the dataset library.

        Returns the metadata rows that were added.  Already-imported samples are
        skipped, so this is safe to call on every launch.
        """
        from ..data.csv_loader import load_csv, sniff_csv
        from ..data.sample import ensure_samples

        paths = ensure_samples(self.workspace)
        if not paths:
            paths = sorted(self.workspace.samples.glob("*.csv"))
        existing = {m.source_path for m in self.datasets.list()}
        added: list[Any] = []
        for path in paths:
            if str(path) in existing:
                continue
            try:
                profile = sniff_csv(path)
                symbol = _symbol_from_sample_name(path.stem)
                instrument = self.instruments.get(symbol) if symbol else None
                if instrument is None:
                    from ..data.models import Instrument

                    instrument = Instrument.with_defaults(symbol or "SAMPLE")
                bars = load_csv(path, profile.mapping, instrument)
                meta = self.datasets.add_from_bars(
                    bars, name=path.stem.replace("_", " "),
                    source_path=str(path),
                    notes="Synthetic test data generated by this application. "
                          "It contains no real market prices.")
                added.append(meta)
                log.info("Imported sample dataset %s (%d bars)", path.name, len(bars))
            except BacktesterError as exc:
                log.warning("Could not import the sample %s: %s", path.name,
                            exc.user_message)
        return added

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def on_dataset_changed(self, dataset_id: str) -> None:
        if not dataset_id:
            self._bars = None
            self._view_bars = None
            self.data_panel.set_bars(None)
            self.chart.clear()
            self._update_actions()
            return
        try:
            bars = self.datasets.load_bars(dataset_id)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._bars = bars
        self.settings.last_dataset = dataset_id
        self.settings.save()
        try:
            from ..data.validation import validate_bars

            self._quality = validate_bars(bars)
        except Exception:
            log.exception("Validation failed")
            self._quality = None
        self.data_panel.set_bars(bars, self._quality)
        self.on_view_changed()
        if self._quality is not None and getattr(self._quality, "errors", None):
            self.status(f"{bars.instrument.symbol}: "
                        f"{len(self._quality.errors)} data problems found — see the "
                        f"quality report before trusting a backtest.")
        self._update_start_here()

    def on_view_changed(self, *_args) -> None:
        """Rebuild the displayed bars after a timeframe or date-range change."""
        if self._bars is None:
            return
        try:
            from ..data.resample import resample

            target = self.data_panel.current_timeframe()
            bars = self._bars
            if target is not None and target != bars.timeframe:
                bars = resample(bars, target)
            start, end = self.data_panel.date_range_ns()
            if start is not None or end is not None:
                bars = bars.slice_time(start, end)
        except InsufficientDataError as exc:
            self.status(exc.user_message)
            return
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._view_bars = bars
        self.chart.set_bars(bars)
        self._show_strategy_indicators()
        self.status_data.setText(bars.describe())
        self._update_actions()

    def _show_strategy_indicators(self) -> None:
        """Draw the current strategy's indicators without running a backtest."""
        if self._view_bars is None or self._spec is None:
            self.chart.set_indicator_panels([])
            return
        try:
            from ..strategy.compiler import compile_strategy

            compiled = compile_strategy(self._spec, self._view_bars,
                                        self.strategy_panel.parameter_overrides())
        except BacktesterError as exc:
            self.chart.set_indicator_panels([])
            self.status(exc.user_message)
            return
        except Exception:
            log.exception("Indicator preview failed")
            self.chart.set_indicator_panels([])
            return
        self.chart.set_indicator_panels(self._build_panel_specs(compiled))

    def _build_panel_specs(self, compiled: Any) -> list[dict[str, Any]]:
        """Translate compiled indicator arrays into chart panel descriptions."""
        from ..indicators.registry import REGISTRY

        panels: list[dict[str, Any]] = []
        colour_index = 0
        for slot in self._spec.indicators if self._spec else []:
            if not slot.plot:
                continue
            arrays = compiled.indicators.get(slot.ref)
            if not arrays:
                continue
            try:
                definition = REGISTRY.get(slot.indicator)
            except BacktesterError:
                continue
            on_price = (slot.panel == "price" or
                        (slot.panel == "auto" and definition.overlay))
            series = []
            for name in definition.outputs:
                values = arrays.get(name)
                if values is None:
                    continue
                style = definition.plot_style.get(name, {})
                colour = (slot.color if slot.color and len(arrays) == 1
                          else style.get("color") or PALETTE.series_color(colour_index))
                colour_index += 1
                entry = {
                    "name": f"{slot.display_label()} {name}" if len(arrays) > 1
                            else slot.display_label(),
                    "output": name,
                    "values": values, "color": colour,
                    "width": style.get("width", 1.3),
                    "style": style.get("style", "solid"),
                    "kind": style.get("kind", "line"),
                }
                # Carry the registry's richer drawing hints through untouched.
                for hint in ("fill_to", "fill_color", "negative_color",
                             "colour_by", "panel"):
                    if hint in style:
                        entry[hint] = style[hint]
                series.append(entry)
            guides, rng = self._panel_guides(definition.scale_hint)
            panels.append({"ref": slot.ref, "label": slot.display_label(),
                           "panel": "price" if on_price else "sub",
                           "series": series, "guides": guides, "range": rng})
        return panels

    @staticmethod
    def _panel_guides(scale_hint: str) -> tuple[tuple[float, ...], tuple[float, float] | None]:
        if scale_hint == "oscillator_0_100":
            return ((30.0, 50.0, 70.0), (0.0, 100.0))
        if scale_hint == "zero_centred":
            return ((0.0,), None)
        return ((), None)

    # ------------------------------------------------------------------
    # Strategy
    # ------------------------------------------------------------------

    def on_strategy_selected(self, strategy_id: str) -> None:
        if not strategy_id:
            self._spec = None
            self.strategy_panel.set_spec(None)
            self._update_actions()
            return
        try:
            spec = self.strategies.load(strategy_id)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._spec = spec
        self._dirty_strategy = False
        self.settings.last_strategy = strategy_id
        self.settings.save()
        self.strategy_panel.set_spec(spec)
        self._apply_strategy_config(spec)
        self._show_strategy_indicators()
        self._update_actions()
        self._update_start_here()

    def _apply_strategy_config(self, spec: StrategySpec) -> None:
        """Load the strategy's own risk and cost settings into the panel.

        With one exception: a strategy that carries no cost model at all -- as
        every built-in one does, because costs depend on the instrument and the
        broker, not on the rules -- must not wipe the costs the user has set.
        Silently zeroing commission and spread when someone switches strategy
        would make every subsequent run look better for no reason, which is
        exactly the kind of quiet flattery this application is built to avoid.
        """
        config = self._config_from_spec(spec)
        if _costs_are_empty(spec.costs):
            try:
                config.costs = self.risk_panel.build_config().costs
                if not _costs_are_empty(config.costs):
                    self.status(
                        f"'{spec.name}' carries no cost model, so the commission, "
                        f"spread and slippage already set have been kept.")
            except BacktesterError:
                pass
        self.risk_panel.apply_config(config)

    def _config_from_spec(self, spec: StrategySpec) -> Any:
        from ..core.types import BacktestConfig

        return BacktestConfig(
            starting_capital=spec.risk.starting_capital, risk=spec.risk,
            costs=spec.costs, session=spec.session, exits=spec.exits,
            execution=spec.execution)

    def on_parameters_changed(self) -> None:
        self._dirty_strategy = True
        self._show_strategy_indicators()
        self._update_actions()

    def _mark_config_dirty(self) -> None:
        self._dirty_strategy = True
        self._update_actions()

    def on_new_strategy(self) -> None:
        from .dialogs.strategy_editor import StrategyEditor

        spec = StrategySpec(name="New Strategy")
        editor = StrategyEditor(spec, self)
        if editor.exec() != editor.DialogCode.Accepted:
            return
        try:
            saved = self.strategies.save(editor.spec)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.strategy_panel.refresh(saved.id)

    def on_edit_strategy(self) -> None:
        if self._spec is None:
            show_info(self, "No Strategy", "Select or create a strategy first.")
            return
        from .dialogs.strategy_editor import StrategyEditor

        editor = StrategyEditor(self._spec.copy(self._spec.name), self,
                                bars=self._view_bars)
        editor.spec.id = self._spec.id
        if editor.exec() != editor.DialogCode.Accepted:
            return
        try:
            edited = editor.spec
            edited.id = self._spec.id
            self._apply_panel_settings(edited)
            saved = self.strategies.save(edited)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.strategy_panel.refresh(saved.id)
        self.on_strategy_selected(saved.id)

    def _apply_panel_settings(self, spec: StrategySpec) -> None:
        """Fold the risk panel's current values back into the strategy."""
        try:
            config = self.risk_panel.build_config()
        except BacktesterError:
            return
        spec.risk = config.risk
        spec.costs = config.costs
        spec.exits = config.exits
        spec.session = config.session
        spec.execution = config.execution

    def on_save_strategy(self) -> None:
        if self._spec is None:
            return
        try:
            self._apply_panel_settings(self._spec)
            for name, value in self.strategy_panel.parameter_overrides().items():
                for p in self._spec.params:
                    if p.name == name:
                        object.__setattr__(p, "default", value)
            saved = self.strategies.save(self._spec)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._dirty_strategy = False
        self.strategy_panel.refresh(saved.id)
        self.status(f"Saved strategy '{saved.name}'.")
        self._update_actions()

    def on_duplicate_strategy(self) -> None:
        if self._spec is None:
            return
        name = ask_text(self, "Duplicate Strategy", "Name for the copy:",
                        f"{self._spec.name} copy")
        if not name:
            return
        try:
            copy = self.strategies.duplicate(self._spec.id, name)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.strategy_panel.refresh(copy.id)

    def on_rename_strategy(self) -> None:
        if self._spec is None:
            return
        name = ask_text(self, "Rename Strategy", "New name:", self._spec.name)
        if not name:
            return
        try:
            renamed = self.strategies.rename(self._spec.id, name)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.strategy_panel.refresh(renamed.id)

    def on_delete_strategy(self) -> None:
        if self._spec is None:
            return
        if self.settings.confirm_on_delete and not confirm(
                self, "Delete Strategy",
                f"Delete '{self._spec.name}'? This cannot be undone."):
            return
        try:
            self.strategies.delete(self._spec.id)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self._spec = None
        self.strategy_panel.refresh()

    def on_import_strategy(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Strategy", str(self.workspace.strategies),
            "Strategy files (*.json *.tbs);;All files (*)")
        if not path:
            return
        try:
            spec = self.strategies.import_from(path)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.strategy_panel.refresh(spec.id)
        self.status(f"Imported strategy '{spec.name}'.")

    def on_export_strategy(self) -> None:
        if self._spec is None:
            return
        default = str(self.workspace.strategies / f"{_slug(self._spec.name)}.json")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Strategy", default, "Strategy files (*.json);;All files (*)")
        if not path:
            return
        try:
            self._apply_panel_settings(self._spec)
            self.strategies.export_to(self._spec.id, path, spec=self._spec)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.status(f"Exported strategy to {path}")

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------

    def on_run_backtest(self) -> None:
        if self._runner.busy:
            return
        if self._view_bars is None:
            show_info(self, "No Data", "Load a dataset before running a backtest.")
            return
        if self._spec is None:
            show_info(self, "No Strategy", "Select a strategy before running a backtest.")
            return
        try:
            config = self.risk_panel.build_config(self._view_bars.instrument)
            overrides = self.strategy_panel.parameter_overrides()
            self._spec.validate()
            warmup = self._spec.warmup_bars(overrides)
            if len(self._view_bars) <= warmup + 2:
                raise InsufficientDataError(
                    f"This strategy needs at least {warmup + 3} bars to warm its "
                    f"indicators up, but the selected range has only "
                    f"{len(self._view_bars)}. Widen the date range or choose a "
                    f"finer timeframe.")
            config.warmup_bars = warmup
        except BacktesterError as exc:
            show_error(self, exc)
            return

        label = f"{self._spec.name} · {self._view_bars.instrument.symbol} " \
                f"{self._view_bars.timeframe.label}"
        self._run_started = time.monotonic()
        self.status(f"Running {label}…")
        self._runner.start(run_backtest_task, self._view_bars, self._spec, config,
                           overrides, label)

    def on_cancel(self) -> None:
        if self._runner.busy:
            self._runner.cancel()
            self.status("Cancelling…")

    def on_progress(self, current: int, total: int, message: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(current)
        if message:
            self.progress.setFormat(f"{message}  (%p%)")
        self.status_message.setText(message or "Working…")

    def on_task_state(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        self.run_button.setEnabled(not busy)
        self.run_button_left.setEnabled(not busy)
        self.cancel_button.setVisible(busy)
        self.act_cancel.setEnabled(busy)
        self.act_run.setEnabled(not busy)
        if not busy:
            self.progress.reset()

    def on_task_finished(self, result: Any) -> None:
        if isinstance(result, BacktestResult):
            self._show_result(result)
        elif result is not None and hasattr(result, "instrument"):
            self._finish_import(result)
        else:
            self.status("Done.")

    def on_task_failed(self, message: str, detail: str) -> None:
        self.status("The task failed.")
        show_error(self, message, "Task Failed", detail)

    def on_task_cancelled(self) -> None:
        self.status("Cancelled.")

    def _show_result(self, result: BacktestResult) -> None:
        self._result = result
        elapsed = time.monotonic() - getattr(self, "_run_started", time.monotonic())
        result.duration_seconds = elapsed
        inst = result.bars.instrument if result.bars is not None else None
        decimals = inst.price_decimals if inst else 2
        currency = currency_symbol(inst.currency if inst else "USD")
        tz = inst.timezone if inst else "UTC"

        self.chart.set_bars(result.bars)
        self.chart.set_indicator_panels(self._panels_from_result(result))
        self.chart.set_trades(result.trades)
        self.equity.set_result(result)
        self.stats.set_metrics(result.metrics, currency, decimals)
        self.trade_table.set_trades(result.trades, decimals, currency, tz)

        try:
            from ..analytics.equity import drawdown_table
            from ..analytics.periodic import monthly_returns

            self.monthly.set_data(monthly_returns(result))
            self.drawdowns.set_data(drawdown_table(result.curves, top=15), currency, tz)
        except Exception:
            log.exception("Periodic analysis failed")

        m = result.metrics or {}
        net = float(m.get("net_profit", 0.0) or 0.0)
        colour = PALETTE.long if net > 0 else PALETTE.short if net < 0 else PALETTE.text
        self.headline.setText(
            f"<span style='color:{PALETTE.text_muted}'>{result.trade_count} trades</span>"
            f"&nbsp;&nbsp;<span style='color:{colour}'>{money(net, currency)}</span>"
            f"&nbsp;&nbsp;<span style='color:{colour}'>"
            f"{pct(float(m.get('return_pct', 0.0) or 0.0), 2, True)}</span>"
            f"&nbsp;&nbsp;<span style='color:{PALETTE.text_muted}'>DD "
            f"{pct(abs(float(m.get('max_drawdown_pct', 0.0) or 0.0)))}</span>&nbsp;&nbsp;")

        for warning in result.warnings[:3]:
            log.info("Backtest warning: %s", warning)
        note = f" · {result.warnings[0]}" if result.warnings else ""
        self.status(f"Finished in {elapsed:.1f}s — {result.trade_count} trades{note}")
        self.tabs.setCurrentIndex(0)
        self._update_actions()
        self._update_start_here()

    def _panels_from_result(self, result: BacktestResult) -> list[dict[str, Any]]:
        if self._spec is None:
            return []

        class _Compiled:
            indicators = result.indicators

        return self._build_panel_specs(_Compiled())

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def on_import_csv(self) -> None:
        from .dialogs.import_dialog import ImportWizard

        wizard = ImportWizard(self.instruments, self)
        if wizard.exec() != wizard.DialogCode.Accepted:
            return
        self.status(f"Importing {Path(wizard.path).name}…")
        self._runner.start(import_csv_task, wizard.path, wizard.mapping,
                           wizard.instrument, wizard.timeframe)

    def _finish_import(self, bars: Any) -> None:
        try:
            meta = self.datasets.add_from_bars(bars, name=Path(bars.source).stem or
                                               bars.instrument.symbol)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.data_panel.refresh_datasets(meta.id)
        self.status(f"Imported {len(bars):,} bars as '{meta.name}'.")

    def on_load_sample(self) -> None:
        """Import the bundled synthetic datasets and select one."""
        try:
            added = self._import_sample_datasets()
        except BacktesterError as exc:
            show_error(self, exc)
            return
        except Exception as exc:
            show_error(self, exc, "Sample Data")
            return

        metas = self.datasets.list()
        candidates = [m for m in metas
                      if "SYNTH" in m.name.upper() or "SYNTH" in m.source_path.upper()]
        chosen = (added[0] if added else (candidates[0] if candidates else None))
        if chosen is None:
            show_info(self, "Sample Data",
                      "No sample dataset could be created in this workspace. "
                      "Check that the workspace folder is writable.")
            return

        self.data_panel.refresh_datasets(chosen.id)
        show_info(self, "Synthetic Sample Data",
                  "This dataset is generated by a random process. It looks like "
                  "market data and is useful for exercising the application, but "
                  "it contains no real prices, and any strategy that appears "
                  "profitable on it is fitting noise.")

    def on_manage_datasets(self) -> None:
        from .dialogs.dataset_manager import DatasetManagerDialog

        dlg = DatasetManagerDialog(self.datasets, self)
        dlg.exec()
        self.data_panel.refresh_datasets()

    def on_instruments(self) -> None:
        from .dialogs.instrument_dialog import InstrumentDialog

        dlg = InstrumentDialog(self.instruments, self)
        dlg.exec()
        if self._view_bars is not None:
            self.risk_panel.apply_instrument_defaults(self._view_bars.instrument)

    def on_quality(self) -> None:
        if self._quality is None:
            show_info(self, "Data Quality", "Load a dataset first.")
            return
        from .dialogs.quality_dialog import DataQualityDialog

        DataQualityDialog(self._quality, self).exec()

    # ------------------------------------------------------------------
    # Saved runs, comparison, optimisation
    # ------------------------------------------------------------------

    def on_save_run(self) -> None:
        if self._result is None:
            show_info(self, "No Result", "Run a backtest before saving it.")
            return
        label = ask_text(self, "Save Backtest", "Label for this run:",
                         self._result.label or self._result.strategy_name)
        if not label:
            return
        try:
            self.backtests.save(self._result, label)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.status(f"Saved backtest '{label}'.")

    def on_browse_runs(self) -> None:
        from .dialogs.backtest_browser import BacktestBrowser

        dlg = BacktestBrowser(self.backtests, self)
        if dlg.exec() != dlg.DialogCode.Accepted or not dlg.selected_ids:
            return
        try:
            results = [self.backtests.load(rid) for rid in dlg.selected_ids]
        except BacktesterError as exc:
            show_error(self, exc)
            return
        if len(results) == 1:
            self._show_result(results[0])
        else:
            self._saved_results = results
            self.comparison.set_results(results)
            self.tabs.setCurrentWidget(self.comparison)

    def on_compare(self) -> None:
        from .dialogs.backtest_browser import BacktestBrowser

        dlg = BacktestBrowser(self.backtests, self, multi=True,
                              current=self._result)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        results: list[BacktestResult] = []
        if dlg.include_current and self._result is not None:
            results.append(self._result)
        try:
            results.extend(self.backtests.load(rid) for rid in dlg.selected_ids)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        if len(results) < 2:
            show_info(self, "Compare Runs",
                      "Choose at least two runs to compare.")
            return
        self._saved_results = results
        self.comparison.set_results(results)
        self.tabs.setCurrentWidget(self.comparison)

    def on_optimize(self) -> None:
        if self._view_bars is None or self._spec is None:
            show_info(self, "Optimise",
                      "Load a dataset and select a strategy first.")
            return
        if not self._spec.params:
            show_info(self, "Optimise",
                      "This strategy has no parameters to optimise. Add some in "
                      "the strategy editor first.")
            return
        from .dialogs.optimizer_dialog import OptimizerDialog

        try:
            config = self.risk_panel.build_config(self._view_bars.instrument)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        dlg = OptimizerDialog(self._view_bars, self._spec, config, self)
        dlg.exec()
        if dlg.chosen_params:
            self.strategy_panel.set_parameter_values(dlg.chosen_params)
            self.status("Applied the selected parameter combination. "
                        "Remember that a grid search reports the best result on "
                        "past data, not a prediction.")
            self.on_run_backtest()

    def on_monte_carlo(self) -> None:
        if self._result is None or not self._result.trades:
            show_info(self, "Monte Carlo",
                      "Run a backtest that takes at least a few trades first. "
                      "There is nothing to resample until there are trades.")
            return
        from .dialogs.montecarlo_dialog import MonteCarloDialog

        MonteCarloDialog(self._result, self).exec()

    def on_mirror_test(self) -> None:
        if self._view_bars is None or self._spec is None:
            show_info(self, "Mirror-market test",
                      "Load a dataset and select a strategy first.")
            return
        from .dialogs.mirror_dialog import MirrorDialog

        try:
            config = self.risk_panel.build_config(self._view_bars.instrument)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        MirrorDialog(self._view_bars, self._spec, config, self).exec()

    def on_load_shipped(self) -> None:
        """Import whatever shipped data is not in the library yet."""
        from ..data.bundled import available

        existing = {m.name for m in self.datasets.list()}
        pending = [d for d in available() if d.name not in existing]
        if not pending:
            show_info(self, "Shipped Market Data",
                      "All of it has already been imported. It is in the "
                      "dataset list on the left.")
            return
        total = sum(d.path().stat().st_size for d in pending) / (1024 * 1024)
        if not confirm(self, "Import Shipped Market Data",
                       f"Import {len(pending)} dataset(s), {total:.1f} MB "
                       f"compressed?\n\n"
                       + "\n".join(f"· {d.name} — {d.description}"
                                    for d in pending)
                       + "\n\nThe largest is half a million bars and takes a "
                         "few seconds."):
            return

        def job(progress=None):
            return self._import_bundled_datasets(None, progress)

        self._runner.finished.connect(self._finish_shipped_import)
        self._runner.start(job)
        self.status("Importing the shipped market data…")

    def _finish_shipped_import(self, added: Any) -> None:
        try:
            self._runner.finished.disconnect(self._finish_shipped_import)
        except (RuntimeError, TypeError):    # pragma: no cover - already gone
            pass
        rows = list(added or [])
        self.data_panel.refresh_datasets(rows[0].id if rows else None)
        self.status(f"Imported {len(rows)} dataset(s)." if rows
                    else "Nothing new to import.")

    # ------------------------------------------------------------------
    # Finding strategies
    # ------------------------------------------------------------------

    def on_find_strategies(self) -> None:
        """Open the search. It does not need a dataset loaded to be useful."""
        from .dialogs.finder_dialog import FinderDialog

        dialog = FinderDialog(self.datasets, self.instruments, self.strategies,
                              self._view_bars, self)
        dialog.exec()
        # A search can save strategies, so the picker has to catch up.
        self.strategy_panel.refresh(self.strategy_panel.current_strategy_id()
                                    or None)
        self._update_start_here()

    # ------------------------------------------------------------------
    # Simple mode
    # ------------------------------------------------------------------

    def on_toggle_simple(self, enabled: bool) -> None:
        self._apply_simple_mode(bool(enabled))
        self.settings.simple_mode = bool(enabled)
        self.settings.save()
        self.status("Simple mode on: the optimiser, comparison and risk "
                    "settings are hidden. Nothing was disabled — View ▸ Simple "
                    "Mode brings them back."
                    if enabled else
                    "Simple mode off: every panel is available again.")

    def _apply_simple_mode(self, enabled: bool) -> None:
        """Show or hide the parts a first backtest does not need.

        This hides rather than disables. A disabled control still has to be
        read, understood and dismissed; a hidden one costs nothing.
        """
        self.risk_panel.setVisible(not enabled)
        for action in getattr(self, "_advanced_toolbar", []):
            if action is not None:
                action.setVisible(not enabled)
        for widget, keep in ((self.comparison, not enabled),):
            index = self.tabs.indexOf(widget)
            if index >= 0 and not keep:
                self.tabs.removeTab(index)
            elif index < 0 and keep:
                self.tabs.addTab(self.comparison, icon("compare", 15),
                                 "Comparison")
        for index in range(self.bottom_tabs.count() - 1, 0, -1):
            # Trades always stay; Drawdowns and Log are for when something has
            # gone wrong, which is not the first thing to show someone.
            self.bottom_tabs.setTabVisible(index, not enabled)

    def on_show_start_here(self) -> None:
        self.start_here.show()
        self.settings.show_start_here = True
        self.settings.save()
        self._update_start_here()

    def _on_start_here_dismissed(self) -> None:
        self.settings.show_start_here = False
        self.settings.save()

    def _update_start_here(self) -> None:
        if not hasattr(self, "start_here"):
            return
        if getattr(self.settings, "show_start_here", True):
            self.start_here.set_state(self._bars is not None,
                                      self._spec is not None,
                                      self._result is not None)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _require_result(self) -> BacktestResult | None:
        if self._result is None:
            show_info(self, "Nothing to Export", "Run a backtest first.")
            return None
        return self._result

    def on_export_trades(self) -> None:
        result = self._require_result()
        if result is None:
            return
        default = str(self.workspace.reports / f"{_slug(result.label)}_trades.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export Trades", default,
                                              "CSV files (*.csv)")
        if not path:
            return
        try:
            from ..reports.csv_export import export_trades_csv

            export_trades_csv(result, path)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.status(f"Exported {result.trade_count} trades to {path}")

    def on_export_equity(self) -> None:
        result = self._require_result()
        if result is None:
            return
        default = str(self.workspace.reports / f"{_slug(result.label)}_equity.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export Equity Curve", default,
                                              "CSV files (*.csv)")
        if not path:
            return
        try:
            from ..reports.csv_export import export_equity_csv

            export_equity_csv(result, path)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.status(f"Exported the equity curve to {path}")

    def on_export_report(self) -> None:
        result = self._require_result()
        if result is None:
            return
        default = str(self.workspace.reports / f"{_slug(result.label)}_report.html")
        path, _ = QFileDialog.getSaveFileName(self, "Export Report", default,
                                              "HTML files (*.html)")
        if not path:
            return
        try:
            from ..reports.html_report import export_html_report

            export_html_report(result, path)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.status(f"Exported the report to {path}")
        self._offer_open(path)

    def on_export_pdf(self) -> None:
        result = self._require_result()
        if result is None:
            return
        default = str(self.workspace.reports / f"{_slug(result.label)}_report.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF Report", default,
                                              "PDF files (*.pdf)")
        if not path:
            return
        try:
            from ..reports.pdf_report import export_pdf_report

            export_pdf_report(result, path)
        except BacktesterError as exc:
            show_error(self, exc)
            return
        self.status(f"Exported the PDF report to {path}")
        self._offer_open(path)

    def _offer_open(self, path: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------
    # Selection sync
    # ------------------------------------------------------------------

    def on_chart_trade_clicked(self, index: int) -> None:
        self.trade_table.select_trade(index)
        self.bottom_dock.raise_()

    def on_table_trade_selected(self, index: int) -> None:
        self.chart.select_trade(index, centre=True)
        self.tabs.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Workspace, help, layout
    # ------------------------------------------------------------------

    def on_change_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Choose Workspace Folder", str(self.workspace.root))
        if not path:
            return
        self.settings.workspace_dir = path
        self.settings.save()
        show_info(self, "Workspace Changed",
                  f"The workspace is now:\n{path}\n\nRestart the application for "
                  f"the change to take effect. Nothing in the old workspace has "
                  f"been moved or deleted.")

    def on_open_workspace(self) -> None:
        self._offer_open(str(self.workspace.root))

    def on_open_log(self) -> None:
        if self.log_file and Path(self.log_file).exists():
            self._offer_open(str(self.log_file))
        else:
            show_info(self, "Log", "No log file has been created yet.")

    def on_assumptions(self) -> None:
        from .dialogs.about_dialog import DocumentDialog

        DocumentDialog("Backtesting Assumptions", "BACKTEST_ASSUMPTIONS.md", self).exec()

    def on_metrics_help(self) -> None:
        from .dialogs.about_dialog import DocumentDialog

        DocumentDialog("Metric Definitions", "METRICS.md", self).exec()

    def on_about(self) -> None:
        from .dialogs.about_dialog import AboutDialog

        AboutDialog(self.workspace, self).exec()

    def on_reset_layout(self) -> None:
        for dock in (self.left_dock, self.right_dock, self.bottom_dock):
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.bottom_dock)
        self.resizeDocks([self.left_dock, self.right_dock], [352, 330],
                         Qt.Orientation.Horizontal)
        self.resizeDocks([self.bottom_dock], [250], Qt.Orientation.Vertical)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def status(self, message: str) -> None:
        self.status_message.setText(message)
        log.info("%s", message)

    def _update_actions(self) -> None:
        has_data = self._view_bars is not None
        has_strategy = self._spec is not None
        has_result = self._result is not None
        runnable = has_data and has_strategy and not self._runner.busy
        for a in (self.act_run,):
            a.setEnabled(runnable)
        self.run_button.setEnabled(runnable)
        self.run_button_left.setEnabled(runnable)
        for a in (self.act_edit_strategy, self.act_save_strategy,
                  self.act_duplicate_strategy, self.act_rename_strategy,
                  self.act_delete_strategy, self.act_export_strategy):
            a.setEnabled(has_strategy)
        for a in (self.act_save_run, self.act_export_trades, self.act_export_equity,
                  self.act_export_report, self.act_export_pdf):
            a.setEnabled(has_result)
        self.act_optimize.setEnabled(has_data and has_strategy)
        self.act_montecarlo.setEnabled(
            self._result is not None and bool(self._result.trades))
        self.act_mirror.setEnabled(has_data and has_strategy)
        self.act_quality.setEnabled(self._quality is not None)
        title = APP_DISPLAY_NAME
        if self._spec is not None:
            title = f"{self._spec.name}{' *' if self._dirty_strategy else ''} — {title}"
        self.setWindowTitle(title)

    def _restore_geometry(self) -> None:
        if self.settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(
                self.settings.window_geometry.encode("ascii")))
        if self.settings.window_state:
            self.restoreState(QByteArray.fromBase64(
                self.settings.window_state.encode("ascii")))
        else:
            self.on_reset_layout()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._runner.busy:
            if not confirm(self, "Task Running",
                           "A task is still running. Close anyway?",
                           "Close", danger=False):
                event.ignore()
                return
            self._runner.cancel()
            self._runner.wait(3000)
        try:
            self.settings.window_geometry = bytes(
                self.saveGeometry().toBase64()).decode("ascii")
            self.settings.window_state = bytes(
                self.saveState().toBase64()).decode("ascii")
            self.settings.save()
        except Exception:
            log.exception("Could not save the window layout")
        super().closeEvent(event)


def _slug(text: str) -> str:
    keep = [c if c.isalnum() or c in "-_" else "_" for c in (text or "backtest")]
    return "".join(keep).strip("_")[:60] or "backtest"


def _costs_are_empty(costs: Any) -> bool:
    """True when a cost model charges nothing at all."""
    return (float(getattr(costs, "commission_value", 0.0) or 0.0) == 0.0
            and float(getattr(costs, "min_commission", 0.0) or 0.0) == 0.0
            and float(getattr(costs, "spread_points", 0.0) or 0.0) == 0.0
            and float(getattr(costs, "slippage_value", 0.0) or 0.0) == 0.0)


def _symbol_from_sample_name(stem: str) -> str:
    """``SYNTHETIC_NQ_5m`` -> ``NQ``.

    The samples are named after the instrument they imitate so they load with
    the right tick size and point value rather than generic defaults.
    """
    parts = [p for p in stem.split("_") if p and p.upper() != "SYNTHETIC"]
    return parts[0].upper() if parts else ""


