"""CSV exports of a finished run: trades, equity curve and metrics.

Three things matter here and none of them is exciting.

*The file must open cleanly in Excel.*  Every file is written through the
:mod:`csv` module with ``newline=""`` so the module's own ``\\r\\n`` terminator is
not translated a second time by the text layer -- the classic cause of a
spreadsheet with a blank row between every row of data.

*The file must be self-describing.*  A CSV that has been emailed twice and
renamed once still has to say which strategy, instrument, timeframe, date range
and cost model produced it, so every export starts with ``#`` comment lines
carrying exactly that.  Spreadsheets show them as ordinary rows; humans read
them; ``pandas.read_csv(..., comment="#")`` skips them.

*Timestamps must be unambiguous.*  Each time column is written twice: once in
ISO 8601 UTC, which is what another program should parse, and once in the
instrument's own timezone, which is what a trader recognises as "the 09:31 bar".

The helpers :func:`describe_cost_model`, :func:`run_header_fields` and
:func:`iso_timestamps` are shared with the HTML and PDF reports so that all
three describe the same run in the same words.
"""

from __future__ import annotations

import csv
import logging
import math
from datetime import datetime, timezone as _timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from ..core.errors import ReportError
from ..core.types import CommissionMode, CostModel, SlippageMode, SpreadMode
from ..engine.results import BacktestResult

log = logging.getLogger(__name__)

#: Written at the end of every comment header so a stray file is traceable.
_GENERATOR = "TradingBacktester"

#: Columns of the trades export.  The first block mirrors the trade table in the
#: application one for one; the identity columns after it exist so that a
#: scaled-out position can be reassembled from the file (``parent_id``).  The
#: row-number column is called ``num`` rather than ``#`` on purpose: a header
#: beginning with a hash is eaten by ``pandas.read_csv(..., comment="#")``.
TRADE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("num", "num", "index"),
    ("id", "trade_id", "int"),
    ("entry_ts", "entry_time_utc", "iso_utc"),
    ("entry_ts", "entry_time_local", "iso_local"),
    ("exit_ts", "exit_time_utc", "iso_utc"),
    ("exit_ts", "exit_time_local", "iso_local"),
    ("side", "side", "side"),
    ("quantity", "quantity", "qty"),
    ("entry_price", "entry_price", "price"),
    ("exit_price", "exit_price", "price"),
    ("stop_loss", "stop_loss", "price"),
    ("take_profit", "take_profit", "price"),
    ("gross_pnl", "gross_pnl", "money"),
    ("commission", "commission", "money"),
    ("slippage_cost", "slippage_cost", "money"),
    ("spread_cost", "spread_cost", "money"),
    ("net_pnl", "net_pnl", "money"),
    ("return_pct", "return_pct", "pct"),
    ("r_multiple", "r_multiple", "ratio"),
    ("bars_held", "bars_held", "int"),
    ("duration_seconds", "duration_seconds", "int"),
    ("mae", "mae_points", "price"),
    ("mfe", "mfe_points", "price"),
    ("exit_reason", "exit_reason", "reason"),
    ("equity_at_entry", "equity_at_entry", "money"),
    ("equity_after", "equity_after", "money"),
    ("entry_bar", "entry_bar", "int"),
    ("exit_bar", "exit_bar", "int"),
    ("parent_id", "parent_trade_id", "int"),
    ("tag", "tag", "text"),
)

#: Columns of the equity export.
EQUITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("bar", "bar_index"),
    ("ts_utc", "timestamp_utc"),
    ("ts_local", "timestamp_local"),
    ("equity", "equity"),
    ("balance", "balance"),
    ("peak", "peak_equity"),
    ("drawdown", "drawdown_cash"),
    ("drawdown_pct", "drawdown_fraction_of_peak"),
    ("exposure", "position_units"),
)


# --------------------------------------------------------------------------
# Shared description helpers
# --------------------------------------------------------------------------

def describe_cost_model(costs: CostModel | None) -> str:
    """One line describing what trading was charged, in the user's own units.

    Shared by all three report formats: a reader comparing a CSV against a PDF
    should not have to work out whether "0.1" meant dollars or percent.
    """
    if costs is None:
        return "no cost model recorded"
    parts: list[str] = []

    value = float(costs.commission_value)
    if value > 0:
        if costs.commission_mode is CommissionMode.PER_UNIT:
            parts.append(f"commission {value:g} per unit per side")
        elif costs.commission_mode is CommissionMode.PER_TRADE:
            parts.append(f"commission {value:g} flat per side")
        else:
            parts.append(f"commission {value:g}% of notional per side")
        if float(costs.min_commission) > 0:
            parts.append(f"minimum commission {float(costs.min_commission):g}")
    else:
        parts.append("no commission")

    spread = float(costs.spread_points)
    if costs.spread_mode is SpreadMode.NONE or spread <= 0:
        parts.append("no spread")
    elif costs.spread_mode is SpreadMode.HALF_EACH_SIDE:
        parts.append(f"spread {spread:g} points, half charged on each side")
    else:
        parts.append(f"spread {spread:g} points, charged in full on entry")

    slip = float(costs.slippage_value)
    if costs.slippage_mode is SlippageMode.NONE or slip <= 0:
        parts.append("no slippage")
    elif costs.slippage_mode is SlippageMode.FIXED_POINTS:
        parts.append(f"slippage {slip:g} points per side")
    elif costs.slippage_mode is SlippageMode.PERCENT:
        parts.append(f"slippage {slip:g}% of price per side")
    else:
        parts.append(f"slippage {slip:g} x ATR per side")

    return "; ".join(parts)


def describe_execution(result: BacktestResult) -> str:
    """One line describing when a signal became a fill and how ties were broken."""
    execution = getattr(result.config, "execution", None)
    if execution is None:
        return "execution settings not recorded"
    timing = ("signal on the close of a bar fills at the open of the next bar"
              if getattr(execution.signal_execution, "value", "") == "next_open"
              else "signal fills at the close of the same bar (optimistic)")
    priority = {
        "pessimistic": "when a bar covers both stop and target the stop is assumed first",
        "optimistic": "when a bar covers both stop and target the target is assumed first",
        "ohlc_path": "when a bar covers both, an open-high-low-close path decides which came first",
    }.get(getattr(execution.intrabar_priority, "value", ""), "intrabar priority not recorded")
    return f"{timing}; {priority}"


def instrument_timezone(result: BacktestResult) -> str:
    """The instrument's timezone, or UTC when the run carries no instrument.

    Falls back rather than raising: a report is not worth refusing over a
    timezone name, and the column header says which zone was used.
    """
    bars = getattr(result, "bars", None)
    instrument = getattr(bars, "instrument", None) if bars is not None else None
    name = str(getattr(instrument, "timezone", "") or "").strip()
    if not name:
        return "UTC"
    try:
        import pandas as pd

        pd.Timestamp(0, tz="UTC").tz_convert(name)
    except Exception:  # unknown zone in a hand-edited instruments.json
        log.warning("Unknown instrument timezone %r; reporting in UTC.", name)
        return "UTC"
    return name


def price_decimals(result: BacktestResult) -> int:
    bars = getattr(result, "bars", None)
    instrument = getattr(bars, "instrument", None) if bars is not None else None
    try:
        return max(0, int(getattr(instrument, "price_decimals", 2)))
    except (TypeError, ValueError):
        return 2


def currency_symbol(result: BacktestResult) -> str:
    """The instrument's currency code, used as a prefix in the visual reports."""
    bars = getattr(result, "bars", None)
    instrument = getattr(bars, "instrument", None) if bars is not None else None
    return str(getattr(instrument, "currency", "") or "")


def run_range_ts(result: BacktestResult) -> tuple[int | None, int | None]:
    """First and last timestamp actually simulated, in UTC nanoseconds."""
    bars = getattr(result, "bars", None)
    if bars is not None and len(getattr(bars, "ts", ())) > 0:
        return int(bars.ts[0]), int(bars.ts[-1])
    curves = result.curves
    if curves is not None and len(curves) > 0:
        return int(curves.ts[0]), int(curves.ts[-1])
    if result.trades:
        return int(result.trades[0].entry_ts), int(result.trades[-1].exit_ts)
    return None, None


def run_header_fields(result: BacktestResult) -> list[tuple[str, str]]:
    """Label/value pairs identifying the run, used by all three report formats."""
    tz = instrument_timezone(result)
    start, end = run_range_ts(result)
    if start is None or end is None:
        span = "no bars"
    else:
        span = f"{_stamp(start, tz)} to {_stamp(end, tz)} ({tz})"
    bars = getattr(result, "bars", None)
    bar_count = len(bars) if bars is not None else int(result.bars_processed or 0)
    fields: list[tuple[str, str]] = [
        ("Strategy", result.strategy_name or "(unnamed strategy)"),
        ("Run label", result.label or "(unlabelled run)"),
        ("Instrument", result.instrument_symbol or "(unknown instrument)"),
        ("Timeframe", result.timeframe_label or "(unknown timeframe)"),
        ("Date range", span),
        ("Bars", f"{bar_count:,}"),
        ("Trades", f"{result.trade_count:,}"),
        ("Starting capital", f"{float(result.config.starting_capital):,.2f}"),
        ("Cost model", describe_cost_model(getattr(result.config, "costs", None))),
        ("Order timing", describe_execution(result)),
        ("Run at", result.created_at or _now_iso()),
        ("Generated by", f"{_GENERATOR} {_app_version()}"),
    ]
    if result.param_values:
        fields.append(("Parameters", ", ".join(
            f"{k}={v}" for k, v in sorted(result.param_values.items()))))
    return fields


def iso_timestamps(ts: Sequence[int] | np.ndarray, tz: str) -> tuple[list[str], list[str]]:
    """Vectorised ISO 8601 formatting: ``(utc_strings, local_strings)``.

    Formatting timestamps one at a time costs seconds on a hundred thousand
    trades, so the whole column is converted once through pandas and the UTC
    offset is given its ISO colon by a single pass over the strings.
    """
    import pandas as pd

    arr = np.asarray(ts, dtype="int64")
    if arr.size == 0:
        return [], []
    idx = pd.DatetimeIndex(pd.to_datetime(arr, utc=True))
    utc = list(idx.strftime("%Y-%m-%dT%H:%M:%SZ"))
    try:
        local_idx = idx.tz_convert(tz)
    except Exception:
        local_idx = idx
    raw = list(local_idx.strftime("%Y-%m-%dT%H:%M:%S%z"))
    local = [f"{s[:-2]}:{s[-2:]}" if len(s) > 5 else s for s in raw]
    return utc, local


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------

def export_trades_csv(result: BacktestResult, path: str | Path) -> str:
    """Write every closed trade to ``path``; returns the path written."""
    trades = list(result.trades)
    tz = instrument_timezone(result)
    decimals = price_decimals(result)
    entry_utc, entry_local = iso_timestamps([t.entry_ts for t in trades], tz)
    exit_utc, exit_local = iso_timestamps([t.exit_ts for t in trades], tz)

    rows: list[list[str]] = []
    for i, trade in enumerate(trades):
        row: list[str] = []
        for key, _header, kind in TRADE_COLUMNS:
            if kind == "index":
                row.append(str(i + 1))
            elif kind == "iso_utc":
                row.append(entry_utc[i] if key == "entry_ts" else exit_utc[i])
            elif kind == "iso_local":
                row.append(entry_local[i] if key == "entry_ts" else exit_local[i])
            else:
                row.append(_cell(getattr(trade, key, None), kind, decimals))
        rows.append(row)

    header = [h for _k, h, _kind in TRADE_COLUMNS]
    notes = [f"Times are given twice: UTC, and the instrument timezone {tz}.",
             "Costs are positive numbers representing cash paid; net_pnl already "
             "has them deducted.",
             "return_pct is the trade's net P&L as a percent of account equity at "
             "its entry.",
             "r_multiple is blank when the trade had no initial stop to measure risk "
             "against."]
    _write(path, result, header, rows, notes, "Trades")
    log.info("Exported %d trades to %s", len(rows), path)
    return str(path)


def export_equity_csv(result: BacktestResult, path: str | Path) -> str:
    """Write the per-bar equity, balance and drawdown series to ``path``."""
    curves = result.curves
    if curves is None or len(curves) == 0:
        raise ReportError(
            "This run has no equity curve to export.",
            detail="BacktestResult.curves is empty; run a backtest before exporting.")

    tz = instrument_timezone(result)
    utc, local = iso_timestamps(curves.ts, tz)
    equity = np.asarray(curves.equity, dtype="float64")
    balance = np.asarray(curves.balance, dtype="float64")
    peak = np.asarray(curves.peak, dtype="float64")
    drawdown = np.asarray(curves.drawdown, dtype="float64")
    drawdown_pct = np.asarray(curves.drawdown_pct, dtype="float64")
    exposure = np.asarray(curves.exposure, dtype="float64")

    rows: list[list[str]] = []
    for i in range(len(curves)):
        rows.append([
            str(i),
            utc[i],
            local[i],
            _money(equity[i]),
            _money(balance[i]),
            _money(peak[i]),
            _money(drawdown[i]),
            _fixed(drawdown_pct[i], 6),
            _fixed(exposure[i], 6),
        ])

    header = [h for _k, h in EQUITY_COLUMNS]
    notes = ["equity is balance plus the mark-to-market value of any open position.",
             "drawdown_cash is equity minus its running peak and is never positive.",
             "drawdown_fraction_of_peak is that same fall expressed as a fraction of "
             "the peak: -0.05 means 5 percent below the previous high.",
             "position_units is the signed size held on that bar; it is what the "
             "exposure ribbon draws."]
    _write(path, result, header, rows, notes, "Equity curve")
    log.info("Exported %d equity rows to %s", len(rows), path)
    return str(path)


def export_metrics_csv(result: BacktestResult, path: str | Path) -> str:
    """Write the metric dictionary as ``metric, value, reliability, note``.

    Nested structures are flattened rather than dropped: the exit-reason
    breakdown becomes ``exit_reason.stop_loss.count`` and so on, so nothing that
    the statistics panel shows is missing from the file.
    """
    metrics: dict[str, Any] = dict(result.metrics or {})
    reliability: dict[str, str] = dict(metrics.pop("reliability", {}) or {})
    notes: dict[str, str] = dict(metrics.pop("reliability_notes", {}) or {})
    breakdown = metrics.pop("exit_reason_breakdown", {}) or {}

    rows: list[list[str]] = []
    for key in sorted(metrics):
        value = metrics[key]
        if isinstance(value, dict):
            for sub in sorted(value):
                rows.append([f"{key}.{sub}", _scalar(value[sub]), "", ""])
            continue
        if isinstance(value, (list, tuple, np.ndarray)):
            rows.append([key, "; ".join(_scalar(v) for v in list(value)[:50]), "", ""])
            continue
        rows.append([key, _scalar(value),
                     str(reliability.get(key, "")), str(notes.get(key, ""))])

    for reason in sorted(breakdown):
        info = breakdown[reason]
        if isinstance(info, dict):
            for sub in sorted(info):
                rows.append([f"exit_reason.{reason}.{sub}", _scalar(info[sub]), "", ""])
        else:
            rows.append([f"exit_reason.{reason}", _scalar(info), "", ""])

    for i, warning in enumerate(result.warnings or (), start=1):
        rows.append([f"warning.{i}", str(warning), "", ""])

    if not rows:
        raise ReportError(
            "This run has no metrics to export.",
            detail="BacktestResult.metrics is empty; the analytics step did not run.")

    notes_block = ["reliability is 'ok', 'low_sample' or 'unavailable'. Anything not "
                   "marked 'ok' should not be read as a number you can act on.",
                   "Blank values are metrics that could not be computed, usually "
                   "because their denominator was zero."]
    _write(path, result, ["metric", "value", "reliability", "note"], rows,
           notes_block, "Metrics")
    log.info("Exported %d metric rows to %s", len(rows), path)
    return str(path)


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------

def _write(path: str | Path, result: BacktestResult, header: Sequence[str],
           rows: Iterable[Sequence[str]], notes: Sequence[str], kind: str) -> None:
    """Write one CSV with its comment header, turning any OS error into a
    :class:`ReportError` the interface can show."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # newline="" is required: the csv module writes its own \r\n and the text
        # layer must not translate it again, or Excel shows a blank row between
        # every pair of records.
        with target.open("w", newline="", encoding="utf-8-sig") as handle:
            handle.write(f"# {_GENERATOR} — {kind} export\r\n")
            for label, value in run_header_fields(result):
                handle.write(f"# {label}: {_comment_safe(value)}\r\n")
            for note in notes:
                handle.write(f"# Note: {_comment_safe(note)}\r\n")
            writer = csv.writer(handle)
            writer.writerow(list(header))
            writer.writerows([list(r) for r in rows])
    except OSError as exc:
        raise ReportError(
            f"The file could not be written to {target}. Check that the folder "
            f"exists and that you have permission to write there.",
            detail=f"{type(exc).__name__}: {exc}") from exc


def _comment_safe(text: str) -> str:
    """Keep a comment on one line; a newline inside would fake a data row."""
    return " ".join(str(text).split())


def _cell(value: Any, kind: str, decimals: int) -> str:
    if value is None:
        return ""
    if kind == "side":
        return str(getattr(value, "value", value))
    if kind == "reason":
        return str(getattr(value, "value", value))
    if kind == "text":
        return str(value)
    if kind == "int":
        try:
            return str(int(value))
        except (TypeError, ValueError):
            return ""
    if kind == "price":
        return _fixed(value, decimals)
    if kind == "qty":
        return _fixed(value, 6)
    if kind == "money":
        return _money(value)
    if kind == "pct":
        return _fixed(value, 4)
    if kind == "ratio":
        return _fixed(value, 4)
    return str(value)


def _money(value: Any) -> str:
    return _fixed(value, 2)


def _fixed(value: Any, decimals: int) -> str:
    """A plain machine-readable number: no thousands separator, blank for NaN."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if math.isnan(v):
        return ""
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    return f"{v:.{decimals}f}"


def _scalar(value: Any) -> str:
    """Format a metric value for the metrics file."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return _fixed(value, 6)
    return _comment_safe(str(value))


def _stamp(ts_ns: int, tz: str) -> str:
    import pandas as pd

    stamp = pd.Timestamp(int(ts_ns), tz="UTC")
    try:
        stamp = stamp.tz_convert(tz)
    except Exception:
        pass
    return stamp.strftime("%Y-%m-%d %H:%M")


def _now_iso() -> str:
    return datetime.now(_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _app_version() -> str:
    from ..config import APP_VERSION

    return str(APP_VERSION)


__all__ = ["export_trades_csv", "export_equity_csv", "export_metrics_csv",
           "describe_cost_model", "describe_execution", "run_header_fields",
           "iso_timestamps", "instrument_timezone", "price_decimals",
           "currency_symbol", "run_range_ts", "TRADE_COLUMNS", "EQUITY_COLUMNS"]
