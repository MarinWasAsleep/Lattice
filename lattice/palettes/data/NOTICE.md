# Palette licences

Every palette in this directory is redistributable. Each `.hex` file carries a
`# source:` line and a `# licence:` line; this file records the full text of the
licences that require one.

## Public domain

`vga16`, `tango` and `web_safe` are public domain. `vga16` is the IBM VGA
hardware standard and `web_safe` is the technical 216-colour cube, so neither has
an author. `tango` is the Tango Desktop Project icon palette, released to the
public domain.

## MIT

`solarized_dark`, `solarized_light`, `nord`, `gruvbox_dark`, `dracula`,
`catppuccin_mocha`, `one_dark`, `tokyo_night` and `rose_pine` are distributed
under the MIT licence. The copyright line of each is in its own file. The full
text follows.

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Left out

Palettes whose licence could not be verified were not shipped, as the card
requires. That includes the artist pixel-art palettes that are widely
redistributed without a stated licence (PICO-8, DawnBringer, Endesga, Sweetie,
Apollo and similar) and the console palettes whose values are emulator
approximations rather than published data. `pico8` and `gameboy` remain
available as built-in palettes, where they were already shipped in 1.0.

## Verification

The hex values were transcribed from each project's published palette. A
maintainer should diff them against upstream before a release; the tests check
the structure of every file, not the exact colours.
