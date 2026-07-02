"""Overseerr API client — request media and read availability status.

Optional integration: every public function assumes the caller has already
checked `is_configured()` (or the router has), mirroring how jellyfin/plex are
gated in routers/status.py. When Overseerr isn't configured the feature simply
never surfaces in the UI.
"""
import logging
import httpx
from config import settings

logger = logging.getLogger("showrec.overseerr")

# Overseerr media availability codes (mediaInfo.status).
_STATUS = {
    1: "unknown",
    2: "pending",       # requested, awaiting approval
    3: "processing",    # approved, downloading
    4: "partial",       # some seasons available
    5: "available",     # on disk / playable
}


def is_configured() -> bool:
    return bool(settings.overseerr_url and settings.overseerr_api_key)


def _base() -> str:
    return settings.overseerr_url.rstrip("/")


def _headers() -> dict:
    return {
        "X-Api-Key": settings.overseerr_api_key,
        "Content-Type": "application/json",
    }


async def ping() -> bool:
    """True when Overseerr is reachable and the API key is accepted."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{_base()}/api/v1/status", headers=_headers())
            return r.status_code == 200
    except Exception:
        return False


async def get_status(tmdb_id: int, media_type: str) -> dict:
    """
    Return {"status": <str>, "requested": <bool>} for a title, so the UI can
    show whether it's already on the server / requested. Falls back to
    "unknown" on any error so the request button still works.
    """
    kind = "movie" if media_type == "movie" else "tv"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{_base()}/api/v1/{kind}/{tmdb_id}", headers=_headers())
            if r.status_code != 200:
                return {"status": "unknown", "requested": False, "seasons": {}}
            info = (r.json() or {}).get("mediaInfo") or {}
            code = info.get("status")
            # Per-season status (TV), so the per-season Request buttons reflect the
            # real state, not just this session's clicks. Merge two sources: the
            # tracked seasons (availability) and the request objects (where a
            # freshly-requested season shows up before it's on disk). Keep the most
            # "available" status when they disagree.
            _RANK = {"unknown": 0, "pending": 1, "processing": 2, "partial": 3, "available": 4}
            seasons: dict[str, str] = {}

            def _merge(season_number, status_code):
                if season_number is None:
                    return
                key = str(season_number)
                new = _STATUS.get(status_code, "unknown")
                if _RANK.get(new, 0) >= _RANK.get(seasons.get(key, "unknown"), 0):
                    seasons[key] = new

            for s in (info.get("seasons") or []):
                _merge(s.get("seasonNumber"), s.get("status"))
            for req in (info.get("requests") or []):
                for rs in (req.get("seasons") or []):
                    # A season inside a request is at least being processed.
                    _merge(rs.get("seasonNumber"), rs.get("status") or 3)
            return {
                "status": _STATUS.get(code, "unknown"),
                "requested": code in (2, 3, 4, 5),
                "seasons": seasons,
            }
    except Exception:
        return {"status": "unknown", "requested": False, "seasons": {}}


async def get_all_statuses() -> dict[int, str]:
    """
    Map of {tmdb_id: status_string} for everything Overseerr/Jellyseerr tracks —
    both requested items and titles already available via its library sync.
    Powers the per-card availability badge with a single call (paginated).
    """
    result: dict[int, str] = {}
    take = 100
    skip = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for _ in range(50):  # hard cap: 5000 items, avoids runaway loops
            # Guard each page independently: a transient error on page N must
            # not discard the whole map (a truncated map reads as "not
            # requested" for everything past the failure). Stop paginating and
            # return what we have, but log it so silent partials are visible.
            try:
                r = await client.get(
                    f"{_base()}/api/v1/media",
                    headers=_headers(),
                    params={"take": take, "skip": skip},
                )
                if r.status_code != 200:
                    logger.warning("Overseerr /media page at skip=%d returned %d; returning partial map (%d items)",
                                   skip, r.status_code, len(result))
                    break
                data = r.json() or {}
            except Exception as e:
                logger.warning("Overseerr /media page at skip=%d failed (%r); returning partial map (%d items)",
                               skip, e, len(result))
                break
            items = data.get("results", [])
            for m in items:
                tmdb = m.get("tmdbId")
                if tmdb is not None:
                    try:
                        result[int(tmdb)] = _STATUS.get(m.get("status"), "unknown")
                    except (ValueError, TypeError):
                        continue
            total = (data.get("pageInfo") or {}).get("results", 0)
            skip += take
            if not items or skip >= total:
                break
    return result


async def cancel_request(tmdb_id: int, media_type: str, seasons: list[int] | None = None) -> dict:
    """
    Cancel Overseerr request(s) for a title. Looks up the request ids from the media
    detail (mediaInfo.requests) and DELETEs each. With `seasons` given (TV only),
    cancel just the request object(s) covering those seasons; otherwise cancel all.

    Overseerr can't drop a single season from a multi-season request, so cancelling a
    season removes the whole request object it belongs to — `also_affected` lists any
    other seasons that came down with it (usually empty, since the app requests
    seasons individually). Returns
    {"ok": bool, "cancelled": int, "status": str, "also_affected": list[int]}.
    """
    kind = "movie" if media_type == "movie" else "tv"
    want = set(seasons or [])
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{_base()}/api/v1/{kind}/{tmdb_id}", headers=_headers())
            if r.status_code != 200:
                return {"ok": False, "status": "error", "detail": f"lookup {r.status_code}"}
            info = (r.json() or {}).get("mediaInfo") or {}
            req_ids: list[int] = []
            also: set[int] = set()
            for req in (info.get("requests") or []):
                rid = req.get("id")
                if not rid:
                    continue
                # No season filter (or a movie): every request object qualifies.
                if not want or kind == "movie":
                    req_ids.append(rid)
                    continue
                req_seasons = [rs.get("seasonNumber") for rs in (req.get("seasons") or [])]
                if want.intersection(req_seasons):
                    req_ids.append(rid)
                    also.update(s for s in req_seasons if s is not None and s not in want)
            if not req_ids:
                return {"ok": True, "cancelled": 0, "status": "no_request", "also_affected": []}
            cancelled = 0
            for rid in req_ids:
                dr = await client.delete(f"{_base()}/api/v1/request/{rid}", headers=_headers())
                if dr.status_code in (200, 204):
                    cancelled += 1
            return {"ok": cancelled > 0, "cancelled": cancelled, "status": "cancelled",
                    "also_affected": sorted(also)}
    except Exception as e:
        return {"ok": False, "status": "error", "detail": str(e)}


async def request_media(tmdb_id: int, media_type: str, seasons: list[int] | None = None) -> dict:
    """
    File a request with Overseerr. For TV, request `seasons` (the unseen ones the
    app computed); when None, request all. An empty list means nothing to request.
    Returns {"ok": bool, "status": <str>, "detail": <str|None>}.
    """
    kind = "movie" if media_type == "movie" else "tv"
    body: dict = {"mediaType": kind, "mediaId": tmdb_id}
    if kind == "tv":
        if seasons is None:
            body["seasons"] = "all"
        elif len(seasons) == 0:
            return {"ok": True, "status": "nothing_to_request", "detail": None}
        else:
            body["seasons"] = seasons
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{_base()}/api/v1/request", headers=_headers(), json=body)
            if r.status_code in (200, 201):
                return {"ok": True, "status": "requested", "detail": None}
            # 409 = already requested/available — treat as success-ish for the UI.
            if r.status_code == 409:
                return {"ok": True, "status": "already_requested", "detail": None}
            return {"ok": False, "status": "error", "detail": f"{r.status_code} {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "status": "error", "detail": str(e)}
