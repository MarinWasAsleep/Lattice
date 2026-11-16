"""Fetch palette files into lattice_dither/palettes/data (manual, never imported).

This script is not part of the application and is never imported by it. It exists
so a maintainer can refresh the shipped palettes by hand, with network access,
and then review the diff before committing. The core never touches the network.

    python tools/fetch_palettes.py --list
    python tools/fetch_palettes.py --url https://example.org/palette.hex --name mine
    python tools/fetch_palettes.py --url https://example.org/palette.gpl --name mine --licence MIT

Only fetch sources whose licence permits redistribution. The script refuses to
write a file without a --licence value, because every shipped palette must carry
one.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "lattice_core" / "palettes" / "data"
TIMEOUT_SECONDS = 20
MAX_BYTES = 1 << 20
USER_AGENT = "lattice-dither-fetch-palettes/1.0"


def _existing() -> list[str]:
    """Return the names of the palettes already shipped."""
    return sorted(path.stem for path in DATA_DIR.glob("*.hex"))


def _download(url: str) -> str:
    """Return the text at url, refusing anything larger than MAX_BYTES."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"{url}: response larger than {MAX_BYTES} bytes")
    return payload.decode("utf-8", errors="replace")


def _header(source: str, licence: str, copyright_: str | None) -> str:
    """Return the comment header every shipped palette carries."""
    lines = [f"# source: {source}", f"# licence: {licence}"]
    if copyright_:
        lines.append(f"# copyright: {copyright_}")
    return "\n".join(lines) + "\n\n"


def main(argv: list[str] | None = None) -> int:
    """Run the fetcher and return an exit code."""
    parser = argparse.ArgumentParser(
        prog="fetch_palettes.py",
        description="Fetch one palette file into the shipped data directory. Manual only.",
    )
    parser.add_argument("--list", action="store_true", help="list the shipped palettes and exit")
    parser.add_argument("--url", help="URL of a .hex or .gpl palette")
    parser.add_argument("--name", help="file stem to write, without extension")
    parser.add_argument("--licence", help="licence of the source, required to write a file")
    parser.add_argument("--copyright", help="copyright holder, when the licence needs one")
    parser.add_argument("--force", action="store_true", help="overwrite an existing palette")
    args = parser.parse_args(argv)

    if args.list:
        for name in _existing():
            print(name)
        return 0
    if not (args.url and args.name and args.licence):
        parser.error("--url, --name and --licence are required unless --list is used")
    target = DATA_DIR / f"{args.name}.hex"
    if target.exists() and not args.force:
        print(f"{target} already exists; pass --force to overwrite", file=sys.stderr)
        return 1
    try:
        body = _download(args.url)
    except (urllib.error.URLError, ValueError, OSError) as exc:
        print(f"cannot fetch {args.url}: {exc}", file=sys.stderr)
        return 2
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _header(args.url, args.licence, args.copyright) + body, encoding="utf-8", newline="\n"
    )
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
