"""Workspace bootstrap: turn a bare directory into a usable project folder.

The application keeps everything it owns in one folder so that a user can back
it up, copy it to another machine or throw it away without hunting through
hidden application-data directories.  :func:`bootstrap` is what makes that
folder real: it creates the directory tree, seeds the instrument catalogue with
the built-in contract specifications the *first* time it runs, writes the
bundled synthetic samples if they are missing, and leaves a ``README.txt``
behind explaining what every folder holds and that the whole thing is safe to
back up, move or delete.

Three properties matter more than anything else here:

*Idempotence.*  ``bootstrap`` is called on every start-up.  Running it a
hundred times must produce the same folder as running it once, and must be
cheap when there is nothing to do.

*It never overwrites the user's work.*  The instrument catalogue is seeded only
when the file does not exist; a user who has spent an afternoon entering tick
sizes keeps them.  The samples are regenerated only when they are missing.  The
one file this module does rewrite is the ``README.txt`` it wrote itself, and
only when its text has actually changed (a new application version, say).

*A convenience failing is not a start-up failure.*  If the directories cannot
be created the workspace is unusable and a :class:`StorageError` is raised with
a message telling the user to choose another location.  If a sample file or the
README cannot be written -- a read-only volume, a full disk -- that is logged
and start-up continues, because the user can still open a dataset they already
have.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import APP_DISPLAY_NAME, APP_VERSION, AppSettings, Workspace
from ..core.errors import BacktesterError, StorageError

log = logging.getLogger(__name__)

__all__ = [
    "README_FILENAME",
    "MARKER_FILENAME",
    "bootstrap",
    "readme_text",
    "write_readme",
    "read_marker",
    "is_workspace",
    "workspace_size_bytes",
]

#: The explanatory file written into the workspace root.
README_FILENAME = "README.txt"

#: A small machine-readable stamp identifying the folder as a workspace.
MARKER_FILENAME = "workspace.json"

_MARKER_SCHEMA = 1

#: The instrument catalogue, relative to :attr:`Workspace.settings`.
INSTRUMENTS_FILENAME = "instruments.json"


# ---------------------------------------------------------------------------
# The README
# ---------------------------------------------------------------------------


def readme_text() -> str:
    """The text written into ``<workspace>/README.txt``.

    Kept as one function so the wording lives in exactly one place: this file is
    the only documentation many users will ever read about where their data
    went, and it has to be accurate about what deleting the folder costs them.
    """
    return f"""\
{APP_DISPLAY_NAME} workspace
{'=' * (len(APP_DISPLAY_NAME) + 10)}

Everything this application saves is inside this one folder.  The only thing it
writes anywhere else is a small preferences file in your user profile, which
remembers where this folder is and what the window looked like.

This folder is yours.  It is safe to back it up, to copy it to another machine,
to move it somewhere else, or to delete it.  If you move it, point the
application at the new location with File > Change Workspace.  If you delete it,
you lose the imported datasets, strategies and saved runs that are in it and
nothing else: an empty workspace is created again the next time the application
starts.

What is in here
---------------

data/         Imported market data.  One file per dataset -- Parquet where it is
              available, gzip-compressed CSV otherwise -- plus index.json, which
              lists them, and a small .meta.json beside each one so the library
              can be rebuilt if the index is ever lost.  The original CSV you
              imported from is not needed again once a dataset is in here.

strategies/   One .json file per strategy: its indicators, its entry and exit
              rules, its parameters and its risk defaults.  These are plain text
              and are the files to copy if you want to share a strategy.

backtests/    Saved runs, one folder per run, holding meta.json (the summary and
              the full metrics), config.json (costs, risk, session and exit
              settings), strategy.json (the strategy exactly as it was run),
              trades.json (every completed trade) and curves.npz (the per-bar
              equity, balance and drawdown series).
              The bars themselves are NOT saved with a run -- they are large and
              they are already in data/ -- so each run records which dataset,
              symbol, timeframe and date range it used instead.

reports/      CSV, HTML and PDF exports, written only when you ask for one.
              Nothing in here is needed by the application; it is output.

settings/     instruments.json, the contract specification for every symbol you
              trade: tick size, point value, lot size, currency, timezone and
              the default costs.  Edit it from Instruments in the application
              rather than by hand.  Also holds saved interface state.

logs/         Rotating log files.  Useful when something went wrong; safe to
              delete at any time.

samples/      Synthetic sample data files.  These are GENERATED, not recorded:
              they are not real market prices and results computed from them
              mean nothing about a real market.  They exist so that the
              application has something to open on a fresh installation.  Delete
              them and they are written again on the next start.

A few things worth knowing
--------------------------

* No network requests are made by this application and no usage data is
  collected.  Nothing in this folder is sent anywhere.

* Files are saved by writing a temporary file first and renaming it into place,
  so a crash or a power cut leaves you with the previous version of a file
  rather than a half-written one.

* If a file in here is damaged, the application reports it and carries on rather
  than deleting it; a damaged instrument catalogue is moved aside with a
  .corrupt suffix so you can pick the contents out of it.

* The application only writes to this folder while it is running, so backing it
  up while the application is closed is always safe.

Written by {APP_DISPLAY_NAME} {APP_VERSION}.
"""


def write_readme(workspace: Workspace) -> bool:
    """Write ``README.txt`` if it is missing or its text has changed.

    Returns ``True`` when the file was written.  Comparing the text first keeps
    the folder's modification times quiet on the overwhelmingly common path
    where there is nothing to do, which matters to backup tools that watch
    them.
    """
    path = workspace.root / README_FILENAME
    wanted = readme_text()
    try:
        if path.exists() and path.read_text(encoding="utf-8") == wanted:
            return False
    except OSError as exc:  # unreadable, but possibly still writable
        log.debug("Could not read the existing %s (%r); rewriting it", path, exc)
    try:
        _atomic_write_text(path, wanted)
    except StorageError as exc:
        # The README is an explanation, not data.  Losing it must not stop the
        # application from starting on a read-only or full volume.
        log.warning("The workspace README could not be written: %s", exc.user_message)
        return False
    return True


# ---------------------------------------------------------------------------
# The marker file
# ---------------------------------------------------------------------------


def read_marker(workspace: Workspace) -> dict[str, Any]:
    """Read ``workspace.json``, returning ``{}`` when it is absent or damaged."""
    path = workspace.root / MARKER_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def is_workspace(path: str | Path) -> bool:
    """True when ``path`` looks like a workspace this application created.

    Used to tell "an empty folder the user just picked" apart from "a workspace
    with their year's work in it" before doing anything to it.
    """
    root = Path(path).expanduser()
    if not root.is_dir():
        return False
    if (root / MARKER_FILENAME).is_file():
        return True
    # A workspace created by an earlier version has no marker; recognise it by
    # its shape instead so it is never treated as a fresh folder.
    space = Workspace(root)
    return sum(1 for d in (space.data, space.strategies, space.backtests,
                           space.settings) if d.is_dir()) >= 3


def _write_marker(workspace: Workspace) -> None:
    """Stamp the folder with the application version and the times it was used."""
    now = _utc_now_iso()
    existing = read_marker(workspace)
    payload = {
        "schema": _MARKER_SCHEMA,
        "application": APP_DISPLAY_NAME,
        "version": APP_VERSION,
        "created_at": str(existing.get("created_at") or now),
        "created_by_version": str(existing.get("created_by_version") or APP_VERSION),
        "last_opened_at": now,
    }
    try:
        _atomic_write_text(workspace.root / MARKER_FILENAME,
                           json.dumps(payload, indent=2) + "\n")
    except StorageError as exc:
        log.warning("The workspace marker could not be written: %s", exc.user_message)


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap(settings: AppSettings | Workspace | str | Path,
              *, samples: bool = True) -> Workspace:
    """Create and seed the workspace, and return it.

    Parameters
    ----------
    settings:
        Normally the loaded :class:`~tradingbacktester.config.AppSettings`,
        whose :meth:`~tradingbacktester.config.AppSettings.workspace` decides
        the location.  A :class:`~tradingbacktester.config.Workspace` or a plain
        path is accepted too, which is what tests and the "change workspace"
        flow have to hand.
    samples:
        Write the bundled synthetic sample files when they are missing.  Turned
        off by tests that do not want to spend the time generating them.

    Raises
    ------
    StorageError
        When the directory tree or the instrument catalogue cannot be written.
        Both mean the chosen location is unusable and the user has to pick
        another one, so they are reported rather than swallowed.
    """
    workspace, app_settings = _resolve(settings)
    existed = is_workspace(workspace.root)

    workspace.ensure()  # raises StorageError with a user-facing message

    seeded_instruments = _seed_instruments(workspace)
    write_readme(workspace)
    _write_marker(workspace)

    if samples:
        _ensure_samples(workspace)

    # Record where the workspace ended up so the next start finds the same one
    # even if the default location changes.  Only filled in when the user has
    # not chosen a location, so this never moves anybody's workspace.
    if app_settings is not None and not app_settings.workspace_dir:
        app_settings.workspace_dir = str(workspace.root)
        app_settings.save()

    if not existed:
        log.info("Created a new workspace at %s", workspace.root)
    if seeded_instruments:
        log.info("Seeded the instrument catalogue with %d instruments",
                 seeded_instruments)
    log.debug("Workspace ready at %s", workspace.root)
    return workspace


def _resolve(settings: AppSettings | Workspace | str | Path,
             ) -> tuple[Workspace, AppSettings | None]:
    """Work out which workspace was meant, and whether we may write settings back."""
    if isinstance(settings, AppSettings):
        return settings.workspace(), settings
    if isinstance(settings, Workspace):
        return settings, None
    if isinstance(settings, (str, Path)):
        return Workspace(Path(settings)), None
    raise StorageError(
        "The workspace location could not be worked out.",
        detail=f"bootstrap() was given a {type(settings).__name__}")


def _seed_instruments(workspace: Workspace) -> int:
    """Seed ``settings/instruments.json`` on first run; never touch it after.

    Returns the number of instruments written, or ``0`` when the catalogue was
    already there.  The registry itself does the seeding when the file is
    missing -- this function only decides whether that happened, so that a user
    who has edited or deleted instruments keeps their edits.
    """
    from ..data.instruments import InstrumentRegistry  # imported late: it is heavy

    path = workspace.settings / INSTRUMENTS_FILENAME
    fresh = not path.exists()
    try:
        registry = InstrumentRegistry(path)
    except BacktesterError:
        raise
    except OSError as exc:
        raise StorageError(
            f"The instrument catalogue could not be created at {path}.\n\n"
            f"Choose a different workspace location from File > Change Workspace.",
            detail=repr(exc)) from exc
    return len(registry) if fresh else 0


def _ensure_samples(workspace: Workspace) -> None:
    """Write the bundled synthetic samples if they are missing.

    Sample data is a convenience: it lets a new user press one button and see a
    chart.  A failure to generate it is logged and start-up continues.
    """
    from ..data.sample import ensure_samples  # imported late: it pulls in pandas

    try:
        paths = ensure_samples(workspace)
    except BacktesterError as exc:
        log.warning("The sample datasets could not be created: %s", exc.user_message)
        return
    except Exception:  # noqa: BLE001 - start-up must never be blocked by samples
        log.exception("Unexpected failure creating the sample datasets")
        return
    log.debug("%d sample dataset(s) present in %s", len(paths), workspace.samples)


# ---------------------------------------------------------------------------
# Odds and ends
# ---------------------------------------------------------------------------


def workspace_size_bytes(workspace: Workspace) -> int:
    """Total size of everything in the workspace, for the dataset manager.

    Unreadable entries are skipped rather than raising: this is a number shown
    in a status line, and no status line is worth an error dialog.
    """
    total = 0
    for folder in workspace.all_dirs():
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
    return total


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temporary file in the same directory.

    ``os.replace`` is atomic on Windows as well as POSIX, which ``Path.rename``
    is not when the destination already exists, and the ``fsync`` before it is
    what makes the write survive a power cut rather than merely a crash.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                                        dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        raise StorageError(
            f"The file {path.name} could not be saved to {path.parent}.\n\n"
            f"Check that the folder exists and that you have permission to "
            f"write to it.",
            detail=repr(exc)) from exc
