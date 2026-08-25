"""Strategies on disk: one JSON file each, in the workspace.

The whole point of a declarative strategy is that it is a document, so the store
is deliberately dull: a folder of ``<slug>-<id>.json`` files that a user can
copy, e-mail, keep in version control or edit in a text editor.  There is no
database and no index file to fall out of step with the folder.

Three things this module has to get right.

*A damaged file must not take the list down.*  A folder with fifty strategies
and one truncated file has to show forty-nine strategies and a note about the
fiftieth, not an error dialog on startup.  Every failure while scanning becomes
a :class:`StrategyProblem` in :attr:`StrategyStore.problems`.

*Writes must be atomic.*  A power cut in the middle of a save must leave either
the old file or the new one, never half of either, so every write goes to a
temporary file in the same folder and is then renamed over the target.

*The filename must follow the name.*  Renaming a strategy renames its file, so
the folder stays readable, but the ``id`` inside the file is what identifies it;
a user who renames a file by hand loses nothing.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Mapping

from ..config import Workspace
from ..core.errors import BacktesterError, StrategyStorageError
from .spec import StrategySpec

log = logging.getLogger(__name__)

__all__ = ["StrategyEntry", "StrategyProblem", "StrategyStore", "slugify"]

#: Extensions the store will open.  ``.tbs`` is offered in the import dialog for
#: users who prefer an application-specific extension; the contents are the
#: same JSON.
_READABLE_SUFFIXES = (".json", ".tbs")


def slugify(text: str, fallback: str = "strategy") -> str:
    """A filename-safe, lowercase version of a strategy name."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")
    return cleaned[:60] or fallback


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class StrategyEntry:
    """One strategy as it appears in a list, without loading its rules twice."""

    id: str
    name: str
    path: Path
    description: str = ""
    tags: tuple[str, ...] = ()
    updated_at: str = ""
    modified: float = 0.0
    """File modification time, epoch seconds, for 'most recent' sorting."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


@dataclass(frozen=True)
class StrategyProblem:
    """A file in the strategies folder that could not be read."""

    path: Path
    message: str
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.path.name}: {self.message}"


@dataclass
class _CachedFile:
    """A parsed file plus the stat values that say whether it is still current."""

    mtime_ns: int
    size: int
    spec: StrategySpec = field(repr=False)


class StrategyStore:
    """Load, save and organise the strategy files in a workspace.

    Accepts a :class:`~tradingbacktester.config.Workspace` or a bare folder
    path, which keeps tests free of the rest of the workspace layout.
    """

    def __init__(self, workspace: Workspace | Path | str) -> None:
        if isinstance(workspace, Workspace):
            self.workspace: Workspace | None = workspace
            self.folder = Path(workspace.strategies)
        else:
            self.workspace = None
            self.folder = Path(workspace).expanduser()
        self.problems: list[StrategyProblem] = []
        """Files that could not be read during the last :meth:`list`."""
        self._cache: dict[Path, _CachedFile] = {}

    # -- folder ----------------------------------------------------------

    def ensure_folder(self) -> Path:
        """Create the strategies folder if it is missing."""
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StrategyStorageError(
                f"The strategies folder could not be created at {self.folder}.",
                detail=repr(exc),
            ) from exc
        return self.folder

    def path_for(self, spec: StrategySpec) -> Path:
        """Where a strategy's file belongs, given its current name and id."""
        return self.folder / f"{slugify(spec.name)}-{spec.id}.json"

    # -- reading ---------------------------------------------------------

    def _candidate_files(self) -> list[Path]:
        if not self.folder.exists():
            return []
        try:
            files = [p for p in self.folder.iterdir()
                     if p.is_file() and p.suffix.lower() in _READABLE_SUFFIXES]
        except OSError as exc:
            raise StrategyStorageError(
                f"The strategies folder at {self.folder} could not be read.",
                detail=repr(exc),
            ) from exc
        return sorted(files, key=lambda p: p.name.lower())

    def _read_file(self, path: Path) -> StrategySpec:
        """Parse one file, reusing the cached parse while the file is unchanged."""
        try:
            stat = path.stat()
        except OSError as exc:
            raise StrategyStorageError(
                f"'{path.name}' could not be opened.", detail=repr(exc)) from exc
        cached = self._cache.get(path)
        if cached is not None and cached.mtime_ns == stat.st_mtime_ns \
                and cached.size == stat.st_size:
            return cached.spec
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise StrategyStorageError(
                f"'{path.name}' could not be read from disk.", detail=repr(exc)) from exc
        except UnicodeDecodeError as exc:
            raise StrategyStorageError(
                f"'{path.name}' is not a text file, so it is not a strategy.",
                detail=repr(exc)) from exc
        spec = StrategySpec.from_json(text)          # raises StrategyError
        if not spec.id:
            spec.id = uuid.uuid4().hex[:12]
        self._cache[path] = _CachedFile(stat.st_mtime_ns, stat.st_size, spec)
        return spec

    def list(self) -> list[StrategyEntry]:
        """Every readable strategy in the folder, sorted by name.

        Never raises for a bad file: unreadable ones are collected in
        :attr:`problems` so the caller can show them once, out of the way.
        """
        self.problems = []
        entries: list[StrategyEntry] = []
        seen_ids: dict[str, Path] = {}
        for path in self._candidate_files():
            try:
                spec = self._read_file(path)
            except BacktesterError as exc:
                self.problems.append(StrategyProblem(
                    path, exc.user_message, exc.detail or ""))
                log.warning("Skipping unreadable strategy file %s: %s",
                            path.name, exc.user_message)
                continue
            except Exception as exc:  # pragma: no cover - defensive
                self.problems.append(StrategyProblem(
                    path, "This file could not be read as a strategy.",
                    f"{type(exc).__name__}: {exc}"))
                log.exception("Unexpected failure reading %s", path)
                continue
            first = seen_ids.get(spec.id)
            if first is not None:
                # Two files claiming one id would make load() ambiguous; keep the
                # first alphabetically and say so rather than choosing silently.
                self.problems.append(StrategyProblem(
                    path,
                    f"This strategy has the same internal id as '{first.name}', so "
                    f"it was skipped. Open it and save it under a new name to keep "
                    f"both.",
                    detail=f"id={spec.id}"))
                continue
            seen_ids[spec.id] = path
            try:
                modified = path.stat().st_mtime
            except OSError:  # pragma: no cover - the file was just read
                modified = 0.0
            entries.append(StrategyEntry(
                id=spec.id, name=spec.name, path=path,
                description=spec.description, tags=tuple(spec.tags),
                updated_at=spec.updated_at, modified=modified))
        entries.sort(key=lambda e: (e.name.lower(), e.id))
        return entries

    def list_with_problems(self) -> tuple[list[StrategyEntry], list[StrategyProblem]]:
        """:meth:`list` and the problems it found, in one call."""
        entries = self.list()
        return entries, list(self.problems)

    def exists(self, strategy_id: str) -> bool:
        return self._find_by_id(strategy_id) is not None

    def _find_by_id(self, strategy_id: str) -> tuple[Path, StrategySpec] | None:
        """Locate a strategy by id and by id only.

        Everything that *writes* uses this rather than :meth:`_find`: a lookup
        that can fall back to a name match must never decide which file to
        overwrite or delete.
        """
        wanted = str(strategy_id or "").strip()
        if not wanted:
            return None
        for path in self._candidate_files():
            try:
                spec = self._read_file(path)
            except BacktesterError:
                continue
            if spec.id == wanted:
                return path, spec
        return None

    def _find(self, strategy_id: str) -> tuple[Path, StrategySpec] | None:
        """Locate a strategy by id, falling back to an exact name match.

        The fallback exists for read-only lookups, where being able to say
        ``load("EMA Cross + RSI")`` from a script is a convenience and the worst
        case is opening the wrong strategy rather than losing one.
        """
        found = self._find_by_id(strategy_id)
        if found is not None:
            return found
        wanted = str(strategy_id or "").strip()
        if not wanted:
            return None
        for path in self._candidate_files():
            try:
                spec = self._read_file(path)
            except BacktesterError:
                continue
            if spec.name == wanted:
                return path, spec
        return None

    def load(self, strategy_id: str) -> StrategySpec:
        """Load one strategy by id (or by exact name), raising if it is gone."""
        found = self._find(strategy_id)
        if found is None:
            raise StrategyStorageError(
                f"The strategy '{strategy_id}' is no longer in "
                f"{self.folder}. It may have been deleted or moved.")
        path, spec = found
        # A copy, so that editing what the caller was handed cannot change what a
        # later load() returns out of the cache.
        clone = StrategySpec.from_dict(json.loads(spec.to_json()))
        clone.id = spec.id
        log.debug("Loaded strategy '%s' from %s", clone.name, path.name)
        return clone

    # -- writing ---------------------------------------------------------

    def save(self, spec: StrategySpec) -> StrategySpec:
        """Write a strategy, renaming its file if the name changed.

        The strategy is *not* validated here.  A half-finished strategy is worth
        keeping — the editor is where validity is enforced — and refusing to
        save would lose the user's work at exactly the wrong moment.
        """
        if not isinstance(spec, StrategySpec):
            raise StrategyStorageError(
                "Only a strategy can be saved to the strategies folder.",
                detail=f"got {type(spec).__name__}")
        if not str(spec.name).strip():
            raise StrategyStorageError("Give the strategy a name before saving it.")
        self.ensure_folder()
        if not spec.id:
            spec.id = uuid.uuid4().hex[:12]

        previous = self._find_by_id(spec.id)
        if previous is not None:
            old_path, old_spec = previous
            if _content_changed(old_spec, spec):
                spec.version = max(int(old_spec.version), int(spec.version)) + 1
            else:
                spec.version = int(old_spec.version)
            spec.created_at = spec.created_at or old_spec.created_at
        else:
            old_path = None
            spec.created_at = spec.created_at or _now()
        spec.updated_at = _now()

        target = self.path_for(spec)
        _atomic_write(target, spec.to_json())
        self._cache.pop(target, None)
        if old_path is not None and old_path != target:
            # The name changed, so the old filename is stale.  Removing it keeps
            # one file per strategy; a failure here is not worth an error dialog
            # because the new file is already written and correct.
            try:
                old_path.unlink()
                self._cache.pop(old_path, None)
            except OSError as exc:  # pragma: no cover - rare
                log.warning("Could not remove the old strategy file %s: %s",
                            old_path.name, exc)
        log.info("Saved strategy '%s' to %s", spec.name, target.name)
        return spec

    def delete(self, strategy_id: str) -> None:
        """Remove a strategy file, matched by id so nothing else can be hit."""
        found = self._find_by_id(strategy_id)
        if found is None:
            raise StrategyStorageError(
                f"The strategy '{strategy_id}' is not in {self.folder}, so it "
                f"cannot be deleted.")
        path, spec = found
        try:
            path.unlink()
        except OSError as exc:
            raise StrategyStorageError(
                f"'{spec.name}' could not be deleted. It may be open in another "
                f"program, or the folder may be read-only.",
                detail=repr(exc),
            ) from exc
        self._cache.pop(path, None)
        log.info("Deleted strategy '%s'", spec.name)

    def duplicate(self, strategy_id: str, new_name: str | None = None) -> StrategySpec:
        """Copy a strategy under a new id and a new name."""
        original = self.load(strategy_id)
        name = str(new_name or "").strip() or f"{original.name} copy"
        copy = original.copy(self._unique_name(name))
        copy.created_at = ""
        copy.version = 1
        return self.save(copy)

    def rename(self, strategy_id: str, name: str) -> StrategySpec:
        """Change a strategy's name, and its filename with it."""
        clean = str(name or "").strip()
        if not clean:
            raise StrategyStorageError("A strategy needs a name.")
        spec = self.load(strategy_id)
        spec.name = clean
        return self.save(spec)

    # -- import / export -------------------------------------------------

    def export_to(self, strategy_id: str, path: str | Path,
                  spec: StrategySpec | None = None) -> str:
        """Write a strategy to any path, e.g. to share it.

        ``spec`` overrides what is stored, which is how the main window exports
        the strategy as currently edited rather than as last saved.
        """
        target = Path(path).expanduser()
        payload = spec if spec is not None else self.load(strategy_id)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StrategyStorageError(
                f"The folder {target.parent} could not be created.",
                detail=repr(exc)) from exc
        _atomic_write(target, payload.to_json())
        log.info("Exported strategy '%s' to %s", payload.name, target)
        return str(target)

    def import_from(self, path: str | Path) -> StrategySpec:
        """Read a strategy file from anywhere and add it to the workspace.

        A file whose id already belongs to a different strategy here is given a
        fresh id, so importing a colleague's edited copy of a strategy you
        already have adds a second strategy instead of overwriting yours.
        """
        source = Path(path).expanduser()
        try:
            text = source.read_text(encoding="utf-8-sig")
        except FileNotFoundError as exc:
            raise StrategyStorageError(
                f"There is no file at {source}.", detail=repr(exc)) from exc
        except OSError as exc:
            raise StrategyStorageError(
                f"{source.name} could not be read.", detail=repr(exc)) from exc
        except UnicodeDecodeError as exc:
            raise StrategyStorageError(
                f"{source.name} is not a text file, so it is not a strategy.",
                detail=repr(exc)) from exc

        spec = StrategySpec.from_json(text)           # raises StrategyError
        if not spec.id or self._find_by_id(spec.id) is not None:
            spec.id = uuid.uuid4().hex[:12]
        spec.name = self._unique_name(spec.name or source.stem)
        spec.created_at = spec.created_at or _now()
        saved = self.save(spec)
        log.info("Imported strategy '%s' from %s", saved.name, source)
        return saved

    def seed_builtins(
            self, builtins: Mapping[str, Callable[[], StrategySpec]] | Iterable[StrategySpec],
    ) -> list[StrategySpec]:
        """Write any built-in strategy the workspace does not already have.

        Existing files are never overwritten: a user who has edited the shipped
        EMA Cross keeps their version across upgrades.  Matching is by id *and*
        by name, so a built-in that a user renamed is not written back a second
        time under its original name.
        """
        self.ensure_folder()
        existing = self.list()
        known_ids = {e.id for e in existing}
        known_names = {e.name.strip().lower() for e in existing}
        created: list[StrategySpec] = []

        if isinstance(builtins, Mapping):
            items: list[tuple[str, Callable[[], StrategySpec] | StrategySpec]] = \
                list(builtins.items())
        else:
            items = [(getattr(s, "name", "strategy"), s) for s in builtins]

        for name, factory in items:
            try:
                spec = factory() if callable(factory) else factory
            except Exception as exc:  # pragma: no cover - a broken built-in
                log.exception("Built-in strategy '%s' could not be created", name)
                self.problems.append(StrategyProblem(
                    self.folder / f"{slugify(str(name))}.json",
                    f"The built-in strategy '{name}' could not be created.",
                    f"{type(exc).__name__}: {exc}"))
                continue
            if spec.id in known_ids or spec.name.strip().lower() in known_names:
                continue
            try:
                created.append(self.save(spec))
            except BacktesterError as exc:
                log.warning("Could not seed built-in '%s': %s", name, exc.user_message)
                self.problems.append(StrategyProblem(
                    self.path_for(spec), exc.user_message, exc.detail or ""))
                continue
            known_ids.add(spec.id)
            known_names.add(spec.name.strip().lower())
        if created:
            log.info("Seeded %d built-in strategies into %s", len(created), self.folder)
        return created

    # -- helpers ---------------------------------------------------------

    def _unique_name(self, name: str) -> str:
        """A name not already used in the folder, with ' (2)', ' (3)' appended.

        An existing counter is stripped first, so duplicating a duplicate gives
        "Breakout (3)" rather than the "Breakout (2) (2)" that a naive suffix
        would produce.
        """
        base = str(name).strip() or "Strategy"
        taken = {e.name.strip().lower() for e in self.list()}
        if base.lower() not in taken:
            return base
        counted = re.match(r"^(?P<base>.+?)\s*\(\d+\)$", base)
        if counted:
            base = counted.group("base")
            if base.lower() not in taken:
                return base
        for suffix in range(2, 1000):
            candidate = f"{base} ({suffix})"
            if candidate.lower() not in taken:
                return candidate
        return f"{base} ({uuid.uuid4().hex[:6]})"  # pragma: no cover - absurd folder


def _content_changed(old: StrategySpec, new: StrategySpec) -> bool:
    """Has anything but the bookkeeping fields changed between two versions?"""
    ignore = ("updated_at", "created_at", "version")
    a = {k: v for k, v in old.to_dict().items() if k not in ignore}
    b = {k: v for k, v in new.to_dict().items() if k not in ignore}
    return a != b


def _atomic_write(target: Path, text: str) -> None:
    """Write ``text`` to ``target`` so that a crash cannot truncate the file.

    The temporary file is created in the destination folder because
    ``os.replace`` is only atomic within one filesystem, and a workspace on a
    different drive to the temp directory is normal on Windows.
    """
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise StrategyStorageError(
            f"'{target.name}' could not be written. Check that {target.parent} "
            f"exists and is not read-only.",
            detail=repr(exc),
        ) from exc
