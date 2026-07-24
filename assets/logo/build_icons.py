"""Rasterize the docir icon set from SVG.

Run with an ephemeral environment (no repo deps touched):

    uv run --with cairosvg --with pillow python assets/logo/build_icons.py

Produces, next to this script: PNGs at several sizes, an opaque apple-touch
icon, and a multi-resolution favicon.ico — all from docir-icon.svg (the tile).
"""

from __future__ import annotations

import io
import os

import cairosvg
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TILE = os.path.join(HERE, "docir-icon.svg")
INK = (18, 22, 28)  # #12161C — fills the rounded corners for opaque outputs


def render(svg_path: str, size: int) -> Image.Image:
    """Render an SVG to an RGBA PIL image at size x size."""
    png_bytes = cairosvg.svg2png(url=svg_path, output_width=size, output_height=size)
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


def flatten(img: Image.Image, bg: tuple[int, int, int] = INK) -> Image.Image:
    """Composite over an opaque background (square, no alpha) for Apple/manifest."""
    base = Image.new("RGBA", img.size, bg + (255,))
    base.alpha_composite(img)
    return base.convert("RGB")


def main() -> None:
    # Transparent, rounded PNGs (web / manifest use).
    for size, name in [(16, "icon-16.png"), (32, "icon-32.png"),
                       (192, "icon-192.png"), (512, "icon-512.png")]:
        render(TILE, size).save(os.path.join(HERE, name))

    # Apple touch icon: fully opaque square, 180px (iOS applies its own mask).
    flatten(render(TILE, 180)).save(os.path.join(HERE, "apple-touch-icon.png"))

    # Multi-resolution favicon.ico (16/32/48) — visible on any browser chrome.
    # Pass each crisply-rendered frame via append_images; do NOT combine with
    # `sizes=`, which would instead upscale the base image and drop these frames.
    big, *rest = [render(TILE, s) for s in (48, 32, 16)]
    big.save(
        os.path.join(HERE, "favicon.ico"),
        format="ICO",
        append_images=rest,
    )

    produced = sorted(
        f for f in os.listdir(HERE)
        if f.endswith((".png", ".ico"))
    )
    print("built:", ", ".join(produced))


if __name__ == "__main__":
    main()
