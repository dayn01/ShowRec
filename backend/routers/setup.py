"""
First-run setup wizard endpoints.

The app can be configured from the UI on first run: the wizard tests keys,
writes them to .env, applies them to the live settings (no restart), and kicks
off the initial sync. Once a TMDB key exists the app counts as configured, so
every mutating endpoint here returns 403 and the wizard disappears — re-running
setup means SSHing in to clear .env (or the TMDB key) and restarting. This keeps
secret-writing off the unauthenticated LAN surface after the one-time setup.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio

import env_store
import database
from config import settings
from integrations import tmdb, jellyfin

router = APIRouter(prefix="/setup", tags=["setup"])


def _configured() -> bool:
    """
    Already configured == a TMDB key is present. This is the lock: once a key
    exists (from the wizard, a hand-edited .env, or an upgrade), the wizard is
    hidden and its mutating endpoints are closed. No flag is written to .env, so
    this works even where .env is mounted read-only (Docker). To re-run setup,
    clear .env (or remove the TMDB key) over SSH and restart.
    """
    return bool(settings.tmdb_api_key)


def _guard():
    if _configured():
        raise HTTPException(
            status_code=403,
            detail="Setup already completed. To re-run, SSH in and clear .env "
                   "(or remove the TMDB key), then restart the service.",
        )


@router.get("/status")
async def status():
    """Booleans only — never returns the stored secret values."""
    has = {
        "tmdb": bool(settings.tmdb_api_key),
        "jellyfin": bool(settings.jellyfin_url and settings.jellyfin_api_key),
        "jellyfin_user": bool(settings.jellyfin_user_id),
        "trakt": bool(settings.trakt_access_token),
        "plex": bool(settings.plex_url and settings.plex_token),
        "overseerr": bool(settings.overseerr_url and settings.overseerr_api_key),
        "anthropic": bool(settings.anthropic_api_key),
        "home_assistant": bool(settings.ha_url and settings.ha_token),
        "reddit": bool(settings.reddit_client_id and settings.reddit_client_secret),
        "tastedive": bool(settings.tastedive_api_key),
    }
    return {"configured": _configured(), "has": has}


class TmdbTest(BaseModel):
    api_key: str


@router.post("/test/tmdb")
async def test_tmdb(body: TmdbTest):
    _guard()
    return {"ok": await tmdb.validate_key(body.api_key)}


class JellyfinTest(BaseModel):
    url: str
    api_key: str


@router.post("/test/jellyfin")
async def test_jellyfin(body: JellyfinTest):
    _guard()
    users = await jellyfin.list_users(body.url, body.api_key)
    return {"ok": users is not None, "users": users or []}


class SetupIn(BaseModel):
    # env key -> value (e.g. {"TMDB_API_KEY": "...", "JELLYFIN_URL": "..."})
    values: dict[str, str]
    profile_name: str = "Me"
    profile_emoji: str = "🍿"


@router.post("")
async def save(body: SetupIn):
    _guard()

    # Only persist keys the wizard is allowed to write.
    clean = {k: (v or "").strip() for k, v in body.values.items()
             if k in env_store.ALLOWED_KEYS}

    if not clean.get("TMDB_API_KEY"):
        raise HTTPException(400, "A TMDB API key is required.")

    new_jf_user = clean.get("JELLYFIN_USER_ID", "")

    # Persist to .env and apply to the live settings object. Writing the TMDB
    # key is itself the lock — once present, _configured() is true.
    env_store.update(clean)
    env_store.apply_to_settings(clean)

    # NB: we deliberately do NOT wipe data when the Jellyfin link changes. The
    # ShowRec profile is the source of truth; Jellyfin/Plex/Trakt are just
    # additive, replaceable watch-history sources. The next sync swaps only the
    # 'jellyfin'-sourced rows (replace_watched_source), leaving manual marks,
    # Netflix imports, Trakt/Plex history, watchlist and likes untouched.

    # Guarantee the default profile exists, is named, and is linked to the chosen
    # Jellyfin account — so finishing setup always leaves a usable profile (the
    # auto-seed can leave it empty if .env was blank at DB-creation time).
    name = (body.profile_name or "Me").strip() or "Me"
    emoji = (body.profile_emoji or "🍿").strip() or "🍿"
    await database.upsert_default_profile(name, emoji, new_jf_user or None)

    # Build everything in the background with the new config.
    import prefetch
    asyncio.create_task(prefetch.refresh_all())

    return {"ok": True, "wiped": False}
