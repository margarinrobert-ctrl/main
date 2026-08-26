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
from typing import Any

from .config import AppSettings, Workspace
from .core.errors import BacktesterError
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


def _resolve_bars(args: argparse.Namespace):
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
    for meta in rows:
        print(f"  {meta.name:<28} {meta.describe()}")
    print("\nShipped with the application:")
    for dataset in available():
        size = dataset.path().stat().st_size / (1024 * 1024)
        print(f"  {dataset.name:<28} {size:5.1f} MB  {dataset.description}")
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
    from .finder.styles import STYLES

    if args.style == "list":
        for s in STYLES:
            print(f"{s.key:<10} {s.label:<16} {s.summary}")
            print(f"{'':<10} {s.describe()}")
        return 0

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
    from .finder.styles import STYLES
    from .research import format_study, study_features
    from .finder import style as get_style

    if args.style == "list":
        for s in STYLES:
            print(f"{s.key:<10} {s.label:<16} {s.summary}")
        return 0

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


def cmd_run(args: argparse.Namespace) -> int:
    from .analytics.metrics import compute_metrics
    from .engine.backtester import Backtester
    from .strategy.builtin import BUILTIN_STRATEGIES
    from .strategy.storage import StrategyStore

    bars, name = _resolve_bars(args)
    store = StrategyStore(_workspace(args))
    spec = None
    for entry in store.list():
        if args.strategy.lower() in (entry.name.lower(), entry.id.lower()):
            spec = store.load(entry.id)
            break
    if spec is None and args.strategy in BUILTIN_STRATEGIES:
        spec = BUILTIN_STRATEGIES[args.strategy]()
    if spec is None:
        known = [e.name for e in store.list()] + list(BUILTIN_STRATEGIES)
        raise BacktesterError(
            f"No strategy called '{args.strategy}'. Available: "
            f"{', '.join(known)}")

    config = BacktestConfig(starting_capital=args.capital)
    config.exits, config.execution = spec.exits, spec.execution
    config.session, config.costs, config.risk = spec.session, spec.costs, spec.risk
    config.warmup_bars = spec.warmup_bars()
    result = Backtester(bars, spec, config).run()

    print(f"{spec.name} on {name} ({len(bars):,} bars, {bars.timeframe.label})")
    print(result.summary_line())
    metrics = compute_metrics(result)
    if args.json:
        print(json.dumps(metrics, indent=2, default=str))
        return 0
    for key in ("net_profit", "return_pct", "profit_factor", "win_rate",
                "expectancy", "max_drawdown_pct", "sharpe_ratio",
                "sortino_ratio", "trade_count", "avg_trade"):
        if key in metrics:
            value = metrics[key]
            label = key.replace("_", " ")
            print(f"  {label:<20} "
                  + (f"{value:,.2f}" if isinstance(value, (int, float))
                     else str(value)))
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

    p = sub.add_parser("strategies", help="List strategies")
    p.set_defaults(func=cmd_strategies)
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
