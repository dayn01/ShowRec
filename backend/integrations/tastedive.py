"""TasteDive integration — 'people who like X also like…' similar titles."""
import httpx
from config import settings

BASE = "https://tastedive.com/api/similar"


def enabled() -> bool:
    return bool(settings.tastedive_api_key)


async def get_similar(title: str, media_type: str, limit: int = 15) -> list[dict]:
    """
    Returns similar titles for a movie/show as [{name, type}].
    media_type: 'tv' or 'movie'. Returns [] if no key or on error.
    """
    if not settings.tastedive_api_key or not title:
        return []
    td_type = "show" if media_type == "tv" else "movie"
    params = {
        "q": title,
        "type": td_type,
        "k": settings.tastedive_api_key,
        "info": 1,
        "limit": limit,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(BASE, params=params)
            if r.status_code != 200:
                return []
            data = r.json()
    except Exception:
        return []

    # The API has used both lowercase and capitalised keys over versions
    similar = data.get("similar") or data.get("Similar") or {}
    results = similar.get("results") or similar.get("Results") or []
    out = []
    for item in results:
        name = item.get("name") or item.get("Name")
        rtype = (item.get("type") or item.get("Type") or td_type).lower()
        if name and rtype in ("show", "movie"):
            out.append({"name": name, "type": rtype})
    return out
