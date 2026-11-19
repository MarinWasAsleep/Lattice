#!/usr/bin/env bash
# Installe Lattice sur cette machine : le binaire de la fenetre et celui de la ligne de commande
# dans ~/.local/bin, une entree de menu dans ~/.local/share/applications. Jamais de raccourci sur
# le Bureau (regle utilisateur).
#
# Lattice 1.0 est un seul programme : deux fichiers a installer au lieu de six, et une seule
# entree de menu. Les anciennes entrees et lanceurs des trois applications separees sont retires
# par ce script, sinon le menu proposerait des programmes qui n'existent plus.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
DIST_DIR="${DIST_DIR:-$ROOT/dist}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_DIR="${DESKTOP_DIR:-$DATA_HOME/applications}"
BIN_DIR="${BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
UNINSTALL=0

GUI_BINARY="Lattice"
CLI_BINARY="lattice-cli"
GUI_LINK="lattice"
CLI_LINK="lattice-cli"
DESKTOP_FILE="lattice.desktop"

# Everything the three-application era installed, removed on sight so a menu never offers a
# launcher for a program that is no longer built.
LEGACY_LINKS=(lattice-dither lattice-dither-cli lattice-glyph lattice-glyph-cli
              lattice-glitch lattice-glitch-cli LatticeDither-linux)
LEGACY_DESKTOPS=(lattice-dither.desktop lattice-glyph.desktop lattice-glitch.desktop
                 LatticeDither.desktop)

log() { printf '[Lattice install] %s\n' "$1"; }
die() {
    printf 'LATTICE INSTALL ERROR: %s: %s\n' "$1" "$2" >&2
    exit 1
}

[[ $# -gt 0 && "$1" == "--uninstall" ]] && UNINSTALL=1

[[ "$DESKTOP_DIR" != "$HOME/Desktop" ]] ||
    die "desktop" "refus d'ecrire sur le Bureau (regle utilisateur non negociable)"

purge_legacy() {
    local name
    for name in "${LEGACY_LINKS[@]}"; do
        if [[ -e "$BIN_DIR/$name" ]]; then
            rm -f "$BIN_DIR/$name"
            log "ancien lanceur retire : $name"
        fi
    done
    for name in "${LEGACY_DESKTOPS[@]}"; do
        if [[ -e "$DESKTOP_DIR/$name" ]]; then
            rm -f "$DESKTOP_DIR/$name"
            log "ancienne entree retiree : $name"
        fi
    done
}

if [[ $UNINSTALL -eq 1 ]]; then
    rm -f "$BIN_DIR/$GUI_LINK" "$BIN_DIR/$CLI_LINK" "$DESKTOP_DIR/$DESKTOP_FILE"
    purge_legacy
    log "desinstallation terminee"
    exit 0
fi

write_gui() {
    local src="$DIST_DIR/$GUI_BINARY"
    if [[ -f "$src" ]]; then
        install -m 0755 "$src" "$BIN_DIR/$GUI_LINK" || die "fenetre" "copie impossible"
        log "fenetre -> $BIN_DIR/$GUI_LINK"
        return
    fi
    # No frozen binary: run from source, which is what a developer wants anyway.
    [[ -f "$PYTHON" ]] || die "fenetre" "ni binaire ($src) ni python ($PYTHON)"
    printf '#!/usr/bin/env bash\nexec "%s" -m lattice.app "$@"\n' "$PYTHON" >"$BIN_DIR/$GUI_LINK"
    chmod 0755 "$BIN_DIR/$GUI_LINK"
    log "fenetre -> $BIN_DIR/$GUI_LINK (depuis les sources)"
}

write_cli() {
    local src="$DIST_DIR/$CLI_BINARY"
    if [[ -f "$src" ]]; then
        install -m 0755 "$src" "$BIN_DIR/$CLI_LINK" || die "console" "copie impossible"
        log "console -> $BIN_DIR/$CLI_LINK"
        return
    fi
    [[ -f "$PYTHON" ]] || die "console" "ni binaire ($src) ni python ($PYTHON)"
    printf '#!/usr/bin/env bash\nexec "%s" -m lattice "$@"\n' "$PYTHON" >"$BIN_DIR/$CLI_LINK"
    chmod 0755 "$BIN_DIR/$CLI_LINK"
    log "console -> $BIN_DIR/$CLI_LINK (depuis les sources)"
}

write_desktop() {
    local dest="$DESKTOP_DIR/$DESKTOP_FILE" icon="$ROOT/lattice/resources/icon-app.svg"
    [[ -f "$icon" ]] || icon="applications-graphics"
    cat >"$dest" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Lattice
GenericName=Image Studio
Comment=Dithering, glyph and glitch studio for raster images
Exec=$BIN_DIR/$GUI_LINK %f
Icon=$icon
Terminal=false
Categories=Graphics;2DGraphics;RasterGraphics;
MimeType=image/png;image/jpeg;image/bmp;image/tiff;image/webp;
StartupNotify=true
EOF
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$dest" || die "desktop" "fichier invalide: $dest"
    fi
    log "entree de menu -> $dest"
}

mkdir -p "$DESKTOP_DIR" "$BIN_DIR" ||
    die "repertoires" "creation impossible de $DESKTOP_DIR ou $BIN_DIR"

write_gui
write_cli
write_desktop
purge_legacy

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

log "termine : aucun raccourci cree sur le Bureau"
