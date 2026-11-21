#Requires -Version 5.1
<#
.SYNOPSIS
    Construit les binaires PyInstaller Windows (GUI et CLI) des trois applications Lattice.
.DESCRIPTION
    Pour chaque application selectionnee, produit deux binaires a partir de la meme
    version de code : un executable fenetre (LatticeDither/GLYPH/GLITCH.exe) et un
    executable console (lattice-*-cli.exe). PyInstaller est un outil de build : il
    n'est pas ajoute aux dependances d'execution. Un manifeste par binaire est ecrit
    dans build\manifests pour que tools\check_versions.py prouve la coherence 1.0.0.
.PARAMETER App
    Application a construire : dither, glyph, glitch ou all (defaut all).
.PARAMETER Mode
    gui, cli ou all (defaut all).
.PARAMETER NoOneFile
    Construit un dossier au lieu d'un executable monofichier.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_exe.ps1 -App all
#>
[CmdletBinding()]
param(
    [ValidateSet('dither', 'glyph', 'glitch', 'all')][string]$App = 'all',
    [ValidateSet('gui', 'cli', 'all')][string]$Mode = 'all',
    [switch]$NoOneFile
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$SpecDir = Join-Path $PSScriptRoot 'packaging'
$Checker = Join-Path $ProjectRoot 'tools\check_versions.py'
$DistDir = Join-Path $ProjectRoot 'dist'
$WorkDir = Join-Path $ProjectRoot 'build\pyinstaller'
$Apps = if ($App -eq 'all') { @('dither', 'glyph', 'glitch') } else { @($App) }
$Modes = if ($Mode -eq 'all') { @('gui', 'cli') } else { @($Mode) }

function Fail([string]$Label, [string]$Message) {
    throw "LATTICE BUILD ERROR: ${Label}: ${Message}"
}

function Get-BinaryName([string]$AppName, [string]$BuildMode) {
    $table = @{
        'dither.gui' = 'LatticeDither'; 'dither.cli' = 'lattice-dither-cli'
        'glyph.gui' = 'LatticeGlyph'; 'glyph.cli' = 'lattice-glyph-cli'
        'glitch.gui' = 'LatticeGlitch'; 'glitch.cli' = 'lattice-glitch-cli'
    }
    $key = "${AppName}.${BuildMode}"
    if (-not $table.ContainsKey($key)) { Fail $key 'paire application/mode inconnue' }
    return [string]$table[$key]
}

function Get-DataArguments([string]$AppName) {
    $items = @('data;data', 'presets;presets', 'assets;assets',
               'lattice_core\data;lattice_core\data',
               'lattice_core\palettes\data;lattice_core\palettes\data')
    switch ($AppName) {
        'dither' { $items += 'lattice_dither\i18n;lattice_dither\i18n' }
        'glyph' { $items += 'lattice_glyph\presets;lattice_glyph\presets' }
        'glitch' { $items += 'lattice_glitch\presets;lattice_glitch\presets' }
    }
    return $items
}

function Assert-Prerequisites {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        Fail 'python' "interpreteur introuvable: $Python"
    }
    & $Python -c 'import PyInstaller' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Fail 'pyinstaller' 'PyInstaller absent : outil de build uniquement, aucune dependance runtime'
    }
    & $Python -c 'import numpy, numba, PIL, PySide6' 2>$null
    if ($LASTEXITCODE -ne 0) { Fail 'dependances' 'numpy/numba/Pillow/PySide6 requis' }
    if (-not (Test-Path -LiteralPath $Checker -PathType Leaf)) {
        Fail 'checker' "verificateur de versions introuvable: $Checker"
    }
    & $Python $Checker --distributions-only 2>$null
    if ($LASTEXITCODE -ne 0) { Fail 'versions' 'les pyproject ne sont pas a 1.0.0' }
    New-Item -ItemType Directory -Force -Path $DistDir, $WorkDir | Out-Null
}

function Invoke-Build([string]$AppName, [string]$BuildMode) {
    $spec = Join-Path $SpecDir "lattice_${AppName}.spec"
    if (-not (Test-Path -LiteralPath $spec -PathType Leaf)) {
        Fail "$AppName/$BuildMode" "spec introuvable: $spec"
    }
    $name = Get-BinaryName $AppName $BuildMode
    $arguments = @('-m', 'PyInstaller', '--noconfirm', '--clean')
    if ($BuildMode -eq 'gui') { $arguments += '--windowed' }
    if ($AppName -eq 'dither' -and $BuildMode -eq 'gui') {
        $icon = Join-Path $ProjectRoot 'assets\lattice_dither.ico'
        if (Test-Path -LiteralPath $icon -PathType Leaf) { $arguments += @('--icon', $icon) }
    }
    if (-not $NoOneFile) { $arguments += '--onefile' }
    $arguments += @('--name', $name, '--distpath', $DistDir)
    $arguments += @('--workpath', (Join-Path $WorkDir "${AppName}-${BuildMode}"))
    foreach ($item in (Get-DataArguments $AppName)) { $arguments += @('--add-data', $item) }
    foreach ($module in @('numba', 'llvmlite')) {
        $arguments += @('--collect-submodules', $module)
    }
    if ($AppName -eq 'dither') {
        $arguments += @('--hidden-import', 'imageio_ffmpeg')
        $arguments += @('--collect-data', 'imageio_ffmpeg')
    }
    foreach ($excluded in @('numba.tests', 'llvmlite.tests', 'tkinter', 'pytest',
                            'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick')) {
        $arguments += @('--exclude-module', $excluded)
    }
    $arguments += $spec

    $env:LATTICE_BUILD_MODE = $BuildMode
    try {
        Push-Location $ProjectRoot
        & $Python @arguments
        if ($LASTEXITCODE -ne 0) {
            Fail "$AppName/$BuildMode" "PyInstaller a echoue (code $LASTEXITCODE)"
        }
    } finally {
        Pop-Location
        Remove-Item Env:\LATTICE_BUILD_MODE -ErrorAction SilentlyContinue
    }

    $output = if ($NoOneFile) {
        Join-Path $DistDir "$name\$name.exe"
    } else {
        Join-Path $DistDir "$name.exe"
    }
    if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
        Fail "$AppName/$BuildMode" "binaire absent apres build: $output"
    }
    & $Python $Checker --emit-manifest $AppName windows $BuildMode $output
    if ($LASTEXITCODE -ne 0) { Fail "$AppName/$BuildMode" 'manifeste de build non ecrit' }
    $size = [math]::Round((Get-Item -LiteralPath $output).Length / 1MB, 1)
    Write-Host "built $output ($size MB)"
}

Assert-Prerequisites
foreach ($application in $Apps) {
    foreach ($buildMode in $Modes) { Invoke-Build $application $buildMode }
}
& $Python $Checker
if ($LASTEXITCODE -ne 0) {
    Fail 'release' 'les deux binaires ne partagent pas la meme version de code'
}
Write-Host 'LATTICE BUILD OK'
exit 0
