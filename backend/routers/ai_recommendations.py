from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from integrations import trakt, tmdb, reddit
from integrations.claude import get_ai_recommendations, get_custom_recommendations
from routers.recommendations import _gather_history
from config import settings
from deps import get_profile_id, pkey
import asyncio
import concurrent.futures
import database

router = APIRouter(prefix="/ai-recommendations", tags=["ai"])


class CustomRequest(BaseModel):
    media_type: str = "any"
    genres: list[str] = []
    prompt: str = ""


@router.get("")
async def get_ai_recs(pid: int = Depends(get_profile_id)):
    if not settings.anthropic_api_key or settings.anthropic_api_key == "your_anthropic_api_key_here":
        raise HTTPException(503, "Anthropic API key not configured — add ANTHROPIC_API_KEY to .env")

    cached = await database.cache_get(pkey(pid, "ai_picks"), "ai_picks")
    if cached:
        return {**cached, "from_cache": True}

    # Cache miss — build live
    history, reddit_posts = await asyncio.gather(
        _gather_history(pid),
        reddit.get_trending_posts(limit_per_sub=6),
    )
    if not history:
        raise HTTPException(503, "No watch history found")

    watched_ids = [(h["tmdb_id"], h["media_type"]) for h in history if h.get("tmdb_id")]

    async def fetch_recs(tmdb_id, media_type):
        try:
            return await tmdb.get_recommendations(tmdb_id, media_type), media_type
        except Exception:
            return [], media_type

    rec_results = await asyncio.gather(*[fetch_recs(tid, mt) for tid, mt in watched_ids[:8]])
    seen_ids = {tid for tid, _ in watched_ids}
    candidates: dict[int, dict] = {}
    for results, media_type in rec_results:
        for item in results:
            item_id = item.get("id")
            if not item_id or item_id in seen_ids or item_id in candidates:
                continue
            candidates[item_id] = {**item, "media_type": media_type,
                                   "poster_url": tmdb.poster_url(item.get("poster_path"))}

    try:
        show_ratings, movie_ratings = await asyncio.gather(
            trakt.get_ratings("shows"), trakt.get_ratings("movies")
        )
        ratings = {
            (e.get("show") or e.get("movie") or {}).get("ids", {}).get("tmdb"): e.get("rating")
            for e in show_ratings + movie_ratings
        }
    except Exception:
        ratings = {}

    enriched_history = [{**h, "rating": ratings.get(h.get("tmdb_id"))} for h in history[:40]]

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        ai_result = await loop.run_in_executor(
            pool,
            lambda: get_ai_recommendations(enriched_history, reddit_posts, list(candidates.values())),
        )

    picks = []
    for pick in ai_result.get("picks", []):
        candidate = candidates.get(pick["tmdb_id"], {})
        picks.append({
            **candidate,
            "id": pick["tmdb_id"],
            "title": pick.get("title") or candidate.get("title") or candidate.get("name"),
            "reason": pick.get("reason"),
            "reddit_buzz": pick.get("reddit_buzz"),
            "media_type": pick.get("media_type") or candidate.get("media_type", "tv"),
            "poster_url": candidate.get("poster_url"),
            "vote_average": candidate.get("vote_average", 0),
            "overview": candidate.get("overview", ""),
        })

    result = {
        "taste_profile": ai_result.get("taste_profile"),
        "picks": picks,
        "reddit_posts_used": len(reddit_posts),
        "candidates_analysed": len(candidates),
    }
    await database.cache_set(pkey(pid, "ai_picks"), result)
    return {**result, "from_cache": False}


@router.post("/custom")
async def get_custom_recs(req: CustomRequest, pid: int = Depends(get_profile_id)):
    if not settings.anthropic_api_key or settings.anthropic_api_key == "your_anthropic_api_key_here":
        raise HTTPException(503, "Anthropic API key not configured")

    if not req.prompt and not req.genres and req.media_type == "any":
        raise HTTPException(400, "Provide at least a prompt, genres, or media type")

    history, reddit_posts = await asyncio.gather(
        _gather_history(pid),
        reddit.get_trending_posts(limit_per_sub=4),
    )

    tmdb_type = None if req.media_type == "any" else ("tv" if req.media_type == "tv" else "movie")
    candidates: dict[int, dict] = {}

    if req.prompt:
        try:
            results = await tmdb.search(req.prompt, tmdb_type or "multi")
            for item in results[:5]:
                item_id = item.get("id")
                mt = tmdb_type or item.get("media_type", "tv")
                if item_id and mt in ("tv", "movie"):
                    for r in (await tmdb.get_recommendations(item_id, mt))[:8]:
                        rid = r.get("id")
                        if rid and rid not in candidates:
                            candidates[rid] = {**r, "media_type": mt,
                                              "poster_url": tmdb.poster_url(r.get("poster_path"))}
                    for r in (await tmdb.get_similar(item_id, mt))[:8]:
                        rid = r.get("id")
                        if rid and rid not in candidates:
                            candidates[rid] = {**r, "media_type": mt,
                                              "poster_url": tmdb.poster_url(r.get("poster_path"))}
        except Exception:
            pass

    watched_ids = [(h["tmdb_id"], h["media_type"]) for h in history if h.get("tmdb_id")]
    if tmdb_type:
        watched_ids = [(tid, mt) for tid, mt in watched_ids if mt == tmdb_type]

    async def fetch_recs(tmdb_id, media_type):
        try:
            return await tmdb.get_recommendations(tmdb_id, media_type), media_type
        except Exception:
            return [], media_type

    seen_ids = {tid for tid, _ in watched_ids}
    rec_results = await asyncio.gather(*[fetch_recs(tid, mt) for tid, mt in watched_ids[:6]])
    for results, media_type in rec_results:
        for item in results:
            item_id = item.get("id")
            if not item_id or item_id in seen_ids or item_id in candidates:
                continue
            if tmdb_type and media_type != tmdb_type:
                continue
            candidates[item_id] = {**item, "media_type": media_type,
                                   "poster_url": tmdb.poster_url(item.get("poster_path"))}

    if not candidates:
        raise HTTPException(404, "No candidates found — try a different prompt")

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        ai_result = await loop.run_in_executor(
            pool,
            lambda: get_custom_recommendations(
                history[:30], reddit_posts, list(candidates.values()),
                req.media_type, req.genres, req.prompt
            ),
        )

    picks = []
    for pick in ai_result.get("picks", []):
        candidate = candidates.get(pick["tmdb_id"], {})
        picks.append({
            **candidate,
            "id": pick["tmdb_id"],
            "title": pick.get("title") or candidate.get("title") or candidate.get("name"),
            "reason": pick.get("reason"),
            "reddit_buzz": pick.get("reddit_buzz"),
            "media_type": pick.get("media_type") or candidate.get("media_type", "tv"),
            "poster_url": candidate.get("poster_url"),
            "vote_average": candidate.get("vote_average", 0),
            "overview": candidate.get("overview", ""),
        })

    return {"picks": picks, "query_summary": ai_result.get("query_summary")}
