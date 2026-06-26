"""
Watch state — SQLite is the source of truth.
Every mark/unmark writes to the local DB and works without Trakt.
If a Trakt token is configured, changes are also synced to Trakt (best-effort).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import datetime, timezone, date
import httpx
import logging
from config import settings
from deps import get_profile_id
import database

router = APIRouter(prefix="/watched", tags=["watched"])
logger = logging.getLogger(__name__)


def _trakt_enabled() -> bool:
    return bool(settings.trakt_access_token)


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": settings.trakt_client_id,
        "Authorization": f"Bearer {settings.trakt_access_token}",
    }


async def _trakt_sync(path: str, payload: dict):
    """Best-effort Trakt sync — never raises, just logs."""
    if not _trakt_enabled():
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"https://api.trakt.tv/sync/{path}", json=payload, headers=_headers())
            if r.status_code not in (200, 201):
                logger.warning(f"Trakt sync {path} returned {r.status_code}")
    except Exception as e:
        logger.warning(f"Trakt sync {path} failed: {e}")


# ── Models ────────────────────────────────────────────────────────────────────

class WatchedItem(BaseModel):
    tmdb_id: int
    media_type: str  # "movie" or "tv"
    title: str
    year: int | None = None
    watched_at: str | None = None


class WatchedSeason(BaseModel):
    tmdb_id: int
    title: str
    season_number: int
    episode_numbers: list[int] | None = None  # episodes to mark, if known
    watched_at: str | None = None


class WatchedEpisode(BaseModel):
    tmdb_id: int
    title: str
    season_number: int
    episode_number: int
    episode_tmdb_id: int | None = None
    watched_at: str | None = None


# ── Movie / show ──────────────────────────────────────────────────────────────

@router.post("")
async def mark_watched(item: WatchedItem, pid: int = Depends(get_profile_id)):
    watched_at = item.watched_at or datetime.now(timezone.utc).isoformat()

    # Movie — simple single row
    if item.media_type == "movie":
        await database.mark_watched(pid, "movie", item.tmdb_id, title=item.title, source="user")
        await _trakt_sync("history", {
            "movies": [{"title": item.title, "year": item.year,
                        "watched_at": watched_at, "ids": {"tmdb": item.tmdb_id}}]
        })
        return {"status": "marked as watched", "store": "sqlite"}

    # TV show — mark the show AND every aired episode of every season
    await database.mark_watched(pid, "show", item.tmdb_id, title=item.title, source="user")

    today = date.today().isoformat()
    marked_seasons = []
    try:
        from routers.details import _fetch_and_cache_show, _fetch_and_cache_season
        show = await database.get_show(item.tmdb_id) or await _fetch_and_cache_show(item.tmdb_id, "tv")
        for s in show.get("seasons", []):
            sn = s.get("season_number")
            if sn is None or sn < 1:
                continue
            season_data = await database.get_season(item.tmdb_id, sn) or await _fetch_and_cache_season(item.tmdb_id, sn)
            total = len(season_data.get("episodes", []))
            aired = [
                ep["episode_number"] for ep in season_data.get("episodes", [])
                if not ep.get("air_date") or ep["air_date"] <= today
            ]
            if aired:
                await database.mark_episodes_bulk(pid, item.tmdb_id, sn, aired, title=item.title, source="user")
            marked_seasons.append({"season_number": sn, "total": total, "watched": aired})
    except Exception as e:
        logger.warning(f"mark show {item.tmdb_id}: episode marking failed: {e}")

    # Trakt — mark the whole show
    await _trakt_sync("history", {
        "shows": [{"title": item.title, "year": item.year,
                   "watched_at": watched_at, "ids": {"tmdb": item.tmdb_id}}]
    })
    return {"status": "marked as watched", "store": "sqlite", "seasons": marked_seasons}


@router.delete("")
async def mark_unwatched(item: WatchedItem, pid: int = Depends(get_profile_id)):
    mt = "movie" if item.media_type == "movie" else "show"
    if mt == "movie":
        await database.unmark_watched(pid, "movie", item.tmdb_id)
        await _trakt_sync("history/remove", {"movies": [{"ids": {"tmdb": item.tmdb_id}}]})
    else:
        await database.unmark_show(pid, item.tmdb_id)
        await _trakt_sync("history/remove", {"shows": [{"ids": {"tmdb": item.tmdb_id}}]})
    return {"status": "removed", "store": "sqlite"}


# ── Season ────────────────────────────────────────────────────────────────────

@router.post("/season")
async def mark_season_watched(item: WatchedSeason, pid: int = Depends(get_profile_id)):
    if item.episode_numbers:
        await database.mark_episodes_bulk(
            pid, item.tmdb_id, item.season_number, item.episode_numbers,
            title=item.title, source="user"
        )
    else:
        await database.mark_watched(pid, "episode", item.tmdb_id, item.season_number, 0,
                                    title=item.title, source="user")

    watched_at = item.watched_at or datetime.now(timezone.utc).isoformat()
    await _trakt_sync("history", {
        "shows": [{"ids": {"tmdb": item.tmdb_id}, "title": item.title,
                   "seasons": [{"number": item.season_number, "watched_at": watched_at}]}]
    })
    return {"status": "season marked", "store": "sqlite"}


@router.delete("/season")
async def mark_season_unwatched(item: WatchedSeason, pid: int = Depends(get_profile_id)):
    await database.unmark_season(pid, item.tmdb_id, item.season_number)
    await _trakt_sync("history/remove", {
        "shows": [{"ids": {"tmdb": item.tmdb_id},
                   "seasons": [{"number": item.season_number}]}]
    })
    return {"status": "season removed", "store": "sqlite"}


# ── Episode ───────────────────────────────────────────────────────────────────

@router.post("/episode")
async def mark_episode_watched(item: WatchedEpisode, pid: int = Depends(get_profile_id)):
    await database.mark_watched(pid, "episode", item.tmdb_id, item.season_number,
                                item.episode_number, title=item.title, source="user")
    watched_at = item.watched_at or datetime.now(timezone.utc).isoformat()
    await _trakt_sync("history", {
        "shows": [{"ids": {"tmdb": item.tmdb_id}, "title": item.title,
                   "seasons": [{"number": item.season_number,
                                "episodes": [{"number": item.episode_number, "watched_at": watched_at}]}]}]
    })
    return {"status": "episode marked", "store": "sqlite"}


@router.delete("/episode")
async def mark_episode_unwatched(item: WatchedEpisode, pid: int = Depends(get_profile_id)):
    await database.unmark_watched(pid, "episode", item.tmdb_id, item.season_number, item.episode_number)
    await _trakt_sync("history/remove", {
        "shows": [{"ids": {"tmdb": item.tmdb_id},
                   "seasons": [{"number": item.season_number,
                                "episodes": [{"number": item.episode_number}]}]}]
    })
    return {"status": "episode removed", "store": "sqlite"}


# ── History (read from SQLite) ────────────────────────────────────────────────

@router.get("/history")
async def get_watched_history(pid: int = Depends(get_profile_id)):
    state = await database.get_watch_state(pid)
    # If this profile has nothing yet, kick off a background sync of its linked account
    if not state.get("tmdb_ids") and not state.get("episodes"):
        import asyncio, prefetch
        asyncio.create_task(prefetch.refresh_profile(pid))
    return state


@router.post("/sync")
async def sync_now(pid: int = Depends(get_profile_id)):
    """Pull this profile's watched state from its linked Jellyfin/Plex/Trakt right
    now (no recommendation rebuild) and return the fresh state. Used by the UI to
    stay current without waiting for the scheduled sync."""
    import prefetch
    profile = await database.get_profile(pid)
    if profile:
        try:
            await prefetch.sync_watch_state(profile)
        except Exception:
            pass
    return await database.get_watch_state(pid)


@router.get("/available")
async def get_available_episodes(pid: int = Depends(get_profile_id)):
    """Latest library-available episode per in-progress show, for the Watching sort:
    {tmdb_id: [season, episode]}. Cached 15m. Returns {} when Jellyfin isn't usable
    so the UI just falls back to its recency sort."""
    cache_key = f"avail:{pid}"
    cached = await database.cache_get(cache_key, "availability")
    if cached is not None:
        return {"items": cached}
    from integrations import jellyfin
    profile = await database.get_profile(pid)
    jf_user = profile.get("jellyfin_user_id") if profile else None
    try:
        items = await jellyfin.get_episode_availability(jf_user)
    except Exception:
        items = {}
    await database.cache_set(cache_key, items)
    return {"items": items}


@router.get("/sources")
async def get_watch_sources(pid: int = Depends(get_profile_id)):
    return await database.get_watch_state_stats(pid)


@router.get("/library")
async def get_watched_library(pid: int = Depends(get_profile_id)):
    """
    Fully-watched movies + shows for the Watched page. Served entirely from the
    show cache in one bulk query — with hundreds of watched titles, fetching the
    uncached ones from TMDB on the request path would stall the page (and did).
    Missing posters fill in on the next load once the background warmer caches
    them; titles always show (from watch_state).
    """
    rows = await database.get_watched_library(pid)

    # Also include shows fully watched via episodes (no explicit show-level mark)
    state = await database.get_watch_state(pid)
    existing = {(r["media_type"], r["tmdb_id"]) for r in rows}
    for tid in state.get("complete_tmdb_ids", []):
        if ("tv", tid) not in existing:
            rows.append({"tmdb_id": tid, "media_type": "tv", "title": ""})

    cache = await database.get_shows_bulk([r["tmdb_id"] for r in rows])
    items = []
    for row in rows:
        tmdb_id, mt = row["tmdb_id"], row["media_type"]
        cached = cache.get(tmdb_id)
        items.append({
            "id": tmdb_id,
            "media_type": mt,
            "title": (cached and (cached.get("title") or cached.get("name"))) or row["title"] or "Unknown",
            "poster_url": cached.get("poster_url") if cached else None,
            "vote_average": cached.get("vote_average", 0) if cached else 0,
            "overview": cached.get("overview", "") if cached else "",
            "release_date": cached.get("release_date") if cached else None,
            "first_air_date": cached.get("first_air_date") if cached else None,
        })
    return {"items": items}


# ── "Not interested" dismissals ───────────────────────────────────────────────

class DismissItem(BaseModel):
    tmdb_id: int
    media_type: str  # "tv" or "movie"
    title: str = ""


@router.post("/dismiss")
async def dismiss(item: DismissItem, pid: int = Depends(get_profile_id)):
    await database.add_dismissed(pid, item.tmdb_id, item.media_type, item.title)
    await database.remove_liked(pid, item.tmdb_id)   # 👎 and 👍 are mutually exclusive
    return {"status": "dismissed"}


@router.delete("/dismiss")
async def undismiss(item: DismissItem, pid: int = Depends(get_profile_id)):
    await database.remove_dismissed(pid, item.tmdb_id)
    return {"status": "restored"}


@router.post("/like")
async def like(item: DismissItem, pid: int = Depends(get_profile_id)):
    await database.add_liked(pid, item.tmdb_id, item.media_type, item.title)
    await database.remove_dismissed(pid, item.tmdb_id)   # 👍 clears a 👎
    return {"status": "liked"}


@router.delete("/like")
async def unlike(item: DismissItem, pid: int = Depends(get_profile_id)):
    await database.remove_liked(pid, item.tmdb_id)
    return {"status": "unliked"}


@router.get("/liked")
async def list_liked(pid: int = Depends(get_profile_id)):
    return {"tmdb_ids": await database.get_liked_ids(pid)}


@router.get("/dismissed")
async def list_dismissed(pid: int = Depends(get_profile_id)):
    return {"tmdb_ids": await database.get_dismissed_ids(pid)}


@router.get("/dismissed/list")
async def list_dismissed_full(pid: int = Depends(get_profile_id)):
    return {"items": await database.get_dismissed_full(pid)}
