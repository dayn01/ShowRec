"""Reddit integration — fetch trending TV/movie discussion for AI context."""
import httpx
from config import settings

SUBREDDITS = ["television", "movies", "trakt", "NetflixBestOf", "HBOMax", "appletv"]
USER_AGENT = "ShowRecApp/1.0"


async def _get_token() -> str | None:
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        return None
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            headers={"User-Agent": USER_AGENT},
        )
        if r.status_code == 200:
            return r.json().get("access_token")
    return None


async def get_trending_posts(limit_per_sub: int = 5) -> list[dict]:
    """
    Fetch hot posts from TV/movie subreddits (optional buzz for AI picks).
    Requires Reddit credentials — Reddit now blocks unauthenticated server
    requests, so we skip entirely if none are configured.
    """
    if not settings.reddit_client_id or settings.reddit_client_id == "your_reddit_client_id_here":
        return []

    posts = []
    token = await _get_token()
    # Credentials are configured (checked above) but the token fetch failed —
    # a transient blip at Reddit's token endpoint. Don't fall through to the
    # public endpoint, which Reddit blocks for servers; just skip this round.
    if not token:
        return []

    async with httpx.AsyncClient(timeout=10) as client:
        for sub in SUBREDDITS:
            try:
                r = await client.get(
                    f"https://oauth.reddit.com/r/{sub}/hot.json",
                    params={"limit": limit_per_sub},
                    headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
                )
                if r.status_code != 200:
                    continue
                for child in r.json()["data"]["children"]:
                    p = child["data"]
                    if p.get("stickied") or p.get("score", 0) < 100:
                        continue
                    posts.append({
                        "subreddit": sub,
                        "title": p.get("title", ""),
                        "score": p.get("score", 0),
                        "num_comments": p.get("num_comments", 0),
                        "url": f"https://reddit.com{p.get('permalink', '')}",
                        "selftext": (p.get("selftext", "") or "")[:500],
                    })
            except Exception:
                continue

    return sorted(posts, key=lambda x: x["score"], reverse=True)
