"""Fitting a report to a terminal.

Every plain-text report in this application declares a width and then has to
honour it. A line that overruns does not get truncated by the terminal, it
wraps -- and a table row that wraps at an arbitrary column puts half a number
on the next line, which is worse than no table at all.

The reports were written with the widths in mind and still drifted past them:
a decile line reached 129 characters and a paragraph in the indicator study
reached 197, because a `f"..."` that fits when the numbers are small does not
when they are not. :func:`fit` is the fix, and `test_reports.py` asserts every
formatter's output against its own declared width so it cannot drift again.
"""

from __future__ import annotations

import textwrap

#: The width every report defaults to. Eighty columns minus a margin, so a
#: pasted report still fits in a mail client or a code fence.
DEFAULT_WIDTH = 78


def fit(text: str, width: int = DEFAULT_WIDTH, hang: int = 0,
        indent: str = "") -> list[str]:
    """``text`` wrapped to ``width``, continuations indented by ``hang``.

    Returns at least one line, so a caller can always ``extend`` with it
    without checking for an empty result. Long unbroken tokens -- a path, a
    URL, a symbol -- are left to overrun rather than being broken mid-word,
    because a broken identifier cannot be copied back out.
    """
    lines = textwrap.wrap(
        text, width=max(20, int(width)), initial_indent=indent,
        subsequent_indent=indent + " " * max(0, int(hang)),
        break_long_words=False, break_on_hyphens=False)
    return lines or [indent.rstrip() or ""]


def row(cells: str, verdict: str, width: int = DEFAULT_WIDTH) -> list[str]:
    """A table row whose trailing free-text column wraps under itself.

    ``cells`` is the fixed-width part, already padded; ``verdict`` is the prose
    that follows it. When the two together overrun, the prose continues on the
    next line aligned to where it started, so the numeric columns stay in line.
    """
    if not verdict:
        return [cells.rstrip()]
    return fit(f"{cells}{verdict}", width, hang=len(cells))


#: Currency codes we have a symbol for. Anything else is prefixed with the code
#: and a space -- "SEK 1,234.50" -- because an ISO code jammed against the
#: digits ("SEK1,234.50") reads as a typo, and a made-up symbol would be worse
#: than either.
CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
                    "CHF": "CHF ", "AUD": "A$", "CAD": "C$"}


def currency_symbol(code: str) -> str:
    """The prefix to put in front of an amount in ``code``.

    A symbol where one exists, the code and a space where it does not, and an
    empty string for no currency at all. :func:`money`-style formatters take a
    *prefix*, never a code, so anything holding an instrument should pass its
    currency through here first.
    """
    text = str(code or "").strip().upper()
    if not text:
        return ""
    return CURRENCY_SYMBOLS.get(text, f"{text} ")
