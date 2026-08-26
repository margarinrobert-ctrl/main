"""Turning a search into something a person can read and act on.

The hard part of reporting a strategy search is not the table, it is refusing
to bury the caveats under it. A number like "+$412 per trade" is meaningless
without the multiplicity that produced it, the control it was measured
against, and whether the locked block agreed -- so those appear beside every
row rather than in a footnote.
"""

from __future__ import annotations

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
    out.append(f"{report.bars:,} bars.  Research {report.research_start} to "
               f"{report.research_end} ({report.research_bars:,} bars); "
               f"locked {report.research_end} to {report.holdout_end} "
               f"({report.holdout_bars:,} bars).")
    out.append(f"{report.combinations:,} combinations tried, {report.tested:,} "
               f"had enough trades to score.  {report.elapsed:.1f}s.")
    out.append(f"Geometry: {report.style.describe()}")
    out.append("")

    if not report.shortlist:
        out.append("Nothing survived. See the notes below.")
    for position, finding in enumerate(report.shortlist, start=1):
        out.append(f"{position}. {finding.label}")
        out.extend(_finding_lines(finding, currency))
        out.append("")

    out.append(rule)
    for note in report.notes:
        out.extend(_wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _finding_lines(finding: Finding, currency: str) -> list[str]:
    template = TEMPLATES_BY_KEY[finding.candidate.template]
    research = finding.research
    holdout = finding.holdout or {}
    lines = [f"   {template.describe(finding.candidate.side)}"]
    lines.append(
        f"   research: {int(research['trades']):,} trades, "
        f"{research['win_rate'] * 100:.1f}% won, "
        f"{research['per_trade']:+,.2f} {currency}/trade, "
        f"net {research['net']:+,.0f} {currency}, "
        f"profit factor {research['profit_factor']:.2f}")
    lines.append(
        f"   exits: {research['stops'] * 100:.0f}% stop, "
        f"{research['targets'] * 100:.0f}% target, "
        f"{research['times'] * 100:.0f}% time, "
        f"hold {research.get('median_bars', 0.0):.0f} bars median, "
        f"{research['avg_bars']:.1f} mean")
    lines.append(f"   control: {finding.control.describe(currency)}")
    if finding.sampled is not None:
        lines.append(f"            {finding.sampled.describe(currency)}")
    if finding.neighbourhood is not None:
        n = finding.neighbourhood
        lines.append(
            f"   neighbourhood: {n.positive}/{n.tested} nearby settings also "
            f"beat their control (median {n.median_excess:+,.2f} {currency})")
    if holdout:
        excess = (finding.holdout_control.excess_per_trade
                  if finding.holdout_control else 0.0)
        lines.append(
            f"   LOCKED BLOCK: {int(holdout['trades']):,} trades, "
            f"{holdout['win_rate'] * 100:.1f}% won, "
            f"{holdout['per_trade']:+,.2f} {currency}/trade, "
            f"excess {excess:+,.2f} {currency}")
    lines.append(f"   verdict: {finding.verdict}")
    for concern in finding.concerns:
        lines.extend(_wrap(f"      - {concern}", 78, hang=8))
    return lines


def _wrap(text: str, width: int, hang: int = 0) -> list[str]:
    import textwrap

    return textwrap.wrap(text, width=width,
                         subsequent_indent=" " * hang) or [""]
