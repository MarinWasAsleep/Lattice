# Starters

Twelve ready-made presets: four Dither, four Glitch, four Glyph. Load one to start from a
usable result instead of an empty setting.

## The twelve starters

| Starter | What it does |
|---|---|
| `dither_01_gameboy_bayer8` | ordered dithering on the Game Boy palette |
| `dither_02_pico8_bayer8` | ordered dithering on the PICO-8 palette |
| `dither_03_ega_riemersma` | Rimersma error diffusion on the 16-colour EGA palette |
| `dither_04_grey16_atkinson` | Atkinson diffusion on sixteen grey levels |
| `glitch_01_vhs_soft` | a gentle VHS pass: soft chroma bleed, light scanlines |
| `glitch_02_channel_rift` | the RGB channels drift apart horizontally |
| `glitch_03_sort_echo` | pixel sorting confined to the bright areas |
| `glitch_04_crt_finish` | curvature, phosphor mask and a rolling beam |
| `glyph_01_ascii_gameboy` | ASCII glyphs in Game Boy ink |
| `glyph_02_braille_grey8` | Braille cells, eight grey levels |
| `glyph_03_quadrant_pico8` | quadrant blocks on the PICO-8 palette |
| `glyph_04_shape_ega` | solid glyph shapes on the EGA palette |

## Test source

`docs/starters-source.png` — a full vertical gradient, a bright moon, two foreground planes,
a sharp face and fine texture. Every preset is tuned against it: it holds both smooth
gradients and hard edges, so a preset that flattens the sky or smears the face shows it
immediately.
