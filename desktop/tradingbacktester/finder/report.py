"""Turning a search into something a person can read and act on.

The hard part of reporting a strategy search is not the table, it is refusing
to bury the caveats under it. A number like "+$412 per trade" is meaningless
without the multiplicity that produced it, the control it was measured
against, and whether the locked block agreed -- so those appear beside every
row rather than in a footnote.
"""

from __future__ import annotations

from ..core.textfmt import fit
from .search import FinderReport, Finding
from .candidates import TEMPLATES_BY_KEY


def format_report(report: FinderReport, currency: str = "USD",
                  width: int = 78) -> str:
    """The whole search as plain text, suitable for a terminal or a log."""
    rule = "-" * width
    out: list[str] = []
    out.append(f"Strategy search — {report.symbol} {report.timeframe}, "
               f"{report.style.label}")
    out.append(rule)
    out.extend(fit(
        f"{report.bars:,} bars.  Research {report.research_start} to "
        f"{report.research_end} ({report.research_bars:,} bars); "
        f"locked {report.research_end} to {report.holdout_end} "
        f"({report.holdout_bars:,} bars).", width))
    out.extend(fit(
        f"{report.combinations:,} combinations tried, {report.tested:,} "
        f"had enough trades to score.  {report.elapsed:.1f}s.", width))
    out.extend(fit(f"Geometry: {report.style.describe()}", width, hang=10))
    if report.overfitting is not None and report.overfitting.ran:
        # Before the rows, not after them: this measures whether picking a
        # winner from this search means anything, so it is the sentence that
        # decides how to read every row below it.
        # Not str.capitalize(): it lower-cases everything after the first
        # letter, which turned the rest of the sentence into mush.
        sentence = report.overfitting.describe()
        out.extend(fit(sentence[:1].upper() + sentence[1:], width))
    out.append("")

    if not report.shortlist:
        out.append("Nothing survived. See the notes below.")
    for position, finding in enumerate(report.shortlist, start=1):
        out.extend(fit(f"{position}. {finding.label}", width, hang=3))
        out.extend(_finding_lines(finding, currency, width))
        out.append("")

    out.append(rule)
    for note in report.notes:
        out.extend(fit(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _finding_lines(finding: Finding, currency: str,
                   width: int = 78) -> list[str]:
    template = TEMPLATES_BY_KEY[finding.candidate.template]
    research = finding.research
    holdout = finding.holdout or {}
    # Continuations hang under the label rather than under the first number, so
    # a wrapped row still reads as one row.
    lines = fit(f"   {template.describe(finding.candidate.side)}", width, hang=3)
    lines.extend(fit(
        f"   research: {int(research['trades']):,} trades, "
        f"{research['win_rate'] * 100:.1f}% won, "
        f"{research['per_trade']:+,.2f} {currency}/trade, "
        f"net {research['net']:+,.0f} {currency}, "
        f"profit factor {research['profit_factor']:.2f}", width, hang=6))
    lines.extend(fit(
        f"   exits: {research['stops'] * 100:.0f}% stop, "
        f"{research['targets'] * 100:.0f}% target, "
        f"{research['times'] * 100:.0f}% time, "
        f"hold {research.get('median_bars', 0.0):.0f} bars median, "
        f"{research['avg_bars']:.1f} mean", width, hang=6))
    lines.extend(fit(f"   control: {finding.control.describe(currency)}",
                     width, hang=6))
    if finding.sampled is not None:
        lines.extend(fit(f"            {finding.sampled.describe(currency)}",
                         width, hang=6))
    if finding.deflated is not None:
        lines.extend(fit(f"   deflated Sharpe: {finding.deflated.describe()}",
                         width, hang=6))
    if finding.neighbourhood is not None:
        n = finding.neighbourhood
        lines.extend(fit(
            f"   neighbourhood: {n.positive}/{n.tested} nearby settings also "
            f"beat their control (median {n.median_excess:+,.2f} {currency})",
            width, hang=6))
    if holdout:
        excess = (finding.holdout_control.excess_per_trade
                  if finding.holdout_control else 0.0)
        lines.extend(fit(
            f"   LOCKED BLOCK: {int(holdout['trades']):,} trades, "
            f"{holdout['win_rate'] * 100:.1f}% won, "
            f"{holdout['per_trade']:+,.2f} {currency}/trade, "
            f"excess {excess:+,.2f} {currency}", width, hang=6))
    lines.extend(_engine_lines(finding, currency, width))
    lines.extend(_robustness_lines(finding, width))
    lines.extend(fit(f"   verdict: {finding.verdict}", width, hang=6))
    for concern in finding.concerns:
        lines.extend(fit(f"      - {concern}", width, hang=2))
    return lines


#: Rows of the engine table: metric key, label, and how to render it.
#: "money" takes the currency, "ratio" two decimals, "pct" a percentage,
#: "count" an integer, "duration" seconds turned into something readable.
_ENGINE_ROWS: tuple[tuple[str, str, str], ...] = (
    ("total_trades", "Trades", "count"),
    ("net_profit", "Net profit", "money"),
    ("profit_factor", "Profit factor", "ratio"),
    ("win_rate", "Win rate", "pct"),
    ("avg_win", "Average win", "money"),
    ("avg_loss", "Average loss", "money"),
    ("expectancy", "Expectancy", "money"),
    ("max_drawdown", "Max drawdown", "cost"),
    ("max_drawdown_pct", "Max drawdown", "pct"),
    ("sharpe_ratio", "Sharpe", "ratio"),
    ("sortino_ratio", "Sortino", "ratio"),
    ("calmar_ratio", "Calmar", "ratio"),
    ("recovery_factor", "Recovery factor", "ratio"),
    ("annual_return_pct", "Annualised return", "pct"),
    ("max_consecutive_wins", "Longest winning run", "count"),
    ("max_consecutive_losses", "Longest losing run", "count"),
    ("avg_trade_duration_seconds", "Average duration", "duration"),
    ("exposure_pct", "Exposure", "pct"),
    ("total_commission", "Commission", "cost"),
    ("total_slippage", "Slippage", "cost"),
    ("total_spread_cost", "Spread", "cost"),
    ("total_costs", "Total costs", "cost"),
)


def _cell(value, kind: str, currency: str) -> str:
    """One metric, rendered, or a dash when the engine did not produce it."""
    import math

    if value is None or isinstance(value, bool):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(number):
        return "inf" if number > 0 else "-inf" if number < 0 else "—"
    if kind == "count":
        return f"{int(round(number)):,}"
    if kind == "pct":
        return f"{number:.1f}%"
    if kind == "ratio":
        return f"{number:.2f}"
    if kind == "cost":
        # A drawdown or a commission is a magnitude. Rendering it "+904.37"
        # puts a profit sign on a loss, which is the one place a reader must
        # not be nudged.
        return f"{abs(number):,.2f} {currency}"
    if kind == "duration":
        seconds = int(round(number))
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m"
        if seconds < 86400:
            return f"{seconds / 3600:.1f}h"
        return f"{seconds / 86400:.1f}d"
    return f"{number:+,.2f} {currency}"


def _engine_lines(finding: Finding, currency: str, width: int) -> list[str]:
    """The engine's own measurement of this rule, in-sample beside locked.

    Two columns, never one.  A single blended figure is how a rule chosen on
    one block gets described as profitable; keeping them apart makes the decay
    between them the first thing a reader sees.
    """
    confirmation = getattr(finding, "confirmation", None)
    if confirmation is None:
        return fit("   engine: this rule was not re-run through the engine, so "
                   "the figures above come from the search's own fast path and "
                   "nothing has independently confirmed them.", width, hang=6)

    lines = ["   engine backtest (research | locked):"]
    if not confirmation.research.ran:
        lines.extend(fit(f"      the engine could not run it: "
                         f"{confirmation.research.error}", width, hang=6))
        return lines

    research = confirmation.research.metrics
    holdout = confirmation.holdout.metrics if confirmation.holdout.ran else {}
    label_width = max(len(label) for _k, label, _f in _ENGINE_ROWS)
    for key, label, kind in _ENGINE_ROWS:
        left = _cell(research.get(key), kind, currency)
        right = (_cell(holdout.get(key), kind, currency) if holdout
                 else "not run")
        lines.append(f"      {label:<{label_width}}  {left:>18}  {right:>18}")
    if confirmation.holdout.ran and confirmation.holdout.trades == 0:
        lines.extend(fit("      The locked column is empty because the rule "
                         "took no trades there.", width, hang=6))
    for note in confirmation.notes:
        lines.extend(fit(f"      {note}", width, hang=6))
    return lines


def _robustness_lines(finding: Finding, width: int = 78) -> list[str]:
    """The multi-dimensional score, blockers first.

    Blockers come before the number and the number is withheld when one fired,
    because a score printed beside a disqualifying reason is a score someone
    will quote without the reason.
    """
    score = getattr(finding, "robustness", None)
    if score is None:
        return []
    if score.blocked:
        lines = ["   robustness: DISQUALIFIED — not scored."]
        for blocker in score.blockers:
            lines.extend(fit(f"      - {blocker}", width, hang=8))
        return lines

    total = score.total
    headline = ("unmeasured" if total != total else f"{total:.0f}/100")
    lines = [f"   robustness: {headline} — {score.grade} "
             f"({len(score.measured)} of {len(score.dimensions)} dimensions)"]
    label_width = max((len(d.label) for d in score.dimensions), default=0)
    for dimension in score.dimensions:
        mark = "  n/a" if not dimension.applicable else f"{dimension.score:5.2f}"
        lines.extend(fit(
            f"      {mark}  {dimension.label:<{label_width}}  {dimension.detail}",
            width, hang=8 + label_width + 9))
    for note in score.notes:
        lines.extend(fit(f"      {note}", width, hang=6))
    return lines
