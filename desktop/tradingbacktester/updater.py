"""Update the installed application from a downloaded file, in place.

The Windows installer carries a fixed AppId, so running a newer one over an
existing installation upgrades it: no uninstall, and the workspace in
Documents -- strategies, datasets, results -- is never touched. What this
module adds is doing it from inside the application:

1. :func:`inspect_update` checks that a file really is an update: the Inno
   Setup installer (``TradingBacktesterSetup.exe``) or the portable zip.
2. :func:`build_script` writes a small PowerShell script that waits for this
   process to exit, installs the update over this copy's folder, and starts
   the application again.
3. :func:`launch` starts that script detached; the caller then quits, so the
   files it is about to replace are no longer in use.

Nothing here touches the network. "Download the latest update" in the UI
opens the release page in the user's browser; the application itself never
fetches anything.

Every step the script takes is appended to ``update.log`` beside the
workspace's other logs, so a failed update leaves a reason behind. If the
install fails, the script still reopens the application that was there.
"""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

__all__ = ["RELEASE_PAGE", "EXE_NAME", "PRODUCT_NAME", "install_kind",
           "app_directory", "is_inside", "UpdateFile", "inspect_update",
           "build_script", "launch"]

RELEASE_PAGE = "https://github.com/margarinrobert-ctrl/main/releases/latest"
EXE_NAME = "TradingBacktester.exe"
#: The installer's version resource names the product (``VersionInfoProductName``
#: in packaging/installer.iss). Resource strings are UTF-16, as Windows stores them.
PRODUCT_NAME = "Trading Backtester"
_PRODUCT_MARK = PRODUCT_NAME.encode("utf-16-le")
#: Inno Setup writes this beside an installed application.
_UNINSTALLER = "unins000.exe"


def app_directory() -> Path | None:
    """The folder this copy runs from, when it is a frozen Windows build."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def is_inside(path: str | Path, directory: str | Path) -> bool:
    """Is ``path`` the folder ``directory`` or somewhere inside it?"""
    try:
        Path(path).resolve().relative_to(Path(directory).resolve())
    except ValueError:
        return False
    return True


def install_kind(directory: Path | None = None) -> str:
    """``installed``, ``portable`` or ``source`` (running from Python)."""
    directory = directory if directory is not None else app_directory()
    if directory is None:
        return "source"
    return "installed" if (directory / _UNINSTALLER).exists() else "portable"


@dataclass
class UpdateFile:
    path: Path
    kind: str            # "installer" or "zip"
    ok: bool
    reason: str = ""


def inspect_update(path: str | Path) -> UpdateFile:
    """Is ``path`` an update this application can install?"""
    path = Path(path)
    if not path.is_file():
        return UpdateFile(path, "", False, f"There is no file at {path}.")
    suffix = path.suffix.lower()
    if suffix == ".exe":
        try:
            with open(path, "rb") as fh:
                head = fh.read(8 * 1024 * 1024)
        except OSError as exc:
            return UpdateFile(path, "installer", False,
                              f"{path.name} could not be read: {exc}")
        if not head.startswith(b"MZ"):
            return UpdateFile(path, "installer", False,
                              f"{path.name} is not a Windows program.")
        # An installer made with Inno Setup that is not THIS product's would
        # otherwise be run silently into this application's folder.
        if b"Inno Setup" not in head or _PRODUCT_MARK not in head:
            return UpdateFile(path, "installer", False,
                              f"{path.name} is not this application's installer. "
                              f"Use TradingBacktesterSetup.exe from the release page.")
        return UpdateFile(path, "installer", True)
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
        except (OSError, zipfile.BadZipFile) as exc:
            return UpdateFile(path, "zip", False,
                              f"{path.name} is not a readable zip: {exc}")
        if not any(n.replace("\\", "/").rsplit("/", 1)[-1] == EXE_NAME for n in names):
            return UpdateFile(path, "zip", False,
                              f"{path.name} does not contain {EXE_NAME}, so it is "
                              f"not the portable build of this application.")
        return UpdateFile(path, "zip", True)
    return UpdateFile(path, "", False,
                      "Choose TradingBacktesterSetup.exe or "
                      "TradingBacktester-portable.zip.")


def _ps(text: str | Path) -> str:
    """A PowerShell single-quoted string literal."""
    return "'" + str(text).replace("'", "''") + "'"


def build_script(update: UpdateFile, app_dir: Path, pid: int, log_path: Path,
                 relaunch: bool = True) -> str:
    """The PowerShell that installs ``update`` over ``app_dir`` once ``pid`` exits.

    The installer runs silently with ``/DIR`` set to this copy's folder, so an
    upgrade lands where the application already is. The zip is unpacked beside
    the folder and SWAPPED in -- the old folder is renamed, the new one moved
    into its place, and the old one deleted only after that succeeded -- so a
    failure half-way leaves the old copy, never a mixture of two versions.
    """
    if not update.ok:
        raise ValueError(update.reason)
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$log = {_ps(log_path)}",
        f"$appDir = {_ps(app_dir)}",
        f"$source = {_ps(update.path)}",
        f"$exe = Join-Path $appDir {_ps(EXE_NAME)}",
        "$relaunch = $exe",
        "$kept = $true",
        "$backup = ''",
        "function Log([string]$m) {",
        "  try { Add-Content -LiteralPath $log -Value ((Get-Date).ToString('u') + ' ' + $m) } catch {}",
        "}",
        "Log ('update started: ' + $source)",
        f"$old = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue",
        # Replacing files a running copy holds would fail half-way, and
        # relaunching would start a second copy: leave everything as it is.
        "if ($old -and -not $old.WaitForExit(120000)) {",
        "  Log 'update NOT installed: the application was still running two minutes later'",
        "  exit 1",
        "}",
        "try {",
    ]
    if update.kind == "installer":
        lines += [
            "  $arguments = @('/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART',",
            "                 '/CLOSEAPPLICATIONS', ('/DIR=\"' + $appDir + '\"'))",
            "  $p = Start-Process -FilePath $source -ArgumentList $arguments -Wait -PassThru",
            "  if ($p.ExitCode -ne 0) { throw ('the installer exited with code ' + $p.ExitCode) }",
        ]
    else:
        lines += [
            "  $stage = $appDir + '.update-' + [guid]::NewGuid().ToString('N')",
            "  try {",
            "    Expand-Archive -LiteralPath $source -DestinationPath $stage -Force",
            "    $root = Get-ChildItem -LiteralPath $stage -Recurse -Filter "
            + _ps(EXE_NAME) + " | Select-Object -First 1",
            "    if (-not $root) { throw 'the zip has no " + EXE_NAME + "' }",
            "    $newDir = $root.Directory.FullName",
            "    $backup = $appDir + '.previous-' + (Get-Date).ToString('yyyyMMddHHmmss')",
            "    Move-Item -LiteralPath $appDir -Destination $backup",
            "    try {",
            "      Move-Item -LiteralPath $newDir -Destination $appDir",
            "    } catch {",
            "      $err = $_",
            "      try {",
            "        Move-Item -LiteralPath $backup -Destination $appDir",
            "      } catch {",
            # The old copy is intact but under another name: say where, and
            # reopen it from there rather than leaving nothing to open.
            "        $kept = $false",
            "        $relaunch = Join-Path $backup " + _ps(EXE_NAME),
            "      }",
            "      throw $err",
            "    }",
            "    Remove-Item -LiteralPath $backup -Recurse -Force -ErrorAction SilentlyContinue",
            "  } finally {",
            # Never leave a whole unpacked copy lying beside the application.
            "    if (Test-Path -LiteralPath $stage) {",
            "      Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue",
            "    }",
            "  }",
        ]
    lines += [
        "  Log 'update installed'",
        "} catch {",
        "  if ($kept) {",
        "    Log ('update FAILED, the previous version is kept: ' + $_)",
        "  } else {",
        "    Log ('update FAILED: ' + $_ + ' -- and the previous version could not be '"
        " + 'moved back. It is complete, in ' + $backup + '. Rename that folder to '"
        " + $appDir + '.')",
        "  }",
        "}",
    ]
    if relaunch:
        lines.append("if (Test-Path -LiteralPath $relaunch) { Start-Process -FilePath $relaunch }")
    return "\r\n".join(lines) + "\r\n"


def launch(script: str, directory: Path) -> Path:
    """Write ``script`` and start it detached from this process (Windows)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "apply-update.ps1"
    # BOM: Windows PowerShell 5.1 reads a BOM-less script as the ANSI code
    # page, which breaks any non-ASCII character in a path.
    path.write_text(script, encoding="utf-8-sig")
    flags = 0
    for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
        flags |= getattr(subprocess, name, 0)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", str(path)],
        creationflags=flags, close_fds=True,
        cwd=os.environ.get("TEMP") or str(directory))
    return path
