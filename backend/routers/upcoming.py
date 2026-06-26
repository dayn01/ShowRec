from fastapi import APIRouter, Query, Depends
from integrations import trakt, homeassistant
from scheduler import check_upcoming_episodes, check_new_seasons
from deps import get_profile_id, pkey
from datetime import date, timedelta
import database

router = APIRouter(prefix="/upcoming", tags=["upcoming"])


def _window(cached: dict, days: int) -> list:
    today = date.today().isoformat()
    cutoff = (date.today() + timedelta(days=days)).isoformat()
    return [
        e for e in cached.get("episodes", [])
        if today <= e.get("first_aired", "")[:10] <= cutoff
    ]


@router.get("")
async def get_upcoming(days: int = Query(30, le=90), pid: int = Depends(get_profile_id)):
    cached = await database.cache_get(pkey(pid, "upcoming"), "upcoming")
    if cached:
        return {"episodes": _window(cached, days), "days": days, "from_cache": True}

    # No cache yet — build it on demand from THIS profile's watch state (not global Trakt)
    import prefetch
    history = await database.get_watched_for_recommendations(pid)
    if not history:
        # Profile has no synced data yet — kick off a background sync so it's ready next time
        import asyncio
        asyncio.create_task(prefetch.refresh_profile(pid))
        return {"episodes": [], "days": days, "from_cache": False, "building": True}

    built = await prefetch._build_upcoming(history, pid)
    if built:
        await database.cache_set(pkey(pid, "upcoming"), built)
        return {"episodes": _window(built, days), "days": days, "from_cache": False}
    return {"episodes": [], "days": days, "from_cache": False}


@router.get("/jellyfin-users")
async def get_jellyfin_users():
    """Helper to find your Jellyfin user ID — needed in .env."""
    from integrations.jellyfin import _base, _headers
    import httpx
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{_base()}/Users", headers=_headers())
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code}", "detail": r.text}
        return {"users": [{"id": u["Id"], "name": u["Name"]} for u in r.json()]}


@router.get("/debug")
async def debug_upcoming():
    """Shows what's in the upcoming cache and checks a few shows directly from TMDB."""
    from routers.recommendations import _gather_history
    from integrations import tmdb as tmdb_client

    cached = await database.cache_get("upcoming", "upcoming")
    from integrations import trakt as trakt_client
    history = await _gather_history()
    tv_ids = {h["tmdb_id"] for h in history if h.get("tmdb_id") and h.get("media_type") == "tv"}
    try:
        all_watched = await trakt_client.get_all_watched_shows()
        for entry in all_watched:
            tid = entry.get("show", {}).get("ids", {}).get("tmdb")
            if tid:
                tv_ids.add(tid)
    except Exception:
        pass
    tv_ids = list(tv_ids)

    # Check first 10 TV shows from history for next_episode_to_air
    sample = []
    for tid in tv_ids[:10]:
        try:
            data = await tmdb_client.get_upcoming_episodes_for_show(tid)
            sample.append({
                "tmdb_id": tid,
                "title": data.get("show_title"),
                "next_episode": data.get("next_episode"),
                "status": data.get("status"),
            })
        except Exception as e:
            sample.append({"tmdb_id": tid, "error": str(e)})

    return {
        "cached_episode_count": len(cached.get("episodes", [])) if cached else 0,
        "cached_episodes_sample": (cached.get("episodes", [])[:5]) if cached else [],
        "history_tv_count": len(tv_ids),
        "history_sample_tmdb_ids": tv_ids[:10],
        "tmdb_sample": sample,
    }


@router.post("/notify-now")
async def trigger_notification():
    """Manually trigger the Home Assistant episode notification (only sends if episodes air today)."""
    await check_upcoming_episodes()
    return {"status": "checked — sent only if episodes air today"}


@router.post("/test-notify")
async def test_notify():
    """Send a test HA notification immediately (bypasses the airing-today check)."""
    return await homeassistant.send_test()


@router.post("/check-new-seasons")
async def trigger_new_season_check():
    """Run the 'new season for a show you watch' check now (also runs daily at 09:00).
    First call records a baseline; later calls notify on newly-announced seasons."""
    await check_new_seasons()
    return {"status": "checked — notifies on newly-detected seasons"}
