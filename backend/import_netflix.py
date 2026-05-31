"""
Import a Netflix "Viewing Activity" CSV into a profile's watch state.

Netflix gives rows like:
    "Stranger Things: Season 4: Chapter One: The Hellfire Club","2024-01-15"
    "The Crown: Season 1: Windsor","2024-02-02"
    "Inception","2024-03-10"

It provides episode *titles*, not numbers, so this resolves each title against
TMDB (matching the episode name within the show's seasons) — best-effort, with a
report of anything it couldn't match.

Usage (inside the backend container, with the CSV in the mounted ./data dir):
    docker compose exec backend python import_netflix.py /data/netflix.csv 1
                                                          ^csv path   ^profile id
"""
import sys
import csv
import re
import asyncio
from collections import defaultdict

import database
from integrations import tmdb

SEASON_RE = re.compile(r"(?:season|part|volume|book|series|chapter)\s+(\d+)", re.I)
LIMITED_RE = re.compile(r"(limited series|mini[- ]?series)", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def match_title(tmdb_name: str, netflix_ep: str) -> bool:
    a, b = norm(tmdb_name), norm(netflix_ep)
    if not a or not b:
        return False
    return a in b or b in a


async def _search_first(query: str, media_type: str, cache: dict):
    if query in cache:
        return cache[query]
    try:
        results = await tmdb.search(query, media_type)
        rid = results[0]["id"] if results else None
    except Exception:
        rid = None
    cache[query] = rid
    return rid


async def main(csv_path: str, profile_id: int):
    # ── Parse CSV ──
    titles: list[str] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        # If the first row isn't a header (no "title"), keep it
        if header and header and "title" not in norm(header[0]):
            if header[0].strip():
                titles.append(header[0].strip())
        for row in reader:
            if row and row[0].strip():
                titles.append(row[0].strip())

    print(f"Read {len(titles)} rows from {csv_path}")

    # ── Classify movie vs TV episode ──
    tv_eps: dict[str, list] = defaultdict(list)   # show name -> [(season_hint, ep_title)]
    movies: set[str] = set()

    for title in titles:
        parts = [p.strip() for p in title.split(":")]
        if len(parts) >= 3:
            tv_eps[parts[0]].append((parts[1], ": ".join(parts[2:])))
        elif len(parts) == 2:
            tv_eps[parts[0]].append((None, parts[1]))   # ambiguous; treat as TV first
        else:
            movies.add(title)

    show_cache, movie_cache, season_cache, details_cache = {}, {}, {}, {}
    marked_movies = marked_eps = 0
    unmatched: list[str] = []

    # ── Movies ──
    for name in sorted(movies):
        mid = await _search_first(name, "movie", movie_cache)
        if mid:
            await database.mark_watched(profile_id, "movie", mid, title=name, source="netflix")
            marked_movies += 1
        else:
            unmatched.append(name)

    # ── TV ──
    for show, eps in tv_eps.items():
        sid = await _search_first(show, "tv", show_cache)

        # If it doesn't look like a TV show, retry the 2-part ones as movies
        if not sid:
            for hint, ep_title in eps:
                full = f"{show}: {ep_title}" if ep_title else show
                mid = await _search_first(full, "movie", movie_cache)
                if mid:
                    await database.mark_watched(profile_id, "movie", mid, title=full, source="netflix")
                    marked_movies += 1
                else:
                    unmatched.append(full)
            continue

        if sid not in details_cache:
            try:
                details_cache[sid] = await tmdb.get_details(sid, "tv")
            except Exception:
                details_cache[sid] = None
        details = details_cache[sid]
        all_seasons = [s["season_number"] for s in (details.get("seasons", []) if details else [])
                       if s.get("season_number", 0) >= 1]

        to_mark: dict[int, set] = defaultdict(set)
        for hint, ep_title in eps:
            hint_season = None
            if hint:
                m = SEASON_RE.search(hint)
                if m:
                    hint_season = int(m.group(1))
                elif LIMITED_RE.search(hint):
                    hint_season = 1
            candidates = [hint_season] if hint_season else all_seasons

            found = False
            for sn in candidates:
                if sn is None:
                    continue
                key = (sid, sn)
                if key not in season_cache:
                    try:
                        sd = await tmdb.get_tv_season(sid, sn)
                        season_cache[key] = sd.get("episodes", [])
                        await asyncio.sleep(0.05)
                    except Exception:
                        season_cache[key] = []
                for ep in season_cache[key]:
                    if match_title(ep.get("name", ""), ep_title):
                        to_mark[sn].add(ep["episode_number"])
                        found = True
                        break
                if found:
                    break
            if not found:
                unmatched.append(f"{show}: {hint or '?'}: {ep_title}")

        for sn, ep_nums in to_mark.items():
            await database.mark_episodes_bulk(profile_id, sid, sn, sorted(ep_nums),
                                              title=show, source="netflix")
            marked_eps += len(ep_nums)

    # ── Report ──
    print("\n=== Netflix import complete ===")
    print(f"  Movies marked:   {marked_movies}")
    print(f"  Episodes marked: {marked_eps}")
    print(f"  Unmatched:       {len(unmatched)}")
    if unmatched:
        print("\nUnmatched rows (first 40) — check spelling / non-Netflix-original naming:")
        for u in unmatched[:40]:
            print("   ·", u)
    print("\nNext: refresh the profile so recommendations + 'seen' state update:")
    print(f"  curl -X POST http://localhost:8087/api/profiles/{profile_id}/refresh")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python import_netflix.py <csv_path> [profile_id]")
        sys.exit(1)
    path = sys.argv[1]
    pid_arg = sys.argv[2].strip() if len(sys.argv) > 2 else "1"
    if not pid_arg.isdigit():
        print(f"Profile id must be a number, got '{pid_arg}'.")
        print("Tip: run this command on its own line, e.g.:")
        print("  python import_netflix.py /data/netflix.csv 1")
        sys.exit(1)
    asyncio.run(main(path, int(pid_arg)))
