#!/usr/bin/env bash
# Installe les lanceurs Lattice dans ~/.local/bin et les entrees de menu dans
# ~/.local/share/applications. Jamais de raccourci sur le Bureau (regle utilisateur).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
DIST_DIR="${DIST_DIR:-$ROOT/dist}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DESKTOP_DIR="${DESKTOP_DIR:-$DATA_HOME/applications}"
BIN_DIR="${BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
ENTRY_DIR="$SCRIPT_DIR/packaging/entry"
APPS="dither glyph glitch"
UNINSTALL=0

log() { printf '[Lattice install] %s\n' "$1"; }
die() {
    printf 'LATTICE INSTALL ERROR: %s: %s\n' "$1" "$2" >&2
    exit 1
}
[[ $# -gt 0 && "$1" == "--uninstall" ]] && UNINSTALL=1

app_title() {
    case "$1" in
        dither) printf 'Lattice Dither' ;;
        glyph)  printf 'Lattice Glyph' ;;
        glitch) printf 'Lattice Glitch' ;;
        *) return 1 ;;
    esac
}
app_comment() {
    case "$1" in
        dither) printf 'Dithering studio for PhotoCraft' ;;
        glyph)  printf 'Glyph, bitmask and text rendering' ;;
        glitch) printf 'Feedback, displacement and signal degradation' ;;
        *) return 1 ;;
    esac
}
app_binary() {
    case "$1" in
        dither) printf 'LatticeDither' ;;
        glyph)  printf 'LatticeGlyph' ;;
        glitch) printf 'LatticeGlitch' ;;
        *) return 1 ;;
    esac
}
app_icon() {
    case "$1" in
        dither) printf '%s/assets/lattice_dither.png' "$ROOT" ;;
        *) printf 'applications-graphics' ;;
    esac
}

install_one() {
    local app="$1" mode src dest suffix built=0 wrapper
    for mode in gui cli; do
        if [ "$mode" = cli ]; then suffix="-cli"; else suffix=""; fi
        dest="$BIN_DIR/lattice-${app}${suffix}"
        if [ "$mode" = gui ]; then
            src="$DIST_DIR/$(app_binary "$app")"
        else
            src="$DIST_DIR/lattice-${app}-cli"
        fi
        if [[ -f "$src" ]]; then
            install -m 0755 "$src" "$dest" || die "$app/$mode" "copie impossible vers $dest"
            built=1
        else
            [[ -f "$PYTHON" ]] || die "$app/$mode" "ni binaire ($src) ni python ($PYTHON)"
            [[ -f "$ENTRY_DIR/${app}_${mode}.py" ]] ||
                die "$app/$mode" "point d'entree absent: $ENTRY_DIR/${app}_${mode}.py"
            wrapper="$(mktemp)"
            {
                printf '#!/usr/bin/env bash\n'
                printf '# Lanceur Lattice %s (%s) installe dans ~/.local/bin\n' "$app" "$mode"
                printf 'exec "%s" "%s" "$@"\n' "$PYTHON" "$ENTRY_DIR/${app}_${mode}.py"
            } >"$wrapper"
            install -m 0755 "$wrapper" "$dest" || die "$app/$mode" "installation de $dest impossible"
            rm -f "$wrapper"
        fi
        [[ -x "$dest" ]] || die "$app/$mode" "lanceur non executable: $dest"
        log "$app/$mode -> $dest"
    done
    if [ "$built" = 0 ]; then
        log "$app: lanceurs Python (aucun binaire PyInstaller trouve dans $DIST_DIR)"
    fi
}

write_desktop_one() {
    local app="$1" dest="$DESKTOP_DIR/lattice-${app}.desktop"
    cat >"$dest" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$(app_title "$app")
GenericName=$(app_title "$app")
Comment=$(app_comment "$app")
Exec=$BIN_DIR/lattice-${app} %f
Icon=$(app_icon "$app")
Terminal=false
Categories=Graphics;2DGraphics;RasterGraphics;
MimeType=image/png;image/jpeg;image/bmp;image/tiff;image/webp;
StartupNotify=true
EOF
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$dest" || die "desktop:$app" "fichier invalide: $dest"
    fi
    log "entree de menu -> $dest"
}

remove_one() {
    local app="$1"
    rm -f "$DESKTOP_DIR/lattice-${app}.desktop" \
          "$BIN_DIR/lattice-${app}" "$BIN_DIR/lattice-${app}-cli"
    log "$app: lanceurs et entree de menu supprimes"
}

[[ "$DESKTOP_DIR" != "$HOME/Desktop" ]] ||
    die "desktop" "refus d'ecrire sur le Bureau (regle utilisateur non negociable)"

if [ "$UNINSTALL" = 1 ]; then
    mkdir -p "$DESKTOP_DIR" "$BIN_DIR"
    for app in $APPS; do remove_one "$app"; done
    log "desinstallation terminee"
    exit 0
fi

mkdir -p "$DESKTOP_DIR" "$BIN_DIR" ||
    die "repertoires" "creation impossible de $DESKTOP_DIR ou $BIN_DIR"
for app in $APPS; do
    app_title "$app" >/dev/null || die "$app" "application inconnue"
    install_one "$app"
    write_desktop_one "$app"
done
log "termine : aucun raccourci cree sur le Bureau"
