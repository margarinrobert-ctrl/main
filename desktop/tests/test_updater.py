"""Updating in place from a downloaded file.

The scripts are RUN, not just generated, wherever PowerShell exists -- this
machine's `pwsh`, or Windows' own. The installer path itself needs Windows
and is exercised by the Windows build; here its script is parsed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from tradingbacktester import updater

PWSH = os.environ.get("PWSH") or shutil.which("pwsh") or shutil.which("powershell")
needs_pwsh = pytest.mark.skipif(PWSH is None, reason="PowerShell is not installed")


def _portable(folder: Path, marker: str, extra: str) -> Path:
    app = folder / "TradingBacktester"
    (app / "_internal").mkdir(parents=True)
    (app / updater.EXE_NAME).write_text(marker)
    (app / "_internal" / extra).write_text(marker)
    return app


def _setup_bytes(product: str = updater.PRODUCT_NAME) -> bytes:
    """The parts of an Inno Setup installer the updater looks at."""
    return (b"MZ" + b"\0" * 100 + b"Inno Setup Setup Data (6.2.0)" + b"\0" * 64
            + product.encode("utf-16-le") + b"\0" * 100)


def _zip_of(app: Path, target: Path) -> Path:
    with zipfile.ZipFile(target, "w") as archive:
        for path in app.rglob("*"):
            archive.write(path, Path(app.name) / path.relative_to(app))
    return target


def _run(script: str, where: Path) -> subprocess.CompletedProcess:
    path = where / "apply-update.ps1"
    path.write_text(script, encoding="utf-8-sig")
    return subprocess.run([PWSH, "-NoProfile", "-File", str(path)],
                          capture_output=True, text=True, timeout=120)


# --------------------------------------------------------------------------
# Recognising an update
# --------------------------------------------------------------------------

def test_an_installer_is_recognised_and_a_random_exe_is_not(tmp_path):
    good = tmp_path / "TradingBacktesterSetup.exe"
    good.write_bytes(_setup_bytes())
    assert updater.inspect_update(good).ok
    # Another product's Inno Setup installer is not this application's.
    foreign = tmp_path / "Git-2.45.1-64-bit.exe"
    foreign.write_bytes(_setup_bytes("Git"))
    assert "not this application's installer" in updater.inspect_update(foreign).reason
    other = tmp_path / "other.exe"
    other.write_bytes(b"MZ" + b"\0" * 1000)
    assert "not this application's installer" in updater.inspect_update(other).reason
    text = tmp_path / "notes.exe"
    text.write_text("hello")
    assert "not a Windows program" in updater.inspect_update(text).reason


def test_a_portable_zip_must_contain_the_application(tmp_path):
    app = _portable(tmp_path / "src", "new", "a.dll")
    assert updater.inspect_update(_zip_of(app, tmp_path / "ok.zip")).ok
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("readme.txt", "x")
    assert "does not contain" in updater.inspect_update(empty).reason
    assert not updater.inspect_update(tmp_path / "missing.zip").ok
    assert not updater.inspect_update(tmp_path / "x.txt").ok


def test_the_kind_of_copy_is_read_from_its_folder(tmp_path):
    assert updater.install_kind(None) == "source"
    assert updater.install_kind(tmp_path) == "portable"
    (tmp_path / "unins000.exe").write_text("")
    assert updater.install_kind(tmp_path) == "installed"


def test_the_installer_script_installs_silently_into_this_folder(tmp_path):
    exe = tmp_path / "TradingBacktesterSetup.exe"
    exe.write_bytes(_setup_bytes())
    script = updater.build_script(updater.inspect_update(exe),
                                  Path("C:/Users/me/App's dir"), 4242,
                                  tmp_path / "update.log")
    for piece in ("/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS",
                  "Get-Process -Id 4242", "'C:/Users/me/App''s dir'",
                  "Start-Process -FilePath $relaunch"):
        assert piece in script, piece


# --------------------------------------------------------------------------
# Running the scripts
# --------------------------------------------------------------------------

@needs_pwsh
def test_both_scripts_parse_in_powershell(tmp_path):
    exe = tmp_path / "Setup.exe"
    exe.write_bytes(_setup_bytes())
    app = _portable(tmp_path / "old", "old", "a.dll")
    z = _zip_of(_portable(tmp_path / "new", "new", "b.dll"), tmp_path / "u.zip")
    for update in (updater.inspect_update(exe), updater.inspect_update(z)):
        script = updater.build_script(update, app, 1, tmp_path / "log.txt")
        path = tmp_path / "parse.ps1"
        path.write_text(script, encoding="utf-8-sig")
        check = ("$e = $null; [void][System.Management.Automation.Language.Parser]"
                 "::ParseFile('" + str(path) + "', [ref]$null, [ref]$e); "
                 "if ($e.Count) { $e | ForEach-Object { $_.Message }; exit 1 }")
        done = subprocess.run([PWSH, "-NoProfile", "-Command", check],
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stdout + done.stderr


@needs_pwsh
def test_the_portable_update_swaps_the_folder_and_waits_for_the_app(tmp_path):
    base = tmp_path / "My App's folder"
    app = _portable(base, "old", "old.dll")
    z = _zip_of(_portable(tmp_path / "build", "new", "new.dll"), tmp_path / "TB-portable.zip")
    log = tmp_path / "update.log"
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    # Reap it when it ends: on Linux an unreaped child lingers as a zombie that
    # still answers to its PID. (Windows has no zombies; the app just exits.)
    import threading
    threading.Thread(target=sleeper.wait, daemon=True).start()
    started = time.monotonic()
    done = _run(updater.build_script(updater.inspect_update(z), app, sleeper.pid, log,
                                     relaunch=False), tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert time.monotonic() - started >= 2.5          # waited for the old process
    assert (app / updater.EXE_NAME).read_text() == "new"
    assert (app / "_internal" / "new.dll").exists()
    assert not (app / "_internal" / "old.dll").exists()   # a swap, not a mix
    leftovers = [p.name for p in base.iterdir() if p.name != "TradingBacktester"]
    assert leftovers == []
    assert "update installed" in log.read_text()


@needs_pwsh
def test_a_bad_update_keeps_the_copy_that_was_there(tmp_path):
    app = _portable(tmp_path / "apps", "old", "old.dll")
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("TradingBacktester/readme.txt", "no exe here")
    forged = updater.UpdateFile(bad, "zip", True)       # skip the check on purpose
    log = tmp_path / "update.log"
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()                                         # a PID that has exited
    done = _run(updater.build_script(forged, app, gone.pid, log, relaunch=False),
                tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (app / updater.EXE_NAME).read_text() == "old"
    assert (app / "_internal" / "old.dll").exists()
    assert "FAILED" in log.read_text()
    # No unpacked copy is left lying beside the application.
    assert [p.name for p in app.parent.iterdir()] == ["TradingBacktester"]


# -- the menu command ---------------------------------------------------------


@pytest.fixture
def window(qapp, tmp_path):
    from tradingbacktester.config import AppSettings, Workspace
    from tradingbacktester.ui.main_window import MainWindow

    workspace = Workspace(tmp_path / "ws").ensure()
    settings = AppSettings()
    settings.workspace_dir = str(workspace.root)
    return MainWindow(settings, workspace)


def _menu_update(window, monkeypatch, tmp_path, kind, update_file, answer):
    """Drive Help > Update from a Downloaded File with the dialogs stubbed."""
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

    import tradingbacktester.ui.main_window as mw

    calls = {"launched": None, "quit": 0, "errors": [], "infos": []}
    app_dir = tmp_path / "app"
    monkeypatch.setattr(updater, "install_kind", lambda directory=None: kind)
    monkeypatch.setattr(updater, "app_directory", lambda: app_dir)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(update_file), "")))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: answer))
    monkeypatch.setattr(updater, "launch",
                        lambda script, directory: calls.__setitem__("launched", script))
    monkeypatch.setattr(QApplication, "quit",
                        staticmethod(lambda: calls.__setitem__("quit", calls["quit"] + 1)))
    monkeypatch.setattr(mw, "show_error",
                        lambda parent, message, *a, **k: calls["errors"].append(str(message)))
    monkeypatch.setattr(mw, "show_info",
                        lambda parent, title, message, *a, **k: calls["infos"].append(message))
    window.on_update_from_file()
    return calls, app_dir


def test_the_menu_installs_a_portable_zip_and_quits(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    new = _zip_of(_portable(tmp_path / "new", "new", "lib.dll"), tmp_path / "u.zip")
    calls, app_dir = _menu_update(window, monkeypatch, tmp_path, "portable", new,
                                  QMessageBox.StandardButton.Yes)
    assert calls["errors"] == [] and calls["infos"] == []
    script = calls["launched"]
    assert script and str(app_dir) in script and str(new) in script
    assert f"Get-Process -Id {os.getpid()}" in script      # waits for THIS process
    assert "Start-Process -FilePath $relaunch" in script          # and reopens it
    assert calls["quit"] == 1


def test_the_menu_does_nothing_when_the_user_says_no(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    new = _zip_of(_portable(tmp_path / "new", "new", "lib.dll"), tmp_path / "u.zip")
    calls, _ = _menu_update(window, monkeypatch, tmp_path, "portable", new,
                            QMessageBox.StandardButton.No)
    assert calls["launched"] is None and calls["quit"] == 0


def test_the_menu_refuses_the_wrong_kind_of_update(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    yes = QMessageBox.StandardButton.Yes
    new = _zip_of(_portable(tmp_path / "new", "new", "lib.dll"), tmp_path / "u.zip")
    calls, _ = _menu_update(window, monkeypatch, tmp_path, "installed", new, yes)
    assert calls["launched"] is None and calls["quit"] == 0
    assert "TradingBacktesterSetup.exe" in calls["errors"][0]

    setup = tmp_path / "TradingBacktesterSetup.exe"
    setup.write_bytes(_setup_bytes())
    calls, _ = _menu_update(window, monkeypatch, tmp_path, "portable", setup, yes)
    assert calls["launched"] is None
    assert "TradingBacktester-portable.zip" in calls["errors"][0]

    junk = tmp_path / "notes.txt"
    junk.write_text("hello")
    calls, _ = _menu_update(window, monkeypatch, tmp_path, "portable", junk, yes)
    assert calls["launched"] is None and calls["errors"]


def test_running_from_source_explains_instead_of_updating(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    calls, _ = _menu_update(window, monkeypatch, tmp_path, "source", tmp_path / "x.zip",
                            QMessageBox.StandardButton.Yes)
    assert calls["launched"] is None and "git" in calls["infos"][0]


def test_a_workspace_inside_the_portable_folder_is_never_swapped_away(
        qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox

    from tradingbacktester.config import AppSettings, Workspace
    from tradingbacktester.ui.main_window import MainWindow

    app_dir = tmp_path / "app"
    workspace = Workspace(app_dir / "workspace").ensure()
    settings = AppSettings()
    settings.workspace_dir = str(workspace.root)
    win = MainWindow(settings, workspace)
    new = _zip_of(_portable(tmp_path / "new", "new", "lib.dll"), tmp_path / "u.zip")
    calls, used_dir = _menu_update(win, monkeypatch, tmp_path, "portable", new,
                                   QMessageBox.StandardButton.Yes)
    assert used_dir == app_dir
    assert calls["launched"] is None and calls["quit"] == 0
    assert "Change Workspace Folder" in calls["errors"][0]
    assert updater.is_inside(app_dir / "workspace", app_dir)
    assert not updater.is_inside(tmp_path / "elsewhere", app_dir)


@needs_pwsh
@pytest.mark.parametrize("rollback_fails", [False, True])
def test_a_failed_swap_puts_the_old_copy_back_or_says_where_it_is(tmp_path, rollback_fails):
    app = _portable(tmp_path / "apps", "old", "old.dll")
    z = _zip_of(_portable(tmp_path / "build", "new", "new.dll"), tmp_path / "u.zip")
    log = tmp_path / "update.log"
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    script = updater.build_script(updater.inspect_update(z), app, gone.pid, log,
                                  relaunch=False)
    # Inject the failures a locked or vanished folder would cause.
    move_new = "      Move-Item -LiteralPath $newDir -Destination $appDir"
    move_back = "        Move-Item -LiteralPath $backup -Destination $appDir"
    assert move_new in script and move_back in script
    script = script.replace(move_new, "      throw 'injected: the new folder would not move'")
    if rollback_fails:
        script = script.replace(move_back, "        throw 'injected: nor would the old one'")
    done = _run(script, tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    text = log.read_text()
    left = sorted(p.name for p in app.parent.iterdir())
    assert not any(".update-" in name for name in left)      # stage cleaned up
    if not rollback_fails:
        assert "the previous version is kept" in text
        assert left == ["TradingBacktester"]
        assert (app / updater.EXE_NAME).read_text() == "old"
    else:
        assert "could not be moved back" in text and "previous version is kept" not in text
        backup = [name for name in left if ".previous-" in name]
        assert len(backup) == 1 and backup[0] in text
        assert (app.parent / backup[0] / updater.EXE_NAME).read_text() == "old"
