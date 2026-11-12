#Requires -Version 5.1
<#
.SYNOPSIS
    Build the standalone LatticeDither.exe with PyInstaller.
.DESCRIPTION
    Produces dist\LatticeDither.exe, a single windowed executable that bundles the
    interpreter, PySide6, numpy, numba and llvmlite, the ffmpeg binary shipped by
    imageio-ffmpeg, plus data\, presets\ and assets\.
    PyInstaller is a build-time tool only: it is not in requirements.txt and the
    application never imports it.
.PARAMETER OneFile
    Build the single-file executable (default). Use -NoOneFile for a folder build,
    which starts faster because nothing is extracted at launch.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_exe.ps1
#>
[CmdletBinding()]
param(
    [switch]$NoOneFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$Launcher = Join-Path $ProjectRoot 'LatticeDither.pyw'
$Icon = Join-Path $ProjectRoot 'assets\lattice_dither.ico'

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "interpreter not found: $Python"
}

& $Python -c 'import PyInstaller' 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'PyInstaller is missing. Install it with: .venv\Scripts\python.exe -m pip install pyinstaller'
}

$arguments = @(
    '-m', 'PyInstaller'
    '--noconfirm'
    '--clean'
    '--windowed'
    '--name', 'LatticeDither'
    '--icon', $Icon
    '--add-data', 'data;data'
    '--add-data', 'presets;presets'
    '--add-data', 'assets;assets'
    '--collect-submodules', 'numba'
    '--collect-submodules', 'llvmlite'
    '--hidden-import', 'imageio_ffmpeg'
    '--collect-data', 'imageio_ffmpeg'
    '--exclude-module', 'numba.tests'
    '--exclude-module', 'llvmlite.tests'
    '--exclude-module', 'tkinter'
    '--exclude-module', 'pytest'
    '--exclude-module', 'PySide6.QtNetwork'
    '--exclude-module', 'PySide6.QtQml'
    '--exclude-module', 'PySide6.QtQuick'
)
if (-not $NoOneFile) {
    $arguments += '--onefile'
}
$arguments += $Launcher

Push-Location $ProjectRoot
try {
    & $Python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

$output = if ($NoOneFile) {
    Join-Path $ProjectRoot 'dist\LatticeDither\LatticeDither.exe'
} else {
    Join-Path $ProjectRoot 'dist\LatticeDither.exe'
}
if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
    throw "build finished but $output is missing"
}
$size = [math]::Round((Get-Item -LiteralPath $output).Length / 1MB, 1)
Write-Host "built $output ($size MB)"
