# H9 acceptance checklist — Lattice Dither 1.1

This is the manual recipe for checkpoint **H9**. It is not a test suite: it is the pass a
human takes before 1.1 is called done. Every line is one action and one expected result.
Tick a box only when you saw the result yourself.

Run it on a clean profile the first time (`%APPDATA%/LatticeDither` and
`%LOCALAPPDATA%/LatticeDither` removed) and once more on your normal profile, because the
second run is the one that exercises the remembered settings.

Budget: about 45 minutes. Stop at the first failure and write it up; do not "work around"
a failure, the point of the pass is to find it.

---

## 0. Setup

- [ ] `pip install -r requirements.txt` completes with no error.
- [ ] `python -m pytest -q` is green.
- [ ] `ruff check .` reports nothing.
- [ ] `python tools/check_contract.py` exits 0.
- [ ] `python LatticeDither.pyw` opens the window: canvas in the middle, **Gallery** dock on
      the left, **Panels** dock (Algorithm / Palette / Effects) on the right, toolbar on top,
      status bar at the bottom.
- [ ] The status bar reads `PhotoCraft: …`, `Render: -`, an empty grid label and
      `Preset: none`.
- [ ] The gallery fills with thumbnails within a few seconds and the search box filters them
      by name and by family.

Prepare three source images and keep them for the whole pass:

| Name | What it is | Why |
|---|---|---|
| `photo.png` | a normal colour photograph, 2000 px or more on the long side | the case a pre-pass must never damage |
| `pixelart.png` | existing pixel art that has been upscaled 4× with nearest neighbour | the case the Pixel Snapper exists for |
| `scan.png` | a scanned or photographed halftone print, screen visible | the case descreen exists for |

---

## 1. Source type A — photo

- [ ] **Open image** → `photo.png`. The preview appears and `Render: … ms` fills in.
- [ ] Turn **Prepare source** on. The grid label reports a confidence **below 0.5** and says
      the source is left untouched.
- [ ] Compare before/after with **Space**. The two views are identical: the pre-pass did not
      touch the photo. This is the single most important line of the pass.
- [ ] Turn **Prepare source** off again.
- [ ] Drag `photo.png` from Explorer onto the window. It opens, exactly as with the menu.
- [ ] `File > Recent` now lists `photo.png` at the top. Close and reopen the application: it
      is still there.

## 2. Source type B — existing pixel art

- [ ] **Open image** → `pixelart.png`.
- [ ] Turn **Prepare source** on. The grid label reports the detected cell size (4×4 for a
      4× upscale) and a confidence **above 0.8**.
- [ ] The preview is now the original, un-upscaled artwork: hard edges, no anti-aliasing
      halo. Zoom to 400 % and confirm the edges are clean.
- [ ] Turn **Prepare source** off: the preview returns to the upscaled source.
- [ ] With **Prepare source** on, set **Pixel size** to 1 and render. The output is the
      original pixel grid, not a re-dithered approximation of it.

## 3. Source type C — scan

- [ ] **Open image** → `scan.png`.
- [ ] Turn **Descreen** on. The rosette or line screen visibly softens and the grid label
      reports the detected screen.
- [ ] Turn **Descreen** off and on again: the change is reversible and the preview follows.
- [ ] With **Descreen** on, pick a palette and an algorithm and render. The result is not
      dominated by the print screen.
- [ ] Confirm that a photo with **Descreen** on and a confidence below 0.5 is still left
      untouched (repeat the §1 check with the toggle on).

## 4. Every export path

For each of the four formats, open **Export…** (`Ctrl+E`) and check the defaults first:
`cell = 1`, `dpi = 300`, `bleed_mm = 0`, `crop_marks = off`, `separations = off`,
`fps = 12`.

- [ ] **PNG** — toolbar **Export PNG** (`Ctrl+S`) writes a PNG at the full source resolution,
      not the preview proxy. Open it and compare with the preview.
- [ ] **SVG** — `cell = 1`, no background. The file opens in a browser and in Inkscape; the
      colours are flat, the edges are crisp, and the file size is plausible for the content
      (a dithered render is large, flat artwork is small).
- [ ] **SVG** again with `cell = 8` and a background colour. The document scales and the
      background is filled.
- [ ] **Print PNG** — `dpi = 300`, `bleed_mm = 0`, no crop marks. The PNG opens and its
      metadata carries 300 dpi.
- [ ] **Print PNG** with `bleed_mm = 5` and `crop_marks = on`. The bleed border replicates
      the edge colour and the crop marks sit outside the trim area.
- [ ] **Print PNG** with `separations = on`. Four extra files appear (`_C`, `_M`, `_Y`, `_K`)
      and the dialog reports every file it wrote.
- [ ] **Animated GIF** — `fps = 12`, `loop = 0`. The GIF plays in a browser and loops
      forever.
- [ ] **Video** — `fps = 12`. Either an `.mp4` is written and plays, or the dialog says
      `No ffmpeg available.` and writes nothing. Both are acceptable; a traceback is not.
- [ ] The last export directory survives a restart: export, close, reopen, export again and
      the dialog opens where you left it.

## 5. The CLI

Run these from the repository root with the virtual environment active.

- [ ] `python -m lattice_dither.cli info --preset presets/01_gameboy.json` prints the preset
      summary and exits 0.
- [ ] `python -m lattice_dither.cli render --preset presets/01_gameboy.json --in photo.png
      --out cli.png` writes `cli.png`, and that file is **byte-identical** to the same render
      made from the GUI with the same preset. This is gate G6; if it differs, stop.
- [ ] `python -m lattice_dither.cli render --preset presets/01_gameboy.json --in missing.png
      --out x.png` exits **2** with a one-line message and no traceback.
- [ ] `python -m lattice_dither.cli render --preset presets/01_gameboy.json --in photo.png
      --out cli.png --json` prints `{"ok": true, "files": [...], "errors": []}`.
- [ ] `python -m lattice_dither.cli batch --preset presets/01_gameboy.json --in-dir <dir>
      --out-dir <dir>` processes the files in sorted order and prints one line per file.
- [ ] `python -m lattice_dither.cli export-svg --preset presets/01_gameboy.json --in photo.png
      --out cli.svg` writes the same bytes as the dialog's SVG with the same options.
- [ ] `python -m lattice_dither.cli export-print …` and `export-anim …` likewise match the
      dialog byte for byte.

## 6. Both languages

- [ ] Set the language to **French** (or start with a French system locale and no stored
      choice). Every label of the window is French: the tabs read *Algorithme*, *Palette*,
      *Effets*; the toolbar reads *Ouvrir une image*, *Préparer la source*; the status bar
      reads *Prêt*.
- [ ] The French catalogue uses **tramage** for dithering, **algorithme**, **force**,
      **densité**, **avant / après**, and leaves **palette** unchanged.
- [ ] Switch back to **English**. Every label returns to English without a restart.
- [ ] No label anywhere is a raw key, a dotted identifier or an empty string, in either
      language. Walk every tab, every menu and the export dialog in both.
- [ ] The choice survives a restart.

## 7. Undo and redo

- [ ] Change the algorithm, the palette, a slider and an effect. `Ctrl+Z` steps back through
      them one at a time and the preview follows each step.
- [ ] `Ctrl+Shift+Z` and `Ctrl+Y` step forward again.
- [ ] `Edit > Undo` and `Edit > Redo` are greyed out when there is nothing to step to.
- [ ] Fifty edits deep, the oldest is dropped and the application stays responsive.
- [ ] Undo after loading a preset restores the previous pipeline, not the preset.

## 8. The PhotoCraft round trip

- [ ] Start PhotoCraft from the **PhotoCraft (Lattice Dither)** shortcut. The status bar
      changes to `PhotoCraft: connected` within a few seconds.
- [ ] **Get from PhotoCraft** pulls the visible document into the canvas.
- [ ] Render, then **Send to PhotoCraft** (`Ctrl+Shift+S`). One new layer appears in
      PhotoCraft, named after the preset, and the status bar reports its index.
- [ ] Send twice in a row: two layers, not three, and the document itself is untouched.
- [ ] The layer content matches the preview pixel for pixel at full resolution.
- [ ] Close PhotoCraft. The status bar returns to `PhotoCraft: disconnected` and the next
      **Send** reports a one-line error instead of a traceback.
- [ ] If the installed PhotoCraft version is untested, the warning appears once, in the
      permanent label, and later status messages do not wipe it.

## 9. Sign-off

| Check | Result | Notes |
|---|---|---|
| §1 photo untouched | | |
| §2 pixel art recovered | | |
| §3 scan descreened | | |
| §4 every export path | | |
| §5 CLI parity (G6) | | |
| §6 both languages | | |
| §7 undo / redo | | |
| §8 PhotoCraft round trip | | |
| G5 witness presets byte-identical | | |
| `pytest -q` green | | |

Signed off by: ____________________  Date: ____________

Anything that failed goes into `harness/v1.1/DEVIATIONS.md` with the class, the facts and the
measurement, before the next card starts.
