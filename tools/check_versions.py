"""Vérifie la cohérence de la version de Lattice et des manifests de build.

Lattice 1.0 est une seule distribution : le pyproject racine déclare la version attendue et,
pour la plateforme dont un build a été enregistré, les deux binaires (fenêtre + console)
portent la même version et la même empreinte de code source. Une release dont les deux
binaires divergent est refusée.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

EXPECTED_VERSION = "1.0.1"
APP = "lattice"
PLATFORMS: tuple[str, ...] = ("linux", "windows")
MODES: tuple[str, ...] = ("gui", "cli")
DISTRIBUTIONS: dict[str, str] = {
    "lattice": "pyproject.toml",
}
MANIFEST_DIR = Path("build/manifests")
FINGERPRINT_SUFFIXES: tuple[str, ...] = (
    "pyproject.toml",
    "scripts/packaging/lattice.spec",
    "lattice/__main__.py",
    "lattice/__init__.py",
)


def repo_root() -> Path:
    """Return the repository root, inferred from this tool's location."""
    return Path(__file__).resolve().parents[1]


def read_version(project_file: Path) -> str:
    """Return the [project].version string of one pyproject.toml."""
    with project_file.open("rb") as stream:
        data: dict[str, Any] = tomllib.load(stream)
    try:
        return str(data["project"]["version"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{project_file}: [project].version is missing") from exc


def current_fingerprint(root: Path | None = None) -> str:
    """Return a short sha256 over the version-bearing sources and packaging files."""
    base = root or repo_root()
    digest = hashlib.sha256()
    for relative in FINGERPRINT_SUFFIXES:
        path = base / relative
        if not path.is_file():
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def check_distributions(root: Path) -> list[str]:
    """Return one named error line per distribution whose version is not EXPECTED_VERSION."""
    errors: list[str] = []
    for name, relative in DISTRIBUTIONS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"DISTRIBUTION {name}: pyproject missing at {relative}")
            continue
        try:
            version = read_version(path)
        except (ValueError, OSError) as exc:
            errors.append(f"DISTRIBUTION {name}: {exc}")
            continue
        if version != EXPECTED_VERSION:
            errors.append(
                f"DISTRIBUTION {name}: version {version} != {EXPECTED_VERSION} ({relative})"
            )
    return errors


def _load_manifests(root: Path) -> list[dict[str, Any]]:
    """Return the build manifests found under build/manifests, sorted by name."""
    directory = root / MANIFEST_DIR
    if not directory.is_dir():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            manifests.append({"file": path.name, "error": str(exc)})
            continue
        if isinstance(payload, dict):
            payload["file"] = path.name
            manifests.append(payload)
    return manifests


def check_manifests(root: Path, fingerprint: str) -> tuple[list[str], dict[str, Any]]:
    """Return named errors and a per-app/platform summary of built binaries."""
    errors: list[str] = []
    built: dict[str, Any] = {APP: {}}
    for manifest in _load_manifests(root):
        name = manifest.get("file", "?")
        if "error" in manifest:
            errors.append(f"MANIFEST {name}: unreadable: {manifest['error']}")
            continue
        app = manifest.get("app")
        platform = manifest.get("platform")
        mode = manifest.get("mode")
        if app != APP or platform not in PLATFORMS or mode not in MODES:
            errors.append(f"MANIFEST {name}: invalid app/platform/mode")
            continue
        version = manifest.get("version")
        stamp = manifest.get("fingerprint")
        if version != EXPECTED_VERSION:
            errors.append(f"MANIFEST {name}: version {version} != {EXPECTED_VERSION}")
        if stamp != fingerprint:
            errors.append(f"MANIFEST {name}: fingerprint {stamp} != {fingerprint}")
        built[app].setdefault(platform, {})[mode] = manifest.get("binary")
    for app in (APP,):
        for platform in PLATFORMS:
            modes = built[app].get(platform)
            if not modes:
                continue
            for mode in MODES:
                if mode not in modes or not modes[mode]:
                    errors.append(
                        f"RELEASE {app}/{platform}: missing {mode} binary "
                        "(both gui and cli must ship from one code version)"
                    )
    return errors, built


def emit_manifest(root: Path, app: str, platform: str, mode: str, binary: str) -> Path:
    """Write one build manifest so the checker can prove release consistency."""
    if app != APP or platform not in PLATFORMS or mode not in MODES:
        raise ValueError(f"invalid manifest coordinates: {app}/{platform}/{mode}")
    directory = root / MANIFEST_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{app}-{platform}-{mode}.json"
    payload: dict[str, Any] = {
        "app": app,
        "platform": platform,
        "mode": mode,
        "version": EXPECTED_VERSION,
        "fingerprint": current_fingerprint(root),
        "binary": binary,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """Run the checks (or emit a manifest) and print a named, machine-readable result."""
    parser = argparse.ArgumentParser(prog="check_versions.py")
    parser.add_argument("--root", type=Path, default=None, help="repository root")
    parser.add_argument("--json", action="store_true", help="print only JSON")
    parser.add_argument("--distributions-only", action="store_true",
                        help="ignore build manifests (used before a build is complete)")
    parser.add_argument("--emit-manifest", nargs=4, metavar=("APP", "PLATFORM", "MODE", "BIN"))
    args = parser.parse_args(argv)

    root = args.root or repo_root()
    if args.emit_manifest:
        path = emit_manifest(root, *args.emit_manifest)
        print(f"manifest written: {path}")
        return 0

    fingerprint = current_fingerprint(root)
    dist_errors = check_distributions(root)
    if args.distributions_only:
        for line in dist_errors:
            print(f"CHECK FAILED: {line}", file=sys.stderr)
        print("VERSION CHECK OK (distributions only)" if not dist_errors
              else f"VERSION CHECK FAILED ({len(dist_errors)})")
        return 0 if not dist_errors else 1
    manifest_errors, built = check_manifests(root, fingerprint)
    errors = dist_errors + manifest_errors
    result = {
        "ok": not errors,
        "expected_version": EXPECTED_VERSION,
        "fingerprint": fingerprint,
        "versions": {
            name: (read_version(root / rel) if (root / rel).is_file() else None)
            for name, rel in DISTRIBUTIONS.items()
        },
        "builds": built,
        "errors": errors,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for name, version in result["versions"].items():
            print(f"{name:16} {version}")
        print(f"fingerprint       {fingerprint}")
        for line in errors:
            print(f"CHECK FAILED: {line}", file=sys.stderr)
        print("VERSION CHECK OK" if result["ok"] else f"VERSION CHECK FAILED ({len(errors)})")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
