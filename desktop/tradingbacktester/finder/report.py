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
    lines.extend(fit(f"   verdict: {finding.verdict}", width, hang=6))
    for concern in finding.concerns:
        lines.extend(fit(f"      - {concern}", width, hang=2))
    return lines
