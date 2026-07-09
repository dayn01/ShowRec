"""
TVmaze integration — accurate episode air dates/times. Free, no API key.

Why this exists: TMDB stores an episode `air_date` as a bare date with no time,
and for streamers (notably Apple TV+, which drops at 9pm US-Pacific the evening
before) that date is the US-Pacific date — a day behind the rest of the world.
TVmaze exposes a full `airstamp` (date + time + offset), so we use it to correct
the air date for the viewer's timezone. Falls back silently when a show isn't found.
"""
import datetime
import logging

import httpx

logger = logging.getLogger(__name__)
BASE = "https://api.tvmaze.com"


async def _find_show_id(client: httpx.AsyncClient, imdb_id: str | None, name: str | None) -> int | None:
    """Resolve a TVmaze show id, preferring the IMDb id (exact) over a name search."""
    if imdb_id:
        try:
            r = await client.get(f"{BASE}/lookup/shows", params={"imdb": imdb_id})
            if r.status_code == 200:
                data = r.json()
                if data and data.get("id"):
                    return data["id"]
        except Exception:
            pass
    if name:
        try:
            r = await client.get(f"{BASE}/singlesearch/shows", params={"q": name})
            if r.status_code == 200:
                data = r.json()
                if data and data.get("id"):
                    return data["id"]
        except Exception:
            pass
    return None


async def get_upcoming_air_dates(imdb_id: str | None = None, name: str | None = None) -> dict:
    """
    Return {(season, number): airstamp} for episodes airing ~today or later.
    `airstamp` is a full ISO datetime (usually UTC). Empty dict if the show
    can't be resolved on TVmaze or has no scheduled upcoming episodes.
    """
    if not imdb_id and not name:
        return {}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            show_id = await _find_show_id(client, imdb_id, name)
            if not show_id:
                return {}
            r = await client.get(f"{BASE}/shows/{show_id}/episodes")
            if r.status_code != 200:
                return {}
            episodes = r.json()
    except Exception as e:
        logger.debug(f"TVmaze lookup failed for {imdb_id or name!r}: {e!r}")
        return {}

    # 18h grace so an episode airing "today" isn't dropped by clock skew.
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=18)
    out: dict = {}
    for e in episodes:
        stamp = e.get("airstamp")
        s, n = e.get("season"), e.get("number")
        if not stamp or s is None or n is None:
            continue
        try:
            dt = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except Exception:
            continue
        if dt >= cutoff:
            out[(s, n)] = stamp
    return out
