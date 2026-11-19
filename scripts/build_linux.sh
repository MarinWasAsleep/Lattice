#!/usr/bin/env bash
# Construit les binaires PyInstaller Linux (GUI et CLI) des trois applications Lattice.
# PyInstaller est un outil de build : aucune dépendance d'exécution n'est ajoutée.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
SPEC_DIR="$SCRIPT_DIR/packaging"
DIST_DIR="${DIST_DIR:-$ROOT/dist}"
WORK_DIR="${WORK_DIR:-$ROOT/build/pyinstaller}"
CHECKER="$ROOT/tools/check_versions.py"
APPS="${APPS:-dither glyph glitch}"
MODES="${MODES:-gui cli}"

log() { printf '[Lattice build] %s\n' "$1"; }
die() {
    printf 'LATTICE BUILD ERROR: %s: %s\n' "$1" "$2" >&2
    exit 1
}

binary_name() {
    case "$1:$2" in
        dither:gui) printf 'LatticeDither' ;;
        dither:cli) printf 'lattice-dither-cli' ;;
        glyph:gui)  printf 'LatticeGlyph' ;;
        glyph:cli)  printf 'lattice-glyph-cli' ;;
        glitch:gui) printf 'LatticeGlitch' ;;
        glitch:cli) printf 'lattice-glitch-cli' ;;
        *) return 1 ;;
    esac
}

[[ -x "$PYTHON" ]] || die "python" "interpreteur introuvable: $PYTHON"
"$PYTHON" -c 'import PyInstaller' 2>/dev/null ||
    die "pyinstaller" "PyInstaller absent de $PYTHON (outil de build, pas une dependance runtime)"
"$PYTHON" -c 'import numpy, numba, PIL, PySide6' 2>/dev/null ||
    die "dependances" "numpy/numba/Pillow/PySide6 requis dans $PYTHON"

mkdir -p "$DIST_DIR" "$WORK_DIR"
log "versions attendues verifiees par $CHECKER"
"$PYTHON" "$CHECKER" --distributions-only >/dev/null ||
    die "versions" "les pyproject ne sont pas a 0.1.0"

for app in $APPS; do
    spec="$SPEC_DIR/lattice_${app}.spec"
    [[ -f "$spec" ]] || die "$app" "spec introuvable: $spec"
    for mode in $MODES; do
        name="$(binary_name "$app" "$mode")" || die "$app/$mode" "paire app/mode inconnue"
        log "build $app/$mode -> $name"
        LATTICE_BUILD_MODE="$mode" "$PYTHON" -m PyInstaller \
            --noconfirm --clean \
            --distpath "$DIST_DIR" \
            --workpath "$WORK_DIR/${app}-${mode}" \
            "$spec" || die "$app/$mode" "PyInstaller a echoue"
        output="$DIST_DIR/$name"
        [[ -f "$output" ]] || die "$app/$mode" "binaire absent apres build: $output"
        chmod +x "$output"
        "$PYTHON" "$CHECKER" --emit-manifest "$app" linux "$mode" "$output" \
            || die "$app/$mode" "manifest de build non ecrit"
    done
done

"$PYTHON" "$CHECKER" || die "release" "les binaires ne partagent pas la meme version de code"
log "termine : binaires dans $DIST_DIR"
