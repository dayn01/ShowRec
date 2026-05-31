from fastapi import APIRouter
from integrations import jellyfin, plex, homeassistant
from config import settings

router = APIRouter(prefix="/status", tags=["status"])


@router.get("")
async def get_status():
    jf_ok = await jellyfin.ping() if settings.jellyfin_url else None
    ha_ok = await homeassistant.ping() if settings.ha_url else None
    plex_ok = plex.ping() if settings.plex_url else None

    trakt_configured = bool(settings.trakt_client_id and settings.trakt_access_token)
    tmdb_configured = bool(settings.tmdb_api_key)

    return {
        "jellyfin": jf_ok,
        "plex": plex_ok,
        "home_assistant": ha_ok,
        "trakt": trakt_configured,
        "tmdb": tmdb_configured,
    }
