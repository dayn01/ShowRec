"""Request media via Overseerr. Entirely optional — every endpoint 503s with a
clear message when Overseerr isn't configured, so the rest of the app is
unaffected when the feature is off."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from integrations import overseerr

router = APIRouter(prefix="/request", tags=["request"])


class RequestBody(BaseModel):
    tmdb_id: int
    media_type: str  # "movie" | "tv"


def _require_configured():
    if not overseerr.is_configured():
        raise HTTPException(status_code=503, detail="Overseerr is not configured")


@router.post("")
async def create_request(body: RequestBody):
    _require_configured()
    result = await overseerr.request_media(body.tmdb_id, body.media_type)
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["detail"] or "Overseerr request failed")
    return result


@router.get("/status/{media_type}/{tmdb_id}")
async def request_status(media_type: str, tmdb_id: int):
    if not overseerr.is_configured():
        # Not an error — the UI just hides the button. Keep the shape stable.
        return {"enabled": False, "status": "unknown", "requested": False}
    info = await overseerr.get_status(tmdb_id, media_type)
    return {"enabled": True, **info}
