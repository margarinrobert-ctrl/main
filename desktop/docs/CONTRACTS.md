# Internal contracts — read before writing any module

Project root: `/home/user/main/desktop`. Package: `tradingbacktester`.
Python 3.11. Interpreter for running anything: `/home/user/main/.venv-bt/bin/python`
(has numpy, pandas, PySide6 6.11, pyqtgraph, pytest). Run Qt code headless with
`QT_QPA_PLATFORM=offscreen`.

Style: type hints everywhere, `from __future__ import annotations` at the top,
real docstrings, no `TODO`/`pass  # later`/placeholder. Comments explain *why*.
British-neutral plain prose in user-facing strings. Never print; use
`logging.getLogger(__name__)`.

## Already written — do not modify these files

- `tradingbacktester/core/errors.py` — exception hierarchy. Every user-triggerable
  failure raises a subclass of `BacktesterError(user_message, detail=None)`.
  Subclasses: `DataError`, `CsvImportError`, `InsufficientDataError`,
  `TimeframeError`, `IndicatorError`, `StrategyError`, `StrategyStorageError`,
  `ParameterError`, `OrderError`, `RiskError`, `BacktestError`, `CancelledError`,
  `StorageError`, `ReportError`.
- `tradingbacktester/core/timeframe.py` — `Timeframe(multiplier, unit)`,
  `TimeframeUnit`, `Timeframe.parse("5m")`, `.label`, `.display_name`,
  `.pandas_freq`, `.approx_seconds`, `.can_build_from(other)`,
  `STANDARD_TIMEFRAMES`, `infer_timeframe(ts_ns)`.
- `tradingbacktester/core/types.py` — `Side`, `OrderType`, `OrderStatus`,
  `TimeInForce`, `ExitReason`, `SignalExecution`, `IntrabarPriority`, `SizingMode`,
  `CommissionMode`, `SlippageMode`, `SpreadMode`, `AssetClass`, `Order`, `Fill`,
  `Position`, `Trade`, `CostModel`, `RiskSettings`, `SessionSettings`,
  `ExitSettings`, `ExecutionSettings`, `BacktestConfig`.
- `tradingbacktester/data/models.py` — `Instrument`, `BarSeries`.
- `tradingbacktester/indicators/base.py` — `ParamSpec`, `IndicatorDef`,
  `IndicatorRegistry`, `REGISTRY`, helpers `nan_prefix`, `rolling_window`,
  `safe_divide`.
- `tradingbacktester/strategy/spec.py` — operands, conditions, `IndicatorSlot`,
  `StrategySpec`.
- `tradingbacktester/engine/results.py` — `EquityCurves`, `BacktestResult`.
- `tradingbacktester/config.py` — `APP_NAME`, `APP_VERSION`, `Workspace`,
  `AppSettings`, `default_workspace_dir()`, `resource_path()`.
- `tradingbacktester/logging_setup.py` — `configure_logging`, `get_logger`,
  `install_excepthook`.

Read the actual files before coding. They are short and they are the source of truth.

## Key invariants

**Bars.** `BarSeries` holds `ts` (int64 UTC nanoseconds, strictly ascending, bar
OPEN time), `open/high/low/close/volume` (float64, same length), `instrument`,
`timeframe`. `bars.source_array("close"|"hlc3"|...)` resolves a price source.

**Indicators.** A registered function has the signature
`f(bars: BarSeries, **params) -> np.ndarray | dict[str, np.ndarray]`. If the
`IndicatorDef` has `uses_source=True` the function also receives `source: str`
and should read `bars.source_array(source)`. Outputs are float64, length
`len(bars)`, NaN for the warm-up. Register with
`@REGISTRY.register("EMA", "Exponential Moving Average", "Moving Averages",
params=(ParamSpec(...),), outputs=("value",), overlay=True, scale_hint="price")`.
Call through `REGISTRY.compute(key, bars, params, source)` which returns
`{output_name: array}`.

**No look-ahead.** The value of any array at index `i` must depend only on bars
`0..i`. A rule evaluated on bar `i` executes at the OPEN of bar `i+1` under the
default `SignalExecution.NEXT_OPEN`.

**Money.** Cash P&L = `(exit - entry) * side.sign * quantity * instrument.point_value`.
Costs are always adverse. `point_value` is cash per 1.0 of price per unit.

## Module assignments and required public API

### `tradingbacktester/indicators/library.py`
Registers every indicator into `REGISTRY` at import time. Required keys:
`SMA, EMA, WMA, HMA, DEMA, TEMA, RMA, VWMA, RSI, MACD, BBANDS, ATR, STOCH, ADX,
VWAP, OBV, CCI, MFI, ROC, MOM, STDDEV, KELTNER, DONCHIAN, SUPERTREND, PSAR,
WILLR, CMF, AROON, TRUE_RANGE, ZSCORE, LINREG, PIVOT_HIGH, PIVOT_LOW, VOLUME,
VOL_SMA, RETURNS, CHOP, ULTOSC, TSI, ELDER_RAY, ATR_PERCENT, HIGHEST, LOWEST,
CROSS_COUNT` (add more if useful). Multi-output shapes:
`MACD -> {"macd","signal","histogram"}`, `BBANDS -> {"upper","middle","lower"}`,
`STOCH -> {"k","d"}`, `ADX -> {"adx","plus_di","minus_di"}`,
`KELTNER -> {"upper","middle","lower"}`, `DONCHIAN -> {"upper","middle","lower"}`,
`SUPERTREND -> {"value","direction"}`, `AROON -> {"up","down","oscillator"}`,
`ELDER_RAY -> {"bull","bear"}`.
Definitions that must be exact: `ATR` is Wilder's RMA of true range (also expose
`ATR_EMA` variant via a `method` choice param: `wilder|ema|sma`); `RSI` uses
Wilder smoothing; `CCI` is computed on `hlc3` with mean absolute deviation and
constant 0.015; `VWAP` resets each session day in the instrument timezone.
Vectorised NumPy only; no Python loops over bars except where genuinely
recursive (Wilder smoothing, SuperTrend, PSAR) — those may loop but must stay
O(n). Export `register_all()` (idempotent) and make importing the module enough.

### `tradingbacktester/data/csv_loader.py`
- `sniff_csv(path) -> CsvProfile` — detect delimiter, header presence, candidate
  column mapping, sample rows, detected datetime format. Must not raise on
  unusual files; report problems in the profile.
- `ColumnMapping` dataclass: `datetime`, `date`, `time`, `open`, `high`, `low`,
  `close`, `volume`, plus `datetime_format: str | None`, `timezone: str`,
  `decimal: str`, `thousands: str`, `dayfirst: bool`.
- `load_csv(path, mapping, instrument, timeframe=None, progress=None) -> BarSeries`
  — raise `CsvImportError` with a *useful* message naming the offending row and
  column. Support: separate date+time columns, epoch seconds/ms/us/ns, ISO 8601,
  `%d/%m/%Y %H:%M`, `%m/%d/%Y`, and vendor formats like `20230102 093000`.
  Support tz-naive input interpreted in `mapping.timezone` and converted to UTC.
- `guess_mapping(headers) -> ColumnMapping`.
- `resolve_column(headers, key) -> int | None` — turn a mapping reference (a
  header name or a stringified index) into a column position, the same way the
  loader will.
- `CsvProfile.row_order` — `+1` oldest first, `-1` newest first, `0` unknown.
Handle: BOM, quoted fields, blank lines, thousands separators, comma decimals,
extra columns, files where volume is missing entirely (fill 0 and warn).

### `tradingbacktester/data/autodetect.py`
Deciding the column layout from the values, not the header names. Called by
`sniff_csv` after the name-based guess, so every import path gets it.
- `analyse_columns(headers, rows, decimal, thousands) -> list[ColumnFacts]` —
  per column: `kind` in `datetime|time|numeric|text|empty`, parsed values,
  median, `all_zero`, `integral`, `monotone`, detected datetime format.
- `ohlc_pass_rate(open, high, low, close) -> float` — fraction of bars that can
  really be one candle. This is the falsifiable test the module rests on.
- `price_groups(facts) -> list[list[int]]` — numeric columns clustered by
  row-wise closeness, which separates prices from volume.
- `row_direction(facts) -> int` — `+1`, `-1` or `0`.
- `detect_mapping(headers, rows, has_header, decimal, thousands, base=None)
  -> Detection` — the layout the values imply, names used only to break ties.
- `audit_mapping(mapping, headers, rows, has_header) -> Detection` — the
  conservative entry point: keep a mapping that satisfies the OHLC relation,
  replace one that does not, and only with one that passes. Modifies the
  mapping in place; `Detection.changes` lists every change in plain language.

### `tradingbacktester/data/validation.py`
- `DataIssue(severity, code, message, count, example_index, example_text)`
  severity in `error|warning|info`.
- `DataQualityReport` with `.issues`, `.errors`, `.warnings`, `.is_usable`,
  `.summary_text()`, `.to_dict()`.
- `validate_bars(bars) -> DataQualityReport` checking: NaN/inf in any column,
  duplicate timestamps, non-monotonic timestamps, `high < low`,
  `high < max(open, close)`, `low > min(open, close)`, non-positive prices,
  zero/negative volume, gaps vs the modal bar interval (weekend-aware — report
  only gaps *inside* the observed trading week), constant-price runs, and
  extreme single-bar returns (> 20 sigma).
- `clean_bars(bars, drop_duplicates=True, sort=True, drop_invalid_ohlc=False)
  -> tuple[BarSeries, DataQualityReport]`.

### `tradingbacktester/data/resample.py`
- `resample(bars, target: Timeframe) -> BarSeries` — OHLC aggregation, volume
  sum, label = period start. Raise `TimeframeError` when
  `not target.can_build_from(bars.timeframe)`. Must drop empty periods, not emit
  NaN bars. Use pandas groupby/resample for correctness; keep UTC.
- `available_timeframes(source: Timeframe) -> list[Timeframe]` from
  `STANDARD_TIMEFRAMES`.

### `tradingbacktester/data/instruments.py`
- `InstrumentRegistry(path)` with `all()`, `get(symbol)`, `add(inst)`,
  `update(inst)`, `remove(symbol)`, `save()`, `load()`.
- `DEFAULT_INSTRUMENTS` covering EURUSD, GBPUSD, USDJPY, AUDUSD, BTCUSD, ETHUSD,
  SPY, QQQ, AAPL, TSLA, ES, NQ, MNQ, CL, GC, XAUUSD with correct tick size,
  point value, lot size, decimals, currency and timezone. Seeded on first run,
  user-editable afterwards.

### `tradingbacktester/data/repository.py`
- `DatasetMeta` (id, name, symbol, timeframe, bar_count, start_ts, end_ts,
  source_path, imported_at, checksum, notes).
- `DatasetRepository(workspace)` with `list()`, `get(id)`, `load_bars(id)`,
  `add_from_bars(bars, name)` (writes parquet, falls back to compressed CSV if
  pyarrow is missing), `remove(id)`, `rename(id, name)`, `refresh()`.
  Index file `data/index.json`, atomic writes.

### `tradingbacktester/data/providers/base.py`
- `DataProvider` Protocol: `name`, `describe()`, `search(query)`,
  `fetch(symbol, timeframe, start, end) -> BarSeries`, `is_available()`.
- `CsvFileProvider` implementing it over the local filesystem. This is the
  documented extension point for future live/broker feeds; do not add network code.

### `tradingbacktester/data/sample.py`
- `generate_sample_data(...) -> BarSeries` — a deterministic synthetic series
  (seeded) with realistic intraday seasonality, trends, regime shifts and
  volatility clustering, valid OHLC relationships, weekday-only sessions.
- `write_sample_csv(path, ...)` — writes a CSV whose header comment and filename
  make clear it is SYNTHETIC TEST DATA, not real market data.
- `ensure_samples(workspace)` — creates the bundled samples on first run
  (`SYNTHETIC_EURUSD_60m.csv`, `SYNTHETIC_NQ_5m.csv`, `SYNTHETIC_SPY_1D.csv`).

### `tradingbacktester/strategy/compiler.py` (+ `expression.py`, `rules.py`)
- `CompiledStrategy` holding: `spec`, `params`, `indicators: dict[str, dict[str, np.ndarray]]`,
  `entry_long/entry_short/exit_long/exit_short: np.ndarray[bool]`,
  `tradeable: np.ndarray[bool]`, `warmup: int`, `atr: np.ndarray` (for
  ATR-based stops/targets/sizing, computed with `ExitSettings.atr_period`).
- `compile_strategy(spec, bars, overrides=None) -> CompiledStrategy`.
- `evaluate_operand(op, ctx) -> np.ndarray` and
  `evaluate_condition(cond, ctx) -> np.ndarray[bool]` in `expression.py`/`rules.py`.
  Cross semantics: `left` crosses above `right` at `i` iff
  `l[i] > r[i] and l[i-1] <= r[i-1]` and both are finite at `i` and `i-1`.
  NaN anywhere in an operand ⇒ condition False at that bar.
  Offsets shift *backwards* (`offset=1` is the previous bar), NaN-filled at the front.
  `SessionWindow` uses the timezone to build a per-bar boolean; must be vectorised.
- `builtin.py` — at least six ready strategies as `StrategySpec` factories, all
  validating cleanly: `EMA Cross + RSI` (exactly the spec's example),
  `RSI Mean Reversion`, `Bollinger Breakout`, `MACD Trend`,
  `Donchian Channel Breakout`, `Opening Range Momentum` (session-aware),
  `SuperTrend Follower`. Expose `BUILTIN_STRATEGIES: dict[str, Callable[[], StrategySpec]]`.
- `storage.py` — `StrategyStore(workspace)` with `list()`, `load(id)`, `save(spec)`,
  `delete(id)`, `duplicate(id, new_name)`, `rename(id, name)`,
  `export_to(id, path)`, `import_from(path)`. One `.json` per strategy,
  filename `<slug>-<id>.json`, atomic writes, corrupt files reported not crashed.

### `tradingbacktester/engine/*`
- `execution.py` — `CostCalculator(costs, instrument)` with
  `apply_entry(price, side, atr) -> (fill_price, spread_cost_per_unit, slippage_per_unit)`,
  `apply_exit(...)`, `commission(quantity, price) -> float`. Slippage and spread
  are per unit of price; the broker multiplies by quantity and point value.
- `risk.py` — `PositionSizer(risk, instrument)` with
  `size(equity, price, stop_price, atr) -> float` implementing all five
  `SizingMode`s, honouring `max_position_units`, `lot_size` rounding and margin
  availability. Return `0.0` (not an exception) when nothing can be afforded, and
  expose `last_reason: str` explaining why.
- `broker.py` — `SimulatedBroker` owning cash, equity, positions, order book,
  fills, and the intrabar barrier logic (gap-through fills at the open, the
  `IntrabarPriority` rule, trailing-stop update order: check the *existing* stop
  first, then update the trail from this bar's extreme).
- `backtester.py` — `Backtester(bars, spec, config, progress=None, cancel=None)`
  with `.run() -> BacktestResult`. `progress` is `Callable[[int, int], None]`,
  `cancel` is `Callable[[], bool]`; raise `CancelledError` when it returns True.
  Must fill `curves`, `trades`, `orders`, `indicators`, `signals`, `warnings`,
  and call `compute_metrics` from `analytics.metrics`.
  Document the order-simulation rules in the module docstring.

### `tradingbacktester/analytics/*`
- `metrics.py` — `compute_metrics(result) -> dict[str, Any]` producing every key
  the spec lists (see `docs/METRICS.md` which you will also write), plus
  `reliability: dict[str, str]` marking metrics as `ok`/`low_sample`/`unavailable`
  with a plain-language reason when `trade_count < 30` or the denominator is
  degenerate. Never divide by zero; use `inf`/`None` deliberately and say so.
- `equity.py` — `build_curves(...)`, `underwater_periods(curves)`,
  `drawdown_table(curves, top=10)`.
- `periodic.py` — `monthly_returns(result)`, `yearly_returns(result)`,
  `daily_returns(result)` returning tidy structures for the UI table.
- `comparison.py` — `compare_results(results) -> ComparisonTable` with aligned
  equity curves (indexed to 100) and a metric matrix.
- `montecarlo.py` — `resample_trades(net_pnl, starting_capital, ...)` and
  `resample_result(result, ...)` returning a `MonteCarloResult`: percentiles of
  final equity, worst drawdown in cash and percent, and trades spent under
  water, plus where the observed run sits in each distribution, the probability
  of a losing run, and the probability of closing below a ruin level. Three
  resamplers — `shuffle` (a permutation, so the final equity never moves),
  `bootstrap` (with replacement) and `block` (contiguous runs, so a losing
  streak survives). Additive by default; `compounded` resamples each trade's
  return against the equity it was opened against. Draws are processed in
  chunks so a long trade list and a large draw count cannot allocate a matrix
  measured in gigabytes. `format_monte_carlo(result)` renders it as text.

### `tradingbacktester/optimize/*`
- `grid.py` — `ParameterRange(name, start, stop, step)` and
  `build_grid(spec, ranges) -> list[dict]` with a combination count guard.
- `runner.py` — `OptimizationRunner` using `concurrent.futures.ProcessPoolExecutor`
  (fall back to threads if processes are unavailable, e.g. frozen app quirks),
  progress + cancellation, returning `OptimizationResult` rows.
- `ranking.py` — rank by any metric, plus a robustness column (neighbourhood
  mean) and an explicit overfitting warning string.
- `walkforward.py` — `plan_windows(total, folds, train_fraction, anchored)`
  tiling the tail of the series exactly once, and
  `walk_forward(bars, spec, config, ranges, ...) -> WalkForwardResult` which
  optimises on each training block and trades the block that follows.
  `efficiency` (out-of-sample over in-sample, NaN when the in-sample total is
  not positive), `stability` (how often the winner survived a window), and
  `verdict()` in one sentence. Every block is handed `warmup` bars of history
  and pinned to trade only from its own first bar, so the test blocks neither
  gap nor overlap. `format_walk_forward(result, bars)` renders it as text.

### `tradingbacktester/reports/*`
- `csv_export.py` — `export_trades_csv`, `export_equity_csv`, `export_metrics_csv`.
- `html_report.py` — a single self-contained dark-themed HTML report with inline
  SVG equity/drawdown charts, the metrics table, monthly returns and the trade
  list. No external assets, no network requests.
- `pdf_report.py` — use Qt's `QPdfWriter`/`QPainter` (always present) to render
  the report; no reportlab dependency.

### `tradingbacktester/storage/*`
- `workspace.py` — `bootstrap(settings) -> Workspace` creating dirs, seeding
  instruments and samples, returning the workspace.
- `backtest_store.py` — `BacktestStore(workspace)` with `save(result, label)`,
  `list()`, `load(id)`, `delete(id)`. Persist trades + curves + metrics + config
  + strategy JSON; store curves as `.npz`, everything else as JSON.

## Testing

Every module gets tests in `desktop/tests/`. Use pytest. Prefer *hand-checkable*
cases: an SMA of `[1..5]` with period 3 is `[nan, nan, 2, 3, 4]`; a single long
trade entered at 100 and exited at 110 with 2 units, point value 1, commission
$1/side, gives gross 20, commission 2, net 18. Assert exact numbers.


## `tradingbacktester/finder/` — automatic strategy search

The search is affordable because a trade's result depends only on the bar it
was signalled on and the geometry it was given, never on the rule that produced
the signal. So the forward walk is done once per geometry, for every bar, and
cached; after that a candidate rule is a boolean mask and scoring it is a sum.

- `styles.TradingStyle` — the geometry a search may look in: timeframes, stop
  and target multiples, max hold, session window, minimum trade count.
  `STYLES` holds scalp / intraday / swing / position.
- `outcomes.build_outcomes(bars, Geometry, costs, hold_limit) -> OutcomeCache`
  — per-signal-bar net result, exit reason, bars held, entry/stop/target.
  Same conservative choices as the engine: fill at the next open, ATR read at
  the signal bar, a bar reaching both barriers counts as the stop, a gap
  through the stop fills at the open, costs always adverse.
- `outcomes.select_sequential(cache, mask)` — thins a mask to the trades one
  contract could actually have taken. Without it, clustered signals inflate
  every result.
- `outcomes.verify_against_engine(...)` — re-runs a result through the real
  `Backtester` and reports the difference rather than assuming it away.
- `control.analytic_control(...)` / `control.sampled_control(...)` — random
  entries matched on time-of-day. The analytic one is closed-form and cheap
  enough to gate every candidate; the sampled one confirms the shortlist
  without a distributional assumption.
- `control.benjamini_hochberg(p_values, alpha)` — the multiplicity correction.
- `candidates.TEMPLATES` — six entry-rule families, each able to emit a real
  `StrategySpec` so anything found is runnable, saveable and exportable.
- `search.find_strategies(bars, style, ...) -> FinderReport` — the protocol:
  split, gate on the control, correct for multiplicity, test the
  neighbourhood, reveal the locked block once, judge in plain English.
- `report.format_report(report)` — plain text, multiplicity and disclaimer
  included on every path.

## `tradingbacktester/cli.py`

`data`, `import`, `find`, `run`, `strategies`. Reads and writes the same
workspace as the GUI. `--json` for machine-readable output; `--workspace` to
point elsewhere. Imports no Qt.


## `tradingbacktester/research/` — indicators and anomalies

Shares the finder's simulation and controls, so a feature is scored against
what a real trade would have paid rather than against an abstract return.

- `features.Feature` / `all_features()` / `compute_matrix(bars)` — 54
  scale-free causal features in seven families. Every one is checked by
  truncating the series and asserting earlier values do not move.
- `ic.rank_standardise(values)` — rank transform to mean 0, unit variance,
  with tied ranks averaged.
- `ic.newey_west(values, lag)` — `(mean, standard error)` with Bartlett
  weights. The lag is the trade's horizon. Without it a 5% test on unrelated
  data rejects 62% of the time.
- `ic.evaluate(name, feature, target, lag) -> ICResult` — IC, t, p, decile
  profile, spread in currency, monotonicity.
- `ic.redundancy_groups(matrix, names, threshold)` — clusters of features
  saying the same thing.
- `study.study_features(bars, style, ...) -> FeatureStudy` — the protocol:
  research/holdout split, overlap-corrected errors, BH correction, redundancy
  clustering, decile spread against the round-turn cost, verdicts in English.
- `anomalies.DETECTORS` — 15 causal detectors. `anomalies.scan(bars, style,
  ...) -> AnomalyScan` counts each one and then trades it against a matched
  control on both sides, separating data-quality problems from market ones.
- `report.format_study` / `report.format_anomalies` — plain text with the
  caveats beside the numbers.

CLI: `indicators` and `anomalies` subcommands, both with `--json`.
