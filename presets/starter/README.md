# Starters

Twelve ready-made presets: four Dither, four Glitch, four Glyph. Load one to start from a
usable result instead of an empty setting.

## Status of the eight Dither and Glyph starters

Reviewed visually by an independent judge (Claude Opus) across twelve passes. Ratings and
the measured symptom behind each one:

| Starter | Rating | Status |
|---|---|---|
| `dither_01_gameboy_bayer8` | 6/10 | ships |
| `dither_02_pico8_bayer8` | **8.5/10** | ships — gallery thumbnail |
| `dither_03_ega_riemersma` | 6.5/10 | ships (noisy sky) |
| `dither_04_grey16_atkinson` | **8/10** | ships (banding in the sky) |
| `glyph_01_ascii_gameboy` | 3/10 | **held back** — see below |
| `glyph_02_braille_grey8` | 7/10 | ships |
| `glyph_03_quadrant_pico8` | 7.5/10 | ships |
| `glyph_04_shape_ega` | 4/10 | **held back** — see below |

### Why the two Glyph starters are held back

Both build their image from a text font, and that sets a hard ceiling: at a 6×6 cell the
densest character covers only part of its cell, so the darkest tone reachable stays grey.
Measured coverage with a bold font:

| Glyph | Cell coverage |
|---|---|
| `@` | 23.6 % |
| `M` | 33.3 % |
| `▓` | 49.2 % |
| `█` | 62.3 % |

A thin ASCII character cannot blacken its cell, so the dark mountains of the test source
come out pale, and the sky gradient collapses into two or three levels. Neither the
background colour nor the alphabet fixes it — both were measured:

- grey background `#aaaaaa` → contrast 0.186; white `#ffffff` → **0.279** (better, not enough)
- 95-character ASCII → 38 glyphs cover under 5 % of their cell
- with the block alphabet ` ░▒▓█`, correlation rose 0.39 → **0.50** and contrast 0.26 → 0.33,
  still short of `dither_02` and `glyph_03`, which read at a glance

**The fix is a renderer, not a setting:** draw the block characters as solid rectangles
covering the cell (or 25/50/75/100 % motifs) instead of going through a font, or set the
cell height to the glyph's real height with no leading. That removes the 62 % ceiling and
the one-pixel stripes at the same time. Until then these two presets stay out of the
gallery.

`glyph_01` keeps the Game Boy identity in its ink: `#0f380f` was verified to be the darkest
colour of that palette (luma 0.174).

## Test source

`harness/lattice/docs/starters/source.png` — a full vertical gradient, a bright moon, two
foreground planes, a sharp face and fine texture. The original test image was a motion-
blurred portrait with 32.6 % of its pixels in a single tonal bucket, which hid every
difference between the algorithms.
