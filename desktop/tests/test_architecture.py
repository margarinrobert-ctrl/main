"""The layering the README claims, asserted rather than trusted.

"Everything below `ui/` imports without Qt" is the sentence that makes the
engine scriptable and the test suite fast, and it was false: `reports/` reached
into `ui.theme` for a colour table and a thousands separator, so the one
package that produces the shareable artifact could not be imported on a machine
without PySide6.

The PDF renderer is the deliberate exception — it paints with `QPainter`, which
is the whole reason there is no reportlab dependency. Everything else is
checked here, in a subprocess with PySide6 blocked at the import hook, because
a module already imported by an earlier test would make an in-process check
vacuous.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

#: Every module below `ui/` that must import with no Qt available at all.
QT_FREE_MODULES = [
    "tradingbacktester.core.presentation",
    "tradingbacktester.core.textfmt",
    "tradingbacktester.core.types",
    "tradingbacktester.analytics.correlation",
    "tradingbacktester.analytics.diagnose",
    "tradingbacktester.analytics.metrics",
    "tradingbacktester.analytics.montecarlo",
    "tradingbacktester.data.csv_loader",
    "tradingbacktester.engine.backtester",
    "tradingbacktester.finder.search",
    "tradingbacktester.indicators.library",
    "tradingbacktester.optimize.walkforward",
    "tradingbacktester.reports.csv_export",
    "tradingbacktester.reports.html_report",
    "tradingbacktester.research.mirror",
    "tradingbacktester.storage.backtest_store",
    "tradingbacktester.indicators.quant",
    "tradingbacktester.strategy.compiler",
    "tradingbacktester.strategy.parameterise",
    "tradingbacktester.cli",
]

_BLOCKER = '''
import sys

class _NoQt:
    """Refuse PySide6 the way a machine without it would."""

    def find_module(self, name, path=None):
        if name == "PySide6" or name.startswith("PySide6."):
            return self

    def load_module(self, name):
        raise ImportError("No module named 'PySide6'")

sys.meta_path.insert(0, _NoQt())
sys.path.insert(0, {root!r})
import {module}
assert "PySide6" not in sys.modules, "{module} pulled in Qt"
print("ok")
'''


def _import_without_qt(module: str) -> subprocess.CompletedProcess:
    script = _BLOCKER.format(root=str(ROOT), module=module)
    return subprocess.run([sys.executable, "-c", textwrap.dedent(script)],
                          capture_output=True, text=True, timeout=180)


@pytest.mark.parametrize("module", QT_FREE_MODULES)
def test_module_imports_without_qt(module):
    done = _import_without_qt(module)
    assert done.returncode == 0, (
        f"{module} cannot be imported without PySide6:\n"
        f"{done.stderr.strip()[-1500:]}")
    assert "ok" in done.stdout


def test_the_pdf_renderer_is_the_one_deliberate_exception():
    """It paints with QPainter; that is why there is no reportlab dependency."""
    done = _import_without_qt("tradingbacktester.reports.pdf_report")
    assert done.returncode != 0
    assert "PySide6" in done.stderr


def _imported_names(path: Path) -> set[str]:
    """Every module this file imports *at import time*.

    Parsed rather than grepped, for two reasons. The string "PySide6" appears
    in a docstring in more than one Qt-free module explaining why it does not
    import Qt, and a check that cannot tell prose from code is worse than no
    check. And an import inside a function body does not affect whether the
    module can be imported — `Palette.qcolor` builds a QColor for the widgets
    that paint, and defers the import precisely so the palette stays usable
    without Qt — so only what actually runs on import is collected here.
    """
    import ast

    names: set[str] = set()

    def record(node: ast.AST) -> None:
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            names.add(f"{prefix}{node.module or ''}")

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            record(node)
            # A class body runs on import; a function body does not.
            if isinstance(node, ast.ClassDef):
                visit(node.body)
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                visit(node.body)
                visit(getattr(node, "orelse", []) or [])
                visit(getattr(node, "finalbody", []) or [])
                for handler in getattr(node, "handlers", []) or []:
                    visit(handler.body)

    visit(ast.parse(path.read_text(encoding="utf-8"),
                    filename=str(path)).body)
    return names


def test_no_package_below_ui_reaches_into_it_except_the_pdf_renderer():
    """Source-level, so a new import is caught before anyone has to run it."""
    offenders: list[str] = []
    for package in ("core", "data", "indicators", "strategy", "engine",
                    "analytics", "finder", "research", "optimize", "reports",
                    "storage"):
        for path in sorted((ROOT / "tradingbacktester" / package).rglob("*.py")):
            for name in _imported_names(path):
                bare = name.lstrip(".")
                if name.startswith("PySide6") or bare.split(".")[0] == "ui" \
                        or bare.startswith("tradingbacktester.ui"):
                    # `as_posix`, not `str`: on Windows the latter gives
                    # backslashes and this comparison fails on the
                    # runner for a repository that is perfectly layered.
                    offenders.append(path.relative_to(ROOT).as_posix())
                    break
    assert offenders == ["tradingbacktester/reports/pdf_report.py"], offenders
