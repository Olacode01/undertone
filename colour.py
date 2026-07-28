"""
Seasonal colour analysis from YouCam Facial Color Tones output.

This module is the reason the project isn't a wrapper around an API call.
YouCam gives us hex values:

    {"skin_color": "#b9947c", "hair_color": "#a0a0a0", "eye_color": "#293F9B",
     "lip_color": "#D23245", "eyebrow_color": "#5B2B31", ...}

Turning those into "wear these colours" needs actual colour science:

  * undertone  — warm vs cool, from the hue angle and the b* axis in CIELAB
  * value      — how light or deep the colouring is, from L*
  * contrast   — the gap between skin and hair lightness
  * chroma     — how saturated the natural colouring is

Those four axes give the season. Seasonal colour analysis is long-established
public colour theory (Itten's warm/cool work, later four- and twelve-season
systems); the palettes below are constructed from those principles rather than
copied from any commercial system.

No dependencies beyond the standard library.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass, asdict, field
from typing import Any


# --------------------------------------------------------------------------
# Colour space conversion
# --------------------------------------------------------------------------


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    s = (value or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        raise ValueError(f"Not a hex colour: {value!r}")
    return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_xyz(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return (
        r * 0.4124564 + g * 0.3575761 + b * 0.1804375,
        r * 0.2126729 + g * 0.7151522 + b * 0.0721750,
        r * 0.0193339 + g * 0.1191920 + b * 0.9503041,
    )


# D65 reference white
_WHITE = (0.95047, 1.00000, 1.08883)


def xyz_to_lab(xyz: tuple[float, float, float]) -> tuple[float, float, float]:
    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)

    fx, fy, fz = (f(c / w) for c, w in zip(xyz, _WHITE))
    return (116 * fy) - 16, 500 * (fx - fy), 200 * (fy - fz)


def hex_to_lab(value: str) -> tuple[float, float, float]:
    """L* 0-100, a* green/red, b* blue/yellow."""
    return xyz_to_lab(rgb_to_xyz(hex_to_rgb(value)))


def hex_to_hsv(value: str) -> tuple[float, float, float]:
    r, g, b = hex_to_rgb(value)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s, v


# --------------------------------------------------------------------------
# Palettes
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    season: str
    summary: str
    wear: list[tuple[str, str]]      # (hex, name)
    avoid: list[tuple[str, str]]
    metals: str
    neutrals: list[tuple[str, str]]


PALETTES: dict[str, Palette] = {
    "spring": Palette(
        season="Spring",
        summary="Warm and light, with clear brightness. Colours that look "
                "sunlit rather than muted.",
        wear=[("#FF6F5E", "Coral"), ("#FFD24C", "Golden yellow"),
              ("#7ED957", "Fresh green"), ("#5EC8E5", "Aqua"),
              ("#FF9AA2", "Warm pink"), ("#F5A623", "Apricot"),
              ("#9BD4C4", "Light jade"), ("#E8734A", "Warm terracotta")],
        avoid=[("#2C2C2C", "Black"), ("#4A4A6A", "Dusty navy"),
               ("#6E6E6E", "Cool grey")],
        metals="Gold, warm brass",
        neutrals=[("#F5EBDC", "Ivory"), ("#C8A882", "Camel"),
                  ("#8B7355", "Warm taupe")],
    ),
    "summer": Palette(
        season="Summer",
        summary="Cool and light, with softness. Colours that look slightly "
                "hazy rather than sharp.",
        wear=[("#A8C0D8", "Powder blue"), ("#D9A7C7", "Soft rose"),
              ("#9CAF9C", "Sage"), ("#B8A9C9", "Lavender"),
              ("#7A9CB5", "Denim blue"), ("#E8B4B8", "Dusty pink"),
              ("#6B8E9F", "Slate teal"), ("#C9CBD3", "Pearl grey")],
        avoid=[("#FF6600", "Orange"), ("#2C2C2C", "Black"),
               ("#D4AF37", "Mustard")],
        metals="Silver, white gold, rose gold",
        neutrals=[("#F0F0F2", "Soft white"), ("#8E8E9C", "Cool grey"),
                  ("#4A5568", "Charcoal navy")],
    ),
    "autumn": Palette(
        season="Autumn",
        summary="Warm and deep, with richness. Colours with earth in them "
                "rather than brightness.",
        wear=[("#B7410E", "Rust"), ("#8B6914", "Olive gold"),
              ("#556B2F", "Moss"), ("#A0522D", "Sienna"),
              ("#C67B5C", "Clay"), ("#7B3F00", "Chocolate"),
              ("#DAA520", "Goldenrod"), ("#6B4423", "Umber")],
        avoid=[("#FF69B4", "Icy pink"), ("#E0FFFF", "Pastel blue"),
               ("#2C2C2C", "Pure black")],
        metals="Antique gold, bronze, copper",
        neutrals=[("#EFE6D5", "Cream"), ("#8B7355", "Coffee"),
                  ("#3E3428", "Deep bark")],
    ),
    "winter": Palette(
        season="Winter",
        summary="Cool and deep, with high contrast. Colours that are clear "
                "and saturated, never muddy.",
        wear=[("#00205B", "True navy"), ("#B00020", "True red"),
              ("#00755E", "Emerald"), ("#4B0082", "Royal purple"),
              ("#0F52BA", "Sapphire"), ("#E91E63", "Magenta"),
              ("#008B8B", "Teal"), ("#FFFFFF", "Pure white")],
        avoid=[("#E8C39E", "Beige"), ("#C68642", "Camel"),
               ("#9CAF88", "Olive")],
        metals="Silver, platinum, white gold",
        neutrals=[("#FFFFFF", "Optic white"), ("#2C2C2C", "True black"),
                  ("#36454F", "Charcoal")],
    ),
}


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------


@dataclass
class ColourProfile:
    undertone: str            # warm | cool | neutral
    undertone_score: float    # -1 cool .. +1 warm
    hue_angle: float          # h_ab in degrees, lightness-invariant
    value: str                # light | medium | deep
    skin_lightness: float     # L*
    contrast: str             # low | medium | high
    contrast_delta: float
    contrast_source: str      # hair | eyebrow
    chroma: str               # soft | clear
    season: str
    confidence: float         # 0..1, how decisive the axes were
    warnings: list[str] = field(default_factory=list)


def _undertone(skin_hex: str) -> tuple[str, float, float]:
    """Warm/cool from the CIELAB hue angle, h_ab = atan2(b*, a*).

    Deliberately NOT from raw a*/b* magnitudes. Those scale with lightness, so
    thresholds tuned on mid-light skin misread deep skin as "neutral" — the
    reading collapses toward zero simply because the sample is darker, not
    because the undertone is genuinely ambiguous.

    Hue angle is lightness-invariant: it measures the DIRECTION of the colour
    in the a*/b* plane, not its magnitude. Human skin lands roughly between
    35° and 75° regardless of depth. Golden/olive skin sits high in that range,
    pink/red skin low. That makes one threshold valid across the whole tonal
    range, which is the only defensible way to do this.

    Returns (label, score in -1..+1, hue angle in degrees).
    """
    _, a, b = hex_to_lab(skin_hex)
    hue = math.degrees(math.atan2(b, a))

    # 51° is the neutral axis; ±12° covers the warm/cool decision band.
    score = max(-1.0, min(1.0, (hue - 51.0) / 12.0))
    if score > 0.33:
        return "warm", score, hue
    if score < -0.33:
        return "cool", score, hue
    return "neutral", score, hue


def _chroma_value(hex_value: str) -> float:
    """C* — distance from the neutral axis. How saturated the colour is."""
    _, a, b = hex_to_lab(hex_value)
    return math.hypot(a, b)


def _value(skin_hex: str) -> tuple[str, float]:
    lightness, _, _ = hex_to_lab(skin_hex)
    if lightness >= 70:
        return "light", lightness
    if lightness >= 50:
        return "medium", lightness
    return "deep", lightness


def validate(colors: dict[str, Any]) -> list[str]:
    """Sanity-check the detector's output before trusting it.

    The tone analyzer samples pixel regions, and on plain light backgrounds —
    passport photos especially — the hair region can pick up the backdrop
    instead of hair. That produces readings like `hair_color: #FAF0BE`
    ("Blonde") on deep skin, which then wrecks the contrast axis.

    Better to name the problem than to silently produce a confident wrong
    answer.
    """
    warnings: list[str] = []
    skin = colors.get("skin_color")
    hair = colors.get("hair_color")
    if not skin or not hair:
        return warnings

    skin_l = hex_to_lab(skin)[0]
    hair_l = hex_to_lab(hair)[0]
    hair_c = _chroma_value(hair)

    # Near-white and nearly unsaturated is a backdrop, not hair.
    if hair_l > 82 and hair_c < 30:
        warnings.append(
            f"hair_color {hair} is very light and desaturated (L* {hair_l:.0f}, "
            f"C* {hair_c:.0f}) — likely the photo background rather than hair. "
            f"Using eyebrow colour for the contrast reading instead."
        )
    elif hair_l - skin_l > 45:
        warnings.append(
            f"hair_color {hair} is much lighter than skin (ΔL* "
            f"{hair_l - skin_l:.0f}). Possible background contamination; "
            f"verify against the photo."
        )
    return warnings


def _contrast(skin_hex: str, hair_hex: str, eyebrow_hex: str | None,
              suspect_hair: bool) -> tuple[str, float, str]:
    """Skin-to-hair lightness gap, with eyebrows as the fallback reference.

    Eyebrows track hair depth closely and sit inside the face region, so they
    are far less likely to be contaminated by the background.
    """
    skin_l = hex_to_lab(skin_hex)[0]
    if suspect_hair and eyebrow_hex:
        reference, source = hex_to_lab(eyebrow_hex)[0], "eyebrow"
    else:
        reference, source = hex_to_lab(hair_hex)[0], "hair"

    delta = abs(skin_l - reference)
    if delta >= 45:
        return "high", delta, source
    if delta >= 22:
        return "medium", delta, source
    return "low", delta, source


def _chroma(skin_hex: str, eye_hex: str, lip_hex: str) -> str:
    """Clear colouring has saturated features; soft colouring is muted."""
    saturations = [hex_to_hsv(c)[1] for c in (skin_hex, eye_hex, lip_hex) if c]
    return "clear" if (sum(saturations) / len(saturations)) > 0.42 else "soft"


def analyse(colors: dict[str, Any]) -> ColourProfile:
    """Map YouCam's `results.color` block onto a seasonal profile.

    Expects at minimum `skin_color`. Falls back gracefully when hair, eye or
    lip colour is missing — those refine the result rather than determine it.
    """
    skin = colors.get("skin_color")
    if not skin:
        raise ValueError("skin_color is required for colour analysis")

    hair = colors.get("hair_color") or skin
    eye = colors.get("eye_color") or skin
    lip = colors.get("lip_color") or skin
    eyebrow = colors.get("eyebrow_color")

    warnings = validate(colors)
    suspect_hair = any("background" in w for w in warnings)

    undertone, undertone_score, hue = _undertone(skin)
    value, lightness = _value(skin)
    contrast, delta, contrast_source = _contrast(skin, hair, eyebrow, suspect_hair)
    chroma = _chroma(skin, eye, lip)

    # Warm/cool picks the pair; depth and contrast pick within it.
    warm = undertone == "warm" or (undertone == "neutral" and undertone_score >= 0)
    deep = value == "deep" or contrast == "high"

    if warm:
        season = "autumn" if deep else "spring"
    else:
        season = "winter" if deep else "summer"

    # Chroma can override a borderline call: clear colouring belongs in the
    # bright seasons, soft colouring in the muted ones.
    if chroma == "clear" and season == "summer" and contrast != "low":
        season = "winter"
    if chroma == "soft" and season == "spring" and contrast == "low":
        season = "summer" if not warm else "autumn"

    # Confidence: decisive axes give a trustworthy answer. Say so honestly
    # rather than presenting every result as equally certain.
    undertone_certainty = min(1.0, abs(undertone_score) / 0.6)
    contrast_certainty = min(1.0, abs(delta - 33) / 33 + 0.4)
    confidence = 0.5 * undertone_certainty + 0.5 * contrast_certainty

    # Degraded inputs must lower the stated confidence. A number that stays
    # high while the inputs are known-bad is worse than useless.
    if warnings:
        confidence *= 0.65

    return ColourProfile(
        undertone=undertone,
        undertone_score=round(undertone_score, 3),
        hue_angle=round(hue, 1),
        value=value,
        skin_lightness=round(lightness, 1),
        contrast=contrast,
        contrast_delta=round(delta, 1),
        contrast_source=contrast_source,
        chroma=chroma,
        season=season,
        confidence=round(min(confidence, 0.99), 2),
        warnings=warnings,
    )


def recommend(profile: ColourProfile) -> dict[str, Any]:
    """Profile -> palette plus a plain-language explanation."""
    palette = PALETTES[profile.season]
    why = (
        f"Your skin reads {profile.undertone} (hue angle "
        f"{profile.hue_angle:.0f}°) at {profile.value} depth "
        f"(L* {profile.skin_lightness:.0f}), with {profile.contrast} contrast "
        f"between skin and {profile.contrast_source} "
        f"(ΔL* {profile.contrast_delta:.1f}) and {profile.chroma} natural "
        f"colouring. That places you in {palette.season}."
    )
    return {
        **asdict(profile),
        "palette": palette.season,
        "summary": palette.summary,
        "why": why,
        "wear": [{"hex": h, "name": n} for h, n in palette.wear],
        "avoid": [{"hex": h, "name": n} for h, n in palette.avoid],
        "neutrals": [{"hex": h, "name": n} for h, n in palette.neutrals],
        "metals": palette.metals,
    }


if __name__ == "__main__":
    import json

    # The example from YouCam's own docs.
    sample = {
        "eye_color": "#293F9B", "eye_color_name": "Blue",
        "lip_color": "#D23245", "eyebrow_color": "#5B2B31",
        "skin_color": "#b9947c", "hair_color": "#a0a0a0",
        "hair_color_name": "Auburn",
    }
    print(json.dumps(recommend(analyse(sample)), indent=2, ensure_ascii=False))
