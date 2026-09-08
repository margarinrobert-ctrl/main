"""The research loop as plain text.

Failures are printed, not summarised away.  A loop that lists only what it
found reads like a machine that finds things; the experiments that came back
empty are what tell you the ground has been covered.
"""

from __future__ import annotations

import math
from typing import Any

from ..core.textfmt import fit


def format_loop(report: Any, currency: str = "USD", width: int = 78) -> str:
    """The whole loop, suitable for a terminal or a log."""
    rule = "-" * width
    out: list[str] = []
    out.append(f"Research loop — {report.symbol}, {report.style}")
    out.append(rule)
    out.extend(fit(
        f"{len(report.experiments)} experiments over "
        f"{report.total_combinations:,} rule-and-geometry combinations in "
        f"{report.elapsed:.1f}s.", width))
    out.append("")

    for index, experiment in enumerate(report.experiments, start=1):
        mark = "FOUND" if experiment.worked else "     "
        out.extend(fit(f"{mark} {index}. {experiment.hypothesis.idea}",
                       width, hang=7))
        if experiment.hypothesis.rationale:
            out.extend(fit(f"       why: {experiment.hypothesis.rationale}",
                           width, hang=12))
        if experiment.error:
            out.extend(fit(f"       could not be tested: {experiment.error}",
                           width, hang=12))
        else:
            out.extend(fit(
                f"       {experiment.combinations:,} combinations, "
                f"{experiment.tested:,} scorable, "
                f"{experiment.shortlisted} shortlisted — {experiment.verdict}",
                width, hang=12))
        out.append("")

    survivors = report.survivors
    out.append(rule)
    if survivors:
        out.append("Ranked by robustness, never by return:")
        out.append("")
        for position, finding in enumerate(survivors, start=1):
            score = finding.robustness.total
            headline = ("unmeasured" if not math.isfinite(score)
                        else f"{score:.0f}/100")
            out.extend(fit(
                f"{position}. [{headline} {finding.robustness.grade}] "
                f"{finding.label}", width, hang=4))
            confirmation = getattr(finding, "confirmation", None)
            if confirmation is not None and confirmation.ran:
                research = confirmation.research.metrics
                holdout = confirmation.holdout.metrics
                out.extend(fit(
                    f"   engine: net "
                    f"{research.get('net_profit', 0.0):+,.0f} research / "
                    f"{holdout.get('net_profit', 0.0):+,.0f} locked, "
                    f"{confirmation.research.trades:,} / "
                    f"{confirmation.holdout.trades:,} trades", width, hang=6))
            out.append("")
    else:
        out.append("Nothing survived.")
        out.append("")

    for note in report.notes:
        out.extend(fit(note, width))
        out.append("")
    return "\n".join(out).rstrip() + "\n"
