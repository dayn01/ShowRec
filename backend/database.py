"""
SQLite persistent cache for all app data.
Database: ../showrec_cache.db (project root)
"""
import aiosqlite
import json
import time
import os
from pathlib import Path

# DB_PATH env var lets Docker point at a mounted volume; defaults to project root.
DB_PATH = Path(os.environ.get("DB_PATH") or (Path(__file__).parent.parent / "showrec_cache.db"))

# TTLs (seconds)
TTL = {
    "show":            86400,       # 24h
    "season":          21600,       # 6h
    "recommendations": 21600,       # 6h
    "trending":        21600,       # 6h
    "ai_picks":        86400,       # 24h (expensive)
    "upcoming":        3600,        # 1h
}


async def _has_column(db, table: str, column: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        cols = [r[1] for r in await cur.fetchall()]
    return column in cols


async def _table_exists(db, table: str) -> bool:
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ) as cur:
        return await cur.fetchone() is not None


async def _migrate_add_profiles(db):
    """Add profile_id to the per-user tables, migrating existing rows to profile 1."""
    # watch_state
    if await _table_exists(db, "watch_state") and not await _has_column(db, "watch_state", "profile_id"):
        await db.executescript("""
            CREATE TABLE watch_state_new (
                profile_id     INTEGER NOT NULL DEFAULT 1,
                media_type     TEXT NOT NULL,
                tmdb_id        INTEGER NOT NULL,
                season_number  INTEGER NOT NULL DEFAULT -1,
                episode_number INTEGER NOT NULL DEFAULT -1,
                title          TEXT,
                watched_at     INTEGER NOT NULL,
                source         TEXT,
                PRIMARY KEY (profile_id, media_type, tmdb_id, season_number, episode_number)
            );
            INSERT INTO watch_state_new
                (profile_id, media_type, tmdb_id, season_number, episode_number, title, watched_at, source)
                SELECT 1, media_type, tmdb_id, season_number, episode_number, title, watched_at, source FROM watch_state;
            DROP TABLE watch_state;
            ALTER TABLE watch_state_new RENAME TO watch_state;
        """)

    if await _table_exists(db, "dismissed") and not await _has_column(db, "dismissed", "profile_id"):
        await db.executescript("""
            CREATE TABLE dismissed_new (
                profile_id   INTEGER NOT NULL DEFAULT 1,
                tmdb_id      INTEGER NOT NULL,
                media_type   TEXT NOT NULL,
                title        TEXT,
                dismissed_at INTEGER NOT NULL,
                PRIMARY KEY (profile_id, tmdb_id, media_type)
            );
            INSERT INTO dismissed_new (profile_id, tmdb_id, media_type, title, dismissed_at)
                SELECT 1, tmdb_id, media_type, title, dismissed_at FROM dismissed;
            DROP TABLE dismissed;
            ALTER TABLE dismissed_new RENAME TO dismissed;
        """)

    if await _table_exists(db, "watchlist") and not await _has_column(db, "watchlist", "profile_id"):
        await db.executescript("""
            CREATE TABLE watchlist_new (
                profile_id   INTEGER NOT NULL DEFAULT 1,
                tmdb_id      INTEGER NOT NULL,
                media_type   TEXT NOT NULL,
                title        TEXT,
                poster_url   TEXT,
                vote_average REAL,
                overview     TEXT,
                release_date TEXT,
                added_at     INTEGER NOT NULL,
                PRIMARY KEY (profile_id, tmdb_id, media_type)
            );
            INSERT INTO watchlist_new
                (profile_id, tmdb_id, media_type, title, poster_url, vote_average, overview, release_date, added_at)
                SELECT 1, tmdb_id, media_type, title, poster_url, vote_average, overview, release_date, added_at FROM watchlist;
            DROP TABLE watchlist;
            ALTER TABLE watchlist_new RENAME TO watchlist;
        """)


async def init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS shows (
                tmdb_id     INTEGER PRIMARY KEY,
                media_type  TEXT NOT NULL,
                data        TEXT NOT NULL,
                cached_at   INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS seasons (
                tmdb_id       INTEGER NOT NULL,
                season_number INTEGER NOT NULL,
                data          TEXT NOT NULL,
                cached_at     INTEGER NOT NULL,
                PRIMARY KEY (tmdb_id, season_number)
            );
            CREATE TABLE IF NOT EXISTS cache (
                key         TEXT PRIMARY KEY,
                data        TEXT NOT NULL,
                cached_at   INTEGER NOT NULL
            );
            -- Profiles: each gets its own watch data + recommendations.
            CREATE TABLE IF NOT EXISTS profiles (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                name             TEXT NOT NULL,
                emoji            TEXT DEFAULT '👤',
                jellyfin_user_id TEXT,    -- NULL = standalone profile
                plex_token       TEXT,
                trakt_token      TEXT,
                created_at       INTEGER NOT NULL
            );
            -- Local watch state — the source of truth, independent of Trakt.
            CREATE TABLE IF NOT EXISTS watch_state (
                profile_id     INTEGER NOT NULL DEFAULT 1,
                media_type     TEXT NOT NULL,    -- 'movie' | 'show' | 'episode'
                tmdb_id        INTEGER NOT NULL,
                season_number  INTEGER NOT NULL DEFAULT -1,
                episode_number INTEGER NOT NULL DEFAULT -1,
                title          TEXT,
                watched_at     INTEGER NOT NULL,
                source         TEXT,
                PRIMARY KEY (profile_id, media_type, tmdb_id, season_number, episode_number)
            );
            -- "Not interested" dismissals — hidden from all recommendations.
            CREATE TABLE IF NOT EXISTS dismissed (
                profile_id   INTEGER NOT NULL DEFAULT 1,
                tmdb_id      INTEGER NOT NULL,
                media_type   TEXT NOT NULL,
                title        TEXT,
                dismissed_at INTEGER NOT NULL,
                PRIMARY KEY (profile_id, tmdb_id, media_type)
            );
            -- Watchlist — titles saved to watch later.
            CREATE TABLE IF NOT EXISTS watchlist (
                profile_id   INTEGER NOT NULL DEFAULT 1,
                tmdb_id      INTEGER NOT NULL,
                media_type   TEXT NOT NULL,
                title        TEXT,
                poster_url   TEXT,
                vote_average REAL,
                overview     TEXT,
                release_date TEXT,
                added_at     INTEGER NOT NULL,
                PRIMARY KEY (profile_id, tmdb_id, media_type)
            );
            CREATE INDEX IF NOT EXISTS idx_shows_cached   ON shows(cached_at);
            CREATE INDEX IF NOT EXISTS idx_seasons_cached ON seasons(cached_at);
        """)
        # Migrate legacy tables to add profile_id BEFORE creating the profile index
        await _migrate_add_profiles(db)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_watch_profile ON watch_state(profile_id)")

        # Seed a default profile from the configured Jellyfin user if none exist
        async with db.execute("SELECT COUNT(*) FROM profiles") as cur:
            count = (await cur.fetchone())[0]
        if count == 0:
            from config import settings
            await db.execute(
                "INSERT INTO profiles (id, name, emoji, jellyfin_user_id, created_at) VALUES (1, ?, ?, ?, ?)",
                ("Me", "🍿", settings.jellyfin_user_id, int(time.time()))
            )
        await db.commit()


# ── Profiles ──────────────────────────────────────────────────────────────────

async def list_profiles() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, emoji, jellyfin_user_id, plex_token, trakt_token FROM profiles ORDER BY id"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_profile(profile_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, emoji, jellyfin_user_id, plex_token, trakt_token FROM profiles WHERE id=?",
            (profile_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_profile(name: str, emoji: str = "👤", jellyfin_user_id: str | None = None,
                         plex_token: str | None = None, trakt_token: str | None = None) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO profiles (name, emoji, jellyfin_user_id, plex_token, trakt_token, created_at) VALUES (?,?,?,?,?,?)",
            (name, emoji, jellyfin_user_id or None, plex_token or None, trakt_token or None, int(time.time()))
        )
        await db.commit()
        pid = cur.lastrowid
    return await get_profile(pid)


async def update_profile(profile_id: int, **fields):
    allowed = {"name", "emoji", "jellyfin_user_id", "plex_token", "trakt_token"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    cols = ", ".join(f"{k}=?" for k in sets)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE profiles SET {cols} WHERE id=?", (*sets.values(), profile_id))
        await db.commit()


async def delete_profile(profile_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        for t in ("watch_state", "dismissed", "watchlist"):
            await db.execute(f"DELETE FROM {t} WHERE profile_id=?", (profile_id,))
        await db.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        await db.commit()


async def all_profile_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM profiles ORDER BY id") as cur:
            return [r[0] for r in await cur.fetchall()]


# ── Dismissals ("not interested") ─────────────────────────────────────────────

async def add_dismissed(profile_id: int, tmdb_id: int, media_type: str, title: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO dismissed (profile_id, tmdb_id, media_type, title, dismissed_at) VALUES (?,?,?,?,?)",
            (profile_id, tmdb_id, "tv" if media_type == "tv" else "movie", title, int(time.time()))
        )
        await db.commit()


async def remove_dismissed(profile_id: int, tmdb_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM dismissed WHERE profile_id=? AND tmdb_id=?", (profile_id, tmdb_id))
        await db.commit()


async def get_dismissed_ids(profile_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tmdb_id FROM dismissed WHERE profile_id=?", (profile_id,)) as cur:
            return [r[0] for r in await cur.fetchall()]


# ── Watchlist ─────────────────────────────────────────────────────────────────

async def add_watchlist(profile_id: int, item: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO watchlist
               (profile_id, tmdb_id, media_type, title, poster_url, vote_average, overview, release_date, added_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                profile_id, item["tmdb_id"], "tv" if item.get("media_type") == "tv" else "movie",
                item.get("title", ""), item.get("poster_url"), item.get("vote_average", 0),
                item.get("overview", ""), item.get("release_date") or item.get("first_air_date"),
                int(time.time()),
            )
        )
        await db.commit()


async def remove_watchlist(profile_id: int, tmdb_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM watchlist WHERE profile_id=? AND tmdb_id=?", (profile_id, tmdb_id))
        await db.commit()


async def get_watchlist(profile_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT tmdb_id, media_type, title, poster_url, vote_average, overview, release_date
               FROM watchlist WHERE profile_id=? ORDER BY added_at DESC""", (profile_id,)
        ) as cur:
            rows = await cur.fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = d["tmdb_id"]
        d["first_air_date"] = d.get("release_date") if d["media_type"] == "tv" else None
        out.append(d)
    return out


async def get_watchlist_ids(profile_id: int) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tmdb_id FROM watchlist WHERE profile_id=?", (profile_id,)) as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_dismissed_full(profile_id: int) -> list[dict]:
    """Dismissed items with title + poster (from the shows cache when available)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT tmdb_id, media_type, title, dismissed_at FROM dismissed WHERE profile_id=? ORDER BY dismissed_at DESC",
            (profile_id,)
        ) as cur:
            rows = await cur.fetchall()

    items = []
    for tmdb_id, media_type, title, _ in rows:
        poster = None
        cached = await get_show(tmdb_id)
        if cached:
            poster = cached.get("poster_url")
            title = title or cached.get("title") or cached.get("name")
        items.append({
            "tmdb_id": tmdb_id, "media_type": media_type,
            "title": title or "Unknown", "poster_url": poster,
        })
    return items


# ── Watch state (local source of truth) ───────────────────────────────────────

async def mark_watched(profile_id: int, media_type: str, tmdb_id: int, season: int = -1,
                       episode: int = -1, title: str = "", source: str = "user"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO watch_state
               (profile_id, media_type, tmdb_id, season_number, episode_number, title, watched_at, source)
               VALUES (?,?,?,?,?,?,?,?)""",
            (profile_id, media_type, tmdb_id, season, episode, title, int(time.time()), source)
        )
        await db.commit()


async def mark_episodes_bulk(profile_id: int, tmdb_id: int, season: int, episode_numbers: list[int],
                             title: str = "", source: str = "user"):
    now = int(time.time())
    rows = [(profile_id, "episode", tmdb_id, season, ep, title, now, source) for ep in episode_numbers]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT OR REPLACE INTO watch_state
               (profile_id, media_type, tmdb_id, season_number, episode_number, title, watched_at, source)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows
        )
        await db.commit()


async def sync_watched_bulk(profile_id: int, rows: list[tuple]):
    """
    Insert watched rows from an external source (Jellyfin/Plex/Trakt) without
    overwriting existing rows (so user marks/unmarks are preserved).
    Each row: (media_type, tmdb_id, season, episode, title, source)
    """
    now = int(time.time())
    full_rows = [(profile_id, r[0], r[1], r[2], r[3], r[4], now, r[5]) for r in rows]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT OR IGNORE INTO watch_state
               (profile_id, media_type, tmdb_id, season_number, episode_number, title, watched_at, source)
               VALUES (?,?,?,?,?,?,?,?)""",
            full_rows
        )
        await db.commit()


async def unmark_watched(profile_id: int, media_type: str, tmdb_id: int, season: int = -1, episode: int = -1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """DELETE FROM watch_state
               WHERE profile_id=? AND media_type=? AND tmdb_id=? AND season_number=? AND episode_number=?""",
            (profile_id, media_type, tmdb_id, season, episode)
        )
        await db.commit()


async def unmark_season(profile_id: int, tmdb_id: int, season: int):
    """Remove a season-level mark and all its episode rows."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM watch_state WHERE profile_id=? AND tmdb_id=? AND season_number=? AND media_type='episode'",
            (profile_id, tmdb_id, season)
        )
        await db.commit()


async def unmark_show(profile_id: int, tmdb_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM watch_state WHERE profile_id=? AND tmdb_id=?", (profile_id, tmdb_id))
        await db.commit()


async def get_watch_state(profile_id: int) -> dict:
    """Returns the full local watch state for the frontend."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT media_type, tmdb_id, season_number, episode_number FROM watch_state WHERE profile_id=?",
            (profile_id,)
        ) as cur:
            rows = await cur.fetchall()

    # tmdb_ids = FULLY-watched items only (movies + explicit show-level marks).
    # Shows that merely have watched episodes go into episodes/seasons so the
    # frontend can compute partial-vs-complete progress itself.
    tmdb_ids: set[int] = set()
    episodes = []
    season_counts: dict[tuple[int, int], int] = {}

    for media_type, tmdb_id, season, episode in rows:
        if media_type in ("movie", "show"):
            tmdb_ids.add(tmdb_id)
        elif media_type == "episode":
            episodes.append({"tmdb_id": tmdb_id, "season": season, "episode": episode})
            key = (tmdb_id, season)
            season_counts[key] = season_counts.get(key, 0) + 1

    seasons = [
        {"tmdb_id": tid, "season": sn, "episodes_watched": cnt}
        for (tid, sn), cnt in season_counts.items()
    ]

    return {"tmdb_ids": list(tmdb_ids), "seasons": seasons, "episodes": episodes}


async def get_watched_library(profile_id: int) -> list[dict]:
    """
    Fully-watched items for the Watched page: movies + explicit show-level marks.
    Returns [{tmdb_id, media_type('movie'|'tv'), title}], most-recent first.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT media_type, tmdb_id, title, MAX(watched_at) AS w
               FROM watch_state
               WHERE profile_id=? AND media_type IN ('movie','show')
               GROUP BY media_type, tmdb_id
               ORDER BY w DESC""", (profile_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [
        {"tmdb_id": tid, "media_type": "movie" if mt == "movie" else "tv", "title": title or ""}
        for mt, tid, title, _ in rows
    ]


async def get_watched_for_recommendations(profile_id: int) -> list[dict]:
    """
    Returns unique watched titles for the recommender, most-recent first.
    Movies as media_type 'movie', shows (any episode/show row) as 'tv'.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT media_type, tmdb_id, title, MAX(watched_at) AS last_watched
               FROM watch_state WHERE profile_id=?
               GROUP BY (CASE WHEN media_type='movie' THEN 'movie' ELSE 'tv' END), tmdb_id
               ORDER BY last_watched DESC""", (profile_id,)
        ) as cur:
            rows = await cur.fetchall()

    items = []
    for media_type, tmdb_id, title, _ in rows:
        norm = "movie" if media_type == "movie" else "tv"
        items.append({"tmdb_id": tmdb_id, "media_type": norm, "title": title or "", "genres": []})
    return items


async def get_watch_state_stats(profile_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT source, COUNT(*) FROM watch_state WHERE profile_id=? GROUP BY source", (profile_id,)
        ) as cur:
            rows = await cur.fetchall()
    return {source or "unknown": count for source, count in rows}


# ── Generic key/value cache ───────────────────────────────────────────────────

async def cache_get(key: str, ttl_key: str) -> dict | list | None:
    ttl = TTL.get(ttl_key, 3600)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT data, cached_at FROM cache WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    data, cached_at = row
    if time.time() - cached_at > ttl:
        return None
    return json.loads(data)


async def cache_set(key: str, value: dict | list):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO cache (key, data, cached_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), int(time.time()))
        )
        await db.commit()


async def cache_age(key: str) -> int | None:
    """Returns age in seconds, or None if not cached."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT cached_at FROM cache WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return int(time.time() - row[0])


# ── Shows ─────────────────────────────────────────────────────────────────────

async def get_show(tmdb_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT data, cached_at FROM shows WHERE tmdb_id=?", (tmdb_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    if time.time() - row[1] > TTL["show"]:
        return None
    return json.loads(row[0])


async def set_show(tmdb_id: int, media_type: str, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO shows (tmdb_id, media_type, data, cached_at) VALUES (?,?,?,?)",
            (tmdb_id, media_type, json.dumps(data), int(time.time()))
        )
        await db.commit()


# ── Seasons ───────────────────────────────────────────────────────────────────

async def get_season(tmdb_id: int, season_number: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT data, cached_at FROM seasons WHERE tmdb_id=? AND season_number=?",
            (tmdb_id, season_number)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    if time.time() - row[1] > TTL["season"]:
        return None
    return json.loads(row[0])


async def set_season(tmdb_id: int, season_number: int, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO seasons (tmdb_id, season_number, data, cached_at) VALUES (?,?,?,?)",
            (tmdb_id, season_number, json.dumps(data), int(time.time()))
        )
        await db.commit()


# ── Utilities ─────────────────────────────────────────────────────────────────

async def get_all_cached_show_ids() -> list[tuple[int, str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tmdb_id, media_type FROM shows") as cur:
            return await cur.fetchall()


async def purge_stale(older_than_days: int = 30):
    cutoff = int(time.time()) - (older_than_days * 86400)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM shows   WHERE cached_at < ?", (cutoff,))
        await db.execute("DELETE FROM seasons WHERE cached_at < ?", (cutoff,))
        await db.execute("DELETE FROM cache   WHERE cached_at < ?", (cutoff,))
        await db.commit()


async def get_cache_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM shows") as c:
            shows = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM seasons") as c:
            seasons = (await c.fetchone())[0]
        async with db.execute("SELECT key, cached_at FROM cache") as c:
            rows = await c.fetchall()

    keys = {}
    now = time.time()
    for key, cached_at in rows:
        keys[key] = {"age_minutes": round((now - cached_at) / 60)}

    return {"shows": shows, "seasons": seasons, "cache_keys": keys}
