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
import math
import sys
from pathlib import Path
from typing import Any

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


def _stderr_progress(label: str = "working"):
    """A progress callback that draws on a terminal and stays quiet in a pipe.

    ``message`` is optional so the same callback fits both conventions in this
    codebase: the analytics layers name each phase as they go, and the
    optimisation runner reports only ``(done, total)``. A runner that does not
    name its work gets ``label``.
    """
    last = [0.0]

    def progress(done: int, total: int, message: str = "") -> None:
        if not sys.stderr.isatty():
            return
        share = done / max(1, total)
        if share - last[0] < 0.02:
            return
        last[0] = share
        sys.stderr.write(f"\r  {message or label} … {share * 100:3.0f}%")
        sys.stderr.flush()

    return progress


def _clear_progress() -> None:
    if sys.stderr.isatty():
        sys.stderr.write("\r" + " " * 78 + "\r")


def _numbers(text: str, what: str) -> tuple[float, ...]:
    """``"1.0,1.5,2"`` -> ``(1.0, 1.5, 2.0)``."""
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    try:
        return tuple(float(p) for p in parts)
    except ValueError as exc:
        raise BacktesterError(
            f"The {what} must be numbers separated by commas, not "
            f"'{text}'.") from exc


def _constrain(chosen, args: argparse.Namespace):
    """Apply the user's own constraints to a style, or leave it alone.

    Every one of these is fixed BEFORE the search runs and reported with the
    result. None of them is searched over: handing a list of sessions to a
    search and keeping the best would put the session inside the selection.
    """
    from .finder.styles import customise

    overrides: dict[str, Any] = {}
    if args.session:
        window = str(args.session).strip().lower()
        if window in ("none", "all", "any"):
            overrides["session"] = None
            overrides["flat_at_session_end"] = False
        else:
            parts = window.replace("to", "-").split("-")
            if len(parts) != 2:
                raise BacktesterError(
                    f"Write the session as START-END, for example "
                    f"09:30-16:00, or 'none' for all hours. Got '{args.session}'.")
            overrides["session"] = (parts[0].strip(), parts[1].strip())
    if args.weekdays:
        try:
            overrides["weekdays"] = tuple(
                int(d) for d in str(args.weekdays).split(",") if d.strip())
        except ValueError as exc:
            raise BacktesterError(
                f"Weekdays are numbers 0 (Monday) to 6 (Sunday), separated by "
                f"commas, not '{args.weekdays}'.") from exc
    if args.stop:
        overrides["stop_atr"] = _numbers(args.stop, "stop multiples")
    if args.target:
        overrides["target_r"] = _numbers(args.target, "target multiples")
    if args.max_bars is not None:
        overrides["max_bars"] = int(args.max_bars)
    if args.min_trades is not None:
        overrides["min_trades"] = int(args.min_trades)
    if not overrides:
        return chosen
    return customise(chosen, **overrides)


def cmd_find(args: argparse.Namespace) -> int:
    from .finder import find_strategies, format_report, style as get_style
    if args.style == "list":
        return _list_styles(geometry=True)
    if args.template == "list":
        from .finder.candidates import TEMPLATES

        for template in TEMPLATES:
            for line in row(f"  {template.key:<18} ", template.description):
                print(line)
        return 0

    bars, name = _resolve_bars(args)
    chosen = _constrain(get_style(args.style), args)
    # Empty means "the best bar size this data can actually produce", which the
    # search works out: five-minute bars cannot be turned into one-minute ones.
    timeframe = args.timeframe

    stream = sys.stderr if args.json else sys.stdout
    print(f"{chosen.label} on {name}: {chosen.describe()}", file=stream)

    progress = _stderr_progress()
    report = find_strategies(
        bars, chosen, timeframe=timeframe, top_n=args.top,
        control_draws=args.draws, research_fraction=args.research,
        sides=((1,) if args.side == "long" else (-1,) if args.side == "short"
               else (1, -1)),
        templates=tuple(t.strip() for t in str(args.template).split(",")
                        if t.strip()),
        validate=args.validate,
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


def cmd_autosearch(args: argparse.Namespace) -> int:
    from .finder import auto_search, format_auto_search, plan

    bars, name = _resolve_bars(args)
    stream = sys.stderr if args.json else sys.stdout
    pairs = plan(bars,
                 [s.strip() for s in str(args.style).split(",") if s.strip()],
                 [t.strip() for t in str(args.timeframe).split(",") if t.strip()])
    print(f"{name}: {len(bars):,} bars, {len(pairs)} searches planned",
          file=stream)
    for style_def, timeframe in pairs:
        print(f"  {style_def.label} on {timeframe}", file=stream)
    if args.plan:
        return 0

    report = auto_search(
        bars,
        styles=[s.strip() for s in str(args.style).split(",") if s.strip()],
        timeframes=[t.strip() for t in str(args.timeframe).split(",")
                    if t.strip()],
        templates=tuple(t.strip() for t in str(args.template).split(",")
                        if t.strip()),
        sides=((1,) if args.side == "long" else (-1,) if args.side == "short"
               else (1, -1)),
        research_fraction=args.research, alpha=args.alpha,
        control_draws=args.draws, validate=args.validate, top_n=args.top,
        progress=_stderr_progress("searching"))
    _clear_progress()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print()
        print(format_auto_search(
            report, currency=getattr(bars.instrument, "currency", "USD"),
            top=args.top))

    if args.save and report.survivors:
        from .strategy.storage import StrategyStore

        store = StrategyStore(_workspace(args))
        saved = 0
        for finding in report.survivors:
            if getattr(finding, "spec", None) is None:
                continue
            store.save(finding.spec)
            saved += 1
        print(f"Saved {saved} strategy file(s) into the workspace. They "
              f"survived a correction over {report.scored:,} combinations, "
              f"which makes them candidates for further testing, not "
              f"recommendations.")
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
                            interactions=args.interactions,
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
    return _spec_named(args, str(getattr(args, "strategy", "") or ""))


def _spec_named(args: argparse.Namespace, wanted: str):
    """One strategy by name, from the workspace or the built-in set."""
    from .strategy.builtin import BUILTIN_STRATEGIES
    from .strategy.storage import StrategyStore

    wanted = str(wanted or "").strip()
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


def _default_ranges(spec, ceiling: int = 200, unit: str = " per fold"):
    """Sweep every numeric parameter around its default, or explain why not.

    A walk-forward searches the whole grid once per fold, so a grid that is
    merely large for an ordinary sweep is five times that here.  When the
    obvious grid is too big every range is thinned to its endpoints and centre
    first; only if that is still too big is the user asked which parameters
    matter, rather than being left to wait for a run nobody chose.

    ``unit`` names what the count is per, because the caller knows and this
    function does not: a holdout sweep runs the grid once, not once per fold,
    and telling its user otherwise would misstate the cost by five times.
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
            f"combinations{unit}, which is too many to run by default. "
            f"Name the ones that matter with --param, for example --param "
            f"{example.name}={example.start:g}:{example.stop:g}"
            f":{abs(example.step):g}. Numeric parameters: {names}.")
    return ranges


def cmd_continuous(args: argparse.Namespace) -> int:
    from .data.continuous import (Adjustment, Contract, RollRule,
                                  build_continuous, describe)

    contracts = []
    for entry in args.contract:
        label, _, source = str(entry).partition("=")
        label, source = label.strip(), source.strip()
        if not label or not source:
            raise BacktesterError(
                f"Could not read the contract '{entry}'. Write it as "
                f"LABEL=dataset, for example ESH24='ES Mar 24'.")
        holder = argparse.Namespace(**vars(args))
        holder.data = source
        holder.mirror = False       # reflecting one leg of a splice is nonsense
        bars, name = _load_bars(holder)
        contracts.append(Contract(label, bars))
        print(f"  {label}: {name} — {len(bars):,} bars, "
              f"{bars.timeframe.label}", file=sys.stderr)

    series = build_continuous(
        contracts, adjustment=Adjustment(args.adjust),
        rule=RollRule(args.roll), days_before_end=args.roll_days)

    if args.json:
        print(json.dumps(series.to_dict(), indent=2))
        return 0

    currency = getattr(series.bars.instrument, "currency", "USD")
    print()
    print(f"{'from':<10} {'to':<10} {'at':<20} {'gap':>12} {'ratio':>10}")
    import pandas as pd

    for roll in series.rolls:
        stamp = str(pd.Timestamp(roll.at_ts, tz="UTC"))[:19]
        print(f"{roll.from_label:<10} {roll.to_label:<10} {stamp:<20} "
              f"{roll.gap:>12,.2f} {roll.ratio:>10.6f}")
        for line in row("           ", roll.rule):
            print(line)
    print()
    for line in row("", describe(series, currency)):
        print(line)
    for note in series.notes:
        print()
        for line in row("", note):
            print(line)

    if args.save:
        repository = _repository(args)
        meta = repository.add_from_bars(
            series.bars, name=args.save,
            notes=describe(series, currency))
        print()
        print(f"Saved as '{meta.name}' in the workspace.")
    return 0


def cmd_optimise(args: argparse.Namespace) -> int:
    from .optimize.holdout import format_holdout, optimise_with_holdout

    bars, name = _resolve_bars(args)
    spec = _resolve_spec(args)
    config = _config_for(spec, args.capital)

    ranges = ([_parse_param(text) for text in args.param] if args.param
              else _default_ranges(spec, unit=""))
    stream = sys.stderr if args.json else sys.stdout
    print(f"{spec.name} on {name} ({len(bars):,} bars, {bars.timeframe.label})",
          file=stream)
    for r in ranges:
        print(f"  sweeping {r.describe()}", file=stream)

    result = optimise_with_holdout(
        bars, spec, config, ranges, metric=args.metric,
        research_fraction=args.research, reveal=args.reveal,
        progress=_stderr_progress("sweeping the research block"))
    _clear_progress()
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print()
        print(format_holdout(result, bars,
                             currency=bars.instrument.currency))
    return 0


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


def cmd_diagnose(args: argparse.Namespace) -> int:
    """Measure what a finished run actually rests on."""
    from .analytics.diagnose import diagnose

    bars, name = _resolve_bars(args)
    spec = _resolve_spec(args)
    config = _config_for(spec, args.capital)
    stream = sys.stderr if args.json else sys.stdout
    print(f"{spec.name} on {name} ({len(bars):,} bars, {bars.timeframe.label})",
          file=stream)

    from .engine.backtester import Backtester

    result = Backtester(bars, spec, config, progress=_stderr_progress()).run()
    _clear_progress()
    report = diagnose(result, spec, control=not args.no_control,
                      draws=args.draws)
    if args.json:
        print(json.dumps({
            "trades": report.trades,
            "findings": [{"key": f.key, "severity": f.severity,
                          "headline": f.headline,
                          "measurement": f.measurement,
                          "suggestion": f.suggestion}
                         for f in report.findings],
            "notes": list(report.notes),
        }, indent=2))
    else:
        print()
        print(report.describe())
    # A blocker is not a crash: the run happened and the report is the point.
    return 0


def cmd_correlate(args: argparse.Namespace) -> int:
    """How much of a set of strategies is really one bet."""
    from .analytics.correlation import correlate_results
    from .engine.backtester import Backtester

    bars, name = _resolve_bars(args)
    stream = sys.stderr if args.json else sys.stdout
    specs = [_spec_named(args, n) for n in args.strategies]
    print(f"{len(specs)} strategies on {name} ({len(bars):,} bars, "
          f"{bars.timeframe.label})", file=stream)

    results = []
    for spec in specs:
        config = _config_for(spec, args.capital)
        results.append(Backtester(bars, spec, config).run())
    report = correlate_results(results, unit=args.unit)

    if args.json:
        print(json.dumps({
            "names": list(report.names),
            "matrix": [[None if not math.isfinite(v) else round(float(v), 6)
                        for v in row] for row in report.matrix],
            "effective_bets": report.effective_bets,
            "pairs": [{"a": p.a, "b": p.b, "correlation": p.correlation,
                       "shared_periods": p.shared_periods,
                       "exposure_overlap": p.exposure_overlap,
                       "same_side_share": p.same_side_share,
                       "entry_coincidence": p.entry_coincidence}
                      for p in report.pairs],
            "notes": list(report.notes),
        }, indent=2))
    else:
        print()
        width = max(len(n) for n in report.names) + 2
        header = " " * width + "".join(f"{n[:10]:>12s}" for n in report.names)
        print(header)
        for i, row_name in enumerate(report.names):
            cells = "".join(
                f"{'   —':>12s}" if not math.isfinite(report.matrix[i, j])
                else f"{report.matrix[i, j]:>+12.2f}"
                for j in range(len(report.names)))
            print(f"{row_name[:width - 2]:<{width}s}{cells}")
        print()
        print(report.describe())
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    """The research loop, end to end, reporting failures as well as findings."""
    from .finder import style as get_style
    from .research.loop import run_loop
    from .research.loop_report import format_loop

    bars, _name = _resolve_bars(args)
    chosen = get_style(args.style)
    progress = _stderr_progress()
    report = run_loop(bars, chosen, rounds=args.rounds,
                      validate=args.validate, control_draws=args.draws,
                      progress=progress)
    _clear_progress()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_loop(report,
                          currency=getattr(bars.instrument, "currency", "USD")))

    if args.save:
        from .storage.research_store import ResearchStore

        store = ResearchStore(_workspace(args))
        row = store.save(report, timeframe=bars.timeframe.label)
        print(f"Saved as {row.id} in the workspace's research folder.")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    """Translate a pasted strategy and say exactly what did not come across.

    Exit code 0 only for a faithful conversion.  A partial one exits 2, because
    a script that treats "it produced a spec" as success would go on to
    backtest a strategy nobody wrote.
    """
    import sys as _sys

    from .strategy.importer import import_strategy

    if args.path == "-":
        text = _sys.stdin.read()
    else:
        try:
            text = Path(args.path).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Could not read {args.path}: {exc}", file=_sys.stderr)
            return 1

    report = import_strategy(text)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"Detected: {report.detected}"
              + (f" ({report.evidence[0]})" if report.evidence else ""))
        print(f"Converted {len(report.converted)}, ignored "
              f"{len(report.ignored)}, unsupported {len(report.unsupported)}.")
        print()
        for line in report.lines:
            if line.outcome == "converted":
                continue
            marker = "  " if line.outcome == "ignored" else "!!"
            print(f"{marker} line {line.line}: {line.source}")
            print(f"      {line.outcome}: {line.detail}")
        for warning in report.warnings:
            print(f"NOTE: {warning}")
        for error in report.errors:
            print(f"ERROR: {error}")
        print()
        if report.faithful:
            print("Converted in full. Every line that affects what this "
                  "trades was translated.")
        else:
            print("PARTIAL. This is not the strategy that was pasted, so a "
                  "backtest of it would describe something else.")

    if args.save:
        if not report.faithful:
            print("Not saved: only a faithful conversion is saved, because a "
                  "partial one in the library is indistinguishable from a "
                  "whole one later.", file=_sys.stderr)
            return 2
        from .strategy.storage import StrategyStore

        StrategyStore(_workspace(args)).save(report.spec)
        print(f"Saved '{report.spec.name}'.")
    return 0 if report.faithful else 2


def cmd_variants(args: argparse.Namespace) -> int:
    """Search one strategy's neighbourhood and price whatever wins.

    Exits 0 whether or not a better version was found: "nothing beat what you
    have" is a result, and a script that treats it as failure would retry the
    search until noise obliged.
    """
    from .finder.variants import search_variants

    spec = _resolve_spec(args)
    bars, data_name = _resolve_bars(args)
    report = search_variants(spec, bars, _config_for(spec, args.capital),
                             max_variants=args.max_variants)

    if args.json:
        print(json.dumps({
            "strategy": spec.name, "dataset": data_name,
            "tried": report.tried, "improved": report.improved,
            "headline": report.headline(),
            "baseline": {"trades": report.baseline.trades,
                         "per_trade": report.baseline.per_trade},
            "best": None if report.best is None else {
                "label": report.best.label,
                "trades": report.best.trades,
                "per_trade": report.best.per_trade,
                "excess_per_trade": report.best.excess_per_trade,
                "changes": report.best.changes,
            },
            "deflated": (report.deflated.to_dict()
                         if report.deflated is not None else None),
            "notes": report.notes,
            "spec": None if report.best is None else report.best.spec.to_dict(),
        }, indent=2))
        return 0

    print(f"{spec.name} on {data_name}, {len(bars):,} bars")
    print()
    for line in report.lines():
        print(line)

    if args.save and report.best is not None:
        from .strategy.storage import StrategyStore

        winner = report.best
        kept = winner.spec.copy(f"{spec.name} — {winner.label}")
        verdict = "survived" if report.improved else "did NOT survive"
        kept.description = (
            f"A variant of '{spec.name}' found by searching {report.tried} of "
            f"them.\nChange: {winner.label}.\nIt {verdict} being priced for "
            f"that search.")
        kept.tags = list(kept.tags) + ["variant"]
        StrategyStore(_workspace(args)).save(kept)
        print(f"\nSaved '{kept.name}'.")
    return 0


def cmd_combine(args: argparse.Namespace) -> int:
    """Merge several strategies into one and say what the merge decided.

    Everything the merge had to choose -- which settings were kept, which
    rules could not be joined, how much warm-up it costs -- is printed whether
    or not it is asked for.  A combined strategy that quietly inherits one
    author's stop loss is worse than no combining at all.
    """
    import sys as _sys

    from .strategy.combine import combine_strategies

    names = list(args.strategy or [])
    if len(names) < 2:
        print("Combining needs at least two strategies: give --strategy "
              "twice.", file=_sys.stderr)
        return 1
    specs = [_spec_named(args, n) for n in names]

    primary = 0
    if args.primary:
        matches = [i for i, s in enumerate(specs)
                   if args.primary.lower() in (s.name.lower(), s.id.lower())]
        if not matches:
            print(f"--primary '{args.primary}' is not one of the strategies "
                  f"being combined ({', '.join(s.name for s in specs)}).",
                  file=_sys.stderr)
            return 1
        primary = matches[0]

    report = combine_strategies(
        specs, mode=args.mode, exit_mode=args.exit_mode,
        name=args.name or "", primary=primary, threshold=args.threshold)

    if args.json:
        print(json.dumps({
            "name": report.spec.name, "mode": report.mode,
            "exit_mode": report.exit_mode, "threshold": report.threshold,
            "sources": report.sources, "notes": report.notes,
            "conflicts": report.conflicts, "shared": report.shared,
            "warnings": report.warnings, "spec": report.spec.to_dict(),
        }, indent=2))
        return 0

    print(report.summary())
    print()
    for line in report.spec.summary_lines():
        print(f"  {line}")
    print()
    for label, items in (("Shared", report.shared),
                         ("Conflict", report.conflicts),
                         ("Note", report.notes),
                         ("Warning", report.warnings)):
        for item in items:
            print(f"{label}: {item}")

    if args.save:
        from .strategy.storage import StrategyStore

        StrategyStore(_workspace(args)).save(report.spec)
        print(f"\nSaved '{report.spec.name}'.")
    if args.data:
        _run_combined(args, report)
    return 0


def _run_combined(args: argparse.Namespace, report) -> None:
    """Backtest the merged strategy, and each part, on the same bars.

    Printed side by side because the only honest way to read a combined
    result is against what the parts did on that same data -- and because
    ``any`` in particular does not add the parts up, whatever it looks like.
    """
    from .engine.backtester import Backtester

    bars, data_name = _resolve_bars(args)
    print(f"\nOn {data_name}, {len(bars):,} bars:")
    rows = [(s, _spec_named(args, s)) for s in (args.strategy or [])]
    rows.append((report.spec.name, report.spec))
    # A combined name is a list of its parts, so it can be far longer than
    # every other row; without a cap it pushes the numbers off the terminal.
    width = min(46, max(len(n) for n, _ in rows))
    for name, spec in rows:
        shown = name if len(name) <= width else name[:width - 1] + "\u2026"
        result = Backtester(bars, spec, _config_for(spec, args.capital)).run()
        metrics = result.metrics
        # `max_drawdown_pct` is already a percentage, not a fraction: the
        # metrics layer and every other display treat it as one.
        print(f"  {shown:<{width}}  {len(result.trades):6d} trades  "
              f"net {metrics.get('net_profit', float('nan')):12,.2f}  "
              f"Sharpe {metrics.get('sharpe_ratio', float('nan')):7.3f}  "
              f"max DD {metrics.get('max_drawdown_pct', float('nan')):7.2f}%")
    print("\nThese are backtests of this data only. A combined strategy that "
          "beats its parts here has not been shown to beat them anywhere "
          "else.")


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
    # Imported here rather than at module scope: the help text quotes these
    # defaults, and `cli --help` should not pay for loading the optimiser.
    from .data.continuous import Adjustment, DEFAULT_ROLL_DAYS, RollRule
    from .strategy.combine import COMBINE_MODES
    from .optimize.holdout import DEFAULT_REVEAL, RESEARCH_FRACTION

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
    # Not required, so `--style list` and `--template list` work on their own.
    # A search without it still stops immediately, with the same message.
    p.add_argument("--data", default="",
                   help="Dataset name, shipped dataset, or a path to a CSV")
    p.add_argument("--style", default="intraday",
                   help="scalp | intraday | swing | position, or 'list'")
    p.add_argument("--timeframe", default="", help="Override the bar size")
    p.add_argument("--side", default="both", choices=("both", "long", "short"))
    p.add_argument("--template", default="",
                   help="Comma-separated entry-rule families to search, or "
                        "'list' to see them. Default: all of them.")
    p.add_argument("--session", default="", metavar="START-END",
                   help="Trade only inside this window, in the instrument's "
                        "own timezone; 'none' for all hours. Fixed before the "
                        "search runs, never searched over.")
    p.add_argument("--weekdays", default="", metavar="0,1,2,3,4",
                   help="Weekdays to trade, 0 is Monday")
    p.add_argument("--stop", default="", metavar="1.0,1.5,2.0",
                   help="Stop distances to try, in multiples of ATR")
    p.add_argument("--target", default="", metavar="1.0,2.0",
                   help="Target distances to try, in multiples of the stop")
    # None rather than 0 for "not given": 0 is a real value a user may type,
    # and treating it as absent silently ran the search with the style's own
    # limit instead of refusing an impossible one.
    p.add_argument("--max-bars", type=int, default=None, dest="max_bars",
                   help="Hardest limit on how long a trade may run, in bars")
    p.add_argument("--min-trades", type=int, default=None, dest="min_trades",
                   help="Below this a result is treated as noise whatever it "
                        "says")
    p.add_argument("--top", type=int, default=5, help="How many to shortlist")
    p.add_argument("--draws", type=int, default=2000,
                   help="Draws for the sampled control")
    p.add_argument("--research", type=float, default=0.65,
                   help="Fraction of the data used to choose (rest is locked)")
    p.add_argument("--validate", choices=("quick", "standard", "full"),
                   default="standard",
                   help="How hard to check the shortlist. quick: the engine's "
                        "own backtest only. standard: adds the concentration "
                        "gate, a Monte Carlo resample and the mirror market. "
                        "full: adds walk-forward, which is much slower.")
    p.add_argument("--save", action="store_true",
                   help="Save the shortlist as strategies in the workspace")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser(
        "autosearch",
        help="Search every style and bar size this data supports, at once",
        description="Runs the whole grid -- every trading style, every bar "
                    "size the data can build, every entry-rule family, every "
                    "geometry, both sides -- and applies ONE multiplicity "
                    "correction across all of it. Correcting each search for "
                    "its own size would call a result significant several "
                    "times more often than it should. The consequence is that "
                    "searching harder makes every individual result harder to "
                    "believe, which is the point.")
    p.add_argument("--data", required=True)
    p.add_argument("--style", default="",
                   help="Comma-separated styles to include (default: all)")
    p.add_argument("--timeframe", default="",
                   help="Comma-separated bar sizes to include (default: every "
                        "one the data can build)")
    p.add_argument("--template", default="",
                   help="Comma-separated entry-rule families (default: all)")
    p.add_argument("--side", default="both", choices=("both", "long", "short"))
    p.add_argument("--alpha", type=float, default=0.10,
                   help="False-discovery rate for the pooled correction")
    p.add_argument("--draws", type=int, default=500,
                   help="Draws for the sampled control on the shortlist")
    p.add_argument("--research", type=float, default=0.65)
    p.add_argument("--validate", choices=("quick", "standard", "full"),
                   default="standard",
                   help="How hard to check whatever survives the correction. "
                        "The grid itself is always gated cheaply; this is what "
                        "the survivors then go through.")
    p.add_argument("--top", type=int, default=8,
                   help="How many survivors to detail")
    p.add_argument("--plan", action="store_true",
                   help="List the searches that would run, then stop")
    p.add_argument("--save", action="store_true",
                   help="Save the survivors as strategies in the workspace")
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_autosearch)

    p = sub.add_parser("indicators",
                       help="Rank indicators by what they predict")
    p.add_argument("--data", required=True)
    p.add_argument("--style", default="intraday",
                   help="scalp | intraday | swing | position, or 'list'")
    p.add_argument("--timeframe", default="")
    p.add_argument("--side", default="long", choices=("long", "short"),
                   help="Which side's trades to predict")
    p.add_argument("--top", type=int, default=14)
    p.add_argument("--interactions", type=int, default=0, metavar="N",
                   help="Also build combined features from the N best "
                        "parents, ranked on the research block alone. Every "
                        "pair is another test and none of them is another "
                        "fact, so the multiplicity correction gets harder for "
                        "every feature; the report states the effective "
                        "dimension so that cost is visible.")
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
        "continuous",
        help="Splice several futures contracts into one continuous series",
        description="A futures contract expires, so a long backtest needs "
                    "several spliced into one series. Where the join is put "
                    "and how the price gap across it is handled are modelling "
                    "decisions that change every number downstream, so both "
                    "are yours to make and the report states what each one "
                    "costs you.")
    p.add_argument("--contract", action="append", default=[], required=True,
                   metavar="LABEL=DATASET",
                   help="One delivery month, oldest first; repeat for each. "
                        "The dataset is any name or path --data accepts.")
    p.add_argument("--adjust", default=Adjustment.BACK_ADJUSTED.value,
                   choices=[a.value for a in Adjustment],
                   help="back_adjusted: shift older prices so returns across "
                        "each join are the ones a rolled position earned. "
                        "ratio: scale instead, keeping percentage returns and "
                        "positive prices. unadjusted: splice raw, so every "
                        "price is real and every join contains its roll gap.")
    p.add_argument("--roll", default=RollRule.VOLUME.value,
                   choices=[r.value for r in RollRule],
                   help="volume: roll where the next contract out-trades this "
                        "one. days_before_end: a fixed number of days early. "
                        "last_bar: on the contract's final bar, which "
                        "backtests the days nobody is trading it.")
    p.add_argument("--roll-days", type=int, default=DEFAULT_ROLL_DAYS,
                   dest="roll_days",
                   help="Days for --roll days_before_end, and the fallback "
                        "when a volume crossover never happens")
    p.add_argument("--save", default="", metavar="NAME",
                   help="Save the spliced series into the workspace")
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_continuous)

    p = sub.add_parser(
        "optimize", aliases=["optimise"],
        help="Sweep a grid on one block, then look at the other once",
        description="Rank every combination on the first part of the series, "
                    "fix the ranking, and only then measure the top few on the "
                    "part that was held back. The locked block is scored once, "
                    "after the choice is made, because a holdout that can "
                    "influence the choice is not a holdout.")
    p.add_argument("strategy")
    p.add_argument("--data", required=True)
    p.add_argument("--param", action="append", default=[],
                   metavar="NAME=START:STOP:STEP",
                   help="Parameter to sweep; repeat for more than one. "
                        "Omit to sweep every numeric parameter.")
    p.add_argument("--metric", default="net_profit",
                   help="What the research block is ranked by")
    p.add_argument("--research", type=float, default=RESEARCH_FRACTION,
                   help="Fraction of the series that chooses the parameters")
    p.add_argument("--reveal", type=int, default=DEFAULT_REVEAL,
                   help="How many ranked combinations are measured on the "
                        "locked block. Raising this spends the holdout: "
                        "revealing all of them and picking the best is "
                        "selecting on it with extra steps.")
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_optimise)

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

    p = sub.add_parser(
        "diagnose",
        help="Measure what a run rests on, and what to test next",
        description="Runs the strategy, then measures the result: whether it "
                    "beat random entries matched to its own timing, where the "
                    "money is made, how much of it is a handful of trades, "
                    "what it costs to trade, and whether it can be tuned at "
                    "all. Every finding carries the numbers behind it and "
                    "names an experiment; none of them predicts that a change "
                    "will help.")
    p.add_argument("strategy")
    p.add_argument("--data", required=True)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--draws", type=int, default=2000,
                   help="Random entry sets drawn for the matched control")
    p.add_argument("--no-control", action="store_true",
                   help="Skip the matched control, which is the slow part")
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser(
        "correlate",
        help="Measure how much of a set of strategies is really one bet",
        description="Runs each strategy on the same data and correlates their "
                    "returns, their time in the market and their entries. The "
                    "summary is the effective number of independent bets, "
                    "which is what five strategies at 0.8 correlation "
                    "actually amount to. A low correlation is not by itself a "
                    "reason to add a strategy.")
    p.add_argument("strategies", nargs="+",
                   help="Two or more saved or built-in strategy names")
    p.add_argument("--data", required=True)
    p.add_argument("--capital", type=float, default=100_000.0)
    p.add_argument("--unit", default="day", choices=("day", "week", "month"),
                   help="Calendar the returns are correlated on")
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_correlate)

    p = sub.add_parser("strategies", help="List strategies")
    p.set_defaults(func=cmd_strategies)

    p = sub.add_parser(
        "variants",
        help="Search a strategy's own neighbourhood for a better version")
    p.add_argument("strategy", help="Name of a saved or built-in strategy")
    p.add_argument("--data", required=True,
                   help="Dataset name, shipped dataset, or a path to a CSV")
    p.add_argument("--max-variants", type=int, default=400,
                   dest="max_variants",
                   help="Cap on how many variants to try. Trying more makes "
                        "the deflation stricter, not the result better.")
    p.add_argument("--capital", type=float, default=100_000.0,
                   help="Starting capital")
    p.add_argument("--save", action="store_true",
                   help="Save the winner as a new strategy, with how many "
                        "were tried recorded in its description")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.set_defaults(func=cmd_variants)

    p = sub.add_parser(
        "combine",
        help="Merge two or more strategies into one")
    p.add_argument("--strategy", action="append", required=True,
                   help="Name of a saved or built-in strategy. Give it twice "
                        "or more; the first is the primary unless --primary "
                        "says otherwise.")
    p.add_argument("--mode", default="all", choices=list(COMBINE_MODES),
                   help="How entry rules are joined: all (every strategy must "
                        "signal on the same bar), any (one is enough), or "
                        "majority (at least half agree). Default all.")
    p.add_argument("--exit-mode", default="any", dest="exit_mode",
                   choices=list(COMBINE_MODES),
                   help="How exit rules are joined. Default any, so a "
                        "position whose thesis has ended under one strategy "
                        "is closed rather than held on another's rule.")
    p.add_argument("--threshold", type=int, default=None,
                   help="Override how many strategies a majority needs")
    p.add_argument("--primary", default="",
                   help="Whose risk, exit, execution, session and cost "
                        "settings the result uses. Default the first.")
    p.add_argument("--name", default="", help="Name for the combined strategy")
    p.add_argument("--save", action="store_true",
                   help="Save the result into the workspace")
    p.add_argument("--data", default="",
                   help="Backtest the result and each part on this dataset")
    p.add_argument("--capital", type=float, default=100_000.0,
                   help="Starting capital for --data")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.set_defaults(func=cmd_combine)

    p = sub.add_parser(
        "research",
        help="Run the automated research loop: hypothesis, experiment, "
             "verdict, repeat")
    p.add_argument("--data", required=True,
                   help="Dataset name, shipped dataset, or a path to a CSV")
    p.add_argument("--style", default="intraday",
                   help="scalp | intraday | swing | position")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--validate", choices=("quick", "standard", "full"),
                   default="standard")
    p.add_argument("--draws", type=int, default=500)
    p.add_argument("--save", action="store_true",
                   help="Keep the run in the workspace's research folder")
    p.add_argument("--json", action="store_true")
    p.add_argument("--symbol", default="")
    p.set_defaults(func=cmd_research)

    p = sub.add_parser(
        "convert",
        help="Read a Pine Script or exported strategy and report what "
             "translated")
    p.add_argument("path", help="File to read, or - for standard input")
    p.add_argument("--save", action="store_true",
                   help="Save into the workspace, but only if the conversion "
                        "was faithful")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.set_defaults(func=cmd_convert)

    # Every command that reads a dataset can read its reflection instead. Added
    # in one place rather than in each parser so a new data command cannot
    # forget it; `mirror` is excluded because reflecting is the whole of what
    # it does.
    #
    # `choices` maps every alias to the SAME parser object, so a command with
    # an alias would be visited twice and argparse raises on the duplicate
    # option. Track the objects, not the names.
    seen: set[int] = set()
    for name, subparser in sub.choices.items():
        if name in ("mirror", "data", "import", "strategies", "convert",
                    "continuous"):
            continue
        if id(subparser) in seen:
            continue
        seen.add(id(subparser))
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
