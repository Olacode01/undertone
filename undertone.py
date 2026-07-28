"""
Undertone — one experience, not two features.

    selfie ──► Skin Tone Analysis ──► seasonal colour profile
                                            │
                                            ▼
                                    garment catalogue scored
                                    by CIEDE2000 against the palette
                                            │
                                            ▼
    full-body photo ─────────────────► Apparel VTO on the top matches

The join is the point. Tone analysis decides WHICH garments are worth trying
on; VTO proves the call on the user's own photo. Neither API is decorative.

    python undertone.py analyse Pass.jpg
    python undertone.py match    Pass.jpg
    python undertone.py tryon    Pass.jpg --body full_body.jpg --top 2
    python undertone.py templates
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from colour import analyse, recommend
from match import load_garments, rank_garments, render
from youcam_client import UnitBudget, YouCamClient, YouCamError

log = logging.getLogger("undertone")


def _print_profile(profile: dict) -> None:
    print(f"\n  Season      {profile['palette']}")
    print(f"  Undertone   {profile['undertone']} (hue {profile['hue_angle']:.0f}°)")
    print(f"  Depth       {profile['value']} (L* {profile['skin_lightness']:.0f})")
    print(f"  Contrast    {profile['contrast']} "
          f"(ΔL* {profile['contrast_delta']:.0f} via {profile['contrast_source']})")
    print(f"  Chroma      {profile['chroma']}")
    print(f"  Confidence  {profile['confidence']}")
    for warning in profile.get("warnings", []):
        print(f"\n  ! {warning}")
    print(f"\n  {profile['why']}\n")
    print("  Wear:    " + ", ".join(c["name"] for c in profile["wear"]))
    print("  Neutrals:" + ", ".join(c["name"] for c in profile["neutrals"]))
    print("  Avoid:   " + ", ".join(c["name"] for c in profile["avoid"]))
    print(f"  Metals:  {profile['metals']}\n")


async def cmd_analyse(args) -> dict:
    async with YouCamClient(budget=UnitBudget(max_units=args.max_units)) as client:
        colors = await client.skin_tone(args.selfie)
    print("\n  Detected:", json.dumps(colors))
    profile = recommend(analyse(colors))
    _print_profile(profile)
    Path("profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False))
    print("  Saved profile.json — reuse it with --profile to avoid spending units.\n")
    return profile


async def load_profile(args) -> dict:
    """Reuse a saved profile rather than re-analysing. Units are finite."""
    cached = Path(args.profile or "profile.json")
    if cached.exists() and not args.refresh:
        log.info("Using cached %s (pass --refresh to re-analyse)", cached)
        return json.loads(cached.read_text())
    return await cmd_analyse(args)


async def cmd_match(args) -> None:
    profile = await load_profile(args)
    garments = load_garments(args.catalogue)
    print(f"\n  {len(garments)} garments scored against {profile['palette']}\n")
    print(render(rank_garments(garments, profile)))
    print()


async def cmd_tryon(args) -> None:
    profile = await load_profile(args)
    garments = load_garments(args.catalogue)
    matches = rank_garments(garments, profile, limit=args.top)

    wearable = [m for m in matches if m.garment.wearable]
    if not wearable:
        raise SystemExit(
            "None of the top matches are wearable — they need either an "
            "image_url or a template_id.\n"
            "Build a catalogue from YouCam's own garments:\n"
            "    python catalogue.py\n"
            "    python undertone.py tryon Pass.jpg --body full.jpg "
            "--catalogue garments_youcam.csv"
        )

    async with YouCamClient(budget=UnitBudget(max_units=args.max_units)) as client:
        for match in wearable:
            garment = match.garment
            print(f"\n  Trying on {garment.name} "
                  f"({match.verdict}, score {match.score}, {garment.colour})")
            try:
                url = await client.try_on(
                    args.body,
                    garment_url=garment.image_url or None,
                    template_id=garment.template_id or None,
                    category=garment.category,
                )
                print(f"  → {url}")
            except YouCamError as exc:
                print(f"  ! failed: {exc}")


async def cmd_templates(args) -> None:
    async with YouCamClient(budget=UnitBudget(max_units=args.max_units)) as client:
        print(json.dumps(await client.cloth_templates(), indent=2)[:4000])


def main() -> None:
    # Shared flags live on a parent parser so they work either side of the
    # subcommand — `undertone.py match x.jpg --catalogue y.csv` and
    # `undertone.py --catalogue y.csv match x.jpg` both parse.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--max-units", type=int, default=20)
    common.add_argument("--catalogue", type=Path, default=Path("garments.csv"))
    common.add_argument("--profile", type=Path, default=None)
    common.add_argument("--refresh", action="store_true",
                        help="Re-run tone analysis instead of using profile.json")

    parser = argparse.ArgumentParser(description="Undertone", parents=[common])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyse", parents=[common],
                       help="Selfie -> colour profile")
    p.add_argument("selfie", type=Path)

    p = sub.add_parser("match", parents=[common],
                       help="Score the catalogue against the profile")
    p.add_argument("selfie", type=Path)

    p = sub.add_parser("tryon", parents=[common],
                       help="VTO the best-matching garments")
    p.add_argument("selfie", type=Path)
    p.add_argument("--body", type=Path, required=True,
                   help="Full/upper body photo, forward-facing, standing")
    p.add_argument("--top", type=int, default=2)

    sub.add_parser("templates", parents=[common],
                   help="List YouCam's built-in garments")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    handlers = {
        "analyse": cmd_analyse, "match": cmd_match,
        "tryon": cmd_tryon, "templates": cmd_templates,
    }
    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()
