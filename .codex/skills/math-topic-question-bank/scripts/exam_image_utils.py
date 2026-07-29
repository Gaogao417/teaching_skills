"""Shared image helpers for deterministic exam-source crops."""

from __future__ import annotations

from PIL import Image


def composite_transparency_on_white(image: Image.Image) -> Image.Image:
    """Return an RGB copy, preserving transparent artwork on a white page.

    Word commonly stores black line art as RGB=(0, 0, 0) plus a varying alpha
    channel. Calling ``convert("RGB")`` directly discards alpha and turns the
    whole canvas black. Palette PNG transparency has the same requirement.
    """

    if "A" not in image.getbands() and "transparency" not in image.info:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    return Image.alpha_composite(background, rgba).convert("RGB")
