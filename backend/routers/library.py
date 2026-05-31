"""TMDB search + watchlist."""
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from integrations import tmdb
from deps import get_profile_id
from config import settings
import database
import asyncio
import concurrent.futures

router = APIRouter(tags=["library"])


# ── Search ────────────────────────────────────────────────────────────────────

@router.get("/search")
async def search(q: str = Query(..., min_length=1), type: str = Query("multi", pattern="^(multi|tv|movie)$")):
    """Search TMDB for titles. Returns MediaCard-shaped results."""
    try:
        raw = await tmdb.search(q, type)
    except Exception as e:
        raise HTTPException(502, f"TMDB search failed: {e}")

    results = []
    for item in raw:
        mt = item.get("media_type") or ("tv" if type == "tv" else "movie")
        if mt not in ("tv", "movie"):
            continue  # skip people etc.
        results.append({
            "id": item.get("id"),
            "title": item.get("title") or item.get("name"),
            "name": item.get("name"),
            "overview": item.get("overview", ""),
            "poster_url": tmdb.poster_url(item.get("poster_path")),
            "vote_average": item.get("vote_average", 0),
            "media_type": mt,
            "genre_ids": item.get("genre_ids", []),
            "release_date": item.get("release_date"),
            "first_air_date": item.get("first_air_date"),
            "popularity": item.get("popularity", 0),
        })
    # Most relevant/popular first
    results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return {"results": results}


# ── Watchlist ─────────────────────────────────────────────────────────────────

class WatchlistItem(BaseModel):
    tmdb_id: int
    media_type: str
    title: str = ""
    poster_url: str | None = None
    vote_average: float = 0
    overview: str = ""
    release_date: str | None = None
    first_air_date: str | None = None


@router.post("/watchlist")
async def add_to_watchlist(item: WatchlistItem, pid: int = Depends(get_profile_id)):
    await database.add_watchlist(pid, item.model_dump())
    return {"status": "added"}


@router.delete("/watchlist")
async def remove_from_watchlist(item: WatchlistItem, pid: int = Depends(get_profile_id)):
    await database.remove_watchlist(pid, item.tmdb_id)
    return {"status": "removed"}


@router.get("/watchlist")
async def get_watchlist(pid: int = Depends(get_profile_id)):
    return {"items": await database.get_watchlist(pid)}


@router.get("/watchlist/ids")
async def get_watchlist_ids(pid: int = Depends(get_profile_id)):
    return {"tmdb_ids": await database.get_watchlist_ids(pid)}


# ── Plex users (for linking to profiles) ──────────────────────────────────────

@router.get("/plex-users")
async def get_plex_users():
    """List Plex account owner + Home users so they can be linked to profiles."""
    if not settings.plex_url or not settings.plex_token:
        return {"users": []}
    from integrations import plex
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        users = await loop.run_in_executor(pool, plex.list_home_users)
    return {"users": users}
