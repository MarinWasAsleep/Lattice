# Construit les deux binaires PyInstaller de Lattice sous Windows : la fenetre (GUI) et la
# ligne de commande. Equivalent de scripts/build_linux.sh pour la plateforme Windows.
#
# Lattice 1.0 est un seul programme : un spec, deux binaires (.exe) qui portent la meme version
# et sortent du meme arbre source.
[CmdletBinding()]
param(
    [string[]]$Modes = @("gui", "cli")
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$specDir = Join-Path $scriptDir "packaging"
$distDir = if ($env:DIST_DIR) { $env:DIST_DIR } else { Join-Path $root "dist" }
$workDir = if ($env:WORK_DIR) { $env:WORK_DIR } else { Join-Path $root "build/pyinstaller" }
$checker = Join-Path $root "tools/check_versions.py"

function Log($message) { Write-Host "[Lattice build] $message" }
function Die($tag, $message) {
    Write-Error "LATTICE BUILD ERROR: ${tag}: $message"
    exit 1
}

function BinaryName($mode) {
    # The two names must differ by more than their case: Windows file systems are
    # case-insensitive, so "Lattice" and "lattice" are the same file and the second build
    # silently overwrites the first.
    switch ($mode) {
        "gui" { return "Lattice" }
        "cli" { return "lattice-cli" }
        default { Die $mode "mode de build inconnu" }
    }
}

& $python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) { Die "pyinstaller" "PyInstaller absent (outil de build)" }

& $python -c "import numpy, numba, PIL, PySide6" 2>$null
if ($LASTEXITCODE -ne 0) { Die "dependances" "numpy/numba/Pillow/PySide6 requis" }

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $workDir | Out-Null

Log "versions verifiees par $checker"
& $python $checker --distributions-only
if ($LASTEXITCODE -ne 0) { Die "versions" "le pyproject racine n'est pas a la version attendue" }

$spec = Join-Path $specDir "lattice.spec"
if (-not (Test-Path $spec)) { Die "spec" "spec introuvable: $spec" }

foreach ($mode in $Modes) {
    $name = BinaryName $mode
    Log "build $mode -> $name"
    $env:LATTICE_BUILD_MODE = $mode
    & $python -m PyInstaller --noconfirm --clean `
        --distpath $distDir --workpath (Join-Path $workDir $mode) $spec
    if ($LASTEXITCODE -ne 0) { Die $mode "PyInstaller a echoue" }

    $output = Join-Path $distDir "$name.exe"
    if (-not (Test-Path $output)) { Die $mode "binaire absent apres build: $output" }

    & $python $checker --emit-manifest lattice windows $mode $output
    if ($LASTEXITCODE -ne 0) { Die $mode "manifest de build non ecrit" }
    Log "$mode -> $output"
}

& $python $checker
if ($LASTEXITCODE -ne 0) { Die "release" "les binaires ne partagent pas la meme version de code" }
Log "termine : binaires dans $distDir"
