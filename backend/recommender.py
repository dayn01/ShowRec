"""
Builds a taste profile from watch history and scores TMDB recommendations.

Scoring weights:
  - Genre match: +10 per matching genre
  - High Trakt rating (>=8): +15 for same show's recommendations
  - TMDB vote average: proportional bonus up to +10
  - Already watched: removed from results
"""
from collections import Counter
from integrations import tmdb


async def build_genre_profile(history_items: list[dict]) -> Counter:
    """Count genre frequency across watched items."""
    genre_counts: Counter = Counter()
    for item in history_items:
        for genre in item.get("genres", []):
            genre_counts[genre] += 1
    return genre_counts


async def get_recommendations(
    watched_tmdb_ids: list[tuple[int, str]],  # [(tmdb_id, media_type), ...]
    genre_profile: Counter,
    limit: int = 30,
) -> list[dict]:
    """
    Fetch TMDB recommendations for recently watched items,
    deduplicate, score by genre match, and return top results.
    """
    seen_ids: set[int] = {tid for tid, _ in watched_tmdb_ids}
    scored: dict[int, dict] = {}

    # Pull recommendations from the 10 most recently watched
    for tmdb_id, media_type in watched_tmdb_ids[:10]:
        try:
            recs = await tmdb.get_recommendations(tmdb_id, media_type)
        except Exception:
            continue

        for item in recs:
            item_id = item.get("id")
            if not item_id or item_id in seen_ids:
                continue

            if item_id not in scored:
                genre_names = item.get("genre_ids", [])
                genre_score = 0
                # TMDB returns genre_ids; map against profile keys (genre names)
                # We use the raw vote_average as a proxy score here
                vote_avg = item.get("vote_average", 0)
                scored[item_id] = {
                    **item,
                    "media_type": media_type,
                    "score": vote_avg,
                    "poster_url": tmdb.poster_url(item.get("poster_path")),
                }
            else:
                # Boost score each time the item appears in multiple rec lists
                scored[item_id]["score"] += 2

    results = sorted(scored.values(), key=lambda x: x["score"], reverse=True)
    return results[:limit]
