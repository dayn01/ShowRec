from fastapi import APIRouter, HTTPException
from integrations import tmdb
import database

router = APIRouter(prefix="/details", tags=["details"])


async def _fetch_and_cache_show(tmdb_id: int, media_type: str) -> dict:
    data = await tmdb.get_details(tmdb_id, media_type)
    result = _shape_show(data, media_type)
    await database.set_show(tmdb_id, media_type, result)
    return result


def _shape_show(data: dict, media_type: str) -> dict:
    result = {
        "id": data.get("id"),
        "title": data.get("title") or data.get("name"),
        "tagline": data.get("tagline"),
        "overview": data.get("overview"),
        "poster_url": tmdb.poster_url(data.get("poster_path")),
        "backdrop_url": f"https://image.tmdb.org/t/p/w1280{data['backdrop_path']}" if data.get("backdrop_path") else None,
        "vote_average": data.get("vote_average"),
        "vote_count": data.get("vote_count"),
        "genres": [g["name"] for g in data.get("genres", [])],
        "genre_ids": [g["id"] for g in data.get("genres", [])],
        # Taste signals used by the recommender
        "cast_ids": [c["id"] for c in data.get("credits", {}).get("cast", [])[:8] if c.get("id")],
        "keyword_ids": [
            k["id"] for k in (data.get("keywords", {}).get("keywords")
                              or data.get("keywords", {}).get("results") or [])
        ],
        "media_type": media_type,
        "status": data.get("status"),
        "homepage": data.get("homepage"),
    }
    if media_type == "movie":
        result.update({
            "release_date": data.get("release_date"),
            "runtime": data.get("runtime"),
            "budget": data.get("budget"),
            "revenue": data.get("revenue"),
            "cast": [
                {"name": c["name"], "character": c["character"], "profile_url": tmdb.poster_url(c.get("profile_path"))}
                for c in data.get("credits", {}).get("cast", [])[:10]
            ],
        })
    else:
        result.update({
            "first_air_date": data.get("first_air_date"),
            "last_air_date": data.get("last_air_date"),
            "next_episode_to_air": data.get("next_episode_to_air"),
            "number_of_seasons": data.get("number_of_seasons"),
            "number_of_episodes": data.get("number_of_episodes"),
            "episode_run_time": data.get("episode_run_time", []),
            "networks": [n["name"] for n in data.get("networks", [])],
            "seasons": [
                {
                    "season_number": s["season_number"],
                    "name": s["name"],
                    "episode_count": s["episode_count"],
                    "air_date": s.get("air_date"),
                    "poster_url": tmdb.poster_url(s.get("poster_path")),
                    "overview": s.get("overview"),
                }
                for s in data.get("seasons", [])
                if s["season_number"] > 0
            ],
            "cast": [
                {"name": c["name"], "character": c["character"], "profile_url": tmdb.poster_url(c.get("profile_path"))}
                for c in data.get("credits", {}).get("cast", [])[:10]
            ],
        })
    return result


async def _fetch_and_cache_season(tmdb_id: int, season_number: int) -> dict:
    data = await tmdb.get_tv_season(tmdb_id, season_number)
    result = _shape_season(data)
    await database.set_season(tmdb_id, season_number, result)
    return result


def _shape_season(data: dict) -> dict:
    return {
        "season_number": data.get("season_number"),
        "name": data.get("name"),
        "overview": data.get("overview"),
        "episodes": [
            {
                "id": ep.get("id"),
                "episode_number": ep.get("episode_number"),
                "name": ep.get("name"),
                "overview": ep.get("overview"),
                "air_date": ep.get("air_date"),
                "runtime": ep.get("runtime"),
                "still_url": f"https://image.tmdb.org/t/p/w300{ep['still_path']}" if ep.get("still_path") else None,
                "vote_average": ep.get("vote_average"),
            }
            for ep in data.get("episodes", [])
        ],
    }


@router.get("/{media_type}/{tmdb_id}")
async def get_details(media_type: str, tmdb_id: int):
    if media_type not in ("tv", "movie"):
        raise HTTPException(400, "media_type must be 'tv' or 'movie'")
    cached = await database.get_show(tmdb_id)
    if cached:
        return cached
    try:
        return await _fetch_and_cache_show(tmdb_id, media_type)
    except Exception as e:
        raise HTTPException(502, f"TMDB error: {e}")


@router.get("/tv/{tmdb_id}/season/{season_number}")
async def get_season_episodes(tmdb_id: int, season_number: int):
    cached = await database.get_season(tmdb_id, season_number)
    if cached:
        return cached
    try:
        return await _fetch_and_cache_season(tmdb_id, season_number)
    except Exception as e:
        raise HTTPException(502, f"TMDB error: {e}")


@router.post("/tv/{tmdb_id}/prefetch-seasons")
async def prefetch_seasons(tmdb_id: int):
    """Pre-fetch all seasons for a show into the cache."""
    show = await database.get_show(tmdb_id)
    if not show:
        try:
            show = await _fetch_and_cache_show(tmdb_id, "tv")
        except Exception as e:
            raise HTTPException(502, str(e))

    seasons = show.get("seasons", [])
    results = []
    for s in seasons:
        sn = s["season_number"]
        cached = await database.get_season(tmdb_id, sn)
        if not cached:
            try:
                await _fetch_and_cache_season(tmdb_id, sn)
                results.append(sn)
            except Exception:
                pass
    return {"prefetched_seasons": results, "already_cached": len(seasons) - len(results)}
