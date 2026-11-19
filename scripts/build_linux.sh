#!/usr/bin/env bash
# Construit les deux binaires PyInstaller de Lattice : la fenetre (GUI) et la ligne de commande.
# PyInstaller est un outil de build : aucune dependance d'execution n'est ajoutee.
#
# Lattice 1.0 est un seul programme : un spec, deux binaires (un fenetre, un console) qui
# portent la meme version et sortent du meme arbre source.
#
# L'interpreteur vient de PYTHON s'il est defini, sinon du venv du depot, sinon de celui qui
# execute ce script. Sans ce troisieme cas la CI echoue : sur un runner il n'y a pas de .venv,
# et le Python installe est celui du systeme.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -n "${PYTHON:-}" ]]; then
    PYTHON="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
else
    PYTHON="$(command -v python3 || command -v python)"
fi
SPEC_DIR="$SCRIPT_DIR/packaging"
DIST_DIR="${DIST_DIR:-$ROOT/dist}"
WORK_DIR="${WORK_DIR:-$ROOT/build/pyinstaller}"
CHECKER="$ROOT/tools/check_versions.py"
MODES="${MODES:-gui cli}"

log() { printf '[Lattice build] %s\n' "$1"; }
die() {
    printf 'LATTICE BUILD ERROR: %s: %s\n' "$1" "$2" >&2
    exit 1
}

binary_name() {
    case "$1" in
        gui) printf 'Lattice' ;;
        cli) printf 'lattice-cli' ;;
        *)   return 1 ;;
    esac
}

[[ -x "$PYTHON" ]] || die "python" "interpreteur introuvable: $PYTHON"
"$PYTHON" -c 'import PyInstaller' 2>/dev/null ||
    die "pyinstaller" "PyInstaller absent de $PYTHON (outil de build, pas une dependance runtime)"
"$PYTHON" -c 'import numpy, numba, PIL, PySide6' 2>/dev/null ||
    die "dependances" "numpy/numba/Pillow/PySide6 requis dans $PYTHON"

mkdir -p "$DIST_DIR" "$WORK_DIR"
log "versions verifiees par $CHECKER"
"$PYTHON" "$CHECKER" --distributions-only >/dev/null ||
    die "versions" "le pyproject racine n'est pas a la version attendue"

spec="$SPEC_DIR/lattice.spec"
[[ -f "$spec" ]] || die "spec" "spec introuvable: $spec"

for mode in $MODES; do
    name="$(binary_name "$mode")" || die "$mode" "mode de build inconnu"
    log "build $mode -> $name"
    LATTICE_BUILD_MODE="$mode" "$PYTHON" -m PyInstaller \
        --noconfirm --clean \
        --distpath "$DIST_DIR" \
        --workpath "$WORK_DIR/$mode" \
        "$spec" || die "$mode" "PyInstaller a echoue"
    output="$DIST_DIR/$name"
    [[ -f "$output" ]] || die "$mode" "binaire absent apres build: $output"
    chmod +x "$output"
    "$PYTHON" "$CHECKER" --emit-manifest lattice linux "$mode" "$output" \
        || die "$mode" "manifest de build non ecrit"
    log "$mode -> $output"
done

"$PYTHON" "$CHECKER" || die "release" "les binaires ne partagent pas la meme version de code"
log "termine : binaires dans $DIST_DIR"
