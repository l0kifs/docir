# docir — logo kit

The chosen mark: **Compile Caret** (`[ ▸`). A square bracket — the IR container — meets a
solid caret, the compile/run step. Amber marks the compiled state; ink (or paper on dark) holds
the structure. The wordmark splits `doc` (ink) + `ir` (amber): *doc*uments as *IR*.

## Colors

| Token | Hex | Use |
|---|---|---|
| Ink | `#12161C` | mark on light, wordmark `doc` |
| Signal amber | `#E0932C` | the caret; wordmark `ir` — the "compiled" accent |
| Paper | `#ECEEF1` | mark on dark |

Amber is only ever the caret / the `ir` — it is the compiled signal, never decoration.

## Files

**Vector — primary art**
| File | For |
|---|---|
| `docir-mark.svg` | the mark, ink + amber (light backgrounds) |
| `docir-mark-dark.svg` | the mark, paper + amber (dark backgrounds) |
| `docir-mark-mono.svg` | single-ink mark; `currentColor` — **inline** it so it inherits text color |
| `docir-lockup.svg` | horizontal mark + `docir` wordmark (light) |
| `docir-lockup-dark.svg` | lockup for dark backgrounds |
| `docir-icon.svg` | app-icon tile: the mark on an ink squircle |

**Favicon / raster — generated from `docir-icon.svg`**
| File | For |
|---|---|
| `favicon.svg` | SVG favicon (opaque tile — legible on any chrome) |
| `favicon.ico` | 16/32/48 multi-res fallback |
| `apple-touch-icon.png` | 180×180, opaque (iOS applies its own mask) |
| `icon-16/32/192/512.png` | PWA manifest / general raster |

The favicon set is the **tile** (opaque) on purpose: a bare thin bracket vanishes on dark browser
chrome, so the packaged favicon puts the mark on the ink squircle where it always reads. The
transparent pure mark is `docir-mark*.svg`, for embedding where you control the background.

**Lockup raster — the README banner**
| File | For |
|---|---|
| `docir-lockup.png` | 528×168, transparent — light backgrounds |
| `docir-lockup-dark.png` | 528×168, transparent — dark backgrounds |

The project [README](../../README.md) swaps these by theme with a `<picture>`:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo/docir-lockup-dark.png" />
  <img src="assets/logo/docir-lockup.png" alt="docir" width="240" />
</picture>
```

They're rasterized (not the `.svg` lockups) so the wordmark is pixel-locked and font-independent —
SVG `<text>` renders with whatever monospace the viewer has, which GitHub can't guarantee.

## Geometry (both paths, `viewBox="0 0 48 48"`)

```
bracket:  M18 9H11V39H18   stroke 5, butt caps, miter joins
caret:    M24 12L41 24L24 36Z   filled
```

The tile scales this group by `0.8` and centers it: `translate(4.2 4.8) scale(0.8)` inside a
`rx="11"` squircle. Everything is a plain path — recolor, resize, or invert by changing one value.

## Notes for final production

- The lockups use **live monospace `<text>`**. For locked, portable art, convert the text to
  outlines in the final licensed face (**JetBrains Mono** / **Berkeley Mono**, weight 700,
  `letter-spacing ≈ -0.03em`).
- `docir-mark-mono.svg` uses `currentColor`; it renders black in `<img>`. Inline the SVG (or set
  `color`) to tint it.

## Regenerating the rasters

The PNGs and `.ico` are committed, so this is only needed if the SVG changes.

```bash
# needs libcairo (Linux: apt install libcairo2 · macOS: brew install cairo)
uv run --with cairosvg --with pillow python assets/logo/build_icons.py
```

Rasterizes `docir-icon.svg` to every PNG size, flattens the Apple icon to opaque, and packs
`favicon.ico`.
