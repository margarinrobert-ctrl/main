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


def startup_log_path() -> Path:
    """Where the pre-workspace breadcrumbs go.

    A fixed, always-writable location that does not depend on the workspace,
    because the workspace is one of the things that can be slow to build and a
    launch that stalls before it exists would otherwise leave no trace at all.
    Windows puts it under ``%LOCALAPPDATA%``; everything else uses the temp
    directory, which is the only place guaranteed writable.
    """
    import os
    import tempfile

    from .config import APP_ORG

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    root = (Path(base) / APP_ORG) if base else Path(tempfile.gettempdir())
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception:                       # noqa: BLE001 - a diagnostic path
        # Not just OSError: a path from the environment can be malformed in
        # ways that raise ValueError before it ever reaches the filesystem, and
        # the one place that must not throw is the one that records why
        # something else did.
        root = Path(tempfile.gettempdir())
    return root / "startup.log"


def breadcrumb(message: str) -> None:
    """Append one timestamped line to the start-up log, and never raise.

    Used for the phase before :func:`configure_logging` can run. A launch that
    hangs is diagnosed from the last line this wrote, so it opens, writes and
    closes each time rather than holding a handle: a process killed with the
    Task Manager must not lose the line that says where it was.
    """
    import time

    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with startup_log_path().open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp}  {message}\n")
            handle.flush()
    except Exception:                       # noqa: BLE001 - see the docstring
        pass


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
