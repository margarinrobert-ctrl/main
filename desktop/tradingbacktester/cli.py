"""Driving the platform without the window.

Everything the desktop application does below the user interface is ordinary
Python, so it can be driven from a terminal, a script, a scheduled job -- or by
an assistant with shell access, which is why this exists. The commands read and
write the same workspace the GUI uses: a dataset imported here appears in the
app, and a strategy the finder saves here opens in the editor.

    python -m tradingbacktester.cli data
    python -m tradingbacktester.cli import ~/Downloads/5m_data.csv --symbol US30
    python -m tradingbacktester.cli find --data "US30 15m" --style intraday
    python -m tradingbacktester.cli run "EMA Cross + RSI" --data "US30 15m"

Nothing here reaches the network and nothing leaves the machine.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import AppSettings, Workspace
from .core.errors import BacktesterError
from .core.textfmt import row
from .core.types import BacktestConfig


def _workspace(args: argparse.Namespace) -> Workspace:
    if getattr(args, "workspace", ""):
        return Workspace(Path(args.workspace)).ensure()
    return AppSettings.load().workspace().ensure()


def _repository(args: argparse.Namespace):
    from .data.repository import DatasetRepository

    return DatasetRepository(_workspace(args))


def _instruments(args: argparse.Namespace):
    from .data.instruments import InstrumentRegistry

    return InstrumentRegistry(_workspace(args).settings / "instruments.json")


def _load_bars(args: argparse.Namespace):
    """Find the dataset named on the command line, wherever it lives.

    A name matches, in order: a dataset already in the workspace, one of the
    shipped files, or a path on disk.  That means ``--data US30 15m`` works
    before anything has been imported.
    """
    from .data.bundled import find as find_bundled
    from .data.csv_loader import load_csv, sniff_csv

    wanted = str(getattr(args, "data", "") or "").strip()
    if not wanted:
        raise BacktesterError("Name a dataset with --data.")

    repository = _repository(args)
    for meta in repository.list():
        if wanted.lower() in (meta.name.lower(), meta.id.lower()):
            return repository.load_bars(meta.id), meta.name

    dataset = find_bundled(wanted)
    if dataset is not None and dataset.exists():
        instruments = _instruments(args)
        instrument = instruments.ensure(dataset.symbol, dataset.asset_class)
        profile = sniff_csv(str(dataset.path()))
        return load_csv(str(dataset.path()), profile.mapping, instrument), dataset.name

    path = Path(wanted).expanduser()
    if path.is_file():
        instruments = _instruments(args)
        instrument = instruments.ensure(
            getattr(args, "symbol", "") or path.stem.upper()[:12])
        profile = sniff_csv(str(path))
        return load_csv(str(path), profile.mapping, instrument), path.name

    from .data.bundled import available

    known = [m.name for m in repository.list()] + [d.name for d in available()]
    raise BacktesterError(
        f"No dataset called '{wanted}'. Available: "
        f"{', '.join(known) if known else '(none)'} — or give a path to a CSV.")


def _resolve_bars(args: argparse.Namespace):
    """The named dataset, reflected first when ``--mirror`` was given.

    Every command that reads data accepts ``--mirror``, because the question
    "would this survive on a market that fell?" is worth asking of a search, an
    indicator ranking and an anomaly scan, not only of one backtest.
    """
    bars, name = _load_bars(args)
    if getattr(args, "mirror", False):
        from .research.mirror import mirror_bars

        bars = mirror_bars(bars)
        name = f"{name} (mirrored)"
    return bars, name


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def cmd_data(args: argparse.Namespace) -> int:
    from .data.bundled import available

    repository = _repository(args)
    rows = repository.list()
    print("In the workspace:")
    if not rows:
        print("  (nothing imported yet)")
    # The descriptions run to 130 characters; wrapped under the name they stay
    # in one column instead of folding across the terminal at an arbitrary
    # point.
    for meta in rows:
        for line in row(f"  {meta.name:<28} ", meta.describe()):
            print(line)
    print("\nShipped with the application:")
    for dataset in available():
        size = dataset.path().stat().st_size / (1024 * 1024)
        for line in row(f"  {dataset.name:<20} {size:5.1f} MB  ",
                        dataset.description):
            print(line)
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    from .data.csv_loader import load_csv, sniff_csv
    from .data.validation import validate_bars

    path = Path(args.path).expanduser()
    if not path.is_file():
        raise BacktesterError(f"There is no file at {path}.")
    profile = sniff_csv(str(path))
    print(f"{path.name}: {profile.describe()}")
    for problem in profile.problems:
        print(f"  ! {problem}")
    mapping = profile.mapping
    print(f"  columns: datetime={mapping.datetime or mapping.date} "
          f"open={mapping.open} high={mapping.high} low={mapping.low} "
          f"close={mapping.close} volume={mapping.volume}")

    instruments = _instruments(args)
    symbol = (args.symbol or path.stem.upper()[:12]).strip()
    instrument = instruments.ensure(symbol)
    instruments.save()
    if args.timezone:
        mapping.timezone = args.timezone

    bars = load_csv(str(path), mapping, instrument)
    report = validate_bars(bars)
    import pandas as pd

    first = pd.Timestamp(bars.start_ts, tz="UTC")
    last = pd.Timestamp(bars.end_ts, tz="UTC")
    print(f"  {len(bars):,} bars, {bars.timeframe.label}, "
          f"{first:%Y-%m-%d} to {last:%Y-%m-%d}")
    for issue in report.sorted_issues()[:8]:
        print(f"  {issue.format_line()}")

    if args.dry_run:
        print("  (dry run: nothing was saved)")
        return 0
    meta = _repository(args).add_from_bars(bars, name=args.name or "",
                                           source_path=str(path))
    print(f"  saved as '{meta.name}'")
    return 0


def _list_styles(geometry: bool = False) -> int:
    """The trading styles, one block each, fitted to the terminal."""
    from .finder.styles import STYLES

    for s in STYLES:
        for line in row(f"{s.key:<10} {s.label:<16} ", s.summary):
            print(line)
        if geometry:
            for line in row(f"{'':<10} ", s.describe()):
                print(line)
    return 0


def _stderr_progress():
    """A progress callback that draws on a terminal and stays quiet in a pipe."""
    last = [0.0]

    def progress(done: int, total: int, message: str) -> None:
        if not sys.stderr.isatty():
            return
        share = done / max(1, total)
        if share - last[0] < 0.02:
            return
        last[0] = share
        sys.stderr.write(f"\r  {message} … {share * 100:3.0f}%")
        sys.stderr.flush()

    return progress


def _clear_progress() -> None:
    if sys.stderr.isatty():
        sys.stderr.write("\r" + " " * 78 + "\r")


def cmd_find(args: argparse.Namespace) -> int:
    from .finder import find_strategies, format_report, style as get_style
    if args.style == "list":
        return _list_styles(geometry=True)

    bars, name = _resolve_bars(args)
    chosen = get_style(args.style)
    # Empty means "the best bar size this data can actually produce", which the
    # search works out: five-minute bars cannot be turned into one-minute ones.
    timeframe = args.timeframe

    progress = _stderr_progress()
    report = find_strategies(
        bars, chosen, timeframe=timeframe, top_n=args.top,
        control_draws=args.draws, research_fraction=args.research,
        sides=((1,) if args.side == "long" else (-1,) if args.side == "short"
               else (1, -1)),
        progress=progress)
    _clear_progress()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report,
                            currency=getattr(bars.instrument, "currency", "USD")))

    if args.save:
        from .strategy.storage import StrategyStore

        store = StrategyStore(_workspace(args))
        saved = 0
        for finding in report.shortlist:
            if finding.spec is None:
                continue
            store.save(finding.spec)
            saved += 1
        print(f"Saved {saved} strategy file(s) into the workspace. They are "
              f"candidates for further testing, not recommendations.")
    return 0


def cmd_indicators(args: argparse.Namespace) -> int:
    from .research import format_study, study_features
    from .finder import style as get_style

    if args.style == "list":
        return _list_styles()

    bars, name = _resolve_bars(args)
    report = study_features(bars, get_style(args.style),
                            timeframe=args.timeframe,
                            side=-1 if args.side == "short" else 1,
                            research_fraction=args.research,
                            progress=_stderr_progress())
    _clear_progress()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_study(report, top=args.top))
    return 0


def cmd_anomalies(args: argparse.Namespace) -> int:
    from .research import format_anomalies, scan
    from .finder import style as get_style

    bars, name = _resolve_bars(args)
    report = scan(bars, get_style(args.style), timeframe=args.timeframe,
                  control_draws=args.draws, research_fraction=args.research,
                  progress=_stderr_progress())
    _clear_progress()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_anomalies(report))
    return 0


def _resolve_spec(args: argparse.Namespace):
    """Find the strategy named on the command line, saved or built in."""
    from .strategy.builtin import BUILTIN_STRATEGIES
    from .strategy.storage import StrategyStore

    wanted = str(getattr(args, "strategy", "") or "").strip()
    store = StrategyStore(_workspace(args))
    for entry in store.list():
        if wanted.lower() in (entry.name.lower(), entry.id.lower()):
            return store.load(entry.id)
    for name, build in BUILTIN_STRATEGIES.items():
        if wanted.lower() == name.lower():
            return build()
    known = [e.name for e in store.list()] + list(BUILTIN_STRATEGIES)
    raise BacktesterError(
        f"No strategy called '{wanted}'. Available: {', '.join(known)}")


def _config_for(spec, capital: float) -> BacktestConfig:
    """The strategy's own exits, costs and risk, as a run configuration."""
    config = BacktestConfig(starting_capital=capital)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    config.warmup_bars = spec.warmup_bars()
    return config


def cmd_run(args: argparse.Namespace) -> int:
    from .analytics.metrics import compute_metrics
    from .engine.backtester import Backtester

    bars, name = _resolve_bars(args)
    spec = _resolve_spec(args)
    config = _config_for(spec, args.capital)
    result = Backtester(bars, spec, config).run()

    stream = sys.stderr if args.json else sys.stdout
    for line in row("", f"{spec.name} on {name} ({len(bars):,} bars, "
                    f"{bars.timeframe.label})"):
        print(line, file=stream)
    for line in row("", result.summary_line()):
        print(line, file=stream)
    metrics = compute_metrics(result)
    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
        return 0
    # `trade_count` is not a metric key -- the metrics layer calls it
    # `total_trades` -- so asking for it silently printed nothing, and the one
    # number that decides whether any of the rest means anything was missing.
    reliability = metrics.get("reliability") or {}
    notes = metrics.get("reliability_notes") or {}
    shown = ("total_trades", "net_profit", "return_pct", "profit_factor",
             "win_rate", "expectancy", "max_drawdown_pct", "sharpe_ratio",
             "sortino_ratio", "avg_trade")
    for key in shown:
        if key not in metrics:
            continue
        value = metrics[key]
        label = key.replace("_", " ")
        counts = key in ("total_trades", "winning_trades", "losing_trades")
        text = (f"{value:,.0f}" if counts and isinstance(value, (int, float))
                else f"{value:,.2f}" if isinstance(value, (int, float))
                else str(value))
        # The window badges these; a terminal that prints a profit factor of
        # 4.00 from six trades with no caveat is worse than one that refuses.
        flag = "  LOW n" if reliability.get(key) == "low_sample" else ""
        print(f"  {label:<20} {text:>14}{flag}")

    flagged = [key for key in shown if reliability.get(key) == "low_sample"]
    if flagged:
        print()
        note = next((notes[k] for k in flagged if notes.get(k)), "")
        for line in row("  ", f"LOW n: {', '.join(k.replace('_', ' ') for k in flagged)}"
                        f" — {note}" if note else
                        f"LOW n: {', '.join(flagged)}"):
            print(line)
    return 0


def _parse_param(text: str):
    """``ema_fast=8:20:2`` -> a :class:`ParameterRange`."""
    from .optimize.grid import ParameterRange

    name, _, spec = str(text).partition("=")
    name, spec = name.strip(), spec.strip()
    if not name or not spec:
        raise BacktesterError(
            f"Could not read the swept parameter '{text}'. Write it as "
            f"name=start:stop:step, for example ema_fast=8:20:2.")
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise BacktesterError(
            f"'{text}' needs a start and a stop, and may have a step: "
            f"{name}=start:stop:step.")
    try:
        numbers = [float(p) for p in parts]
    except ValueError as exc:
        raise BacktesterError(
            f"The range for '{name}' must be numbers, not '{spec}'.") from exc
    start, stop = numbers[0], numbers[1]
    step = numbers[2] if len(numbers) == 3 else 1.0
    return ParameterRange(name, start, stop, step)


def _thin(candidate, rungs: int = 3):
    """The same span in fewer steps, keeping both endpoints.

    Used only to bring an automatic grid down to a size worth running; a range
    the user typed is never thinned.
    """
    from .optimize.grid import ParameterRange

    if candidate.count() <= rungs:
        return candidate
    span = abs(float(candidate.stop) - float(candidate.start))
    step = span / max(1, rungs - 1)
    if candidate.is_integer:
        step = max(1.0, round(step))
    return ParameterRange(candidate.name, candidate.start, candidate.stop, step)


def _default_ranges(spec, ceiling: int = 200):
    """Sweep every numeric parameter around its default, or explain why not.

    A walk-forward searches the whole grid once per fold, so a grid that is
    merely large for an ordinary sweep is five times that here.  When the
    obvious grid is too big every range is thinned to its endpoints and centre
    first; only if that is still too big is the user asked which parameters
    matter, rather than being left to wait for a run nobody chose.
    """
    from .optimize.grid import combination_count, suggested_range

    ranges = []
    for param in spec.params:
        if getattr(param, "kind", "") not in ("int", "float"):
            continue
        candidate = suggested_range(param)
        if candidate.count() > 1:
            ranges.append(candidate)
    if not ranges:
        raise BacktesterError(
            f"'{spec.name}' has no numeric parameter to optimise, so there is "
            f"nothing for a walk-forward to choose. An ordinary backtest "
            f"already answers the question.")
    if combination_count(ranges) > ceiling:
        ranges = [_thin(r) for r in ranges]
    total = combination_count(ranges)
    if total > ceiling:
        names = ", ".join(r.name for r in ranges)
        example = ranges[0]
        raise BacktesterError(
            f"Sweeping every parameter of '{spec.name}' is {total:,} "
            f"combinations per fold, which is too many to run by default. "
            f"Name the ones that matter with --param, for example --param "
            f"{example.name}={example.start:g}:{example.stop:g}"
            f":{abs(example.step):g}. Numeric parameters: {names}.")
    return ranges


def cmd_walkforward(args: argparse.Namespace) -> int:
    from .optimize.walkforward import format_walk_forward, walk_forward

    bars, name = _resolve_bars(args)
    spec = _resolve_spec(args)
    config = _config_for(spec, args.capital)

    ranges = ([_parse_param(text) for text in args.param] if args.param
              else _default_ranges(spec))
    # Everything but the payload goes to stderr under --json so the output can
    # be piped straight into a tool that expects one document.
    stream = sys.stderr if args.json else sys.stdout
    print(f"{spec.name} on {name} ({len(bars):,} bars, {bars.timeframe.label})",
          file=stream)
    for r in ranges:
        print(f"  sweeping {r.describe()}", file=stream)

    progress = _stderr_progress()
    result = walk_forward(bars, spec, config, ranges, folds=args.folds,
                          train_fraction=args.train, anchored=args.anchored,
                          metric=args.metric, minimum_trades=args.min_trades,
                          progress=progress)
    _clear_progress()
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print()
        print(format_walk_forward(result, bars,
                                  currency=bars.instrument.currency))
    return 0


def cmd_montecarlo(args: argparse.Namespace) -> int:
    from .analytics.montecarlo import format_monte_carlo, resample_result
    from .engine.backtester import Backtester

    bars, name = _resolve_bars(args)
    spec = _resolve_spec(args)
    config = _config_for(spec, args.capital)
    stream = sys.stderr if args.json else sys.stdout
    print(f"{spec.name} on {name} ({len(bars):,} bars, {bars.timeframe.label})",
          file=stream)
    run = Backtester(bars, spec, config).run()
    print(f"  {run.summary_line()}", file=stream)

    result = resample_result(
        run, method=args.method, draws=args.draws,
        compounded=args.compounded,
        ruin_level=args.ruin if args.ruin > 0 else None,
        block_size=args.block, seed=args.seed, progress=_stderr_progress())
    _clear_progress()
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print()
        print(format_monte_carlo(result, currency=bars.instrument.currency))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .engine.backtester import Backtester

    bars, name = _resolve_bars(args)
    spec = _resolve_spec(args)
    config = _config_for(spec, args.capital)
    print(f"{spec.name} on {name} ({len(bars):,} bars, {bars.timeframe.label})")
    result = Backtester(bars, spec, config).run()
    for line in row("  ", result.summary_line()):
        print(line)

    target = Path(args.out).expanduser()
    kind = args.format
    if kind == "auto":
        kind = "pdf" if target.suffix.lower() == ".pdf" else "html"
    if kind == "pdf":
        # Works with no display: `ensure_application` selects the offscreen
        # platform rather than letting Qt abort the process.
        from .reports.pdf_report import export_pdf_report

        written = export_pdf_report(result, str(target))
    else:
        from .reports.html_report import export_html_report

        written = export_html_report(result, str(target))
    # Deliberately not wrapped. A path is one unbreakable token, so wrapping
    # only orphans it onto a line of its own; printed whole it can be copied
    # straight back out, which is the entire point of echoing it.
    size = Path(written).stat().st_size / 1024.0
    print(f"  wrote {written}  ({size:,.0f} KB)")
    if args.trades:
        from .reports.csv_export import export_trades_csv

        trades = export_trades_csv(result, str(target.with_suffix(".trades.csv")))
        print(f"  wrote {trades}")
    return 0


def cmd_mirror(args: argparse.Namespace) -> int:
    from .research.mirror import format_mirror, mirror_test

    bars, name = _resolve_bars(args)
    spec = _resolve_spec(args)
    config = _config_for(spec, args.capital)
    stream = sys.stderr if args.json else sys.stdout
    print(f"{spec.name} on {name} ({len(bars):,} bars, {bars.timeframe.label})",
          file=stream)

    report = mirror_test(bars, spec, config, progress=_stderr_progress())
    _clear_progress()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print()
        print(format_mirror(report, currency=bars.instrument.currency))
    return 0


def cmd_strategies(args: argparse.Namespace) -> int:
    from .strategy.builtin import BUILTIN_STRATEGIES
    from .strategy.storage import StrategyStore

    store = StrategyStore(_workspace(args))
    print("Saved:")
    entries = store.list()
    if not entries:
        print("  (none)")
    for entry in entries:
        print(f"  {entry.name}")
    print("\nBuilt in:")
    for name in BUILTIN_STRATEGIES:
        print(f"  {name}")
    return 0


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradingbacktester",
        description="Backtest and search for strategies from the command line. "
                    "Uses the same workspace as the desktop application.")
    parser.add_argument("--workspace", default="",
                        help="Workspace folder (default: the app's own)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("data", help="List datasets, imported and shipped")
    p.set_defaults(func=cmd_data)

    p = sub.add_parser("import", help="Import a CSV into the workspace")
    p.add_argument("path")
    p.add_argument("--symbol", default="", help="Instrument symbol, e.g. US30")
    p.add_argument("--name", default="", help="Name for the dataset")
    p.add_argument("--timezone", default="",
                   help="Timezone the file's timestamps are written in")
    p.add_argument("--dry-run", action="store_true",
                   help="Inspect and validate without saving")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("find", help="Search for strategies")
    p.add_argument("--data", required=True,
                   help="Dataset name, shipped dataset, or a path to a CSV")
    p.add_argument("--style", default="intraday",
                   help="scalp | intraday | swing | position, or 'list'")
    p.add_argument("--timeframe", default="", help="Override the bar size")
    p.add_argument("--side", default="both", choices=("both", "long", "short"))
    p.add_argument("--top", type=int, default=5, help="How many to shortlist")
    p.add_argument("--draws", type=int, default=2000,
                   help="Draws for the sampled control")
    p.add_argument("--research", type=float, default=0.65,
                   help="Fraction of the data used to choose (rest is locked)")
    p.add_argument("--save", action="store_true",
                   help="Save the shortlist as strategies in the workspace")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("indicators",
                       help="Rank indicators by what they predict")
    p.add_argument("--data", required=True)
    p.add_argument("--style", default="intraday",
                   help="scalp | intraday | swing | position, or 'list'")
    p.add_argument("--timeframe", default="")
    p.add_argument("--side", default="long", choices=("long", "short"),
                   help="Which side's trades to predict")
    p.add_argument("--top", type=int, default=14)
    p.add_argument("--research", type=float, default=0.65)
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_indicators)

    p = sub.add_parser("anomalies",
                       help="Find unusual bars and test whether they pay")
    p.add_argument("--data", required=True)
    p.add_argument("--style", default="intraday")
    p.add_argument("--timeframe", default="")
    p.add_argument("--draws", type=int, default=1000)
    p.add_argument("--research", type=float, default=0.65)
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_anomalies)

    p = sub.add_parser("run", help="Run one backtest")
    p.add_argument("strategy")
    p.add_argument("--data", required=True)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser(
        "walkforward",
        help="Optimise on the past, trade the future, repeat",
        description="Choose parameters on one block, trade the next block "
                    "with them, move both along and stitch the untouched "
                    "blocks into one equity curve. That curve is the only "
                    "number here that was not chosen with hindsight.")
    p.add_argument("strategy")
    p.add_argument("--data", required=True)
    p.add_argument("--param", action="append", default=[],
                   metavar="NAME=START:STOP:STEP",
                   help="Parameter to sweep; repeat for more than one. "
                        "Omit to sweep every numeric parameter.")
    p.add_argument("--folds", type=int, default=5, help="How many train/test pairs")
    p.add_argument("--train", type=float, default=0.5,
                   help="Fraction of the series in the first training block")
    p.add_argument("--anchored", action="store_true",
                   help="Grow the training block from the start instead of "
                        "rolling a fixed-length window")
    p.add_argument("--metric", default="net_profit",
                   help="What to optimise in each training window")
    p.add_argument("--min-trades", type=int, default=5, dest="min_trades",
                   help="Combinations with fewer training trades are ignored")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_walkforward)

    p = sub.add_parser(
        "montecarlo",
        help="Resample a run's trades to see the range of paths",
        description="Run a backtest, then resample its trade sequence. This "
                    "describes the range of outcomes those trades could have "
                    "produced; it says nothing about whether the strategy has "
                    "an edge.")
    p.add_argument("strategy")
    p.add_argument("--data", required=True)
    p.add_argument("--method", default="block",
                   choices=("shuffle", "bootstrap", "block"),
                   help="shuffle: same trades, different order. bootstrap: a "
                        "different sample of trades. block: a different sample "
                        "in contiguous runs, so streaks survive.")
    p.add_argument("--draws", type=int, default=5000)
    p.add_argument("--compounded", action="store_true",
                   help="Each trade contributes its return as a fraction of "
                        "the equity it was opened against")
    p.add_argument("--block", type=int, default=0,
                   help="Block length for --method block (default: n^(1/3))")
    p.add_argument("--ruin", type=float, default=0.0,
                   help="Count a draw as ruined below this equity "
                        "(default: half the starting capital)")
    p.add_argument("--seed", type=int, default=12345)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_montecarlo)

    p = sub.add_parser(
        "report",
        help="Run a backtest and write a full report to a file",
        description="Everything the window's File → Export menu writes, from "
                    "the terminal. The report is self-contained and makes no "
                    "network request; the PDF renders without a display.")
    p.add_argument("strategy")
    p.add_argument("--data", required=True)
    p.add_argument("--out", required=True, metavar="PATH",
                   help="Where to write it; the suffix chooses the format")
    p.add_argument("--format", default="auto", choices=("auto", "html", "pdf"),
                   help="Override the format implied by --out")
    p.add_argument("--trades", action="store_true",
                   help="Also write the trade list beside it as CSV")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser(
        "mirror",
        help="Run a strategy on this market and on its reflection",
        description="Negate every log return to build a market with the same "
                    "timestamps, the same volatility and the opposite drift, "
                    "then run the same strategy on both. A rule that only "
                    "makes money on the real series was betting on direction.")
    p.add_argument("strategy")
    p.add_argument("--data", required=True)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_mirror)

    p = sub.add_parser("strategies", help="List strategies")
    p.set_defaults(func=cmd_strategies)

    # Every command that reads a dataset can read its reflection instead. Added
    # in one place rather than in each parser so a new data command cannot
    # forget it; `mirror` is excluded because reflecting is the whole of what
    # it does.
    for name, subparser in sub.choices.items():
        if name in ("mirror", "data", "import", "strategies"):
            continue
        subparser.add_argument(
            "--mirror", action="store_true",
            help="Negate every log return first, giving a market with the "
                 "same volatility and session structure and the opposite "
                 "drift. Anything that only works on the real series was "
                 "betting on direction.")
    return parser


def main(argv: list[str] | None = None) -> int:
    from .logging_setup import configure_logging

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        configure_logging(_workspace(args).logs, level="WARNING", console=False)
    except Exception:                       # pragma: no cover - logging only
        pass
    try:
        return int(args.func(args) or 0)
    except BacktesterError as exc:
        print(f"error: {exc.user_message}", file=sys.stderr)
        if exc.detail:
            print(f"  {exc.detail}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:               # pragma: no cover - interactive
        print("\ncancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":               # pragma: no cover - entry point
    raise SystemExit(main())
