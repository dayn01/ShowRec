"""TMDB search + watchlist."""
from fastapi import APIRouter, Query, HTTPException, Depends
from pydantic import BaseModel
from integrations import tmdb, jellyfin, plex
from deps import get_profile_id, pkey
from constants import GENRE_MAP
from config import settings
import database
import asyncio
import concurrent.futures
import re

router = APIRouter(tags=["library"])


# ── Search ────────────────────────────────────────────────────────────────────

# Trailing year, optionally parenthesised: "Dune 2021", "Inception (2010)".
_TRAILING_YEAR = re.compile(r"[\(\[]?\b((?:19|20)\d{2})\b[\)\]]?\s*$")


def _shape_result(item: dict, search_type: str) -> dict | None:
    mt = item.get("media_type") or ("tv" if search_type == "tv" else "movie")
    if mt not in ("tv", "movie"):
        return None  # skip people etc.
    return {
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
    }


def _relevance(title: str, query_lc: str) -> int:
    """Title-match strength against the query (higher = better)."""
    t = (title or "").lower()
    if not t:
        return 0
    if t == query_lc:
        return 1000
    if t.startswith(query_lc):
        return 500
    if query_lc in t:
        return 250
    # token overlap for word-order / partial-word differences
    overlap = len(set(query_lc.split()) & set(t.split()))
    return 100 * overlap


async def _search_with_fallback(q: str, search_type: str) -> list[dict]:
    """TMDB search, retrying with the trailing word dropped if nothing matches."""
    raw = await tmdb.search(q, search_type)
    if raw:
        return raw
    words = q.split()
    if len(words) > 1:
        raw = await tmdb.search(" ".join(words[:-1]), search_type)
    return raw


@router.get("/search")
async def search(q: str = Query(..., min_length=1), type: str = Query("multi", pattern="^(multi|tv|movie)$"),
                 pid: int = Depends(get_profile_id)):
    """Search TMDB for titles. Returns MediaCard-shaped results.

    Forgiving: collapses whitespace, strips a trailing year (used to rank the
    right edition up), retries with the last word dropped when empty, and ranks
    by title-match relevance first, then by closeness to the profile's taste
    (genre affinity + tuning weights), then popularity.
    """
    q = " ".join(q.split())  # normalise whitespace
    if not q:
        return {"results": []}

    year = None
    clean = q
    m = _TRAILING_YEAR.search(q)
    if m:
        year = m.group(1)
        stripped = q[:m.start()].strip()
        if stripped:           # don't blank the query if the year was all of it
            clean = stripped

    try:
        raw = await _search_with_fallback(clean, type)
    except Exception as e:
        raise HTTPException(502, f"TMDB search failed: {e}")

    # Rank against the original query (incl. any year) so titles that genuinely
    # contain a number — "Blade Runner 2049", "1917" — still match exactly.
    query_lc = q.lower()
    results: list[dict] = []
    seen: set[tuple] = set()
    for item in raw:
        shaped = _shape_result(item, type)
        if not shaped:
            continue
        if type != "multi" and shaped["media_type"] != type:
            continue  # keep type integrity even when a fallback broadens results
        key = (shaped["media_type"], shaped["id"])
        if key in seen:
            continue
        seen.add(key)
        results.append(shaped)

    # Personalisation: within a relevance bucket, prefer titles closer to the
    # profile's taste (genre affinity, scaled + reweighted by the Tune settings),
    # then popularity. Relevance stays primary so exact matches never get buried.
    rec_settings = await database.get_rec_settings(pid)
    genre_weight = rec_settings.get("genre_weight", 1.0)
    multipliers = rec_settings.get("genre_multipliers") or {}
    cached_recs = await database.cache_get(pkey(pid, "recommendations"), "recommendations")
    affinity = (cached_recs or {}).get("genre_affinity") or {}
    max_aff = max(affinity.values()) if affinity else 1

    def taste_factor(r: dict) -> float:
        taste, factor = 0.0, 1.0
        for gid in r.get("genre_ids", []):
            name = GENRE_MAP.get(gid)
            if not name:
                continue
            if affinity:
                taste += affinity.get(name, 0) / max_aff   # 0..1 per matching genre
            mult = multipliers.get(name)
            if mult is not None:
                factor *= mult                              # tuning: boost / damp / hide
        return (1 + taste * genre_weight) * factor

    def sort_key(r: dict):
        rel = _relevance(r.get("title") or "", query_lc)
        if year and (r.get("release_date") or r.get("first_air_date") or "")[:4] == year:
            rel += 300  # boost the matching-year edition
        return (rel, (r.get("popularity", 0) + 1) * taste_factor(r))

    results.sort(key=sort_key, reverse=True)
    return {"results": results}


# ── Owned library (in Jellyfin / Plex) ────────────────────────────────────────

@router.get("/library/owned")
async def get_owned_library():
    """Map of {tmdb_id: {source, url}} for titles in the connected Jellyfin/Plex
    library, so the UI can badge "in your library" and offer a play deep-link.
    Cached for an hour (library contents change slowly)."""
    cached = await database.cache_get("owned_library", "owned")
    if cached is not None:
        return {"items": cached}

    items: dict[str, dict] = {}

    # Jellyfin (async)
    try:
        for e in await jellyfin.get_library_index():
            url = f"{settings.jellyfin_url.rstrip('/')}/web/#/details?id={e['item_id']}"
            items[str(e["tmdb_id"])] = {"source": "jellyfin", "url": url}
    except Exception:
        pass

    # Plex (sync plexapi → threadpool); don't overwrite a Jellyfin entry.
    if settings.plex_url and settings.plex_token:
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                plex_items = await loop.run_in_executor(pool, plex.get_library_index)
            for e in plex_items:
                key = str(e["tmdb_id"])
                if key in items:
                    continue
                url = (f"{settings.plex_url.rstrip('/')}/web/index.html#!/server/{e['machine']}"
                       f"/details?key=%2Flibrary%2Fmetadata%2F{e['rating_key']}") if e.get("machine") else None
                items[key] = {"source": "plex", "url": url}
        except Exception:
            pass

    await database.cache_set("owned_library", items)
    return {"items": items}


# ── Full library (for the Library tab) ────────────────────────────────────────

@router.get("/library/all")
async def get_all_library():
    """Full media cards for everything in the connected Jellyfin/Plex library —
    powers the Library tab (type filter / genre / sort).

    The library index only carries {tmdb_id, media_type}; titles, posters and
    genre_ids come from the show cache (one bulk read). Uncached titles are warmed
    from TMDB with bounded fan-out per call, so a cold library fills in over a few
    loads instead of stalling the request. Cached 1h, like the owned-library map.
    """
    cached = await database.cache_get("library_all", "owned")
    if cached is not None:
        return {"items": cached}

    # 1) Collect the library index (tmdb_id → media_type). Jellyfin wins a tie so a
    #    title on both servers isn't listed twice / with the wrong type.
    index: dict[str, str] = {}
    try:
        for e in await jellyfin.get_library_index():
            index[str(e["tmdb_id"])] = e["media_type"]
    except Exception:
        pass
    if settings.plex_url and settings.plex_token:
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                plex_items = await loop.run_in_executor(pool, plex.get_library_index)
            for e in plex_items:
                index.setdefault(str(e["tmdb_id"]), e["media_type"])
        except Exception:
            pass

    if not index:
        return {"items": []}

    ids = [int(t) for t in index]

    # 2) Enrich from cache; warm a bounded batch of cache-misses from TMDB so the
    #    genre filter has data to work with. Concurrency-limited to be gentle.
    cache = await database.get_shows_bulk(ids)
    missing = [(int(t), mt) for t, mt in index.items() if int(t) not in cache][:400]
    if missing:
        from routers.details import _fetch_and_cache_show
        sem = asyncio.Semaphore(8)

        async def warm(tmdb_id: int, media_type: str):
            async with sem:
                try:
                    await _fetch_and_cache_show(tmdb_id, media_type)
                except Exception:
                    pass

        await asyncio.gather(*[warm(t, mt) for t, mt in missing])
        cache = await database.get_shows_bulk(ids)

    # 3) Shape MediaCard objects. media_type comes from the index (authoritative for
    #    the library); metadata from the cache. Titles not yet cached are skipped and
    #    fill in on a later load once the warmer catches them.
    items = []
    for t, mt in index.items():
        c = cache.get(int(t))
        if not c:
            continue
        items.append({
            "id": int(t),
            "media_type": mt,
            "title": c.get("title") or c.get("name") or "Unknown",
            "name": c.get("name"),
            "poster_url": c.get("poster_url"),
            "overview": c.get("overview", ""),
            "vote_average": c.get("vote_average", 0),
            "genre_ids": c.get("genre_ids", []),
            "release_date": c.get("release_date"),
            "first_air_date": c.get("first_air_date"),
        })

    await database.cache_set("library_all", items)
    return {"items": items}


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


# A season counts as "just released" for watchlist ordering/badging if it aired
# within this many days (covers a binge drop and most of a weekly run).
_NEW_SEASON_DAYS = 60


@router.get("/watchlist")
async def get_watchlist(pid: int = Depends(get_profile_id)):
    from datetime import date, timedelta
    items = await database.get_watchlist(pid)
    # The watchlist table doesn't store genres or air dates — enrich from the show
    # cache so the genre filter works and we can surface a freshly-released season.
    cache = await database.get_shows_bulk([i["tmdb_id"] for i in items])
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=_NEW_SEASON_DAYS)).isoformat()
    for it in items:
        show = cache.get(it["tmdb_id"])
        it["genre_ids"] = show.get("genre_ids", []) if show else []
        # TV: flag a season that aired recently so it ranks above plain recency and
        # shows the existing "🆕 New season" card badge (driven by `new_season`).
        if show and it["media_type"] == "tv":
            sn, ad = database.latest_aired_season(show, today)
            if sn and ad and ad >= cutoff:
                it["new_season"] = True
                it["reason"] = f"Season {sn} just released"
    return {"items": items}


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
