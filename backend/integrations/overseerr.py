"""Overseerr API client — request media and read availability status.

Optional integration: every public function assumes the caller has already
checked `is_configured()` (or the router has), mirroring how jellyfin/plex are
gated in routers/status.py. When Overseerr isn't configured the feature simply
never surfaces in the UI.
"""
import httpx
from config import settings

# Overseerr media availability codes (mediaInfo.status).
_STATUS = {
    1: "unknown",
    2: "pending",       # requested, awaiting approval
    3: "processing",    # approved, downloading
    4: "partial",       # some seasons available
    5: "available",     # on disk / playable
}


def is_configured() -> bool:
    return bool(settings.overseerr_url and settings.overseerr_api_key)


def _base() -> str:
    return settings.overseerr_url.rstrip("/")


def _headers() -> dict:
    return {
        "X-Api-Key": settings.overseerr_api_key,
        "Content-Type": "application/json",
    }


async def ping() -> bool:
    """True when Overseerr is reachable and the API key is accepted."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_base()}/api/v1/status", headers=_headers())
            return r.status_code == 200
    except Exception:
        return False


async def get_status(tmdb_id: int, media_type: str) -> dict:
    """
    Return {"status": <str>, "requested": <bool>} for a title, so the UI can
    show whether it's already on the server / requested. Falls back to
    "unknown" on any error so the request button still works.
    """
    kind = "movie" if media_type == "movie" else "tv"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{_base()}/api/v1/{kind}/{tmdb_id}", headers=_headers())
            if r.status_code != 200:
                return {"status": "unknown", "requested": False}
            info = (r.json() or {}).get("mediaInfo") or {}
            code = info.get("status")
            return {
                "status": _STATUS.get(code, "unknown"),
                "requested": code in (2, 3, 4, 5),
            }
    except Exception:
        return {"status": "unknown", "requested": False}


async def request_media(tmdb_id: int, media_type: str) -> dict:
    """
    File a request with Overseerr. For TV, request all seasons.
    Returns {"ok": bool, "status": <str>, "detail": <str|None>}.
    """
    kind = "movie" if media_type == "movie" else "tv"
    body: dict = {"mediaType": kind, "mediaId": tmdb_id}
    if kind == "tv":
        body["seasons"] = "all"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{_base()}/api/v1/request", headers=_headers(), json=body)
            if r.status_code in (200, 201):
                return {"ok": True, "status": "requested", "detail": None}
            # 409 = already requested/available — treat as success-ish for the UI.
            if r.status_code == 409:
                return {"ok": True, "status": "already_requested", "detail": None}
            return {"ok": False, "status": "error", "detail": f"{r.status_code} {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "status": "error", "detail": str(e)}
