"""
Garment matching — the join between Skin Tone Analysis and Apparel VTO.

Without this, a project using both APIs is just two features on one page. This
is what makes them one experience: the colour profile derived from the user's
face decides which garments are worth trying on, and VTO then proves the call
on their actual photo.

Colour distance uses CIEDE2000, the CIE's current standard. Not Euclidean RGB
distance, which is perceptually wrong — it treats a 20-point shift in dark blue
as equivalent to 20 points in bright yellow, when the eye sees those very
differently. CIEDE2000 corrects for lightness, chroma and hue-dependent
sensitivity, which is exactly what "does this colour suit me" depends on.

No dependencies beyond the standard library.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from colour import hex_to_lab


# --------------------------------------------------------------------------
# CIEDE2000
# --------------------------------------------------------------------------


def delta_e_2000(
    lab1: tuple[float, float, float],
    lab2: tuple[float, float, float],
    *,
    k_l: float = 1.0,
    k_c: float = 1.0,
    k_h: float = 1.0,
) -> float:
    """Perceptual colour difference. Roughly: <1 imperceptible, ~2-3 just
    noticeable, >10 clearly different colours."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2

    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25.0**7))) if c_bar else 0.0
    a1p, a2p = (1 + g) * a1, (1 + g) * a2

    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360

    dlp = l2 - l1
    dcp = c2p - c1p

    if c1p * c2p == 0:
        dhp = 0.0
    else:
        dh = h2p - h1p
        if dh > 180:
            dh -= 360
        elif dh < -180:
            dh += 360
        dhp = dh
    dhp_big = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dhp) / 2)

    lbp = (l1 + l2) / 2
    cbp = (c1p + c2p) / 2

    if c1p * c2p == 0:
        hbp = h1p + h2p
    elif abs(h1p - h2p) > 180:
        hbp = (h1p + h2p + 360) / 2 if (h1p + h2p) < 360 else (h1p + h2p - 360) / 2
    else:
        hbp = (h1p + h2p) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(hbp - 30))
        + 0.24 * math.cos(math.radians(2 * hbp))
        + 0.32 * math.cos(math.radians(3 * hbp + 6))
        - 0.20 * math.cos(math.radians(4 * hbp - 63))
    )

    d_theta = 30 * math.exp(-(((hbp - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cbp**7 / (cbp**7 + 25.0**7)) if cbp else 0.0
    s_l = 1 + (0.015 * (lbp - 50) ** 2) / math.sqrt(20 + (lbp - 50) ** 2)
    s_c = 1 + 0.045 * cbp
    s_h = 1 + 0.015 * cbp * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c

    return math.sqrt(
        (dlp / (k_l * s_l)) ** 2
        + (dcp / (k_c * s_c)) ** 2
        + (dhp_big / (k_h * s_h)) ** 2
        + r_t * (dcp / (k_c * s_c)) * (dhp_big / (k_h * s_h))
    )


def distance(hex_a: str, hex_b: str) -> float:
    return delta_e_2000(hex_to_lab(hex_a), hex_to_lab(hex_b))


# --------------------------------------------------------------------------
# Garment scoring
# --------------------------------------------------------------------------

# Calibrated against CIEDE2000's perceptual scale rather than picked at random.
EXCELLENT, GOOD, WORKABLE = 12.0, 22.0, 34.0
CLASH_THRESHOLD = 14.0


@dataclass
class Garment:
    name: str
    colour: str                 # hex
    category: str               # upper_body | lower_body | full_body
    image_url: str = ""
    brand: str = ""
    template_id: str = ""       # YouCam built-in garment, if sourced from there

    @property
    def wearable(self) -> bool:
        return bool(self.image_url or self.template_id)


@dataclass
class Match:
    garment: Garment
    fit_distance: float         # ΔE to nearest palette colour
    nearest_palette: str        # name of that colour
    clash_distance: float       # ΔE to nearest "avoid" colour
    verdict: str
    reason: str

    @property
    def score(self) -> float:
        """0-100, higher is better. For sorting and display."""
        base = max(0.0, 100.0 - (self.fit_distance * 2.4))
        if self.clash_distance < CLASH_THRESHOLD:
            base *= 0.45
        return round(base, 1)


def score_garment(garment: Garment, recommendation: dict[str, Any]) -> Match:
    """Score one garment against a seasonal palette."""
    wear = recommendation["wear"] + recommendation["neutrals"]
    avoid = recommendation["avoid"]

    fit_distance, nearest = min(
        ((distance(garment.colour, c["hex"]), c["name"]) for c in wear),
        key=lambda pair: pair[0],
    )
    clash_distance = min(distance(garment.colour, c["hex"]) for c in avoid)

    if clash_distance < CLASH_THRESHOLD:
        verdict = "clashes"
        reason = (
            f"Sits close to a colour that fights your colouring "
            f"(ΔE {clash_distance:.0f} from an avoid-tone)."
        )
    elif fit_distance <= EXCELLENT:
        verdict = "excellent"
        reason = f"Almost exactly your {nearest} (ΔE {fit_distance:.0f})."
    elif fit_distance <= GOOD:
        verdict = "good"
        reason = f"Close to your {nearest} (ΔE {fit_distance:.0f})."
    elif fit_distance <= WORKABLE:
        verdict = "workable"
        reason = (
            f"In the region of your {nearest} but noticeably off "
            f"(ΔE {fit_distance:.0f}). Fine away from the face."
        )
    else:
        verdict = "poor"
        reason = (
            f"Nothing in your palette is near this "
            f"(closest is {nearest}, ΔE {fit_distance:.0f})."
        )

    return Match(
        garment=garment,
        fit_distance=round(fit_distance, 1),
        nearest_palette=nearest,
        clash_distance=round(clash_distance, 1),
        verdict=verdict,
        reason=reason,
    )


def rank_garments(
    garments: list[Garment], recommendation: dict[str, Any], *, limit: int | None = None
) -> list[Match]:
    matches = sorted(
        (score_garment(g, recommendation) for g in garments),
        key=lambda m: -m.score,
    )
    return matches[:limit] if limit else matches


def load_garments(path: Path) -> list[Garment]:
    with Path(path).open() as fh:
        return [
            Garment(
                name=row["name"],
                colour=row["colour"],
                category=row.get("category", "upper_body"),
                image_url=row.get("image_url", ""),
                brand=row.get("brand", ""),
                template_id=row.get("template_id", ""),
            )
            for row in csv.DictReader(fh)
            if row.get("colour")
        ]


def render(matches: list[Match]) -> str:
    rows = []
    for i, m in enumerate(matches, 1):
        rows.append(
            f"{i:>2}. {m.garment.name[:32]:<32} {m.garment.colour:<8} "
            f"{m.score:>5.1f}  {m.verdict:<9} {m.reason}"
        )
    header = f"{'  #':<4} {'Garment':<32} {'Hex':<8} {'Score':>5}  {'Verdict':<9} Why"
    return "\n".join([header, "-" * len(header), *rows])


if __name__ == "__main__":
    from colour import analyse, recommend

    profile = recommend(analyse({
        "skin_color": "#624836", "hair_color": "#FAF0BE",
        "eyebrow_color": "#5b575a", "eye_color": "#362f32",
        "lip_color": "#9c7e8a",
    }))
    print(f"Season: {profile['palette']}  (confidence {profile['confidence']})\n")

    catalogue = Path("garments.csv")
    if catalogue.exists():
        print(render(rank_garments(load_garments(catalogue), profile)))
    else:
        print("No garments.csv found.")
