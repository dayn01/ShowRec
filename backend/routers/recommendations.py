from fastapi import APIRouter, Query, Depends
from integrations import trakt, jellyfin, plex, tmdb
from recommender import get_recommendations, build_genre_profile
from config import settings
from deps import get_profile_id, pkey
import database
import asyncio

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


async def _gather_history(profile_id: int = 1) -> list[dict]:
    # Prefer the local watch_state DB — works without Trakt
    db_items = await database.get_watched_for_recommendations(profile_id)
    if db_items:
        return db_items

    # Fallback: live fetch from all sources (first run before sync completes)
    items: list[dict] = []

    try:
        shows = await trakt.get_watch_history("shows", limit=50)
        movies = await trakt.get_watch_history("movies", limit=50)
        for entry in shows:
            show = entry.get("show", {})
            ids = show.get("ids", {})
            items.append({"title": show.get("title"), "media_type": "tv",
                          "tmdb_id": ids.get("tmdb"), "genres": []})
        for entry in movies:
            movie = entry.get("movie", {})
            ids = movie.get("ids", {})
            items.append({"title": movie.get("title"), "media_type": "movie",
                          "tmdb_id": ids.get("tmdb"), "genres": []})
    except Exception:
        pass

    if settings.jellyfin_url:
        try:
            jf_items = await jellyfin.get_watch_history(limit=100)
            for item in jf_items:
                provider_ids = item.get("ProviderIds", {})
                tmdb_id = provider_ids.get("Tmdb") or provider_ids.get("tmdb")
                media_type = "movie" if item.get("Type") == "Movie" else "tv"
                items.append({"title": item.get("Name"), "media_type": media_type,
                              "tmdb_id": int(tmdb_id) if tmdb_id else None,
                              "genres": item.get("Genres", [])})
        except Exception:
            pass

    if settings.plex_url:
        try:
            from integrations import plex
            plex_items = plex.get_watch_history(limit=100)
            for item in plex_items:
                guids = item.get("guids", {})
                tmdb_id = guids.get("tmdb")
                media_type = "movie" if item.get("type") == "movie" else "tv"
                items.append({"title": item.get("title"), "media_type": media_type,
                              "tmdb_id": int(tmdb_id) if tmdb_id else None,
                              "genres": item.get("genres", [])})
        except Exception:
            pass

    return items


@router.get("")
async def get_recs(limit: int = Query(40, le=200), page: int = Query(1, ge=1),
                   pid: int = Depends(get_profile_id)):
    cached = await database.cache_get(pkey(pid, "recommendations"), "recommendations")
    if cached:
        recs = cached.get("recommendations", [])
        start = (page - 1) * limit
        return {
            "recommendations": recs[start:start + limit],
            "based_on": cached.get("based_on", 0),
            "top_genres": cached.get("top_genres", []),
            "trakt_blended": cached.get("trakt_blended", False),
            "total": len(recs),
            "from_cache": True,
        }

    # Cache miss — fetch live
    history = await _gather_history(pid)
    if not history:
        return {"recommendations": [], "based_on": 0, "total": 0}

    genre_profile = await build_genre_profile(history)
    watched_ids = [(h["tmdb_id"], h["media_type"]) for h in history if h.get("tmdb_id")]
    recs = await get_recommendations(watched_ids, genre_profile, limit=40)
    result = {"recommendations": recs, "based_on": len(watched_ids)}
    await database.cache_set(pkey(pid, "recommendations"), result)
    return {**result, "total": len(recs), "from_cache": False}


@router.get("/trending")
async def get_trending(
    media_type: str = Query("shows", pattern="^(shows|movies)$"),
    page: int = Query(1, ge=1),
):
    cache_key = f"trending_{media_type}"
    cached = await database.cache_get(cache_key, "trending")
    if cached:
        items = cached.get("trending", [])
        page_size = 20
        start = (page - 1) * page_size
        return {"trending": items[start:start + page_size], "page": page,
                "total": len(items), "from_cache": True}

    return {"trending": [], "page": page, "total": 0, "from_cache": False}
