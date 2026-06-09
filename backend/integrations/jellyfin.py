"""Jellyfin API client — watch history and library browsing."""
import httpx
from typing import Optional
from config import settings


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
        if tmdb:
            result.append({"tmdb_id": int(tmdb), "title": m.get("Name", "")})
    return result


async def get_library_index() -> list[dict]:
    """Every movie + series in the library mapped to its TMDB id and Jellyfin item
    id (for play deep-links): [{tmdb_id, media_type, item_id}, ...]."""
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
                    "Fields": "ProviderIds", "Limit": 10000,
                })
                if r.status_code != 200:
                    continue
                for it in r.json().get("Items", []):
                    pid = it.get("ProviderIds", {})
                    tmdb = pid.get("Tmdb") or pid.get("tmdb")
                    if tmdb and it.get("Id"):
                        out.append({"tmdb_id": int(tmdb), "media_type": mt, "item_id": it["Id"]})
            except Exception:
                continue
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
