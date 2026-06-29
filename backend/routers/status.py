from fastapi import APIRouter
from integrations import jellyfin, plex, homeassistant, overseerr
from config import settings

router = APIRouter(prefix="/status", tags=["status"])


@router.get("")
async def get_status():
    jf_ok = await jellyfin.ping_user() if settings.jellyfin_url else None
    ha_ok = await homeassistant.ping() if settings.ha_url else None
    plex_ok = plex.ping() if settings.plex_url else None
    overseerr_ok = await overseerr.ping() if overseerr.is_configured() else None

    trakt_configured = bool(settings.trakt_client_id and settings.trakt_access_token)
    tmdb_configured = bool(settings.tmdb_api_key)
    ai_enabled = bool(settings.anthropic_api_key) and settings.anthropic_api_key != "your_anthropic_api_key_here"

    return {
        "jellyfin": jf_ok,
        "plex": plex_ok,
        "home_assistant": ha_ok,
        "trakt": trakt_configured,
        "tmdb": tmdb_configured,
        "ai_enabled": ai_enabled,
        "tastedive": bool(settings.tastedive_api_key),
        "overseerr": overseerr_ok,
    }
