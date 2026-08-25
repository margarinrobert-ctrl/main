# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the Windows build.

Produces a **onedir** bundle (``dist/TradingBacktester/``) rather than a
single-file exe.  A onefile build of a Qt application unpacks ~200 MB to a temp
directory on every launch, which adds several seconds of start-up and trips some
corporate antivirus heuristics.  The Inno Setup installer wraps the directory,
so the user still gets one ``TradingBacktesterSetup.exe`` to download.

Build:  pyinstaller packaging/TradingBacktester.spec --noconfirm
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent

block_cipher = None

# Qt modules the application never touches.  Excluding them takes roughly
# 250 MB off the bundle, which matters for a downloadable installer.
EXCLUDED_QT = [
    "PySide6.Qt3DAnimation", "PySide6.Qt3DCore", "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DRender",
    "PySide6.QtBluetooth", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtLocation",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuick3D", "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSpatialAudio", "PySide6.QtSql",
    "PySide6.QtStateMachine", "PySide6.QtTest", "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebSockets",
]

EXCLUDED_OTHER = [
    "tkinter", "matplotlib", "IPython", "notebook", "jupyter", "scipy",
    "sklearn", "torch", "PyQt5", "PyQt6", "PIL.ImageQt", "setuptools._distutils",
    "pytest", "_pytest", "sphinx", "numpy.f2py", "numpy.distutils",
]

hidden = [
    # pandas resolves these lazily, so the analyser cannot see them.
    "pandas._libs.tslibs.base",
    "pandas._libs.tslibs.np_datetime",
    "pandas._libs.tslibs.nattype",
    "pandas._libs.tslibs.timezones",
    "pandas.io.formats.style",
    # The indicator library is imported by name from the registry.
    "tradingbacktester.indicators.library",
]
hidden += collect_submodules("tradingbacktester")

datas = [
    (str(ROOT / "assets" / "app.ico"), "assets"),
    (str(ROOT / "docs" / "METRICS.md"), "docs"),
    (str(ROOT / "docs" / "BACKTEST_ASSUMPTIONS.md"), "docs"),
    (str(ROOT / "README.md"), "."),
]
datas = [(src, dst) for src, dst in datas if Path(src).exists()]

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[str(SPEC_DIR / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_QT + EXCLUDED_OTHER,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TradingBacktester",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX-packed Qt DLLs are a common false-positive trigger.
    console=False,      # A GUI application must not open a console window.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico") if (ROOT / "assets" / "app.ico").exists() else None,
    version=str(SPEC_DIR / "version_info.txt")
    if (SPEC_DIR / "version_info.txt").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="TradingBacktester",
)
