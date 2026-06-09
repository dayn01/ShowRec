"""Plex API client — watch history via plexapi library."""
from typing import Optional

try:
    from plexapi.server import PlexServer
    from plexapi.myplex import MyPlexAccount
    PLEX_AVAILABLE = True
except ImportError:
    PLEX_AVAILABLE = False

from config import settings


def _get_server(token: Optional[str] = None) -> Optional["PlexServer"]:
    """Server connection. Pass a per-user token to read that user's watch state."""
    if not PLEX_AVAILABLE or not settings.plex_url:
        return None
    tok = token or settings.plex_token
    if not tok:
        return None
    return PlexServer(settings.plex_url, tok)


def list_home_users() -> list[dict]:
    """List the Plex account owner + Home/managed users (for linking to profiles)."""
    if not PLEX_AVAILABLE or not settings.plex_token:
        return []
    try:
        account = MyPlexAccount(token=settings.plex_token)
        users = [{"id": "owner", "title": account.title or account.username or "Owner", "owner": True}]
        for u in account.users():
            users.append({"id": str(u.id), "title": u.title, "owner": False})
        return users
    except Exception:
        return []


def get_user_token(identifier: Optional[str]) -> Optional[str]:
    """
    Resolve a Plex access token for a Home user (by id or title).
    'owner' / empty → the global admin token.
    """
    if not identifier or identifier == "owner":
        return settings.plex_token
    if not PLEX_AVAILABLE or not settings.plex_token:
        return None
    try:
        account = MyPlexAccount(token=settings.plex_token)
        for u in account.users():
            if str(u.id) == str(identifier) or u.title == identifier:
                switched = account.switchHomeUser(u.title)
                return getattr(switched, "authToken", None) or getattr(switched, "_token", None)
    except Exception:
        return None
    return None


def get_watch_history(limit: int = 200) -> list[dict]:
    server = _get_server()
    if not server:
        return []

    history = server.history(maxresults=limit)
    items = []
    for entry in history:
        item = {
            "title": entry.title,
            "type": entry.type,  # 'movie' or 'episode'
            "year": getattr(entry, "year", None),
            "genres": [g.tag for g in getattr(entry, "genres", [])],
            "rating": getattr(entry, "userRating", None),
            "guids": {g.id.split("://")[0]: g.id.split("://")[1] for g in getattr(entry, "guids", [])},
        }
        if entry.type == "episode":
            item["show_title"] = entry.grandparentTitle
        items.append(item)
    return items


def _tmdb_from_guids(item) -> Optional[int]:
    """Extract a TMDB id from a Plex item's guids."""
    for g in getattr(item, "guids", []) or []:
        gid = getattr(g, "id", "") or ""
        if gid.startswith("tmdb://"):
            try:
                return int(gid.split("://")[1])
            except (ValueError, IndexError):
                return None
    return None


def get_watched_episodes(token: Optional[str] = None) -> list[dict]:
    """
    Returns every watched episode mapped to its show's TMDB id:
    [{tmdb_id, season, episode, series_name}, ...]
    Iterates Plex TV sections and reads per-episode played state.
    Pass a per-user token to read a specific Home user's watch state.
    """
    server = _get_server(token)
    if not server:
        return []

    result: list[dict] = []
    show_tmdb: dict[str, Optional[int]] = {}  # grandparentRatingKey -> tmdb id

    for section in server.library.sections():
        if section.type != "show":
            continue
        try:
            # Watched episodes only
            episodes = section.searchEpisodes(unwatched=False)
        except Exception:
            try:
                episodes = [e for e in section.searchEpisodes() if getattr(e, "isPlayed", False)]
            except Exception:
                continue

        for ep in episodes:
            try:
                if not getattr(ep, "isPlayed", False) and not (getattr(ep, "viewCount", 0) or 0):
                    continue
                gk = str(getattr(ep, "grandparentRatingKey", "") or "")
                if not gk:
                    continue
                if gk not in show_tmdb:
                    tmdb_id = None
                    try:
                        show = server.fetchItem(int(gk))
                        tmdb_id = _tmdb_from_guids(show)
                    except Exception:
                        pass
                    show_tmdb[gk] = tmdb_id

                tmdb_id = show_tmdb[gk]
                season = getattr(ep, "parentIndex", None)
                number = getattr(ep, "index", None)
                if tmdb_id and season is not None and number is not None:
                    result.append({
                        "tmdb_id": tmdb_id,
                        "season": int(season),
                        "episode": int(number),
                        "series_name": getattr(ep, "grandparentTitle", ""),
                    })
            except Exception:
                continue

    return result


def get_watched_movies(token: Optional[str] = None) -> list[dict]:
    """Returns watched movies mapped to TMDB ids from Plex movie sections."""
    server = _get_server(token)
    if not server:
        return []

    result: list[dict] = []
    for section in server.library.sections():
        if section.type != "movie":
            continue
        try:
            movies = section.search(unwatched=False)
        except Exception:
            try:
                movies = [m for m in section.all() if getattr(m, "isPlayed", False)]
            except Exception:
                continue

        for m in movies:
            try:
                if not getattr(m, "isPlayed", False) and not (getattr(m, "viewCount", 0) or 0):
                    continue
                tmdb_id = _tmdb_from_guids(m)
                if tmdb_id:
                    result.append({"tmdb_id": tmdb_id, "title": getattr(m, "title", "")})
            except Exception:
                continue
    return result


def get_library_index() -> list[dict]:
    """Every movie + show in the library mapped to its TMDB id, ratingKey and the
    server's machine id (for play deep-links): [{tmdb_id, media_type, rating_key, machine}]."""
    server = _get_server()
    if not server:
        return []
    try:
        machine = server.machineIdentifier
    except Exception:
        machine = None

    out: list[dict] = []
    for section in server.library.sections():
        if section.type not in ("movie", "show"):
            continue
        mt = "movie" if section.type == "movie" else "tv"
        try:
            items = section.all()
        except Exception:
            continue
        for it in items:
            try:
                tmdb_id = _tmdb_from_guids(it)
                rk = getattr(it, "ratingKey", None)
                if tmdb_id and rk:
                    out.append({"tmdb_id": tmdb_id, "media_type": mt,
                                "rating_key": str(rk), "machine": machine})
            except Exception:
                continue
    return out


def ping() -> bool:
    try:
        server = _get_server()
        return server is not None
    except Exception:
        return False
