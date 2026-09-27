"""Reporting a feature study and an anomaly scan as plain text."""

from __future__ import annotations

import textwrap

from ..core.textfmt import fit, row


def format_study(study, top: int = 14, width: int = 78) -> str:
    """The feature study, ranked, with the caveats beside the numbers."""
    rule = "-" * width
    out = [f"Indicator study — {study.symbol} {study.timeframe}, "
           f"{study.style.label}", rule]
    out.extend(fit(
        f"{study.bars:,} bars.  Ranked on {study.research_start} to "
        f"{study.research_end} ({study.research_bars:,} bars); locked block "
        f"to {study.holdout_end} ({study.holdout_bars:,} bars).", width))
    out.extend(fit(
        f"{study.tested} features, {study.independent} independent groups, "
        f"{study.significant} significant after correction.  "
        f"{study.elapsed:.1f}s.", width))
    out.extend(fit(
        f"Target: what a {study.style.label.lower()} trade opened on each bar "
        f"would have paid, costs included. Opened on EVERY bar it pays "
        f"{study.baseline:+,.2f} {study.currency} on average, which is the "
        f"line every decile below should be read against.", width))
    out.append("")

    ranked = study.top(top)
    if not any(f.research.significant for f in ranked):
        out.extend(fit("No feature predicts this target once the standard "
                       "errors are corrected for overlap and the count of "
                       "features is taken into account.", width))
        out.append("")
    for position, finding in enumerate(ranked, start=1):
        if not finding.research.significant:
            continue
        out.extend(fit(f"{position}. {finding.name}  "
                       f"[{finding.feature.family}]  — {finding.direction}",
                       width, hang=3))
        out.extend(fit(finding.feature.description, width, indent="   "))
        out.extend(fit(
            "   " + finding.research.describe(study.currency,
                                              study.cost_per_trade),
            width, hang=3))
        out.extend(fit(
            f"   deciles: bottom {finding.research.bottom_decile:+,.2f} → top "
            f"{finding.research.top_decile:+,.2f} {study.currency}/trade "
            f"(baseline {study.baseline:+,.2f}) over "
            f"{finding.research.observations:,} bars", width, hang=6))
        if finding.holdout is not None:
            out.extend(fit(
                f"   locked block: IC {finding.holdout.ic:+.4f} "
                f"(t={finding.holdout.t_stat:+.2f}) over "
                f"{finding.holdout.observations:,} bars", width, hang=6))
        out.extend(fit(f"   verdict: {finding.verdict}", width, hang=6))
        for concern in finding.concerns:
            out.extend(textwrap.wrap(concern, width, initial_indent="      - ",
                                     subsequent_indent="        "))
        out.append("")

    big = [c for c in study.clusters if len(c) > 1]
    if big:
        out.append("Features that measure the same thing:")
        for group in big[:8]:
            out.extend(textwrap.wrap(", ".join(group), width,
                                     initial_indent="   · ",
                                     subsequent_indent="     "))
        out.append("")

    out.append(rule)
    for note in study.notes:
        out.extend(textwrap.wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def format_anomalies(scan, width: int = 78) -> str:
    """The anomaly scan: what was unusual, and whether it was worth anything."""
    rule = "-" * width
    out = [f"Anomaly scan — {scan.symbol} {scan.timeframe}", rule]
    out.extend(fit(f"{scan.bars:,} bars, {scan.start} to {scan.end}.  "
                   f"{scan.elapsed:.1f}s.", width))
    out.append("")

    if scan.quality:
        out.append("DATA QUALITY")
        for issue in scan.quality:
            out.extend(textwrap.wrap(issue, width, initial_indent="   ",
                                     subsequent_indent="   "))
        out.append("")

    out.append("MARKET ANOMALIES")
    out.append(f"   {'event':<24} {'count':>7} {'share':>7} {'edge/trade':>11} "
               f"{'p':>6}  verdict")
    for finding in scan.findings:
        # The verdict is free text and the numbers are not: wrap the prose
        # under itself so a long verdict cannot push the columns out of line.
        out.extend(row(
            f"   {finding.label:<24} {finding.count:>7,} "
            f"{finding.share * 100:>6.2f}% {finding.excess:>+11,.2f} "
            f"{finding.p_value:>6.3f}  ", finding.verdict, width))
    out.append("")

    tradeable = [f for f in scan.findings if f.verdict.startswith("worth")]
    if tradeable:
        out.append("Worth a closer look:")
        for finding in tradeable:
            out.extend(textwrap.wrap(finding.detail, width,
                                     initial_indent="   · ",
                                     subsequent_indent="     "))
        out.append("")

    out.append(rule)
    for note in scan.notes:
        out.extend(textwrap.wrap(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
