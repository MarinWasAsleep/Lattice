#!/usr/bin/env bash
# Publie l'etat courant du depot sur le depot public, en un seul commit.
#
# Le depot public n'a pas d'historique : il porte l'etat livre, pas la fabrique. Ce script
# exporte HEAD (sans .git), rejoue un commit unique signe a l'utilisateur, et force le push.
# A relancer apres chaque lot de changements plutot que de pousser l'historique de travail.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE="${STAGE:-/tmp/lattice-public}"
REMOTE="${REMOTE:-https://github.com/MarinWasAsleep/Lattice.git}"
NAME="${GIT_AUTHOR_NAME:-MarinWasAsleep}"
EMAIL="${GIT_AUTHOR_EMAIL:-180754786+MarinWasAsleep@users.noreply.github.com}"
MESSAGE_FILE="${MESSAGE_FILE:-}"

rm -rf "$STAGE"
mkdir -p "$STAGE"
git -C "$ROOT" archive HEAD | tar -x -C "$STAGE"
cp "$ROOT/.gitignore" "$STAGE/.gitignore"
# `.github` est versionne mais `git archive` ne le prend que s'il est dans l'arbre suivi.
if [[ -d "$ROOT/.github" && ! -d "$STAGE/.github" ]]; then
    cp -r "$ROOT/.github" "$STAGE/.github"
fi

cd "$STAGE"
git init -q -b main
git add -A

if [[ -n "$MESSAGE_FILE" && -f "$MESSAGE_FILE" ]]; then
    git -c user.name="$NAME" -c user.email="$EMAIL" commit -q -F "$MESSAGE_FILE"
else
    git -c user.name="$NAME" -c user.email="$EMAIL" commit -q -m "Lattice 1.0"
fi

git remote add public "$REMOTE"
git push --force public main
printf '[publish] un commit sur %s\n' "$REMOTE"
