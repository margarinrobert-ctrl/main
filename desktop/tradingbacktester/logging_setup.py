"""Logging, and the last line of defence against an unhandled exception.

Technical detail -- tracebacks included -- goes to a rotating file in the
workspace ``logs`` folder.  The console gets a terse stream in development.  The
UI never renders a traceback: :func:`install_excepthook` catches whatever escapes
a slot, writes it to the log and shows a plain-language dialog instead.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Callable

_LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)-32s %(message)s"
_configured = False


def configure_logging(log_dir: Path, level: str = "INFO", console: bool = True) -> Path:
    """Set up file and console logging.  Returns the active log file path."""
    global _configured
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tradingbacktester.log"

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)

    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=4_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(fh)

    if console:
        ch = logging.StreamHandler(sys.stderr)
        try:
            ch.setLevel(getattr(logging, str(level).upper()))
        except AttributeError:
            ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
        root.addHandler(ch)

    logging.getLogger(__name__).info("Logging to %s", log_file)
    _configured = True
    return log_file


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def install_excepthook(on_error: Callable[[str, str], None] | None = None) -> None:
    """Route uncaught exceptions to the log and, optionally, to a UI callback."""
    log = logging.getLogger("tradingbacktester.crash")

    def hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):  # pragma: no cover
            sys.__excepthook__(exc_type, exc, tb)
            return
        detail = "".join(traceback.format_exception(exc_type, exc, tb))
        log.critical("Unhandled exception:\n%s", detail)
        message = getattr(exc, "user_message", None) or (
            "Something went wrong inside the application. The details have been "
            "written to the log file."
        )
        if on_error is not None:
            try:
                on_error(str(message), detail)
            except Exception:  # pragma: no cover - the handler must not throw
                log.exception("The error handler itself failed.")

    sys.excepthook = hook
