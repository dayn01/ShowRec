"""Trakt API client — watch history, ratings, upcoming episodes."""
import httpx
from config import settings

BASE = "https://api.trakt.tv"


def _headers(token: str | None = None) -> dict:
    h = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": settings.trakt_client_id,
    }
    tok = token or settings.trakt_access_token
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return h


async def get_watch_history(media_type: str = "movies", limit: int = 100) -> list[dict]:
    """media_type: 'movies', 'shows', or 'episodes'"""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/users/me/history/{media_type}",
            headers=_headers(),
            params={"limit": limit},
        )
        r.raise_for_status()
        return r.json()


async def get_ratings(media_type: str = "shows") -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/users/me/ratings/{media_type}",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


async def get_watchlist(media_type: str = "shows") -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/users/me/watchlist/{media_type}",
            headers=_headers(),
        )
        r.raise_for_status()
        return r.json()


async def get_calendar_shows(days: int = 30) -> list[dict]:
    """Returns episodes airing in the next N days for shows the user watches."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/calendars/my/shows",
            headers=_headers(),
            params={"days": days},
        )
        r.raise_for_status()
        return r.json()


async def get_show_details(trakt_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/shows/{trakt_id}",
            headers=_headers(),
            params={"extended": "full"},
        )
        r.raise_for_status()
        return r.json()


async def get_all_watched_shows(min_plays: int = 3) -> list[dict]:
    """Returns all shows the user has watched with at least min_plays total plays."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/users/me/watched/shows",
            headers=_headers(),
            params={"extended": "noseasons"},
        )
        r.raise_for_status()
        data = r.json()
        # Filter to shows with meaningful watch history
        return [s for s in data if s.get("plays", 0) >= min_plays]


async def get_personal_recommendations(media_type: str = "shows", limit: int = 30,
                                       token: str | None = None) -> list[dict]:
    """Trakt's personalised recommendations for a specific user's token.

    The token must be passed explicitly (a profile's own Trakt token) — this does
    NOT fall back to the global owner token, so profiles don't leak into each other.
    Returns [] when no token is given.
    """
    if not token:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"{BASE}/recommendations/{media_type}",
                headers=_headers(token),
                params={"limit": limit, "ignore_collected": "true"},
            )
            if r.status_code != 200:
                return []
            return r.json()
    except Exception:
        return []


async def get_trending(media_type: str = "shows", limit: int = 20) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE}/{media_type}/trending",
            headers=_headers(),
            params={"limit": limit},
        )
        r.raise_for_status()
        return r.json()


async def exchange_code_for_token(code: str) -> dict:
    """OAuth2 device code → access token exchange."""
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE}/oauth/token",
            json={
                "code": code,
                "client_id": settings.trakt_client_id,
                "client_secret": settings.trakt_client_secret,
                "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
                "grant_type": "authorization_code",
            },
        )
        r.raise_for_status()
        return r.json()
