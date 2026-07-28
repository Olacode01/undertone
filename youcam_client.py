"""
youcam_client — async Python driver for the YouCam (Perfect Corp) API.

Every YouCam AI feature follows the same four-step shape:

    POST /s2s/v2.0/file/<feature>     -> presigned upload URL + file_id
    PUT  <presigned url>              -> actually upload the bytes
    POST /s2s/v2.0/task/<feature>     -> task_id
    GET  /s2s/v2.0/task/<feature>/id  -> poll until success | error

Things the docs warn about that this handles:

  * Calling the File API does NOT upload the file. Skipping the PUT gives a
    500/unknown_internal_error later, from a completely unrelated endpoint.
  * Polling is MANDATORY. A task that finishes but is never polled expires,
    returns InvalidTaskId, and STILL CHARGES YOUR UNITS.
  * Units are consumed only on success — errors are free. So retries are cheap
    but abandoned tasks are not.
  * Rate limit is 250 requests / 300s per IP and per token. Pace at ~5 QPS.

    pip install httpx
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("youcam")

BASE_URL = "https://yce-api-01.makeupar.com"
API_VERSION = "v2.0"

TERMINAL = {"success", "error"}


def load_env(path: Path = Path(".env")) -> None:
    """Read KEY=value lines from .env into os.environ.

    Keeps secrets out of shell history and out of argv (where any other
    process on the machine can read them via `ps`). .env is gitignored.
    """
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class YouCamError(RuntimeError):
    pass


class UnitBudgetExceeded(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Unit budget
# --------------------------------------------------------------------------


@dataclass
class UnitBudget:
    """Ceiling on billable tasks, persisted across runs.

    You get 1,000 free units. Units are charged per SUCCESSFUL task, so this
    counts completions, not attempts — a failed task costs nothing and is not
    debited here.
    """

    max_units: int
    spent: int = 0
    ledger_path: Path = field(default=Path(".youcam_units.json"))

    def __post_init__(self) -> None:
        if self.ledger_path.exists():
            self.spent = json.loads(self.ledger_path.read_text()).get("spent", 0)

    @property
    def remaining(self) -> int:
        return max(0, self.max_units - self.spent)

    def check(self, n: int = 1) -> None:
        if n > self.remaining:
            raise UnitBudgetExceeded(
                f"Would exceed unit budget: {n} needed, {self.remaining} left "
                f"of {self.max_units}."
            )

    def charge(self, n: int = 1) -> None:
        self.spent += n
        self.ledger_path.write_text(json.dumps({"spent": self.spent}))
        log.info("Charged %s unit(s) — %s/%s used", n, self.spent, self.max_units)


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class YouCamClient:
    def __init__(
        self,
        budget: UnitBudget,
        *,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        version: str = API_VERSION,
        store_dir: Path = Path("youcam_runs"),
        dry_run: bool = False,
    ) -> None:
        load_env()
        self.api_key = api_key or os.environ.get("YOUCAM_API_KEY", "")
        if not self.api_key:
            raise YouCamError(
                "No YOUCAM_API_KEY. Put it in a .env file next to this script:\n"
                "    echo 'YOUCAM_API_KEY=your_key' > .env\n"
                "Get one at https://yce.perfectcorp.com/api-console/en/api-keys/"
            )
        self.base_url = base_url.rstrip("/")
        self.version = version
        self.budget = budget
        self.dry_run = dry_run
        self.store_dir = store_dir
        self.store_dir.mkdir(exist_ok=True)
        self._http = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        self._pace = asyncio.Semaphore(5)  # ~5 QPS, per the rate-limit guidance

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "YouCamClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # -- plumbing ---------------------------------------------------------

    def _persist(self, name: str, payload: Any) -> Path:
        path = self.store_dir / f"{name}_{int(time.time() * 1000)}.json"
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async with self._pace:
            resp = await self._http.post(f"{self.base_url}{path}", json=body)
        return self._handle(resp)

    async def _get(self, path: str) -> dict[str, Any]:
        async with self._pace:
            resp = await self._http.get(f"{self.base_url}{path}")
        return self._handle(resp)

    @staticmethod
    def _handle(resp: httpx.Response) -> dict[str, Any]:
        if resp.status_code == 429:
            raise YouCamError("Rate limited (250 req / 300s). Slow down.")
        try:
            payload = resp.json()
        except Exception:
            resp.raise_for_status()
            raise YouCamError(f"Non-JSON response: {resp.text[:300]}")
        if resp.status_code >= 400 or payload.get("status", 200) >= 400:
            raise YouCamError(
                f"{payload.get('error_code', resp.status_code)}: "
                f"{payload.get('error', resp.text[:300])}"
            )
        return payload

    # -- steps ------------------------------------------------------------

    async def upload(self, feature: str, image_path: Path) -> str:
        """File API + the PUT the docs warn everyone forgets.

        Returns file_id. Free — no units consumed.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise YouCamError(
                f"No such image: {image_path}\n"
                f"Drop a forward-facing selfie into {image_path.parent.resolve()} "
                f"and pass its filename. Requirements: jpg, under 10MB, face "
                f"wider than 60% of the frame, even lighting, no glasses."
            )
        size = image_path.stat().st_size
        if size > 10 * 1024 * 1024:
            raise YouCamError(f"{image_path.name} is {size/1e6:.1f}MB; limit is 10MB")

        suffix = image_path.suffix.lower()
        if suffix in {".heic", ".heif"}:
            raise YouCamError(
                f"{image_path.name} is HEIC — YouCam accepts jpg/jpeg only.\n"
                f"Convert it with the tool already on your Mac:\n"
                f"    sips -s format jpeg {image_path.name} --out "
                f"{image_path.stem}.jpg"
            )
        if suffix not in {".jpg", ".jpeg", ".png"}:
            raise YouCamError(f"Unsupported format {suffix}. Use jpg or png.")

        content_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        meta = await self._post(
            f"/s2s/{self.version}/file/{feature}",
            {"files": [{
                "content_type": content_type,
                "file_name": image_path.name,
                "file_size": size,
            }]},
        )

        entry = meta["data"]["files"][0]
        file_id = entry["file_id"]
        request = entry["requests"][0]

        # THE STEP EVERYONE MISSES. Without it, task creation fails later with
        # an unrelated-looking 500.
        #
        # Use a BARE client here, not self._http. The presigned URL already
        # carries its own credentials in the query string, and S3 rejects the
        # request outright if our `Authorization: Bearer` header rides along:
        #   InvalidArgument: Only one auth mechanism allowed
        # Sending our API key to S3 would also leak it to a third party.
        async with self._pace:
            async with httpx.AsyncClient(timeout=120.0) as raw:
                put = await raw.request(
                    request.get("method", "PUT"),
                    request["url"],
                    content=image_path.read_bytes(),
                    headers=request.get("headers", {}),
                )
        if put.status_code >= 400:
            raise YouCamError(f"Upload PUT failed: {put.status_code} {put.text[:200]}")

        log.info("uploaded %s -> %s…", image_path.name, file_id[:16])
        return file_id

    async def run_task(
        self,
        feature: str,
        payload: dict[str, Any],
        *,
        units: int = 1,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> dict[str, Any]:
        """Create a task and poll it to a terminal state.

        Polling is not optional: an unpolled task expires, returns
        InvalidTaskId, and still charges units.
        """
        self.budget.check(units)

        if self.dry_run:
            log.info("DRY RUN — %s payload: %s", feature, json.dumps(payload)[:300])
            return {"task_status": "dry_run", "payload": payload}

        created = await self._post(f"/s2s/{self.version}/task/{feature}", payload)
        task_id = created["data"]["task_id"]
        log.info("%s task %s… created", feature, task_id[:16])

        deadline = time.time() + timeout
        while time.time() < deadline:
            await asyncio.sleep(poll_interval)
            status = await self._get(f"/s2s/{self.version}/task/{feature}/{task_id}")
            data = status.get("data", {})
            state = data.get("task_status")

            if state == "success":
                self.budget.charge(units)  # only successes are billed
                self._persist(f"{feature}_result", status)
                return data
            if state == "error":
                self._persist(f"{feature}_error", status)
                raise YouCamError(
                    f"{feature} failed: {data.get('error_code') or data}"
                )

        raise TimeoutError(
            f"{feature} task {task_id} did not settle in {timeout}s — "
            f"units may still be charged."
        )

    # -- features ---------------------------------------------------------

    async def skin_tone(
        self, image_path: Path, *, strictness: str = "high"
    ) -> dict[str, Any]:
        """AI Facial Color Tones Analyzer.

        Returns hex values for skin, hair, eye, eyebrow and lip colour —
        the input to seasonal colour analysis.
        """
        file_id = await self.upload("skin-tone-analysis", image_path)
        result = await self.run_task(
            "skin-tone-analysis",
            {"src_file_id": file_id, "face_angle_strictness_level": strictness},
        )
        return (result.get("results") or {}).get("color", {})

    async def skin_analysis(
        self, image_path: Path, *, actions: list[str] | None = None
    ) -> dict[str, Any]:
        """AI Skin Analysis.

        NOTE: use raw_score, not ui_score, for anything that tracks change over
        time. The docs state ui_score is deliberately adjusted upward "to
        instill greater confidence" — it will flatter away real progress.

        HD and SD actions cannot be mixed in one task.
        """
        file_id = await self.upload("skin-analysis", image_path)
        result = await self.run_task(
            "skin-analysis",
            {
                "src_file_id": file_id,
                "dst_actions": actions or ["texture", "pore", "acne", "redness"],
                "format": "json",
            },
        )
        return result.get("results") or {}

    async def cloth_templates(self) -> list[dict[str, Any]]:
        """Predefined garments from the v2.0 catalogue.

        Free (no task is created), and it saves sourcing product photography
        for the demo. Returns template_id values usable with the v2.0 `cloth`
        endpoint.
        """
        payload = await self._get(f"/s2s/{self.version}/task/template/cloth")
        data = payload.get("data") or {}
        return data.get("results") or data.get("templates") or data

    async def try_on(
        self,
        person_image: Path,
        *,
        garment_url: str | None = None,
        garment_image: Path | None = None,
        template_id: str | None = None,
        category: str = "upper_body",
    ) -> str:
        """AI Clothes VTO (v3 engine). Returns a URL to the result image.

        Exactly one garment source: a public URL, a local image, or a
        template_id. Passing more than one returns invalid_parameter.

        Person photo requirements are stricter than the tone analyzer's:
        single person, standing, facing forward, shoulders visible, subject
        filling ~80% of the frame. 1024x768 recommended, 512x384 minimum.
        """
        sources = [bool(garment_url), bool(garment_image), bool(template_id)]
        if sum(sources) != 1:
            raise YouCamError(
                "Provide exactly one of garment_url, garment_image, template_id"
            )

        # template_id is documented but NOT accepted by either engine. Both
        # `cloth` (v2.0) and `cloth-v3` validate against a schema requiring one
        # of src_file_url / ref_file_url / ref_file_id, and reject a payload
        # carrying template_id with a misleading "missing src_file_url".
        # Use the template's thumbnail as ref_file_url instead — the docs
        # permit worn-garment photos as references.
        if template_id and not garment_url:
            raise YouCamError(
                "template_id is not accepted by the try-on API despite being "
                "documented. Use the template's thumb URL as garment_url "
                "instead — rebuild the catalogue with `python catalogue.py`."
            )

        feature = "cloth-v3"
        payload: dict[str, Any] = {
            "src_file_id": await self.upload(feature, person_image),
            "garment_category": category,
        }
        if garment_url:
            payload["ref_file_url"] = garment_url
        else:
            payload["ref_file_id"] = await self.upload(feature, garment_image)

        result = await self.run_task(feature, payload, timeout=420.0)
        url = (result.get("results") or {}).get("url")
        if not url:
            raise YouCamError(f"No result URL in response: {result}")
        return url


# --------------------------------------------------------------------------
# CLI smoke test
# --------------------------------------------------------------------------


async def _main() -> None:
    import argparse
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from colour import analyse, recommend

    parser = argparse.ArgumentParser(description="YouCam tone analysis")
    parser.add_argument("image", type=Path)
    parser.add_argument("--max-units", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async with YouCamClient(
        budget=UnitBudget(max_units=args.max_units), dry_run=args.dry_run
    ) as client:
        colors = await client.skin_tone(args.image)
        print(json.dumps(colors, indent=2))
        print(json.dumps(recommend(analyse(colors)), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(_main())
