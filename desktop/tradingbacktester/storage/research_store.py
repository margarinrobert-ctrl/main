"""Research runs, kept on disk so a loop's findings outlive the dialog.

A backtest is a result; a research run is a *record of what was tried*, and the
second is worth keeping for a reason the first is not: the experiments that
failed are the ones that stop the same ground being re-searched next week.  So
a run stores every experiment, including the ones that found nothing and the
ones that could not be run at all, with the reason.

Stored as one JSON file per run under ``<workspace>/research``.  Plain JSON
rather than a database because a research record that cannot be read without
the application that wrote it is a research record that will not be read.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Workspace
from ..core.errors import StorageError

log = logging.getLogger(__name__)

#: Runs older than this are still listed; nothing is deleted automatically.
#: Silently discarding someone's research is not a housekeeping decision.
INDEX_FILENAME = "index.json"

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_id(run_id: str) -> str:
    cleaned = _SAFE.sub("_", str(run_id).strip())[:64]
    return cleaned or "run"


@dataclass
class ResearchRun:
    """One loop, summarised for a list, with the whole report beside it."""

    id: str
    created_at: str
    symbol: str
    timeframe: str
    style: str
    proposer: str
    experiments: int = 0
    survivors: int = 0
    combinations: int = 0
    best_score: float | None = None
    best_label: str = ""
    elapsed: float = 0.0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "created_at": self.created_at,
                "symbol": self.symbol, "timeframe": self.timeframe,
                "style": self.style, "proposer": self.proposer,
                "experiments": self.experiments, "survivors": self.survivors,
                "combinations": self.combinations,
                "best_score": self.best_score, "best_label": self.best_label,
                "elapsed": self.elapsed, "note": self.note}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchRun":
        return cls(
            id=str(data.get("id", "")),
            created_at=str(data.get("created_at", "")),
            symbol=str(data.get("symbol", "")),
            timeframe=str(data.get("timeframe", "")),
            style=str(data.get("style", "")),
            proposer=str(data.get("proposer", "")),
            experiments=int(data.get("experiments", 0) or 0),
            survivors=int(data.get("survivors", 0) or 0),
            combinations=int(data.get("combinations", 0) or 0),
            best_score=(None if data.get("best_score") is None
                        else float(data["best_score"])),
            best_label=str(data.get("best_label", "")),
            elapsed=float(data.get("elapsed", 0.0) or 0.0),
            note=str(data.get("note", "")))


class ResearchStore:
    """The library of research runs under ``<workspace>/research``."""

    def __init__(self, workspace: Workspace | str | Path) -> None:
        space = (workspace if isinstance(workspace, Workspace)
                 else Workspace(Path(workspace)))
        self.workspace = space
        self.dir: Path = space.research
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(
                f"The research folder could not be created at {self.dir}.",
                detail=str(exc)) from exc

    def __repr__(self) -> str:              # pragma: no cover - diagnostic
        return f"<ResearchStore at {self.dir}>"

    # -- locations -------------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.dir / INDEX_FILENAME

    def path_for(self, run_id: str) -> Path:
        return self.dir / f"{_safe_id(run_id)}.json"

    # -- reading ---------------------------------------------------------

    def list(self) -> list[ResearchRun]:
        """Every run, newest first.

        A corrupt index is reported and treated as empty rather than raised:
        losing the list of past research is bad, and failing to open the
        application because of it is worse.
        """
        try:
            raw = self.index_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        except OSError as exc:
            log.warning("The research index could not be read: %s", exc)
            return []
        try:
            data = json.loads(raw)
        except ValueError as exc:
            log.warning("The research index is not valid JSON (%s); treating "
                        "it as empty. The run files themselves are untouched.",
                        exc)
            return []
        rows = data.get("runs", []) if isinstance(data, dict) else []
        out: list[ResearchRun] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                out.append(ResearchRun.from_dict(row))
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda r: r.created_at, reverse=True)
        return out

    def load(self, run_id: str) -> dict[str, Any] | None:
        """The whole stored report, or None when it is missing or unreadable."""
        try:
            return json.loads(self.path_for(run_id).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            log.warning("Research run %s could not be read: %s", run_id, exc)
            return None

    # -- writing ---------------------------------------------------------

    def save(self, report: Any, *, proposer: str = "systematic",
             timeframe: str = "", note: str = "") -> ResearchRun:
        """Store one loop report and return the row that summarises it."""
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        run_id = f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-" \
                 f"{_safe_id(getattr(report, 'symbol', 'run'))}"

        survivors = list(getattr(report, "survivors", ()) or ())
        best_score = None
        best_label = ""
        if survivors:
            best = survivors[0]
            score = getattr(getattr(best, "robustness", None), "total", None)
            if score is not None and score == score:      # not NaN
                best_score = round(float(score), 1)
            best_label = getattr(best, "label", "")

        row = ResearchRun(
            id=run_id, created_at=stamp,
            symbol=getattr(report, "symbol", ""), timeframe=timeframe,
            style=getattr(report, "style", ""), proposer=proposer,
            experiments=len(getattr(report, "experiments", ()) or ()),
            survivors=len(survivors),
            combinations=int(getattr(report, "total_combinations", 0) or 0),
            best_score=best_score, best_label=best_label,
            elapsed=float(getattr(report, "elapsed", 0.0) or 0.0), note=note)

        payload = {"run": row.to_dict()}
        dump = getattr(report, "to_dict", None)
        payload["report"] = dump() if callable(dump) else {}

        self._write(self.path_for(run_id), payload)
        self._append_to_index(row)
        return row

    def remove(self, run_id: str) -> None:
        """Delete one run and its index row."""
        try:
            self.path_for(run_id).unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise StorageError(f"Research run {run_id} could not be deleted.",
                               detail=str(exc)) from exc
        rows = [r for r in self.list() if r.id != run_id]
        self._write(self.index_path, {"runs": [r.to_dict() for r in rows]})

    # -- the file layer --------------------------------------------------

    def _append_to_index(self, row: ResearchRun) -> None:
        rows = [r for r in self.list() if r.id != row.id]
        rows.insert(0, row)
        self._write(self.index_path, {"runs": [r.to_dict() for r in rows]})

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        """Write through a temporary file, so a crash cannot leave a half file.

        A truncated index would lose every past run; a truncated run file would
        be a research record that cannot be opened. Neither is worth the two
        lines this costs.
        """
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise StorageError(
                f"The research record could not be written to {path}.",
                detail=str(exc)) from exc
