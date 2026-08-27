# UI contracts — the API `main_window.py` already calls

`main_window.py` is written and MUST NOT be edited. It imports and calls the
classes below with exactly these signatures. Build to this API.

Project root `/home/user/main/desktop`; interpreter
`/home/user/main/.venv-bt/bin/python`; run Qt headless with
`QT_QPA_PLATFORM=offscreen`. Read `docs/CONTRACTS.md` first.

## Already written — do not modify

`ui/theme.py` (PALETTE, Fonts, apply_theme, money/pct/number/duration/value_color),
`ui/icons.py` (`icon(name, size, color)`, `available_icons()`, `app_icon()`),
`ui/main_window.py`, `ui/workers.py` (`TaskRunner`, `Worker`, task functions),
`ui/widgets/`: `common.py`, `chart_items.py`, `chart_widget.py`,
`equity_widget.py`, `trade_table.py`, `stats_panel.py`, `periodic_table.py`,
`data_panel.py`, `strategy_panel.py`, `risk_panel.py`, `log_view.py`.

**Reuse `ui/widgets/common.py`.** It has `Card`, `CollapsibleCard`,
`SectionLabel`, `hline()`, `FieldSpec`/`FormPanel` (declarative forms with
`values()` / `set_values()` and `enabled_by` dependencies), `ErrorDialog`,
`show_error`, `show_warning`, `show_info`, `confirm`, `ask_text`. Use the theme's
`PALETTE`, `Fonts`, `money`, `pct`, `number`, `duration` for everything visual —
no literal hex colours, no hard-coded font families.

Every dialog: dark theme inherited from the app stylesheet, `setWindowTitle`,
sensible `setMinimumWidth`, keyboard-navigable, no raw tracebacks shown to the
user, all failures via `show_error`.

## Dialogs to implement

### `ui/dialogs/import_dialog.py` — `ImportWizard(instruments, parent)`
The single most important dialog: it is where a user's own CSV meets the app.

Attributes read by the caller after `exec()` returns `Accepted`:
`path: str`, `mapping: ColumnMapping`, `instrument: Instrument`,
`timeframe: Timeframe | None`.

Flow on one resizable dialog (not a multi-page wizard):
1. File chooser row (`QLineEdit` + Browse) — on choosing a file, call
   `sniff_csv(path)` and populate everything from the profile.
2. A preview table of the first ~50 raw rows, with the detected delimiter and
   header shown.
3. Column mapping: one combo per required field (datetime OR date+time, open,
   high, low, close, volume) listing the file's actual headers plus
   `— none —`. Pre-select the sniffed guess. Volume may be left unmapped.
4. Datetime options: format (editable combo pre-filled with the detected
   format plus common alternatives and `Auto`), source timezone combo,
   day-first checkbox, decimal/thousands separators.
5. Instrument: combo of `instruments.all()` plus a "New instrument…" entry that
   opens an inline editor for symbol / asset class / tick size / point value /
   lot size / decimals / currency / timezone, and adds it to the registry.
6. A live **Validate** button that parses the first 500 rows with the chosen
   mapping and shows either the parsed first/last timestamps, the inferred
   timeframe and the row count, or the exact error. OK stays disabled until a
   validation has succeeded.
Import of the full file is done by the caller on a worker thread — this dialog
must never load a whole 2 M-row file itself.

### `ui/dialogs/instrument_dialog.py` — `InstrumentDialog(registry, parent)`
List on the left, editor on the right. Add / duplicate / delete / reset to
defaults. Fields: symbol, name, asset class, tick size, point value, lot size,
price decimals, currency, exchange, timezone, margin per unit, default
commission, default spread, notes. Validates on save (`Instrument.__post_init__`
raises `DataError` for bad values — catch and show it inline, not as a crash).
Explain `point_value` in a help line: "cash change per 1.0 of price movement per
unit held — 1.0 for a share, 20.0 for an NQ future". Calls `registry.save()`.

### `ui/dialogs/strategy_editor.py` — `StrategyEditor(spec, parent, bars=None)`
Attribute `spec: StrategySpec` holds the edited copy; the caller reads it after
`Accepted`. Tabs:
1. **General** — name, description, tags.
2. **Indicators** — table of `IndicatorSlot`s. Add opens a picker grouped by
   `REGISTRY.by_category()` with each indicator's description; then edit ref
   name, parameters (built from the `IndicatorDef.params` via `FormPanel`, with
   a "use parameter" toggle per numeric field that writes `"$name"` instead of a
   literal), price source, plot on/off, panel, colour.
3. **Rules** — four rule trees (long entry, long exit, short entry, short exit)
   in a `QTreeWidget`. Each node is a group (AND/OR/NOT) or a condition. Adding
   a condition offers Compare / Cross / State / Session / Always, with operand
   pickers for price field, indicator output, constant and strategy parameter,
   and an arithmetic operand builder. Show the rendered `describe()` string live
   under the tree so the user can read the rule back in English.
4. **Parameters** — table of `ParamSpec`s: name, label, kind, default, min, max,
   step, help. Add/remove/reorder. These are what the optimiser sweeps.
5. **Risk & Exits** — reuse `RiskPanel` so the strategy carries its own defaults.
On OK, run `spec.validate()`; block with the error if it raises and show
warnings inline if it returns any.
Provide a **Preview** button when `bars` is not None: compile the strategy and
report the signal counts (`entry_long.sum()` etc.) so the user can see whether a
rule fires at all before running.

### `ui/dialogs/dataset_manager.py` — `DatasetManagerDialog(repository, parent)`
Table of `DatasetMeta` (name, symbol, timeframe, bars, first, last, size, source).
Rename, delete (with `confirm`), reveal the source file, and a Refresh that calls
`repository.refresh()`. Show the total workspace data size.

### `ui/dialogs/quality_dialog.py` — `DataQualityDialog(report, parent)`
Renders a `DataQualityReport`: a headline (usable / not usable), then a table of
issues with severity, code, message, count and an example. Group by severity,
colour by severity, and explain in one line what each severity means for a
backtest.

### `ui/dialogs/backtest_browser.py` — `BacktestBrowser(store, parent, multi=False, current=None)`
Attributes after `Accepted`: `selected_ids: list[str]`, `include_current: bool`.
Table of saved runs: label, strategy, instrument, timeframe, trades, net profit,
return %, max DD, profit factor, Sharpe, saved-at. Sortable. Multi-select when
`multi=True`, plus an "include the current run" checkbox shown only when
`current` is not None. Delete button with `confirm`.

### `ui/dialogs/optimizer_dialog.py` — `OptimizerDialog(bars, spec, config, parent)`
Attribute after close: `chosen_params: dict | None`.
Left: one row per strategy parameter — enable checkbox, start, stop, step —
pre-filled from the parameter's own min/max. A live "N combinations" counter that
turns amber above 500 and red above 5,000, with an estimated runtime derived from
one timed trial run. A metric combo to rank by (net profit, profit factor,
Sharpe, Sortino, return/drawdown, expectancy, win rate, trades) and a minimum
trade-count filter.
Right: results table, sortable, with the rank metric plus net profit, trades,
profit factor, Sharpe, max DD and the parameter values; a heat map for the
two-parameter case; and a **robustness** column (mean of the metric over the
immediate parameter neighbourhood) so an isolated spike is visible as one.
Run on a `TaskRunner` with progress and a working Cancel. Double-clicking a row
sets `chosen_params` and accepts.
A permanent, prominent notice: *"Optimisation reports what would have happened on
this data. The best combination on a historical sample is the one that fitted its
noise best; expect it to be worse out of sample. Prefer a broad plateau of decent
results over an isolated peak."* This is a requirement, not a decoration.

Third tab: **Walk-Forward**, `ui/widgets/walkforward_panel.py` —
`WalkForwardPanel(bars, spec, config, ranges_fn, settings_fn, parent=None)`.
It reads the sweep's own ranges and ranking settings through those two callables
rather than offering its own, so the two halves of the dialog can never disagree
about which strategy is being tested. Controls: fold count, training share,
rolling/anchored. One row per window — the dates it trained on, the dates it
traded, the in-sample and out-of-sample metric, the trade count, and the
parameters it chose — with the headline stating the out-of-sample total, how
many windows were profitable, and the verdict in a sentence. A window that
produced no result shows the reason in place of its numbers rather than being
dropped. Its own `TaskRunner`, with a working Cancel; `shutdown()` is called
from the dialog's `closeEvent`.

Fourth tab: **Out of Sample**, `ui/widgets/holdout_panel.py` —
`HoldoutPanel(bars, spec, config, ranges_fn, settings_fn, parent=None)`.
Same two callables, same reason. Controls: the research-block share and how many
ranked combinations are revealed. One row per revealed combination — its rank,
its parameters, the research and locked values with their trade counts, and the
retention — with the two blocks in their own columns and never blended into one
figure. Retention shows `n/a` rather than a number wherever the ratio would
mislead (a losing research block, a metric where smaller is better), the
headline says which of those it is, and a winner that did *better* out of sample
is coloured as a warning rather than a success. The notes state the grid size
and that the split does not correct for that multiplicity, every run. Cancelling
leaves the locked block unread and the headline says so. Its own `TaskRunner`;
`shutdown()` is called from the dialog's `closeEvent`.

### `ui/dialogs/finder_dialog.py` — `FinderDialog(datasets, instruments, strategies, parent=None)`
Three tabs over one dataset — *Strategies*, *Indicators*, *Anomalies* — each
running its study on a `TaskRunner` with a working Cancel. Pick a dataset and a
trading style; the style fixes bar size, session, stop and target geometry and
minimum trade count, because a geometry the search can choose is a geometry it
can fit.

Under those, a **Constraints (optional)** card, off by default. Switched on it
overrides the style's session (or "all hours"), stop and target multiples, max
hold and minimum trades, and the note beneath states the exact geometry the
search will be given. Every control refreshes that note — it claims to say what
will be searched, so it has to be true after any change, not only the last
toggle. Switching style re-seeds the boxes from it, so a change is always a
change *from* the style. The overrides go through `finder.styles.customise`,
which copies rather than mutating: the shipped styles are module constants and
the next search in the same process must see them unchanged. Nothing here is
searched over, and the note says so.

### `ui/dialogs/montecarlo_dialog.py` — `MonteCarloDialog(result, parent=None)`
Resamples the loaded run's trade sequence. Controls: method (shuffle /
bootstrap / block), draw count, compounding, and the ruin level. A four-row
percentile table (final equity, worst drawdown, worst drawdown %, trades under
water) at the 5th/25th/50th/75th/95th, a histogram of final equity with the
backtest's own result and break-even marked on it, and a headline stating where
the run sits in the distribution and the verdict.
A permanent, prominent notice: *"This resamples the trades the strategy already
took. It cannot tell you whether the strategy has an edge — if these trades came
from a rule fitted to this data, every draw is fitted to it too."* This is a
requirement, not a decoration.
Opened from **Backtest → Monte Carlo…** (`Ctrl+M`), which is disabled until a
run with at least one trade exists.

### `ui/dialogs/mirror_dialog.py` — `MirrorDialog(bars, spec, config, parent=None)`
Runs on construction: the same strategy on the series and on its reflection.
A seven-row comparison (drift, trades, net profit, expectancy, win rate, profit
factor, max drawdown) with the better of each pair coloured, the split into a
direction-independent and a direction-dependent half, the verdict as the
headline, and the caveats below it — including that the mirror is a control and
not a second sample, and that a mirrored bull market is not a bear market.
Opened from **Backtest → Mirror-Market Test…**, enabled whenever a dataset and
a strategy are loaded.

### `ui/dialogs/about_dialog.py`
- `AboutDialog(workspace, parent)` — name, version, Python/Qt versions, the
  workspace path, licence summary, third-party credits, and an explicit
  statement that the application makes no network requests and collects no
  telemetry.
- `DocumentDialog(title, doc_name, parent)` — loads a Markdown file from
  `config.resource_path("docs", doc_name)`, falling back to the repository
  `docs/` folder, and renders it readably (a small Markdown-to-HTML conversion
  into a `QTextBrowser` is fine; do not add a dependency). If the file is
  missing, say so plainly instead of showing an empty window.

### `ui/widgets/comparison_view.py` — `ComparisonView(parent=None)`
Method `set_results(results: list[BacktestResult])`. A splitter with overlaid
normalised equity curves on top (reuse `EquityWidget.set_series`, indexing each
run to 100 at the first common timestamp) and a metric matrix beneath: one row
per metric, one column per run, best value per row highlighted, using
`analytics.comparison.compare_results`. Include a drawdown comparison and a
per-run summary strip. Handle 2–8 runs, runs over different date ranges (show
`align_note`), and the empty case.

## Backend modules to implement

Exactly as specified in `docs/CONTRACTS.md`:
`optimize/grid.py`, `optimize/runner.py`, `optimize/ranking.py`,
`reports/csv_export.py`, `reports/html_report.py`, `reports/pdf_report.py`,
`storage/workspace.py`, `storage/backtest_store.py`.

Additional requirements the main window depends on:
- `StrategyStore` must also have `seed_builtins(BUILTIN_STRATEGIES) -> list[StrategySpec]`
  that writes any built-in strategy not already present, and
  `export_to(id, path, spec=None)` where an explicit `spec` overrides the stored one.
- `reports/csv_export.py` exports `export_trades_csv(result, path) -> str`,
  `export_equity_csv(result, path) -> str`, `export_metrics_csv(result, path) -> str`.
- `reports/html_report.py` exports `export_html_report(result, path) -> str`.
- `reports/pdf_report.py` exports `export_pdf_report(result, path) -> str` using
  `QPdfWriter` + `QPainter` only.
- `storage/backtest_store.py`: `BacktestStore(workspace)` with
  `save(result, label) -> str`, `list() -> list[SavedRunMeta]`,
  `load(run_id) -> BacktestResult`, `delete(run_id)`. `SavedRunMeta` needs
  `id, label, strategy_name, instrument_symbol, timeframe_label, created_at,
  trade_count, net_profit, return_pct, max_drawdown_pct, profit_factor,
  sharpe_ratio`.
- `storage/workspace.py`: `bootstrap(settings) -> Workspace`.
