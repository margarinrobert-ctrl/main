"""About, and a reader for the bundled Markdown documents.

The Markdown renderer here is deliberately small: it handles exactly what this
project's own documents use. A dependency would be a poor trade for what amounts
to two hundred lines, and every extra package is another thing to ship, patch
and explain in an installer.
"""

from __future__ import annotations

import html as _html
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                               QTextBrowser, QVBoxLayout, QWidget)

from ...config import APP_DISPLAY_NAME, APP_VERSION, Workspace, resource_path
from ...logging_setup import get_logger
from ..theme import PALETTE, Fonts

log = get_logger(__name__)


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_UNORDERED = re.compile(r"^\s*[-*+]\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])\s*\1\s*\1[\s\-*_]*$")
_TABLE_DIVIDER = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")


def _inline(text: str) -> str:
    """Escape a line, then apply the inline markers.

    Escaping comes first and unconditionally: a strategy or a document called
    ``<script>`` must render as text, not run.
    """
    out = _html.escape(text, quote=False)
    out = _INLINE_CODE.sub(
        r'<code style="background:%s;padding:1px 4px;border-radius:3px;">\1</code>'
        % PALETTE.elevated, out)
    out = _BOLD.sub(r"<b>\1</b>", out)
    out = _ITALIC.sub(r"<i>\1</i>", out)
    out = _LINK.sub(r'<a style="color:%s;" href="\2">\1</a>' % PALETTE.accent, out)
    return out


def markdown_to_html(text: str) -> str:
    """Render the Markdown subset this project's documents actually use.

    Supports ATX headings, paragraphs, bold, italic, inline code, fenced code
    blocks, unordered and ordered lists, tables, blockquotes and horizontal
    rules.  Anything else is passed through as escaped text, which is the safe
    failure: an unrecognised construct looks plain rather than disappearing.
    """
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    list_stack: list[str] = []
    in_code = False
    code: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_lists() -> None:
        while list_stack:
            out.append(f"</{list_stack.pop()}>")

    index = 0
    while index < len(lines):
        line = lines[index]

        if line.strip().startswith("```"):
            if in_code:
                out.append(
                    f'<pre style="background:{PALETTE.app_bg};border:1px solid '
                    f'{PALETTE.border};border-radius:5px;padding:9px;">'
                    f'<code>{_html.escape(chr(10).join(code))}</code></pre>')
                code.clear()
                in_code = False
            else:
                flush_paragraph()
                close_lists()
                in_code = True
            index += 1
            continue
        if in_code:
            code.append(line)
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            close_lists()
            index += 1
            continue

        if _RULE.match(line):
            flush_paragraph()
            close_lists()
            out.append(f'<hr style="border:0;border-top:1px solid {PALETTE.border};">')
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            close_lists()
            level = len(heading.group(1))
            size = {1: 19, 2: 15, 3: 13}.get(level, 12)
            colour = PALETTE.text if level <= 2 else PALETTE.text_dim
            out.append(
                f'<h{level} style="font-size:{size}px;color:{colour};'
                f'margin:{16 if level <= 2 else 12}px 0 6px 0;">'
                f'{_inline(heading.group(2))}</h{level}>')
            index += 1
            continue

        # Tables: a header row followed by a divider row.
        if "|" in line and index + 1 < len(lines) and _TABLE_DIVIDER.match(lines[index + 1]):
            flush_paragraph()
            close_lists()
            index = _render_table(lines, index, out)
            continue

        if line.lstrip().startswith(">"):
            flush_paragraph()
            close_lists()
            quote = line.lstrip()[1:].strip()
            out.append(
                f'<div style="border-left:3px solid {PALETTE.border_strong};'
                f'padding:2px 0 2px 10px;color:{PALETTE.text_dim};margin:6px 0;">'
                f'{_inline(quote)}</div>')
            index += 1
            continue

        ordered = _ORDERED.match(line)
        unordered = _UNORDERED.match(line)
        if ordered or unordered:
            flush_paragraph()
            want = "ol" if ordered else "ul"
            if not list_stack or list_stack[-1] != want:
                close_lists()
                out.append(f'<{want} style="margin:4px 0 4px 18px;">')
                list_stack.append(want)
            content = (ordered or unordered).group(1)
            out.append(f'<li style="margin:2px 0;">{_inline(content)}</li>')
            index += 1
            continue

        close_lists()
        paragraph.append(line.strip())
        index += 1

    if in_code and code:                    # an unterminated fence
        out.append(f"<pre><code>{_html.escape(chr(10).join(code))}</code></pre>")
    flush_paragraph()
    close_lists()
    return "\n".join(out)


def _render_table(lines: list[str], index: int, out: list[str]) -> int:
    def cells(row: str) -> list[str]:
        return [c.strip() for c in row.strip().strip("|").split("|")]

    header = cells(lines[index])
    index += 2                              # skip the divider
    out.append('<table cellspacing="0" cellpadding="6" '
               'style="border-collapse:collapse;margin:8px 0;width:100%;">')
    out.append("<tr>" + "".join(
        f'<th align="left" style="border-bottom:1px solid {PALETTE.border_strong};'
        f'color:{PALETTE.text_dim};font-size:11px;">{_inline(c)}</th>'
        for c in header) + "</tr>")
    while index < len(lines) and "|" in lines[index] and lines[index].strip():
        row = cells(lines[index])
        row += [""] * (len(header) - len(row))
        out.append("<tr>" + "".join(
            f'<td style="border-bottom:1px solid {PALETTE.border};'
            f'vertical-align:top;">{_inline(c)}</td>' for c in row[:len(header)])
            + "</tr>")
        index += 1
    out.append("</table>")
    return index


def _document_path(name: str) -> Path | None:
    """Find a bundled document, in a source checkout and in a frozen build."""
    candidates = [
        resource_path("docs", name),
        Path(__file__).resolve().parents[3] / "docs" / name,
        Path(__file__).resolve().parents[3] / name,
        Path(getattr(sys, "_MEIPASS", ".")) / "docs" / name,
    ]
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:                     # pragma: no cover - defensive
            continue
    return None


# --------------------------------------------------------------------------
# Dialogs
# --------------------------------------------------------------------------

class DocumentDialog(QDialog):
    """A reader for one of the bundled Markdown documents."""

    def __init__(self, title: str, doc_name: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(880, 720)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(9)

        heading = QLabel(title)
        heading.setFont(Fonts.heading(13))
        lay.addWidget(heading)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(Fonts.body(10))
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background:{PALETTE.panel_bg}; "
            f"border:1px solid {PALETTE.border}; border-radius:6px; padding:14px; }}")
        lay.addWidget(self.browser, 1)

        path = _document_path(doc_name)
        if path is None:
            self.browser.setHtml(
                f'<p style="color:{PALETTE.warning}">'
                f'The document <b>{_html.escape(doc_name)}</b> is not installed '
                f'with this build. It is available in the project repository '
                f'under <code>docs/</code>.</p>')
        else:
            try:
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                body = f"This document could not be read: `{exc}`"
            self.browser.setHtml(
                f'<div style="color:{PALETTE.text};font-family:\'{Fonts.ui}\';">'
                f'{markdown_to_html(body)}</div>')

        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)


class AboutDialog(QDialog):
    """Version, environment and the privacy statement."""

    def __init__(self, workspace: Workspace | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_DISPLAY_NAME}")
        self.setMinimumWidth(520)
        self._workspace = workspace

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        from ..icons import app_icon

        top = QHBoxLayout()
        top.setSpacing(14)
        badge = QLabel()
        badge.setPixmap(app_icon(72).pixmap(72, 72))
        badge.setAlignment(Qt.AlignmentFlag.AlignTop)
        top.addWidget(badge)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        name = QLabel(APP_DISPLAY_NAME)
        name.setFont(Fonts.heading(16))
        titles.addWidget(name)
        version = QLabel(f"Version {APP_VERSION}")
        version.setFont(Fonts.numeric(9))
        version.setStyleSheet(f"color:{PALETTE.text_dim};")
        titles.addWidget(version)
        tagline = QLabel("A desktop backtesting platform for trading strategies.")
        tagline.setWordWrap(True)
        tagline.setStyleSheet(f"color:{PALETTE.text_dim};")
        titles.addWidget(tagline)
        titles.addStretch(1)
        top.addLayout(titles, 1)
        lay.addLayout(top)

        privacy = QLabel(
            "This application runs entirely on this computer. It makes no "
            "network requests of any kind, collects no telemetry, and sends "
            "your data nowhere. Your datasets, strategies and results are "
            "stored only in your workspace folder.")
        privacy.setWordWrap(True)
        privacy.setFont(Fonts.body(9))
        privacy.setStyleSheet(
            f"color:{PALETTE.text}; background:{PALETTE.panel_alt};"
            f"border:1px solid {PALETTE.border}; border-radius:5px; padding:10px;")
        lay.addWidget(privacy)

        details = QTextBrowser()
        details.setOpenExternalLinks(True)
        details.setFont(Fonts.numeric(8))
        details.setMaximumHeight(190)
        details.setHtml(self._details_html())
        lay.addWidget(details)

        row = QHBoxLayout()
        if workspace is not None:
            open_ws = QPushButton("Open Workspace Folder")
            open_ws.setObjectName("Ghost")
            open_ws.clicked.connect(self._open_workspace)
            row.addWidget(open_ws)
        row.addStretch(1)
        close = QPushButton("Close")
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        lay.addLayout(row)

    def _details_html(self) -> str:
        try:
            from PySide6 import __version__ as pyside_version
            from PySide6.QtCore import qVersion

            qt_version = qVersion()
        except Exception:                   # pragma: no cover - defensive
            pyside_version = qt_version = "unknown"
        try:
            import numpy
            import pyqtgraph

            numpy_version = numpy.__version__
            pyqtgraph_version = pyqtgraph.__version__
        except Exception:                   # pragma: no cover
            numpy_version = pyqtgraph_version = "unknown"
        try:
            import pandas

            pandas_version = pandas.__version__
        except Exception:                   # pragma: no cover
            pandas_version = "unknown"

        rows = [
            ("Python", sys.version.split()[0]),
            ("Qt", qt_version),
            ("PySide6", pyside_version),
            ("pyqtgraph", pyqtgraph_version),
            ("NumPy", numpy_version),
            ("pandas", pandas_version),
            ("Platform", sys.platform),
            ("Frozen build", "yes" if getattr(sys, "frozen", False) else "no"),
        ]
        if self._workspace is not None:
            rows.append(("Workspace", str(self._workspace.root)))

        body = "".join(
            f'<tr><td style="color:{PALETTE.text_muted};padding-right:14px;">{k}</td>'
            f'<td style="color:{PALETTE.text};">{_html.escape(str(v))}</td></tr>'
            for k, v in rows)
        return (
            f'<div style="color:{PALETTE.text_dim};">'
            f'<table cellspacing="0" cellpadding="2">{body}</table>'
            f'<p style="margin-top:10px;">Released under the MIT licence. '
            f'Qt for Python (PySide6) is used under the LGPL v3; pyqtgraph under '
            f'the MIT licence; NumPy and pandas under BSD 3-Clause.</p>'
            f'<p style="color:{PALETTE.warning};">Backtested results describe what '
            f'a set of rules would have done on past data. They are not a '
            f'prediction, and historical simulation systematically flatters a '
            f'strategy. Trading involves substantial risk of loss.</p></div>')

    def _open_workspace(self) -> None:
        if self._workspace is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._workspace.root)))
