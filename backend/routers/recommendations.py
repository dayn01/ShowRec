from fastapi import APIRouter, Query, Depends
from integrations import trakt, jellyfin, plex, tmdb
from recommender import get_recommendations, build_genre_profile
from constants import GENRE_MAP
from config import settings
from deps import get_profile_id, pkey
import database
import asyncio
import datetime

# Recency preference: how many years over which "new → old" is normalised, and
# the max score swing at the slider extremes.
_RECENCY_SPAN = 40
_RECENCY_STRENGTH = 0.6

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


async def _gather_history(profile_id: int = 1) -> list[dict]:
    """
    A profile's watch history — strictly from its own watch_state in SQLite.
    The watch_state is seeded per-profile from that profile's linked accounts by
    the sync job. We intentionally do NOT fall back to the global Jellyfin/Plex/
    Trakt accounts, which would leak the owner's data into other profiles.
    """
    items = await database.get_watched_for_recommendations(profile_id)
    return [i for i in items if i.get("tmdb_id")]  # drop any null ids


def _apply_rec_settings(recs: list[dict], settings: dict) -> list[dict]:
    """
    Re-rank a profile's cached recommendations using its tuning:
      - genre_weight: scales the learned genre-affinity component (default 1.0)
      - genre_multipliers: {genre name -> factor}; 0 hides the genre entirely
      - recency: soft era preference in [-1, 1]; >0 favours newer titles, <0 older.
        Nothing is removed — it just nudges the ranking.
    Defaults reproduce the stored ranking exactly (no-op).
    """
    genre_weight = settings.get("genre_weight", 1.0)
    multipliers = settings.get("genre_multipliers") or {}
    recency = settings.get("recency") or 0.0
    if genre_weight == 1.0 and not multipliers and not recency:
        return recs

    this_year = datetime.date.today().year
    out: list[dict] = []
    for item in recs:
        base = item.get("base_score", item.get("score", 0) or 0)
        score = base + genre_weight * item.get("genre_component", 0)

        # Soft recency nudge: r = +1 (brand new) … -1 (>= span years old).
        if recency:
            date = item.get("release_date") or item.get("first_air_date") or ""
            if date[:4].isdigit():
                age = min(max(this_year - int(date[:4]), 0), _RECENCY_SPAN)
                r = 1 - 2 * age / _RECENCY_SPAN
                score *= 1 + recency * _RECENCY_STRENGTH * r

        factor, excluded = 1.0, False
        for gid in item.get("genre_ids", []):
            name = GENRE_MAP.get(gid)
            if name in multipliers:
                v = multipliers[name]
                if v <= 0:
                    excluded = True
                    break
                factor *= v
        if excluded:
            continue
        out.append({**item, "score": round(score * factor, 2)})

    out.sort(key=lambda x: x.get("score", 0), reverse=True)
    return out


@router.get("")
async def get_recs(limit: int = Query(40, le=200), page: int = Query(1, ge=1),
                   pid: int = Depends(get_profile_id)):
    rec_settings = await database.get_rec_settings(pid)
    cached = await database.cache_get(pkey(pid, "recommendations"), "recommendations")
    if cached:
        recs = _apply_rec_settings(cached.get("recommendations", []), rec_settings)
        start = (page - 1) * limit
        return {
            "recommendations": recs[start:start + limit],
            "based_on": cached.get("based_on", 0),
            "top_genres": cached.get("top_genres", []),
            "trakt_blended": cached.get("trakt_blended", False),
            "tastedive_blended": cached.get("tastedive_blended", False),
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
    recs = _apply_rec_settings(recs, rec_settings)
    return {"recommendations": recs[: limit], "based_on": len(watched_ids),
            "total": len(recs), "from_cache": False}


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
