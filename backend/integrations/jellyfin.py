"""Jellyfin API client — watch history and library browsing."""
import time
import httpx
from datetime import datetime
from typing import Optional
from config import settings


def _epoch(iso: str | None) -> int:
    """Jellyfin's DateCreated ("2024-01-15T10:30:00.0000000Z") → Unix epoch, for
    sortable "recently added" ordering. Drops fractional seconds/tz (all items come
    from the same server, so relative order is what matters). 0 when unparseable."""
    if not iso:
        return 0
    try:
        return int(datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").timestamp())
    except Exception:
        return 0


def _base() -> str:
    return settings.jellyfin_url.rstrip("/")


def _headers() -> dict:
    return {
        "X-Emby-Token": settings.jellyfin_api_key,
        "Content-Type": "application/json",
    }


async def get_watch_history(limit: int = 200) -> list[dict]:
    user_id = settings.jellyfin_user_id
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_base()}/Users/{user_id}/Items",
            headers=_headers(),
            params={
                "Filters": "IsPlayed",
                "IncludeItemTypes": "Movie,Episode",
                "Recursive": "true",
                "Fields": "ProviderIds,Genres,Overview",
                "Limit": limit,
                "SortBy": "DatePlayed",
                "SortOrder": "Descending",
            },
        )
        r.raise_for_status()
        return r.json().get("Items", [])


async def get_watched_episodes(user_id: str | None = None) -> list[dict]:
    """
    Returns every watched episode mapped to its show's TMDB id:
    [{tmdb_id, season, episode, series_name}, ...]
    Jellyfin tracks per-episode played state natively.
    """
    user_id = user_id or settings.jellyfin_user_id
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. All played episodes with series linkage + episode/season numbers
        r = await client.get(
            f"{_base()}/Users/{user_id}/Items",
            headers=_headers(),
            params={
                "Filters": "IsPlayed",
                "IncludeItemTypes": "Episode",
                "Recursive": "true",
                "Fields": "SeriesId,ParentIndexNumber,IndexNumber",
                "Limit": 5000,
            },
        )
        r.raise_for_status()
        episodes = r.json().get("Items", [])

        # 2. Map each unique SeriesId → TMDB id
        series_ids = {e.get("SeriesId") for e in episodes if e.get("SeriesId")}
        series_tmdb: dict[str, tuple[int, str]] = {}

        for sid in series_ids:
            try:
                sr = await client.get(
                    f"{_base()}/Users/{user_id}/Items/{sid}",
                    headers=_headers(),
                    params={"Fields": "ProviderIds"},
                )
                if sr.status_code == 200:
                    data = sr.json()
                    pid = data.get("ProviderIds", {})
                    tmdb = pid.get("Tmdb") or pid.get("tmdb")
                    if tmdb:
                        series_tmdb[sid] = (int(tmdb), data.get("Name", ""))
            except Exception:
                continue

    result = []
    for e in episodes:
        sid = e.get("SeriesId")
        season = e.get("ParentIndexNumber")
        episode = e.get("IndexNumber")
        if sid in series_tmdb and season is not None and episode is not None:
            tmdb_id, name = series_tmdb[sid]
            result.append({
                "tmdb_id": tmdb_id, "season": season,
                "episode": episode, "series_name": name,
            })
    return result


async def get_watched_movies(user_id: str | None = None) -> list[dict]:
    """Returns watched movies mapped to TMDB ids."""
    user_id = user_id or settings.jellyfin_user_id
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_base()}/Users/{user_id}/Items",
            headers=_headers(),
            params={
                "Filters": "IsPlayed",
                "IncludeItemTypes": "Movie",
                "Recursive": "true",
                "Fields": "ProviderIds",
                "Limit": 2000,
            },
        )
        r.raise_for_status()
        movies = r.json().get("Items", [])

    result = []
    for m in movies:
        pid = m.get("ProviderIds", {})
        tmdb = pid.get("Tmdb") or pid.get("tmdb")
        if not tmdb:
            continue
        try:
            # Jellyfin doesn't guarantee a clean integer Tmdb id (can be a URL,
            # an IMDb-style value, or empty). Skip the bad row instead of
            # aborting the whole movie sync — matches get_watched_episodes.
            result.append({"tmdb_id": int(tmdb), "title": m.get("Name", "")})
        except (ValueError, TypeError):
            continue
    return result


async def get_library_index() -> list[dict]:
    """Every movie + series in the library mapped to its TMDB id and Jellyfin item
    id (for play deep-links): [{tmdb_id, media_type, item_id, added}, ...].
    `added` is the Unix epoch it entered the library (0 if unknown)."""
    if not settings.jellyfin_url or not settings.jellyfin_api_key:
        return []
    user_id = settings.jellyfin_user_id
    base = f"{_base()}/Users/{user_id}/Items" if user_id else f"{_base()}/Items"
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=30) as client:
        for item_type, mt in (("Movie", "movie"), ("Series", "tv")):
            try:
                r = await client.get(base, headers=_headers(), params={
                    "IncludeItemTypes": item_type, "Recursive": "true",
                    "Fields": "ProviderIds,DateCreated", "Limit": 10000,
                })
                if r.status_code != 200:
                    continue
                for it in r.json().get("Items", []):
                    pid = it.get("ProviderIds", {})
                    tmdb = pid.get("Tmdb") or pid.get("tmdb")
                    if tmdb and it.get("Id"):
                        out.append({"tmdb_id": int(tmdb), "media_type": mt, "item_id": it["Id"],
                                    "added": _epoch(it.get("DateCreated"))})
            except Exception:
                continue
    return out


async def get_episode_availability(user_id: str | None = None) -> dict:
    """For shows with at least one watched episode, the latest episode AVAILABLE in
    the library: {tmdb_id: [season, episode]}. Lets the UI flag 'next episode ready
    to watch'. Uses the library index for series→tmdb (no per-series calls)."""
    user_id = user_id or settings.jellyfin_user_id
    if not (settings.jellyfin_url and settings.jellyfin_api_key and user_id):
        return {}

    index = await get_library_index()
    series_tmdb = {e["item_id"]: e["tmdb_id"] for e in index if e["media_type"] == "tv"}

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_base()}/Users/{user_id}/Items", headers=_headers(), params={
                "IncludeItemTypes": "Episode", "Recursive": "true",
                "Fields": "SeriesId,ParentIndexNumber,IndexNumber,UserData", "Limit": 10000,
            })
        if r.status_code != 200:
            return {}
        episodes = r.json().get("Items", [])

    by_series: dict[str, dict] = {}
    for e in episodes:
        sid, s, ep = e.get("SeriesId"), e.get("ParentIndexNumber"), e.get("IndexNumber")
        if not sid or s is None or ep is None:
            continue
        info = by_series.setdefault(sid, {"max": (0, 0), "any_played": False})
        if (s, ep) > info["max"]:
            info["max"] = (s, ep)
        if (e.get("UserData") or {}).get("Played"):
            info["any_played"] = True

    out: dict[int, list] = {}
    for sid, info in by_series.items():
        if not info["any_played"]:
            continue  # only shows you've started matter for "continue watching"
        tid = series_tmdb.get(sid)
        if tid:
            out[tid] = list(info["max"])
    return out


_series_id_cache: dict = {"at": 0.0, "map": {}}


async def _tmdb_to_series_id() -> dict:
    """Cached {tmdb_id: jellyfin_series_item_id} from the library index (10-min TTL)
    so per-show availability lookups don't re-scan the whole library each time."""
    if _series_id_cache["map"] and (time.time() - _series_id_cache["at"] < 600):
        return _series_id_cache["map"]
    index = await get_library_index()
    m = {e["tmdb_id"]: e["item_id"] for e in index if e.get("media_type") == "tv"}
    _series_id_cache["at"] = time.time()
    _series_id_cache["map"] = m
    return m


async def get_show_episodes(tmdb_id: int, user_id: str | None = None) -> dict:
    """{(season, episode): jellyfin_item_id} for one show's episodes present in the
    library — powers the per-episode 'on the box' + Play markers. {} if not found."""
    user_id = user_id or settings.jellyfin_user_id
    if not (settings.jellyfin_url and settings.jellyfin_api_key and user_id):
        return {}
    series_id = (await _tmdb_to_series_id()).get(tmdb_id)
    if not series_id:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{_base()}/Users/{user_id}/Items", headers=_headers(), params={
                    "ParentId": series_id, "IncludeItemTypes": "Episode",
                    "Recursive": "true", "Fields": "ParentIndexNumber,IndexNumber",
                    "Limit": 5000,
                })
            if r.status_code != 200:
                return {}
            eps = r.json().get("Items", [])
    except Exception:
        return {}
    out: dict = {}
    for e in eps:
        s, n, iid = e.get("ParentIndexNumber"), e.get("IndexNumber"), e.get("Id")
        if s is not None and n is not None and iid:
            out[(s, n)] = iid
    return out


async def get_resume_items() -> list[dict]:
    user_id = settings.jellyfin_user_id
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_base()}/Users/{user_id}/Items/Resume",
            headers=_headers(),
            params={"IncludeItemTypes": "Movie,Episode", "Fields": "ProviderIds,Genres"},
        )
        r.raise_for_status()
        return r.json().get("Items", [])


async def list_users(url: str, api_key: str) -> list[dict] | None:
    """
    List Jellyfin accounts for the setup wizard, using values typed into the
    form (not the saved settings). Returns [{id, name}], or None if the
    server/key is unreachable or rejected.
    """
    if not url or not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{url.rstrip('/')}/Users",
                headers={"X-Emby-Token": api_key, "Content-Type": "application/json"},
            )
            if r.status_code != 200:
                return None
            return [{"id": u["Id"], "name": u.get("Name", "")} for u in r.json()]
    except Exception:
        return None


async def ping() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_base()}/System/Info/Public")
            return r.status_code == 200
    except Exception:
        return False


async def user_exists(user_id: str | None) -> bool | None:
    """True/False if we could check whether the user id is valid; None if we
    couldn't tell (server unreachable, missing config, or an ambiguous status)."""
    if not (settings.jellyfin_url and settings.jellyfin_api_key and user_id):
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{_base()}/Users/{user_id}", headers=_headers())
        if r.status_code == 200:
            return True
        if r.status_code in (400, 404):   # Jellyfin returns these for an unknown id
            return False
        return None                       # 401/5xx — can't be sure
    except Exception:
        return None


async def resolve_user_id(username: str | None = None) -> str | None:
    """Current Jellyfin user id for the configured (stable) username, or None."""
    username = (username or settings.jellyfin_username or "").strip()
    if not username:
        return None
    users = await list_users(settings.jellyfin_url, settings.jellyfin_api_key)
    for u in (users or []):
        if (u.get("name") or "").strip().lower() == username.lower():
            return u.get("id")
    return None


async def ping_user() -> bool:
    """Health for the status dot: the server is reachable AND the configured user
    id is valid. A stale user id (e.g. Jellyfin reinstalled) shows red instead of a
    misleading green, so a broken sync is actually visible."""
    if not await ping():
        return False
    if not settings.jellyfin_user_id:
        return True                       # server up, no user linked yet
    return await user_exists(settings.jellyfin_user_id) is not False
