"""Profile management."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from deps import pkey
import database

router = APIRouter(prefix="/profiles", tags=["profiles"])


class ProfileIn(BaseModel):
    name: str
    emoji: str = "👤"
    jellyfin_user_id: str | None = None
    plex_user: str | None = None       # Plex Home user id/title to link ('owner' = main account)
    plex_token: str | None = None      # resolved server-side from plex_user
    trakt_token: str | None = None


async def _resolve_plex_token(plex_user: str | None) -> str | None:
    if not plex_user:
        return None
    import asyncio, concurrent.futures
    from integrations import plex
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, plex.get_user_token, plex_user)


class ProfileUpdate(BaseModel):
    name: str | None = None
    emoji: str | None = None
    jellyfin_user_id: str | None = None   # "" to unlink
    plex_user: str | None = None          # Plex Home user id/title to (re)link; "" to unlink
    trakt_token: str | None = None


@router.get("")
async def list_profiles():
    return {"profiles": await database.list_profiles()}


@router.post("")
async def create_profile(p: ProfileIn):
    plex_token = p.plex_token or await _resolve_plex_token(p.plex_user)
    profile = await database.create_profile(
        p.name, p.emoji, p.jellyfin_user_id, plex_token, p.trakt_token
    )
    # Kick off a background build for the new profile
    import prefetch, asyncio
    asyncio.create_task(prefetch.refresh_profile(profile["id"]))
    return profile


@router.patch("/{profile_id}")
async def update_profile(profile_id: int, p: ProfileUpdate):
    existing = await database.get_profile(profile_id)
    if not existing:
        raise HTTPException(404, "Profile not found")

    data = p.model_dump(exclude_unset=True)
    fields = {}
    if "name" in data and data["name"]:
        fields["name"] = data["name"]
    if "emoji" in data and data["emoji"]:
        fields["emoji"] = data["emoji"]
    if "jellyfin_user_id" in data:
        fields["jellyfin_user_id"] = data["jellyfin_user_id"] or None
    if "trakt_token" in data:
        fields["trakt_token"] = data["trakt_token"] or None
    if "plex_user" in data:
        # "" means unlink; otherwise resolve to a token
        fields["plex_token"] = (await _resolve_plex_token(data["plex_user"])) if data["plex_user"] else None

    await database.update_profile(profile_id, **fields)

    # If account links changed, rebuild this profile's data in the background
    links_changed = any(k in fields for k in ("jellyfin_user_id", "plex_token", "trakt_token"))
    if links_changed:
        import prefetch, asyncio
        asyncio.create_task(prefetch.refresh_profile(profile_id))

    return await database.get_profile(profile_id)


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int):
    ids = await database.all_profile_ids()
    if len(ids) <= 1:
        raise HTTPException(400, "Cannot delete the last profile")
    await database.delete_profile(profile_id)
    return {"status": "deleted"}


@router.post("/{profile_id}/refresh")
async def refresh_profile(profile_id: int, force: bool = True, max_age_minutes: int = 60):
    """
    Rebuild this profile's watch state + recommendations in the background.
    force=False skips the rebuild if the profile's data is younger than
    max_age_minutes (used for cheap auto-refresh on profile switch).
    """
    import prefetch, asyncio
    if not force:
        age = await database.cache_age(pkey(profile_id, "recommendations"))
        if age is not None and age < max_age_minutes * 60:
            return {"status": "fresh", "age_seconds": age}
    asyncio.create_task(prefetch.refresh_profile(profile_id))
    return {"status": "refresh started"}
