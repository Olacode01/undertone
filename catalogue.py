"""
Build a colour-matchable catalogue from YouCam's built-in garment templates.

The templates endpoint returns id, title, category_name and a thumbnail URL —
but no colour. Colour is what the whole matching layer runs on, so we extract
it from the thumbnail.

Naive "average the pixels" fails badly here: the thumbnails are worn garments
on models against pale backdrops, so averaging blends garment, skin and
background into a muddy beige that matches nothing meaningfully.

Instead:
  1. Crop to the torso band — the garment dominates there, the face doesn't.
  2. Quantise to a small adaptive palette.
  3. Drop backdrop (near-white), shadow (near-black) and low-chroma greys.
  4. Take the most frequent survivor, weighted toward chromatic pixels.

    pip install pillow httpx
    python catalogue.py            # writes garments_youcam.csv
"""

from __future__ import annotations

import asyncio
import csv
import logging
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from colour import hex_to_lab
from youcam_client import UnitBudget, YouCamClient

log = logging.getLogger("catalogue")

# Bands as fractions of the thumbnail (left, top, right, bottom).
FACE_CROP = (0.35, 0.04, 0.65, 0.20)   # head — used to learn the model's skin
TORSO_CROP = (0.28, 0.24, 0.72, 0.52)  # chest/waist — where the garment is

QUANTISE_COLOURS = 12
MIN_LIGHTNESS = 12.0   # below this is shadow
MAX_LIGHTNESS = 94.0   # above this is backdrop
MIN_CHROMA = 8.0       # below this is grey — real, but rarely the garment ID
SKIN_EXCLUSION = 16.0  # ΔE below which a cluster is treated as the model's skin


def _clusters(
    image: Image.Image, crop: tuple[float, float, float, float]
) -> list[tuple[int, tuple[int, int, int]]]:
    """Quantise a crop and return (pixel_count, rgb), most frequent first."""
    width, height = image.size
    left, top, right, bottom = crop
    region = image.crop((
        int(width * left), int(height * top),
        int(width * right), int(height * bottom),
    ))
    region.thumbnail((120, 120))

    quantised = region.quantize(colors=QUANTISE_COLOURS, method=Image.MEDIANCUT)
    palette = quantised.getpalette() or []
    try:
        data = quantised.get_flattened_data()      # Pillow >= 12
    except AttributeError:                          # pragma: no cover
        data = quantised.getdata()

    out = []
    for index, count in Counter(data).items():
        rgb = tuple(palette[index * 3: index * 3 + 3])
        if len(rgb) == 3:
            out.append((count, rgb))
    return sorted(out, key=lambda pair: -pair[0])


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def dominant_colour(image: Image.Image) -> tuple[str, str]:
    """Garment colour from a worn-garment thumbnail.

    Returns (garment_hex, model_skin_hex).

    The hard part is that these are garments ON PEOPLE. Skin is a large,
    coherent, mid-lightness region that quantisation happily returns as the
    dominant colour — and warm skin tones then match warm palettes, producing
    rankings that look excellent and mean nothing.

    Rather than guess a skin range globally (which would also exclude genuinely
    rust, clay and camel garments — the exact colours an Autumn palette wants),
    learn THIS model's skin from the face band, then exclude clusters within
    ΔE 16 of it in the torso band. Per-image, so it adapts to every skin tone
    instead of encoding one.
    """
    from match import distance  # local import avoids a circular import at load

    image = image.convert("RGB")

    face = _clusters(image, FACE_CROP)
    skin_hex = ""
    for _, rgb in face:
        lightness, a, b = hex_to_lab(_hex(rgb))
        if MIN_LIGHTNESS < lightness < MAX_LIGHTNESS and (a * a + b * b) ** 0.5 > 8:
            skin_hex = _hex(rgb)
            break

    scored: list[tuple[float, tuple[int, int, int]]] = []
    for count, rgb in _clusters(image, TORSO_CROP):
        hex_value = _hex(rgb)
        lightness, a, b = hex_to_lab(hex_value)
        chroma = (a * a + b * b) ** 0.5

        if not (MIN_LIGHTNESS < lightness < MAX_LIGHTNESS):
            continue
        if skin_hex and distance(hex_value, skin_hex) < SKIN_EXCLUSION:
            continue  # the model, not the garment
        weight = float(count) * (0.25 if chroma < MIN_CHROMA else 1.0)
        scored.append((weight, rgb))

    if not scored:
        return "#808080", skin_hex
    _, best = max(scored, key=lambda pair: pair[0])
    return _hex(best), skin_hex


def save_debug_crop(image: Image.Image, name: str, folder: Path) -> None:
    """Write the sampled bands so you can SEE what's being measured.

    Cheaper than reasoning about why a number looks wrong.
    """
    folder.mkdir(exist_ok=True)
    width, height = image.size
    safe = "".join(c if c.isalnum() else "_" for c in name)[:40]
    for label, crop in (("face", FACE_CROP), ("torso", TORSO_CROP)):
        left, top, right, bottom = crop
        image.crop((
            int(width * left), int(height * top),
            int(width * right), int(height * bottom),
        )).save(folder / f"{safe}_{label}.png")


def guess_category(title: str, category_name: str) -> str:
    """Templates don't state garment_category; infer it from the label."""
    text = f"{title} {category_name}".lower()
    full_body = ("gown", "dress", "wedding", "tulle", "jumpsuit", "suit", "kit")
    lower_body = ("trouser", "jeans", "skirt", "shorts", "pants")
    if any(word in text for word in full_body):
        return "full_body"
    if any(word in text for word in lower_body):
        return "lower_body"
    return "upper_body"


async def build(
    output: Path = Path("garments_youcam.csv"), *, debug: bool = False
) -> None:
    async with YouCamClient(budget=UnitBudget(max_units=0)) as client:
        templates = await client.cloth_templates()

    if isinstance(templates, dict):
        templates = templates.get("results") or list(templates.values())
    log.info("%s templates returned\n", len(templates))
    log.info("  %-28s %-9s %-9s", "garment", "colour", "skin(excl)")

    rows: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
        for template in templates:
            thumb = template.get("thumb")
            if not thumb:
                continue
            title = template.get("title", template.get("id", "?"))
            try:
                response = await http.get(thumb)
                response.raise_for_status()
                image = Image.open(BytesIO(response.content))
                colour, skin = dominant_colour(image)
                if debug:
                    save_debug_crop(image.convert("RGB"), title, Path("debug_crops"))
            except Exception as exc:
                log.warning("  %s: %s", title, exc)
                continue

            rows.append({
                "name": title,
                "colour": colour,
                "category": guess_category(title, template.get("category_name", "")),
                "brand": f"YouCam / {template.get('category_name', '')}".strip(" /"),
                # The thumb doubles as the try-on reference. template_id is
                # documented but rejected by the API, so the URL is what
                # actually works.
                "image_url": thumb,
                "template_id": template.get("id", ""),
            })
            log.info("  %-28s %-9s %-9s", title[:28], colour, skin or "—")

    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["name", "colour", "category", "brand", "image_url", "template_id"],
        )
        writer.writeheader()
        writer.writerows(rows)

    log.info("wrote %s garments to %s", len(rows), output)
    print(
        f"\nNow score them:\n"
        f"    python undertone.py match Pass.jpg --catalogue {output}\n"
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build a YouCam garment catalogue")
    parser.add_argument("--output", type=Path, default=Path("garments_youcam.csv"))
    parser.add_argument("--debug", action="store_true",
                        help="Write the sampled face/torso crops to debug_crops/ "
                             "so you can check what's actually being measured")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(build(args.output, debug=args.debug))
