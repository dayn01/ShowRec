"""TMDB API client — metadata, recommendations, upcoming episodes."""
import httpx
from typing import Optional
from config import settings

BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _params(**kwargs) -> dict:
    return {"api_key": settings.tmdb_api_key, **kwargs}


async def validate_key(api_key: str) -> bool:
    """Return True if the given TMDB v3 key is accepted. Used by setup wizard."""
    if not api_key:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{BASE}/configuration", params={"api_key": api_key})
            return r.status_code == 200
    except Exception:
        return False


async def search(query: str, media_type: str = "multi") -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/search/{media_type}", params=_params(query=query))
        r.raise_for_status()
        return r.json().get("results", [])


async def get_recommendations(tmdb_id: int, media_type: str) -> list[dict]:
    """media_type: 'movie' or 'tv'"""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}/recommendations",
            params=_params(),
        )
        r.raise_for_status()
        return r.json().get("results", [])


async def get_similar(tmdb_id: int, media_type: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}/similar",
            params=_params(),
        )
        r.raise_for_status()
        return r.json().get("results", [])


async def get_details(tmdb_id: int, media_type: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/{media_type}/{tmdb_id}",
            params=_params(append_to_response="credits,keywords,external_ids"),
        )
        r.raise_for_status()
        return r.json()


async def get_watch_providers(tmdb_id: int, media_type: str) -> dict:
    """Streaming/rent/buy availability by region. Returns TMDB's `results` map
    (region code -> {link, flatrate, rent, buy}). {} on error."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{BASE}/{media_type}/{tmdb_id}/watch/providers",
                params=_params(),
            )
            if r.status_code != 200:
                return {}
            return r.json().get("results", {})
    except Exception:
        return {}


async def get_tv_season(tmdb_id: int, season_number: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/tv/{tmdb_id}/season/{season_number}",
            params=_params(),
        )
        r.raise_for_status()
        return r.json()


async def get_upcoming_episodes_for_show(tmdb_id: int) -> dict | None:
    """Returns next_episode_to_air and last_episode_to_air for a show."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/tv/{tmdb_id}",
            params=_params(append_to_response="next_episode_to_air,external_ids"),
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return {
            "tmdb_id": tmdb_id,
            "show_title": data.get("name"),
            "status": data.get("status"),
            "next_episode": data.get("next_episode_to_air"),
            "imdb_id": (data.get("external_ids") or {}).get("imdb_id"),
        }


async def get_tv_on_air(pages: int = 2) -> list[dict]:
    results = []
    async with httpx.AsyncClient() as client:
        for page in range(1, pages + 1):
            r = await client.get(
                f"{BASE}/tv/on_the_air",
                params=_params(page=page),
            )
            r.raise_for_status()
            results.extend(r.json().get("results", []))
    return results


async def get_trending(media_type: str, pages: int = 5) -> list[dict]:
    """
    TMDB trending across several pages. media_type: 'tv' or 'movie'.
    Returns full item metadata (id, title/name, overview, poster_path,
    vote_average, genre_ids, dates) — no per-item enrichment needed.
    """
    results = []
    async with httpx.AsyncClient(timeout=20) as client:
        for page in range(1, pages + 1):
            try:
                r = await client.get(
                    f"{BASE}/trending/{media_type}/week",
                    params=_params(page=page),
                )
                if r.status_code != 200:
                    break
                results.extend(r.json().get("results", []))
            except Exception:
                break
    return results


async def get_popular(media_type: str, pages: int = 5) -> list[dict]:
    """TMDB popular as a fallback/supplement to trending."""
    results = []
    async with httpx.AsyncClient(timeout=20) as client:
        for page in range(1, pages + 1):
            try:
                r = await client.get(f"{BASE}/{media_type}/popular", params=_params(page=page))
                if r.status_code != 200:
                    break
                results.extend(r.json().get("results", []))
            except Exception:
                break
    return results


async def discover(media_type: str, *, genres: list[int] = None, keywords: list[int] = None,
                   people: list[int] = None, pages: int = 1) -> list[dict]:
    """
    TMDB Discover — generate candidates by taste dimensions.
    media_type: 'tv' or 'movie'. Combine genres / keywords / people (OR within each).
    """
    results = []
    base_params = {"sort_by": "popularity.desc", "vote_count.gte": 50}
    if genres:
        base_params["with_genres"] = "|".join(str(g) for g in genres)
    if keywords:
        base_params["with_keywords"] = "|".join(str(k) for k in keywords)
    if people:
        # cast for movies, with_people works for both
        key = "with_cast" if media_type == "movie" else "with_people"
        base_params[key] = "|".join(str(p) for p in people)

    async with httpx.AsyncClient(timeout=20) as client:
        for page in range(1, pages + 1):
            try:
                r = await client.get(f"{BASE}/discover/{media_type}",
                                     params=_params(page=page, **base_params))
                if r.status_code != 200:
                    break
                results.extend(r.json().get("results", []))
            except Exception:
                break
    return results


def poster_url(path: Optional[str]) -> Optional[str]:
    return f"{IMAGE_BASE}{path}" if path else None


def sized_poster(url: Optional[str], size: str = "w154") -> Optional[str]:
    """Swap a stored w500 poster URL down to a smaller TMDB size — used for list
    thumbnails so the browser downloads ~10 KB instead of ~80 KB per card."""
    return url.replace("/t/p/w500/", f"/t/p/{size}/") if url else None
