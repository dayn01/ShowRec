from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from integrations import tmdb, tastedive, tvmaze, jellyfin, plex
from config import settings
import asyncio
import concurrent.futures
import database

router = APIRouter(prefix="/details", tags=["details"])


async def _correct_next_episode_date(show: dict) -> None:
    """Correct the show's next_episode_to_air.air_date via TVmaze (local tz) — this
    feeds the season header's 'E# <when>' badge. Silent no-op if unmatched."""
    try:
        ne = show.get("next_episode_to_air")
        if not ne or not ne.get("air_date"):
            return
        imdb_id = show.get("imdb_id")
        name = show.get("title") or show.get("name")
        if not imdb_id and not name:
            return
        air = await tvmaze.get_air_dates(imdb_id=imdb_id, name=name, upcoming_only=True)
        ld = air.get((ne.get("season_number"), ne.get("episode_number")))
        if ld:
            ne["air_date"] = ld
    except Exception:
        pass


async def _fetch_and_cache_show(tmdb_id: int, media_type: str) -> dict:
    data = await tmdb.get_details(tmdb_id, media_type)
    result = _shape_show(data, media_type)
    if media_type == "tv":
        await _correct_next_episode_date(result)
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
            "imdb_id": (data.get("external_ids") or {}).get("imdb_id"),
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


async def _apply_tvmaze_season_dates(tmdb_id: int, season: dict) -> None:
    """Overwrite the season's episode air_dates with TVmaze's accurate, local-tz
    dates (TMDB stores a bare date that's a day early for streamers). Silent no-op
    if the show can't be matched on TVmaze or isn't cached yet."""
    try:
        show = await database.get_show(tmdb_id, "tv")
        if not show:
            return
        imdb_id = show.get("imdb_id")
        name = show.get("title") or show.get("name")
        if not imdb_id and not name:
            return
        air = await tvmaze.get_air_dates(imdb_id=imdb_id, name=name)
        if not air:
            return
        sn = season.get("season_number")
        for ep in season.get("episodes", []):
            ld = air.get((sn, ep.get("episode_number")))
            if ld:
                ep["air_date"] = ld
    except Exception:
        pass


async def _fetch_and_cache_season(tmdb_id: int, season_number: int) -> dict:
    data = await tmdb.get_tv_season(tmdb_id, season_number)
    result = _shape_season(data)
    await _apply_tvmaze_season_dates(tmdb_id, result)
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
    # Look up by (id, media_type): TMDB movie and TV ids overlap, so an id-only
    # lookup could return the wrong-type record for a colliding id.
    cached = await database.get_show(tmdb_id, media_type)
    if cached:
        return cached
    try:
        return await _fetch_and_cache_show(tmdb_id, media_type)
    except Exception as e:
        raise HTTPException(502, f"TMDB error: {e}")


def _trim_for_watching(show: dict) -> dict:
    """Just the fields the Watching page needs — drops cast, overviews, keywords
    and per-episode data, so the batched response stays small on a Pi."""
    return {
        "id": show.get("id"),
        "title": show.get("title"),
        # Small thumbnail for the list — the full poster loads only on click.
        "poster_url": tmdb.sized_poster(show.get("poster_url"), "w154"),
        "vote_average": show.get("vote_average"),
        "status": show.get("status"),
        "networks": show.get("networks", []),
        "number_of_seasons": show.get("number_of_seasons"),
        "number_of_episodes": show.get("number_of_episodes"),
        "seasons": [
            {
                "season_number": s.get("season_number"),
                "name": s.get("name"),
                "episode_count": s.get("episode_count"),
                "air_date": s.get("air_date"),
                "poster_url": s.get("poster_url"),
            }
            for s in show.get("seasons", [])
        ],
    }


class DetailsBatchIn(BaseModel):
    ids: list[int]


@router.post("/batch")
async def get_details_batch(body: DetailsBatchIn):
    """
    Fetch trimmed details for many shows in ONE request (the Watching page).
    Served from the SQLite show cache; cache misses fetch from TMDB with bounded
    concurrency so a big list (e.g. after a Netflix import) doesn't fan out into
    hundreds of simultaneous TMDB calls on a low-power host.
    """
    ids = list(dict.fromkeys(body.ids))[:400]   # dedupe + safety cap
    sem = asyncio.Semaphore(6)                   # bound TMDB fan-out for misses

    async def one(tmdb_id: int):
        # Serve cached even if stale — Watching cares about speed, not freshness.
        # Watching is TV-only, so the batch fetches misses as "tv" below.
        show = await database.get_show(tmdb_id, "tv", allow_stale=True)
        if not show:
            async with sem:
                try:
                    show = await _fetch_and_cache_show(tmdb_id, "tv")
                except Exception:
                    return None
        return _trim_for_watching(show)

    results = await asyncio.gather(*[one(i) for i in ids])
    return {"shows": [r for r in results if r]}


async def _resolve_tastedive_item(item: dict, exclude_id: int) -> dict | None:
    """Resolve a TasteDive {name, type} suggestion to a TMDB item (for poster/score/id)."""
    name = item.get("name")
    media_type = "tv" if item.get("type") == "show" else "movie"
    if not name:
        return None
    try:
        results = await tmdb.search(name, media_type)
    except Exception:
        return None
    if not results:
        return None
    r = results[0]
    if not r.get("id") or r["id"] == exclude_id:
        return None
    return {
        "id": r["id"],
        "title": r.get("title") or r.get("name"),
        "media_type": media_type,
        "overview": r.get("overview") or "",
        "poster_url": tmdb.poster_url(r.get("poster_path")),
        "vote_average": r.get("vote_average") or 0,
        "genre_ids": r.get("genre_ids", []),
        "release_date": r.get("release_date"),
        "first_air_date": r.get("first_air_date"),
    }


def _shape_tmdb_similar(r: dict, media_type: str) -> dict:
    return {
        "id": r["id"],
        "title": r.get("title") or r.get("name"),
        "media_type": media_type,
        "overview": r.get("overview") or "",
        "poster_url": tmdb.poster_url(r.get("poster_path")),
        "vote_average": r.get("vote_average") or 0,
        "genre_ids": r.get("genre_ids", []),
        "release_date": r.get("release_date"),
        "first_air_date": r.get("first_air_date"),
    }


async def _tmdb_similar(tmdb_id: int, media_type: str, limit: int) -> list[dict]:
    """TMDB's own 'recommendations' (fall back to 'similar') — near-universal coverage."""
    items: list[dict] = []
    for fetch in (tmdb.get_recommendations, tmdb.get_similar):
        try:
            items = await fetch(tmdb_id, media_type)
        except Exception:
            items = []
        if items:
            break

    out, seen = [], set()
    for r in items:
        rid = r.get("id")
        if not rid or rid == tmdb_id or rid in seen:
            continue
        seen.add(rid)
        out.append(_shape_tmdb_similar(r, media_type))
        if len(out) >= limit:
            break
    return out


async def _tastedive_similar(tmdb_id: int, media_type: str, limit: int) -> list[dict]:
    """TasteDive 'also like' titles resolved to TMDB items. [] if no key / no title."""
    if not tastedive.enabled():
        return []
    show = await database.get_show(tmdb_id, media_type)
    if not show:
        try:
            show = await _fetch_and_cache_show(tmdb_id, media_type)
        except Exception:
            return []
    title = show.get("title") or show.get("name")
    if not title:
        return []

    suggestions = await tastedive.get_similar(title, media_type, limit=limit)
    resolved = await asyncio.gather(
        *(_resolve_tastedive_item(s, tmdb_id) for s in suggestions)
    )
    results, seen = [], set()
    for r in resolved:
        if r and r["id"] not in seen:
            seen.add(r["id"])
            results.append(r)
    return results


@router.get("/{media_type}/{tmdb_id}/similar")
async def get_similar(media_type: str, tmdb_id: int, limit: int = 12):
    """Similar titles for the details view.

    Prefers TasteDive's 'people who like X also like…' when a key is configured,
    and falls back to TMDB's own recommendations/similar (which cover almost
    every title) so the section reliably populates.
    """
    if media_type not in ("tv", "movie"):
        raise HTTPException(400, "media_type must be 'tv' or 'movie'")

    cache_key = f"similar:{media_type}:{tmdb_id}"
    cached = await database.cache_get(cache_key, "similar")
    if cached:  # truthy = non-empty; recompute past empties (e.g. cached before the TMDB fallback)
        return {"enabled": True, "results": cached}

    results = await _tastedive_similar(tmdb_id, media_type, limit)
    if not results:
        results = await _tmdb_similar(tmdb_id, media_type, limit)

    if results:
        await database.cache_set(cache_key, results)
    return {"enabled": True, "results": results}


_PROVIDER_LOGO = "https://image.tmdb.org/t/p/w92"


def _shape_providers(region_data: dict) -> dict:
    """Shape one region's TMDB watch data into {link, flatrate, rent, buy} lists."""
    def items(kind):
        seen, out = set(), []
        for p in region_data.get(kind, []) or []:
            name = p.get("provider_name")
            if name and name not in seen:
                seen.add(name)
                out.append({"name": name, "logo_url": _PROVIDER_LOGO + p["logo_path"] if p.get("logo_path") else None})
        return out
    return {
        "link": region_data.get("link"),
        "flatrate": items("flatrate"),   # streaming (subscription)
        "rent": items("rent"),
        "buy": items("buy"),
    }


@router.get("/{media_type}/{tmdb_id}/watch-providers")
async def get_watch_providers(media_type: str, tmdb_id: int, region: str = "AU"):
    """Where-to-watch for a title in a given region (default AU). One TMDB call
    is cached for all regions, then sliced to the requested one."""
    if media_type not in ("tv", "movie"):
        raise HTTPException(400, "media_type must be 'tv' or 'movie'")
    region = (region or "AU").upper()

    cache_key = f"providers:{media_type}:{tmdb_id}"
    all_regions = await database.cache_get(cache_key, "providers")
    if all_regions is None:
        all_regions = await tmdb.get_watch_providers(tmdb_id, media_type)
        # tmdb.get_watch_providers returns {} on ANY error (timeout/non-200), so
        # only cache a non-empty result — otherwise a transient TMDB blip gets
        # frozen as "no providers" for the full 24h TTL. Empty is retried next call.
        if all_regions:
            await database.cache_set(cache_key, all_regions)

    region_data = all_regions.get(region) or {}
    return {"region": region, "available_regions": sorted(all_regions.keys()), **_shape_providers(region_data)}


async def _merge_episode_availability(tmdb_id: int, season: dict) -> None:
    """Merge live per-episode availability into a season's episodes: sets `available`
    + `play_url` (a deep-link) on episodes present in Jellyfin and/or Plex, per the
    configured backend(s). Read time (not cached) so it stays current as episodes
    download. Jellyfin wins when a show is on both."""
    urls: dict = {}  # {(season, episode): play_url}
    # Jellyfin
    try:
        if settings.jellyfin_url and settings.jellyfin_api_key:
            base = settings.jellyfin_url.rstrip("/")
            for k, iid in (await jellyfin.get_show_episodes(tmdb_id)).items():
                urls[k] = f"{base}/web/#/details?id={iid}"
    except Exception:
        pass
    # Plex (sync plexapi → threadpool); fills in anything Jellyfin didn't cover
    try:
        if settings.plex_url and settings.plex_token:
            pbase = settings.plex_url.rstrip("/")
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                px = await loop.run_in_executor(pool, plex.get_show_episodes, tmdb_id)
            for k, (rk, machine) in px.items():
                if k in urls or not machine:
                    continue
                urls[k] = (f"{pbase}/web/index.html#!/server/{machine}"
                           f"/details?key=%2Flibrary%2Fmetadata%2F{rk}")
    except Exception:
        pass

    sn = season.get("season_number")
    for ep in season.get("episodes", []):
        pu = urls.get((sn, ep.get("episode_number")))
        ep["available"] = bool(pu)
        ep["play_url"] = pu


@router.get("/tv/{tmdb_id}/season/{season_number}")
async def get_season_episodes(tmdb_id: int, season_number: int):
    cached = await database.get_season(tmdb_id, season_number)
    if cached:
        season = cached
    else:
        try:
            season = await _fetch_and_cache_season(tmdb_id, season_number)
        except Exception as e:
            raise HTTPException(502, f"TMDB error: {e}")
    await _merge_episode_availability(tmdb_id, season)
    return season


@router.post("/tv/{tmdb_id}/prefetch-seasons")
async def prefetch_seasons(tmdb_id: int):
    """Pre-fetch all seasons for a show into the cache."""
    show = await database.get_show(tmdb_id, "tv")
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
