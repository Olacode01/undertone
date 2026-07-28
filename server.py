"""
Undertone — FastAPI backend.

    pip install fastapi uvicorn python-multipart
    uvicorn server:app --reload

    UNDERTONE_DEMO=1 uvicorn server:app --reload   # cached profile, zero units

Demo mode matters: the entire interface can be built, styled and reviewed
against a cached profile.json without spending a single unit. Only flip it off
when you're recording the demo video.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from colour import ColourProfile, analyse, recommend
from match import load_garments, rank_garments
from youcam_client import UnitBudget, YouCamClient, YouCamError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("undertone.server")

HERE = Path(__file__).parent
CATALOGUE = HERE / "garments_youcam.csv"
PROFILE_CACHE = HERE / "profile.json"
DEMO_MODE = os.environ.get("UNDERTONE_DEMO") == "1"
MAX_UNITS = int(os.environ.get("UNDERTONE_MAX_UNITS", "50"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = FastAPI(title="Undertone", version="1.0")


def _client() -> YouCamClient:
    return YouCamClient(budget=UnitBudget(max_units=MAX_UNITS))


async def _save_upload(upload: UploadFile) -> Path:
    """Persist an upload to a temp file, enforcing the 10MB API ceiling."""
    suffix = Path(upload.filename or "upload.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(400, "Upload a jpg or png. HEIC is not supported.")

    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    size = 0
    with handle:
        while chunk := await upload.read(1 << 20):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                Path(handle.name).unlink(missing_ok=True)
                raise HTTPException(400, "Image exceeds the 10MB limit.")
            handle.write(chunk)
    return Path(handle.name)


def _rebuild(cached: dict[str, Any]) -> dict[str, Any]:
    """Re-derive palette and prose from the cached MEASUREMENTS.

    The cache stores both the axes (hue angle, L*, ΔL*…) and the presentation
    built from them. Only the axes cost a unit to obtain; wording and palettes
    are free to recompute. Regenerating them means edits to colour.py take
    effect immediately instead of leaving stale text on screen until someone
    pays to re-analyse a face that hasn't changed.
    """
    fields = {f: cached[f] for f in ColourProfile.__dataclass_fields__ if f in cached}
    try:
        return recommend(ColourProfile(**fields))
    except TypeError:
        return cached  # older cache missing an axis — show it as-is


def _catalogue_payload(profile: dict[str, Any]) -> list[dict[str, Any]]:
    if not CATALOGUE.exists():
        return []
    matches = rank_garments(load_garments(CATALOGUE), profile)
    return [
        {
            "name": m.garment.name,
            "colour": m.garment.colour,
            "category": m.garment.category,
            "brand": m.garment.brand,
            "template_id": m.garment.template_id,
            "image_url": m.garment.image_url,
            "score": m.score,
            "verdict": m.verdict,
            "reason": m.reason,
            "fit_distance": m.fit_distance,
            "nearest_palette": m.nearest_palette,
            "wearable": m.garment.wearable,
        }
        for m in matches
    ]


@app.get("/api/health")
async def health() -> dict[str, Any]:
    budget = UnitBudget(max_units=MAX_UNITS)
    return {
        "demo_mode": DEMO_MODE,
        "units_spent": budget.spent,
        "local_cap": MAX_UNITS,          # a dev guard, NOT the account balance
        "catalogue": CATALOGUE.name if CATALOGUE.exists() else None,
        "cached_profile": PROFILE_CACHE.exists(),
    }


@app.get("/api/profile")
async def cached_profile() -> JSONResponse:
    """The last profile, free. Nothing is uploaded, no unit is charged.

    Live mode should not re-analyse a face it has already measured — that
    spends a unit to recompute an identical answer.
    """
    if not PROFILE_CACHE.exists():
        raise HTTPException(404, "No cached profile yet.")
    profile = _rebuild(json.loads(PROFILE_CACHE.read_text()))
    return JSONResponse({
        "profile": profile,
        "garments": _catalogue_payload(profile),
        "source": "cache",
    })


@app.post("/api/analyse")
async def analyse_selfie(selfie: UploadFile | None = File(None)) -> JSONResponse:
    """Selfie -> colour profile -> ranked catalogue.

    In demo mode the cached profile is returned and nothing is uploaded, so the
    UI can be exercised freely.
    """
    if DEMO_MODE or selfie is None:
        if not PROFILE_CACHE.exists():
            raise HTTPException(
                503,
                "Demo mode is on but profile.json is missing. Run "
                "`python undertone.py analyse <selfie.jpg>` once to create it.",
            )
        profile = json.loads(PROFILE_CACHE.read_text())
        return JSONResponse({
            "profile": profile,
            "garments": _catalogue_payload(profile),
            "source": "cache",
        })

    path = await _save_upload(selfie)
    try:
        async with _client() as client:
            colors = await client.skin_tone(path)
        profile = recommend(analyse(colors))
        PROFILE_CACHE.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
    except YouCamError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)

    return JSONResponse({
        "profile": profile,
        "detected": colors,
        "garments": _catalogue_payload(profile),
        "source": "live",
    })


@app.post("/api/tryon")
async def try_on(
    body: UploadFile = File(...),
    template_id: str = "",
    garment_url: str = "",
    category: str = "upper_body",
) -> JSONResponse:
    if DEMO_MODE:
        raise HTTPException(
            503, "Try-on is disabled in demo mode — it always costs a unit."
        )
    if bool(template_id) == bool(garment_url):
        raise HTTPException(400, "Provide exactly one of template_id or garment_url.")

    path = await _save_upload(body)
    try:
        async with _client() as client:
            url = await client.try_on(
                path,
                template_id=template_id or None,
                garment_url=garment_url or None,
                category=category,
            )
    except YouCamError as exc:
        # Surface YouCam's own error codes — error_invalid_src and error_pose
        # tell the user exactly what's wrong with their photo.
        raise HTTPException(422, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, f"YouCam didn't finish in time: {exc}") from exc
    except Exception as exc:
        # Anything else would otherwise return an HTML 500 that the frontend
        # can't parse, hiding the actual cause behind a JSON syntax error.
        log.exception("try-on failed")
        raise HTTPException(500, f"{type(exc).__name__}: {exc}") from exc
    finally:
        path.unlink(missing_ok=True)

    return JSONResponse({"url": url})


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(HERE / "static" / "index.html")


if (HERE / "static").exists():
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


if __name__ == "__main__":
    # Local convenience: `python server.py`. Hosts inject $PORT and require
    # 0.0.0.0 — binding to localhost makes the service unreachable.
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
    )
