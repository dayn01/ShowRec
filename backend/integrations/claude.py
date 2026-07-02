"""Claude AI integration for personalised recommendations."""
import json
import anthropic
from config import settings


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def get_ai_recommendations(
    watch_history: list[dict],
    reddit_posts: list[dict],
    tmdb_candidates: list[dict],
) -> dict:
    """
    Ask Claude to pick and explain the best recommendations given:
    - The user's watch history (titles, genres, ratings)
    - Reddit discussion buzz
    - TMDB candidate titles to consider

    Returns a list of dicts: {tmdb_id, title, media_type, reason, buzz_summary, score}
    """
    client = _client()

    history_summary = "\n".join(
        f"- {h['title']} ({h.get('media_type','?')}) {('★' * int(h['rating']//2)) if h.get('rating') else ''}"
        for h in watch_history[:40]
    )

    reddit_summary = "\n".join(
        f"- [{p['subreddit']}] \"{p['title']}\" — {p['score']} upvotes, {p['num_comments']} comments"
        for p in reddit_posts[:20]
    )

    candidates_summary = "\n".join(
        f"- ID:{c['id']} | {c.get('title') or c.get('name')} ({c.get('media_type')}, {(c.get('release_date') or c.get('first_air_date') or '')[:4]}) score:{round(c.get('vote_average',0)*10)}% | {(c.get('overview',''))[:120]}"
        for c in tmdb_candidates[:100]
    )

    prompt = f"""You are a TV and film recommendation expert. Analyse the user's taste and suggest the best picks.

USER'S WATCH HISTORY (most recent first):
{history_summary}

TRENDING REDDIT DISCUSSIONS (r/television, r/movies etc):
{reddit_summary if reddit_summary else "No Reddit data available."}

CANDIDATE TITLES FROM TMDB (already filtered for quality):
{candidates_summary}

TASK:
1. Infer the user's taste profile from their history (genres, tone, themes they enjoy).
2. Cross-reference with Reddit buzz — are any candidates being discussed positively?
3. Select the 12 best recommendations from the candidates list.
4. For each, write a SHORT 1-sentence reason personalised to THIS user's taste.
5. Note any Reddit buzz if relevant.

Respond with ONLY valid JSON, no markdown, no explanation outside the JSON:
{{
  "taste_profile": "2-3 sentence summary of the user's taste",
  "picks": [
    {{
      "tmdb_id": 12345,
      "title": "Show Title",
      "media_type": "tv",
      "reason": "One sentence why this suits THIS user specifically",
      "reddit_buzz": "Optional: what Reddit is saying, or null"
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return _parse_json(message.content[0].text if message.content else "")


def _parse_json(text: str) -> dict:
    """
    Best-effort parse of the model's JSON reply. NEVER raises: if the response
    isn't valid JSON (prose around it, a truncated object from max_tokens, a
    stray fence), fall back to the outermost {...} span, and finally to an empty
    result — so the AI routes degrade to "no picks" instead of a 500.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        # strip a ```json … ``` fence
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (ValueError, TypeError):
                pass
    return {"picks": []}


def get_custom_recommendations(
    watch_history: list[dict],
    reddit_posts: list[dict],
    candidates: list[dict],
    media_type: str,
    genres: list[str],
    user_prompt: str,
) -> dict:
    client = _client()

    history_summary = "\n".join(
        f"- {h['title']} ({h.get('media_type','?')})"
        for h in watch_history[:30]
    )

    reddit_summary = "\n".join(
        f"- [{p['subreddit']}] \"{p['title']}\" — {p['score']} upvotes"
        for p in reddit_posts[:10]
    ) or "No Reddit data available."

    candidates_summary = "\n".join(
        f"- ID:{c['id']} | {c.get('title') or c.get('name')} ({c.get('media_type')}) score:{round(c.get('vote_average',0)*10)}% | {(c.get('overview',''))[:100]}"
        for c in candidates[:40]
    )

    filters = []
    if media_type != "any":
        filters.append(f"Media type: {media_type} only")
    if genres:
        filters.append(f"Genres: {', '.join(genres)}")
    if user_prompt:
        filters.append(f"User request: \"{user_prompt}\"")
    filter_str = "\n".join(filters) if filters else "No specific filters — general recommendations"

    prompt = f"""You are a TV and film recommendation expert helping a user find their next watch.

USER'S FILTERS:
{filter_str}

USER'S WATCH HISTORY (for personalisation context):
{history_summary}

TRENDING REDDIT DISCUSSIONS:
{reddit_summary}

CANDIDATE TITLES:
{candidates_summary}

TASK:
1. Select the 10 best candidates that match the user's filters and prompt.
2. Prioritise matching the user's specific request ("{user_prompt}") above all else.
3. Write a SHORT 1-sentence reason for each pick explaining WHY it matches their request.
4. Note any Reddit buzz if relevant.

Respond with ONLY valid JSON:
{{
  "query_summary": "One sentence summarising what you searched for",
  "picks": [
    {{
      "tmdb_id": 12345,
      "title": "Title",
      "media_type": "tv",
      "reason": "Why this matches the request",
      "reddit_buzz": null
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(message.content[0].text)
