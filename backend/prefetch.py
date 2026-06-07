"""
Background data pipeline — fetches everything and stores in SQLite.
Runs on startup and every 6 hours via the scheduler.
"""
import asyncio
import concurrent.futures
import logging
import database
from integrations import trakt, tmdb, reddit, jellyfin, tastedive
from integrations.claude import get_ai_recommendations
from routers.recommendations import _gather_history
from routers.details import _fetch_and_cache_show, _fetch_and_cache_season, _resolve_tastedive_item
from config import settings

logger = logging.getLogger(__name__)


# TMDB genre id → name (movie + TV), used to build a genre affinity profile.
GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy", 80: "Crime",
    99: "Documentary", 18: "Drama", 10751: "Family", 14: "Fantasy", 36: "History",
    27: "Horror", 10402: "Music", 9648: "Mystery", 10749: "Romance", 878: "Sci-Fi",
    10770: "TV Movie", 53: "Thriller", 10752: "War", 37: "Western",
    10759: "Action & Adventure", 10762: "Kids", 10763: "News", 10764: "Reality",
    10765: "Sci-Fi & Fantasy", 10766: "Soap", 10767: "Talk", 10768: "War & Politics",
}


async def _build_genre_affinity(watched: list[dict]) -> "Counter":
    """Back-compat shim — returns just the genre Counter."""
    profile = await _build_taste_profile(watched)
    return profile["genres"]


async def _build_taste_profile(watched: list[dict]) -> dict:
    """
    Build a taste profile from watched titles' cached details:
      - genres   (name → weight)
      - keywords (id → weight)   themes/tropes
      - people   (id → weight)   recurring cast
    Fetches+caches details for up to 40 uncached titles (also warms the cache).
    """
    from collections import Counter
    from routers.details import _fetch_and_cache_show
    genres: Counter = Counter()
    keywords: Counter = Counter()
    people: Counter = Counter()

    def absorb(data: dict):
        for g in data.get("genres", []):
            genres[g] += 1
        for k in data.get("keyword_ids", []):
            keywords[k] += 1
        for p in data.get("cast_ids", []):
            people[p] += 1

    uncached: list[dict] = []
    for h in watched:
        cached = await database.get_show(h["tmdb_id"])
        if cached and cached.get("genres"):
            absorb(cached)
        else:
            uncached.append(h)

    async def fetch(h):
        try:
            return await _fetch_and_cache_show(h["tmdb_id"], h["media_type"])
        except Exception:
            return None

    for data in await asyncio.gather(*[fetch(h) for h in uncached[:40]]):
        if data:
            absorb(data)

    return {"genres": genres, "keywords": keywords, "people": people}


async def _tastedive_candidates(history: list[dict], sample_per_type: int = 6,
                                per_title: int = 8, max_resolve: int = 60) -> list[dict]:
    """
    TasteDive 'people who like X also like…' candidates for the recommender.
    Samples recently-watched titles, asks TasteDive for similar titles, then
    resolves the suggested names back to TMDB items. Returns [] without a key.
    """
    if not tastedive.enabled():
        return []

    titled = [h for h in history if h.get("title")]
    tv = [h for h in titled if h.get("media_type") == "tv"][:sample_per_type]
    movie = [h for h in titled if h.get("media_type") == "movie"][:sample_per_type]

    async def fetch(h):
        try:
            return await tastedive.get_similar(h["title"], h["media_type"], limit=per_title)
        except Exception:
            return []

    suggestion_lists = await asyncio.gather(*[fetch(h) for h in tv + movie])

    # Dedup suggestions by (name, type) so we don't resolve the same title twice.
    uniq: dict[tuple, dict] = {}
    for lst in suggestion_lists:
        for s in lst:
            name = s.get("name")
            key = (name.lower() if name else "", s.get("type"))
            if name and key not in uniq:
                uniq[key] = s

    suggestions = list(uniq.values())[:max_resolve]
    resolved = await asyncio.gather(*[_resolve_tastedive_item(s, 0) for s in suggestions])
    return [r for r in resolved if r]


async def _returning_shows(profile_id: int, dismissed: set[int]) -> list[dict]:
    """
    Watched TV shows that have a NEW season available — i.e. the show's next
    episode to air is in a season beyond the highest one this profile has
    watched. These resurface at the top of For You (flagged new_season) even
    though they're "watched", because there's genuinely new content. Dismissed
    ("not interested") shows are excluded.
    """
    max_season = await database.max_watched_season_by_show(profile_id)
    out: list[dict] = []
    for tmdb_id, watched_max in max_season.items():
        if tmdb_id in dismissed:
            continue
        # Reuse the cached next_episode_to_air (the Upcoming build populates it)
        # to avoid a TMDB call per watched show on every rebuild.
        show = await database.get_show(tmdb_id)
        if show and "next_episode_to_air" in show:
            next_ep = show.get("next_episode_to_air")
            info_title = show.get("title") or show.get("name")
        else:
            try:
                info = await tmdb.get_upcoming_episodes_for_show(tmdb_id)
            except Exception:
                continue
            next_ep = (info or {}).get("next_episode")
            info_title = (info or {}).get("show_title")
        if not next_ep or not next_ep.get("air_date"):
            continue
        next_season = next_ep.get("season_number") or 0
        # Only when the upcoming episode is in a season you haven't watched.
        if next_season <= (watched_max or 0):
            continue
        if not show:
            show = await _fetch_and_cache_show(tmdb_id, "tv")
        if not show:
            continue
        out.append({
            "id": tmdb_id,
            "title": show.get("title") or show.get("name") or info_title or "",
            "name": show.get("name"),
            "overview": show.get("overview", ""),
            "poster_url": show.get("poster_url"),
            "vote_average": show.get("vote_average", 0) or 0,
            "media_type": "tv",
            "genre_ids": show.get("genre_ids", []),
            "first_air_date": show.get("first_air_date", ""),
            "score": 9999,                       # pin to the top of For You
            "base_score": 9999,                  # survive genre re-weighting on read
            "genre_component": 0,
            "new_season": True,
            "reason": f"New season {next_season} — premieres {next_ep['air_date']}",
        })
    return out


async def _build_recommendations(history: list[dict], profile_id: int = 1) -> dict | None:
    from collections import Counter
    # "Not interested" titles shouldn't shape the taste profile or seed similar
    # picks (TMDB recs / TasteDive), so drop them from the history first.
    dismissed = set(await database.get_dismissed_ids(profile_id))
    history = [h for h in history if h.get("tmdb_id") not in dismissed]
    watched_ids = [(h["tmdb_id"], h["media_type"]) for h in history if h.get("tmdb_id")]
    if not watched_ids:
        return None

    seen_ids = {tid for tid, _ in watched_ids}
    seen_ids |= dismissed  # also exclude them from the candidate results

    # This profile's own Trakt token (global owner token only for the default
    # profile) — mirrors sync_watch_state so profiles don't share recommendations.
    profile = await database.get_profile(profile_id)
    trakt_token = (profile.get("trakt_token") if profile else None) or (
        settings.trakt_access_token if profile_id == 1 else None)

    taste = await _build_taste_profile(history)
    genre_affinity = taste["genres"]
    max_genre = max(genre_affinity.values()) if genre_affinity else 1
    top_keywords = [k for k, _ in taste["keywords"].most_common(8)]
    top_people = [p for p, _ in taste["people"].most_common(6)]

    # Sample up to 25 watched items spread across the whole history (most-recent
    # first, but not ONLY recent) so picks reflect long-term taste.
    # Sample BOTH media types independently so neither TV nor movies is starved
    # when recent watches happen to be all one type.
    tv_watched = [(tid, mt) for tid, mt in watched_ids if mt == "tv"]
    movie_watched = [(tid, mt) for tid, mt in watched_ids if mt == "movie"]

    def _sample(lst):
        return (lst[:12] + lst[12::3])[:20]

    # (tmdb_id, media_type, rank_within_type) — rank used for recency weighting
    sample = (
        [(tid, mt, i) for i, (tid, mt) in enumerate(_sample(tv_watched))]
        + [(tid, mt, i) for i, (tid, mt) in enumerate(_sample(movie_watched))]
    )

    async def fetch_recs(tmdb_id, media_type, recency_rank):
        try:
            recs = await tmdb.get_recommendations(tmdb_id, media_type)
            return recs, media_type, recency_rank
        except Exception:
            return [], media_type, recency_rank

    rec_results = await asyncio.gather(
        *[fetch_recs(tid, mt, rank) for tid, mt, rank in sample]
    )

    scored: dict[int, dict] = {}
    for results, media_type, recency_rank in rec_results:
        # Recommendations sourced from more recently watched items weigh more
        recency_weight = 1.0 if recency_rank < 15 else 0.6
        for item in results:
            item_id = item.get("id")
            if not item_id or item_id in seen_ids:
                continue

            if item_id not in scored:
                # Quality component: vote_average 0–10 → 0–10
                quality = item.get("vote_average", 0) or 0
                # Genre match component
                genre_score = 0
                for gid in item.get("genre_ids", []):
                    name = GENRE_MAP.get(gid)
                    if name and name in genre_affinity:
                        genre_score += (genre_affinity[name] / max_genre) * 5  # up to ~5 per genre
                scored[item_id] = {
                    **item,
                    "media_type": media_type,
                    "poster_url": tmdb.poster_url(item.get("poster_path")),
                    "_quality": quality,
                    "_genre": genre_score,
                    "_freq": recency_weight,        # accumulates how often it's recommended
                    "_trakt": 0,
                }
            else:
                scored[item_id]["_freq"] += recency_weight

    # Blend in THIS profile's own Trakt recommendations (only if it's linked).
    if trakt_token:
        for media_type, tmdb_type in (("shows", "tv"), ("movies", "movie")):
            try:
                personal = await trakt.get_personal_recommendations(media_type, limit=30, token=trakt_token)
            except Exception:
                personal = []
            for entry in personal:
                tid = entry.get("ids", {}).get("tmdb")
                if not tid or tid in seen_ids:
                    continue
                if tid in scored:
                    scored[tid]["_trakt"] = 8       # strong endorsement
                else:
                    scored[tid] = {
                        "id": tid,
                        "title": entry.get("title"),
                        "name": entry.get("title"),
                        "overview": entry.get("overview", ""),
                        "vote_average": (entry.get("rating") or 0),
                        "media_type": tmdb_type,
                        "poster_url": None,
                        "genre_ids": [],
                        "_quality": entry.get("rating") or 0,
                        "_genre": 0,
                        "_freq": 0,
                        "_trakt": 8,
                    }

    # ── Taste-based discovery: surface titles by the THEMES and PEOPLE you watch
    #    most, not just "similar to specific shows". These broaden personalization.
    top_genre_ids = []
    name_to_id = {v: k for k, v in GENRE_MAP.items()}
    for gname, _ in genre_affinity.most_common(3):
        if gname in name_to_id:
            top_genre_ids.append(name_to_id[gname])

    async def discover_into(media_type, **kwargs):
        try:
            return await tmdb.discover(media_type, pages=1, **kwargs)
        except Exception:
            return []

    discover_tasks = []
    for mt in ("tv", "movie"):
        if top_keywords:
            discover_tasks.append((mt, "keyword", discover_into(mt, keywords=top_keywords, genres=top_genre_ids)))
        if top_people:
            discover_tasks.append((mt, "people", discover_into(mt, people=top_people)))

    for mt, kind, task in discover_tasks:
        for item in await task:
            iid = item.get("id")
            if not iid or iid in seen_ids:
                continue
            taste_boost = 6 if kind == "people" else 4   # "more from actors you love" ranks high
            if iid in scored:
                scored[iid]["_taste"] = max(scored[iid].get("_taste", 0), taste_boost)
            else:
                scored[iid] = {
                    **item,
                    "media_type": mt,
                    "poster_url": tmdb.poster_url(item.get("poster_path")),
                    "_quality": item.get("vote_average", 0) or 0,
                    "_genre": 0, "_freq": 0, "_trakt": 0, "_taste": taste_boost,
                }

    # ── TasteDive: "people who like what you watch also like…" (if a key is set).
    #    A curated similarity signal that complements TMDB's own recommendations.
    for item in await _tastedive_candidates(history):
        iid = item.get("id")
        if not iid or iid in seen_ids:
            continue
        if iid in scored:
            scored[iid]["_tastedive"] = scored[iid].get("_tastedive", 0) + 3
        else:
            genre_score = 0
            for gid in item.get("genre_ids", []):
                name = GENRE_MAP.get(gid)
                if name and name in genre_affinity:
                    genre_score += (genre_affinity[name] / max_genre) * 5
            scored[iid] = {
                **item,
                "_quality": item.get("vote_average", 0) or 0,
                "_genre": genre_score,
                "_freq": 0, "_trakt": 0, "_taste": 0, "_tastedive": 3,
            }

    # Final weighted score. We split it into a genre-affinity component and the
    # rest ("base"), and persist both so the recommendations API can re-weight on
    # read from each profile's tuning (genre slider + per-genre multipliers).
    for item in scored.values():
        genre_component = item["_genre"]
        base = (
            item["_freq"] * 3.0          # how often recommended across your library
            + item.get("_taste", 0)      # theme/actor taste match (discover)
            + item.get("_tastedive", 0)  # TasteDive 'also like' similarity
            + item["_quality"] * 0.8     # overall quality
            + item["_trakt"]             # Trakt personal endorsement
        )
        item["base_score"] = round(base, 2)
        item["genre_component"] = round(genre_component, 2)
        item["score"] = round(base + genre_component, 2)

    # Keep up to 100 of each media type so the For You TV/Movies filters both have
    # plenty (and Load More has depth), then merge into one score-ranked list.
    ranked = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
    tv_items = [i for i in ranked if i.get("media_type") == "tv"][:100]
    movie_items = [i for i in ranked if i.get("media_type") == "movie"][:100]
    results_sorted = sorted(tv_items + movie_items, key=lambda x: x["score"], reverse=True)

    # Backfill posters/genres for items that arrived without them (Trakt-only
    # picks). Mostly cache hits; only genuinely-new titles hit TMDB.
    async def _backfill(item):
        try:
            show = await database.get_show(item["id"]) \
                or await _fetch_and_cache_show(item["id"], item.get("media_type", "tv"))
        except Exception:
            return
        if not show:
            return
        item["poster_url"] = show.get("poster_url")
        if not item.get("genre_ids"):
            item["genre_ids"] = show.get("genre_ids", [])
        if not item.get("overview"):
            item["overview"] = show.get("overview", "")
        if not item.get("vote_average"):
            item["vote_average"] = show.get("vote_average", 0)

    await asyncio.gather(*[_backfill(i) for i in results_sorted if not i.get("poster_url")])

    # Strip internal scoring fields before caching
    for item in results_sorted:
        for k in ("_quality", "_genre", "_freq", "_trakt", "_taste", "_tastedive"):
            item.pop(k, None)

    # Resurface watched shows that have a brand-new season available (not
    # dismissed). They're excluded from the candidate pool above (already
    # watched), so we add them explicitly at the front.
    returning = await _returning_shows(profile_id, dismissed)
    if returning:
        present = {i["id"] for i in results_sorted}
        results_sorted = [r for r in returning if r["id"] not in present] + results_sorted

    top_genres = [g for g, _ in genre_affinity.most_common(5)]
    return {
        "recommendations": results_sorted,
        "based_on": len(watched_ids),
        "top_genres": top_genres,
        "genre_affinity": dict(genre_affinity),   # name -> weight, for search ranking
        "trakt_blended": bool(trakt_token),
        "tastedive_blended": tastedive.enabled(),
    }


async def _build_trending(media_type: str, pages: int = 6) -> dict | None:
    """
    Build a large trending list (~120 items) from TMDB so Load More has plenty.
    TMDB items already carry full metadata, so no per-item enrichment is needed.
    Works without Trakt.
    """
    tmdb_type = "tv" if media_type == "shows" else "movie"

    # Primary: TMDB trending; supplement with popular for more depth
    trending, popular = await asyncio.gather(
        tmdb.get_trending(tmdb_type, pages=pages),
        tmdb.get_popular(tmdb_type, pages=3),
    )

    # Trending is global; per-profile dismissals are filtered client-side.
    seen: set[int] = set()
    out = []
    for item in trending + popular:
        tid = item.get("id")
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append({
            "id": tid,
            "title": item.get("title") or item.get("name"),
            "overview": item.get("overview", ""),
            "poster_url": tmdb.poster_url(item.get("poster_path")),
            "vote_average": item.get("vote_average", 0),
            "media_type": tmdb_type,
            "genre_ids": item.get("genre_ids", []),
            "release_date": item.get("release_date"),
            "first_air_date": item.get("first_air_date"),
            "popularity": item.get("popularity", 0),
        })

    return {"trending": out} if out else None


async def _build_upcoming(history: list[dict], profile_id: int = 1) -> dict | None:
    episodes = []

    # Source 1: Trakt personal calendar
    try:
        calendar = await trakt.get_calendar_shows(days=60)
        for entry in calendar:
            ep = entry.get("episode", {})
            show = entry.get("show", {})
            episodes.append({
                "source": "trakt",
                "first_aired": entry.get("first_aired", ""),
                "show": show,
                "episode": ep,
            })
    except Exception as e:
        logger.warning(f"Trakt calendar failed: {e}")

    # Source 2: TMDB next_episode_to_air for every watched show in the local DB.
    # This works without Trakt — the DB is seeded from Jellyfin/Plex/Trakt.
    watch_state = await database.get_watch_state(profile_id)
    # Any tmdb_id that has watched episodes is a "show"
    show_ids = {ep["tmdb_id"] for ep in watch_state.get("episodes", [])}
    # Plus any tv items from the recommendation history
    show_ids |= {h["tmdb_id"] for h in history if h.get("tmdb_id") and h.get("media_type") == "tv"}
    tv_ids = list(show_ids)

    trakt_show_tmdb_ids = {
        e["show"].get("ids", {}).get("tmdb")
        for e in episodes
        if e.get("show", {}).get("ids", {}).get("tmdb")
    }

    async def check_tmdb(tmdb_id):
        try:
            next_ep = None
            title = ""

            # Check SQLite — but only trust it if next_episode_to_air was stored
            cached = await database.get_show(tmdb_id)
            if cached and "next_episode_to_air" in cached:
                next_ep = cached.get("next_episode_to_air")
                title = cached.get("title") or cached.get("name", "")
            else:
                # Fetch fresh from TMDB and update the cache
                data = await tmdb.get_upcoming_episodes_for_show(tmdb_id)
                if not data:
                    return
                next_ep = data.get("next_episode")
                title = data.get("show_title", "")
                # Re-cache the show with next_episode_to_air included
                if cached:
                    cached["next_episode_to_air"] = next_ep
                    await database.set_show(tmdb_id, "tv", cached)

            if not next_ep or not next_ep.get("air_date"):
                return
            # Skip if already covered by Trakt (match by TMDB ID, not title)
            if tmdb_id in trakt_show_tmdb_ids:
                return

            episodes.append({
                "source": "tmdb",
                "first_aired": next_ep["air_date"] + "T00:00:00.000Z",
                "show": {"title": title, "ids": {"tmdb": tmdb_id}},
                "episode": {
                    "title": next_ep.get("name", ""),
                    "season": next_ep.get("season_number"),
                    "number": next_ep.get("episode_number"),
                    "overview": next_ep.get("overview", ""),
                },
            })
        except Exception:
            pass

    await asyncio.gather(*[check_tmdb(tid) for tid in tv_ids[:60]])

    # Sort by air date
    episodes.sort(key=lambda e: e.get("first_aired", ""))
    return {"episodes": episodes, "days": 60}


async def _build_ai_picks(history: list[dict], reddit_posts: list[dict], candidates: dict) -> dict | None:
    if not settings.anthropic_api_key or settings.anthropic_api_key == "your_anthropic_api_key_here":
        return None
    try:
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            ai_result = await loop.run_in_executor(
                pool,
                lambda: get_ai_recommendations(history[:40], reddit_posts, list(candidates.values())),
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

        return {
            "taste_profile": ai_result.get("taste_profile"),
            "picks": picks,
            "reddit_posts_used": len(reddit_posts),
            "candidates_analysed": len(candidates),
        }
    except Exception as e:
        logger.error(f"AI picks failed: {e}")
        return None


async def _cache_show_seasons(tmdb_id: int, all_seasons: bool = True):
    """
    Cache a show's details and its seasons/episodes.
    all_seasons=True  → cache every season (used for watched shows)
    all_seasons=False → cache only the latest aired season (used for recommended/trending)
    """
    try:
        cached = await database.get_show(tmdb_id)
        if not cached:
            cached = await _fetch_and_cache_show(tmdb_id, "tv")

        seasons = cached.get("seasons", [])
        if not seasons:
            return

        if all_seasons:
            targets = seasons
        else:
            # Just the most recently aired season
            today = __import__("datetime").date.today().isoformat()
            aired = [s for s in seasons if not s.get("air_date") or s["air_date"] <= today]
            targets = [aired[-1]] if aired else [seasons[-1]]

        for s in targets:
            sn = s["season_number"]
            if not await database.get_season(tmdb_id, sn):
                try:
                    await _fetch_and_cache_season(tmdb_id, sn)
                    await asyncio.sleep(0.15)  # gentle on TMDB rate limits
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Failed to cache show {tmdb_id}: {e}")


async def _warm_watched_cache(profile_id: int):
    """
    Cache show/movie DETAILS (incl. posters + season episode counts) for
    everything this profile has watched, so the Watched and Watching pages serve
    from the local cache instead of fetching hundreds of items from TMDB on page
    load. Only the record is fetched (not each season's episodes — the heavy
    part), and already-cached items are skipped, so it's cheap once warm. The
    Netflix importer doesn't populate this cache, which is why a freshly-imported
    library loads slowly (or empty) the first time.
    """
    items = await database.get_watched_for_recommendations(profile_id)
    have = await database.cached_show_ids()
    missing = [
        (i["tmdb_id"], "tv" if i["media_type"] == "tv" else "movie")
        for i in items if i.get("tmdb_id") and i["tmdb_id"] not in have
    ][:800]
    if not missing:
        return
    logger.info(f"Warm[p{profile_id}]: caching details for {len(missing)} watched titles")
    sem = asyncio.Semaphore(6)

    async def warm(tmdb_id, media_type):
        async with sem:
            try:
                await _fetch_and_cache_show(tmdb_id, media_type)
            except Exception:
                pass

    await asyncio.gather(*[warm(t, mt) for t, mt in missing])
    logger.info(f"Warm[p{profile_id}]: watched-detail cache warmed")


async def _cache_watched_shows(history: list[dict]):
    """Cache all seasons + episodes for every watched TV show."""
    tv_ids = list({h["tmdb_id"] for h in history if h.get("tmdb_id") and h.get("media_type") == "tv"})
    logger.info(f"Caching all seasons for {len(tv_ids)} watched shows...")
    for tmdb_id in tv_ids[:50]:
        await _cache_show_seasons(tmdb_id, all_seasons=True)


async def _cache_recommended_shows(recs: dict | None, trending_shows: dict | None, trending_movies: dict | None):
    """Cache the latest season for recommended and trending TV shows."""
    tv_ids: set[int] = set()

    if recs:
        for item in recs.get("recommendations", []):
            if item.get("media_type") == "tv" and item.get("id"):
                tv_ids.add(item["id"])

    if trending_shows:
        for item in trending_shows.get("trending", []):
            if item.get("id"):
                tv_ids.add(item["id"])

    if tv_ids:
        logger.info(f"Caching latest season for {len(tv_ids)} recommended/trending shows...")
        for tmdb_id in list(tv_ids)[:30]:
            await _cache_show_seasons(tmdb_id, all_seasons=False)


async def sync_watch_state(profile: dict):
    """
    Seed a profile's watch_state from its linked accounts.
    Jellyfin uses the profile's jellyfin_user_id. Plex/global-Trakt apply to the
    default profile (id 1). A profile's own trakt_token is used if present.
    Additive only (INSERT OR IGNORE) so user marks/unmarks are preserved.
    """
    pid = profile["id"]
    jf_user = profile.get("jellyfin_user_id")
    is_default = pid == 1
    rows: list[tuple] = []

    # Jellyfin — per-episode watched, scoped to this profile's own linked user.
    # No global fallback: a profile only ever syncs the account explicitly linked
    # to it (the wizard / profile editor sets this), never the main/admin account.
    # We REPLACE this profile's Jellyfin rows rather than add to them, so changing
    # or unlinking the account doesn't leave the old account's data behind.
    if settings.jellyfin_url and jf_user:
        try:
            jf_rows: list[tuple] = []
            eps = await jellyfin.get_watched_episodes(jf_user)
            for e in eps:
                jf_rows.append(("episode", e["tmdb_id"], e["season"], e["episode"],
                                e.get("series_name", "")))
            movies = await jellyfin.get_watched_movies(jf_user)
            for m in movies:
                jf_rows.append(("movie", m["tmdb_id"], -1, -1, m.get("title", "")))
            await database.replace_watched_source(pid, "jellyfin", jf_rows)
            logger.info(f"Sync[p{pid}]: Jellyfin gave {len(eps)} eps, {len(movies)} movies")
        except Exception as e:
            # Transient failure — keep existing rows rather than wiping to empty.
            logger.warning(f"Sync[p{pid}]: Jellyfin failed (keeping existing): {e}")
    else:
        # Profile isn't linked to Jellyfin — clear any stale Jellyfin rows.
        await database.replace_watched_source(pid, "jellyfin", [])

    # Plex — per-profile token if linked, else global token for the default profile
    plex_token = profile.get("plex_token") or (settings.plex_token if is_default else None)
    if settings.plex_url and plex_token:
        try:
            from integrations import plex
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                plex_eps, plex_movies = await asyncio.gather(
                    loop.run_in_executor(pool, plex.get_watched_episodes, plex_token),
                    loop.run_in_executor(pool, plex.get_watched_movies, plex_token),
                )
            for e in plex_eps:
                rows.append(("episode", e["tmdb_id"], e["season"], e["episode"], e.get("series_name", ""), "plex"))
            for m in plex_movies:
                rows.append(("movie", m["tmdb_id"], -1, -1, m.get("title", ""), "plex"))
            logger.info(f"Sync[p{pid}]: Plex gave {len(plex_eps)} eps, {len(plex_movies)} movies")
        except Exception as e:
            logger.warning(f"Sync[p{pid}]: Plex failed: {e}")

    # Trakt — profile's own token, or global token for the default profile
    trakt_token = profile.get("trakt_token") or (settings.trakt_access_token if is_default else None)
    if trakt_token:
        try:
            import httpx
            headers = {
                "Content-Type": "application/json", "trakt-api-version": "2",
                "trakt-api-key": settings.trakt_client_id,
                "Authorization": f"Bearer {trakt_token}",
            }
            async with httpx.AsyncClient(timeout=30) as client:
                wr = await client.get("https://api.trakt.tv/users/me/watched/shows", headers=headers)
                mr = await client.get("https://api.trakt.tv/users/me/watched/movies", headers=headers)
            for entry in (wr.json() if wr.status_code == 200 else []):
                tmdb_id = entry.get("show", {}).get("ids", {}).get("tmdb")
                title = entry.get("show", {}).get("title", "")
                if not tmdb_id:
                    continue
                for season in entry.get("seasons", []):
                    sn = season.get("number")
                    for ep in season.get("episodes", []):
                        if ep.get("plays", 0) > 0:
                            rows.append(("episode", tmdb_id, sn, ep.get("number"), title, "trakt"))
            for entry in (mr.json() if mr.status_code == 200 else []):
                tmdb_id = entry.get("movie", {}).get("ids", {}).get("tmdb")
                if tmdb_id:
                    rows.append(("movie", tmdb_id, -1, -1, entry.get("movie", {}).get("title", ""), "trakt"))
        except Exception as e:
            logger.warning(f"Sync[p{pid}]: Trakt failed: {e}")

    if rows:
        await database.sync_watched_bulk(pid, rows)
        stats = await database.get_watch_state_stats(pid)
        logger.info(f"Sync[p{pid}]: watch_state seeded — {stats}")


async def refresh_profile(profile_id: int):
    """Rebuild one profile's watch state + per-profile caches."""
    profile = await database.get_profile(profile_id)
    if not profile:
        return
    logger.info(f"=== Prefetch[p{profile_id}] '{profile['name']}' ===")

    await sync_watch_state(profile)

    # Warm the Watched/Watching pages' detail cache in the background so they
    # load from cache instead of fetching hundreds of titles from TMDB on open.
    asyncio.create_task(_warm_watched_cache(profile_id))

    history, reddit_posts = await asyncio.gather(
        _gather_history(profile_id),
        reddit.get_trending_posts(limit_per_sub=6),
    )
    if not history:
        # Clear any stale per-profile caches so an unlinked/empty profile shows nothing
        empty = {"recommendations": [], "based_on": 0, "top_genres": []}
        await database.cache_set(_pk(profile_id, "recommendations"), empty)
        await database.cache_set(_pk(profile_id, "ai_picks"), {"picks": [], "taste_profile": ""})
        await database.cache_set(_pk(profile_id, "upcoming"), {"episodes": []})
        logger.info(f"Prefetch[p{profile_id}]: no history — cleared caches")
        return

    # Recommendations
    recs = await _build_recommendations(history, profile_id)
    if recs:
        await database.cache_set(_pk(profile_id, "recommendations"), recs)

    # Upcoming
    upcoming = await _build_upcoming(history, profile_id)
    if upcoming:
        await database.cache_set(_pk(profile_id, "upcoming"), upcoming)

    # Cache watched shows' seasons (global cache)
    await _cache_watched_shows(history)

    # AI picks (per profile)
    if settings.anthropic_api_key and settings.anthropic_api_key != "your_anthropic_api_key_here":
        watched_ids = [(h["tmdb_id"], h["media_type"]) for h in history if h.get("tmdb_id")]
        seen_ids = {tid for tid, _ in watched_ids}
        candidates: dict[int, dict] = {}
        if recs:
            for item in recs["recommendations"][:40]:
                iid = item.get("id")
                if iid and iid not in seen_ids:
                    candidates[iid] = item
        ai_picks = await _build_ai_picks(history, reddit_posts, candidates)
        if ai_picks:
            await database.cache_set(_pk(profile_id, "ai_picks"), ai_picks)
            if recs:
                ai_by_id = {p["id"]: p for p in ai_picks.get("picks", [])}
                for item in recs["recommendations"]:
                    pick = ai_by_id.get(item.get("id"))
                    if pick:
                        item["reason"] = pick.get("reason")
                        item["ai_endorsed"] = True
                        # Bump base_score too so the boost survives on-read re-ranking
                        item["base_score"] = (item.get("base_score", 0) or 0) + 10
                        item["score"] = (item.get("score", 0) or 0) + 10
                recs["recommendations"].sort(key=lambda x: x.get("score", 0), reverse=True)
                recs["ai_blended"] = True
                await database.cache_set(_pk(profile_id, "recommendations"), recs)

    logger.info(f"=== Prefetch[p{profile_id}] complete ===")


def _pk(profile_id: int, key: str) -> str:
    return f"p{profile_id}:{key}"


async def sync_all_watch_states():
    """
    Lightweight, frequent sync: pull each profile's watched state from its linked
    accounts (Jellyfin/Plex/Trakt) — no TMDB recommendation/AI rebuild. Keeps
    Watched/Watching/"seen" state fresh cheaply between full refreshes.
    Also caches seasons for any newly-watched shows so completeness is accurate.
    """
    logger.info("Light sync: refreshing watch state for all profiles...")
    for pid in await database.all_profile_ids():
        profile = await database.get_profile(pid)
        if not profile:
            continue
        try:
            await sync_watch_state(profile)
            # Cache seasons for any newly-watched shows (so 'seen' detection works)
            history = await _gather_history(pid)
            tv_ids = [h["tmdb_id"] for h in history
                      if h.get("tmdb_id") and h.get("media_type") == "tv"]
            for tmdb_id in tv_ids:
                cached = await database.get_show(tmdb_id)
                if not cached:
                    await _cache_show_seasons(tmdb_id, all_seasons=True)
                else:
                    # ensure each season is cached (cheap if already there)
                    for s in cached.get("seasons", []):
                        if not await database.get_season(tmdb_id, s["season_number"]):
                            await _cache_show_seasons(tmdb_id, all_seasons=True)
                            break
        except Exception as e:
            logger.warning(f"Light sync[p{pid}] failed: {e}")
    logger.info("Light sync: done")


async def refresh_all():
    """Build global trending once, then refresh every profile."""
    logger.info("=== Prefetch: full refresh ===")
    await database.purge_stale(older_than_days=30)

    # Trending is global (same for everyone)
    shows_trending, movies_trending = await asyncio.gather(
        _build_trending("shows"),
        _build_trending("movies"),
    )
    if shows_trending:
        await database.cache_set("trending_shows", shows_trending)
    if movies_trending:
        await database.cache_set("trending_movies", movies_trending)
    await _cache_recommended_shows(None, shows_trending, movies_trending)

    # Per-profile data
    for pid in await database.all_profile_ids():
        try:
            await refresh_profile(pid)
        except Exception as e:
            logger.error(f"Prefetch: profile {pid} failed: {e}")

    stats = await database.get_cache_stats()
    logger.info(f"=== Prefetch complete — {stats['shows']} shows, {stats['seasons']} seasons ===")
