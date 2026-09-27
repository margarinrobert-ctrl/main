<#
.SYNOPSIS
    Builds Trading Backtester into dist\TradingBacktester\ and, if Inno Setup is
    installed, into dist\TradingBacktesterSetup.exe.

.DESCRIPTION
    Run from the repository's desktop\ directory in PowerShell on Windows 10 or
    11 with Python 3.10+ on PATH:

        .\packaging\build_windows.ps1

    The script creates an isolated build virtual environment so whatever is in
    your global site-packages cannot leak into the bundle.

.PARAMETER SkipTests
    Skip the test suite. The default is to run it and refuse to build on failure,
    because shipping a build whose tests fail is worse than not shipping.

.PARAMETER SkipInstaller
    Produce only the unpacked application directory.
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "Building Trading Backtester in $Root" -ForegroundColor Cyan

# --- 1. Python -----------------------------------------------------------
$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) {
    throw "Python 3.10 or newer was not found on PATH. Install it from python.org and tick 'Add python.exe to PATH'."
}
$versionText = & $python.Source -c "import sys;print('%d.%d' % sys.version_info[:2])"
Write-Host "Using Python $versionText at $($python.Source)"
if ([version]$versionText -lt [version]"3.10") {
    throw "Python $versionText is too old. Version 3.10 or newer is required."
}

# --- 2. Build virtual environment ---------------------------------------
$venv = Join-Path $Root ".buildenv"
if (-not (Test-Path $venv)) {
    Write-Host "Creating the build virtual environment..." -ForegroundColor Cyan
    & $python.Source -m venv $venv
}
$vpy = Join-Path $venv "Scripts\python.exe"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r requirements.txt --quiet
& $vpy -m pip install pyinstaller pytest --quiet

# --- 3. Icon -------------------------------------------------------------
Write-Host "Generating the application icon..." -ForegroundColor Cyan
$env:QT_QPA_PLATFORM = "offscreen"
& $vpy -c @"
import sys
sys.path.insert(0, r'$Root')
from PySide6.QtWidgets import QApplication
app = QApplication([])
from tradingbacktester.ui.icons import save_app_icon_ico
save_app_icon_ico(r'$Root\assets\app.ico')
print('assets/app.ico written')
"@
Remove-Item Env:\QT_QPA_PLATFORM

# --- 4. Tests ------------------------------------------------------------
if (-not $SkipTests) {
    Write-Host "Running the test suite..." -ForegroundColor Cyan
    & $vpy -m pytest tests -q
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed. Fix them before building, or pass -SkipTests deliberately."
    }
}

# --- 5. Freeze -----------------------------------------------------------
Write-Host "Running PyInstaller..." -ForegroundColor Cyan
Remove-Item -Recurse -Force (Join-Path $Root "build") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $Root "dist\TradingBacktester") -ErrorAction SilentlyContinue
& $vpy -m PyInstaller packaging\TradingBacktester.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$exe = Join-Path $Root "dist\TradingBacktester\TradingBacktester.exe"
if (-not (Test-Path $exe)) { throw "PyInstaller reported success but $exe is missing." }
$sizeMb = [math]::Round((Get-ChildItem (Join-Path $Root "dist\TradingBacktester") -Recurse |
    Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host "Built dist\TradingBacktester ($sizeMb MB)" -ForegroundColor Green

# --- 6. Smoke test the frozen build -------------------------------------
Write-Host "Smoke-testing the frozen application..." -ForegroundColor Cyan
$proc = Start-Process -FilePath $exe -ArgumentList "--self-test" -PassThru -Wait -WindowStyle Hidden
if ($proc.ExitCode -ne 0) {
    throw "The frozen application failed its self-test with exit code $($proc.ExitCode)."
}
Write-Host "Self-test passed." -ForegroundColor Green

# --- 7. Installer --------------------------------------------------------
if ($SkipInstaller) { Write-Host "Skipping the installer as requested."; exit 0 }

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Warning @"
Inno Setup 6 was not found, so dist\TradingBacktesterSetup.exe was not built.
The application itself is complete and runnable at:
    dist\TradingBacktester\TradingBacktester.exe
To build the installer, install Inno Setup 6 from https://jrsoftware.org/isdl.php
and run this script again.
"@
    exit 0
}

Write-Host "Building the installer with $iscc..." -ForegroundColor Cyan
& $iscc packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }
Write-Host "Built dist\TradingBacktesterSetup.exe" -ForegroundColor Green
