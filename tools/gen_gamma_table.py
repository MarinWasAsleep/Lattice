"""Generate the committed gamma lookup table.

The rendering pipeline applies gamma with `np.power`, whose last-bit result
depends on the platform libm (Windows MSVC vs Linux glibc). A one-ulp
difference flips threshold pixels by one palette step on gradient sources,
so the same preset could not render byte-identically across platforms.

Fix: a discrete 8-bit curve committed as data (same pattern as
`algorithms/ostromoukhov_table.py`). The pipeline quantises the input level
to 1/255 and reads the mapped level from the table: no libm call in the hot
path, so the render is bit-identical on every platform.

Grid: gamma in [0.4, 2.2] by 0.025 (73 curves), level 0..255.
Values: round(255 * (level/255) ** (1/gamma)) computed once in float64.
A gamma outside the grid clamps to the nearest curve (documented deviation).

Run from the repository root:
    python tools/gen_gamma_table.py > lattice_core/gamma_table.py
"""

START = 0.4
STEP = 0.025
COUNT = 73
PER_LINE = 16


def main() -> None:
    print('"""Committed gamma correction curves (generated, do not edit).')
    print()
    print("See `tools/gen_gamma_table.py` and `core/color.py` for the rationale: discrete")
    print("8-bit curves make the render independent of the platform libm, so witness")
    print("baselines match bit-for-bit on Windows and Linux.")
    print('"""')
    print()
    print("from __future__ import annotations")
    print()
    print("GAMMA_GRID_START = 0.4")
    print("GAMMA_GRID_STEP = 0.025")
    print("GAMMA_GRID_COUNT = 73")
    print()
    print("GAMMA_LUT: tuple[tuple[int, ...], ...] = (")
    for gi in range(COUNT):
        gamma = START + gi * STEP
        inv = 1.0 / gamma
        row = [int(round(255.0 * ((v / 255.0) ** inv))) for v in range(256)]
        lines = []
        for i in range(0, 256, PER_LINE):
            chunk = row[i : i + PER_LINE]
            lines.append("        " + ", ".join(str(x) for x in chunk))
        print("    (\n" + ",\n".join(lines) + ",\n    ),")
    print(")")


if __name__ == "__main__":
    main()
