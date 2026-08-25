"""Application paths and persisted user settings.

Everything the application writes lives under one workspace directory so a user
can back it up, sync it or move it wholesale.  Nothing is written outside it
except the workspace *pointer* itself, which lives in the per-user config
directory.

No data leaves the machine.  There is no network code in this application other
than what the user's own future data providers might add.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

APP_NAME = "TradingBacktester"
APP_DISPLAY_NAME = "Trading Backtester"
APP_VERSION = "1.0.0"
APP_ORG = "TradingBacktester"


def _platform_config_dir() -> Path:
    """Per-user config directory, following each platform's convention."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME.lower()


def default_workspace_dir() -> Path:
    """Where a fresh install puts its workspace."""
    if sys.platform.startswith("win"):
        docs = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Documents"
        return docs / APP_NAME
    return Path.home() / APP_NAME


@dataclass
class Workspace:
    """The on-disk project layout.

    ::

        TradingBacktester/
          data/          imported datasets (parquet) + an index
          strategies/    one .json per strategy
          backtests/     saved runs, one folder each
          reports/       exported CSV/HTML/PDF
          settings/      instruments.json, ui state
          logs/          rotating log files
          samples/       the bundled synthetic dataset
    """

    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser()

    @property
    def data(self) -> Path: return self.root / "data"
    @property
    def strategies(self) -> Path: return self.root / "strategies"
    @property
    def backtests(self) -> Path: return self.root / "backtests"
    @property
    def reports(self) -> Path: return self.root / "reports"
    @property
    def settings(self) -> Path: return self.root / "settings"
    @property
    def logs(self) -> Path: return self.root / "logs"
    @property
    def samples(self) -> Path: return self.root / "samples"

    def all_dirs(self) -> list[Path]:
        return [self.root, self.data, self.strategies, self.backtests,
                self.reports, self.settings, self.logs, self.samples]

    def ensure(self) -> "Workspace":
        """Create every directory if it does not already exist."""
        from .core.errors import StorageError

        for d in self.all_dirs():
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StorageError(
                    f"The workspace folder could not be created at {d}.\n\n"
                    f"Choose a different location from File > Change Workspace.",
                    detail=repr(exc),
                ) from exc
        return self


@dataclass
class AppSettings:
    """User preferences persisted between sessions."""

    workspace_dir: str = ""
    theme: str = "dark"
    last_dataset: str = ""
    last_strategy: str = ""
    chart_bars_visible: int = 300
    confirm_on_delete: bool = True
    recent_files: list[str] = field(default_factory=list)
    window_geometry: str = ""
    window_state: str = ""
    log_level: str = "INFO"
    price_scale_right: bool = True
    show_volume: bool = True
    decimal_places: int = 2

    @staticmethod
    def path() -> Path:
        return _platform_config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "AppSettings":
        p = cls.path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                known = set(cls.__dataclass_fields__)
                return cls(**{k: v for k, v in data.items() if k in known})
            except Exception:
                # A damaged settings file must never stop the app from starting.
                pass
        return cls()

    def save(self) -> None:
        p = self.path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
            tmp.replace(p)
        except OSError:
            pass  # Preferences are a convenience; failing to save one is not fatal.

    def workspace(self) -> Workspace:
        root = Path(self.workspace_dir) if self.workspace_dir else default_workspace_dir()
        return Workspace(root)

    def push_recent(self, path: str, limit: int = 10) -> None:
        items = [p for p in self.recent_files if p != path]
        items.insert(0, path)
        self.recent_files = items[:limit]


def resource_path(*parts: str) -> Path:
    """Locate a bundled read-only resource, in dev and inside a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)


def app_info() -> dict[str, Any]:
    return {"name": APP_DISPLAY_NAME, "version": APP_VERSION,
            "python": sys.version.split()[0], "platform": sys.platform}
