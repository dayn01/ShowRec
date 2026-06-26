"""
SQLite persistent cache for all app data.
Database: ../showrec_cache.db (project root)
"""
import aiosqlite
import asyncio
import contextlib
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
    "similar":         86400,       # 24h (TasteDive + TMDB resolution)
    "providers":       86400,       # 24h (watch/where-to-watch by region)
    "owned":           3600,        # 1h  (Jellyfin/Plex library contents)
    "request_state":   604800,      # 7d  (Overseerr status baseline for ready-alerts)
    "availability":    900,         # 15m (latest library episode per show)
}


# ── Shared connection ─────────────────────────────────────────────────────────
# One long-lived connection for the whole process instead of opening a fresh one
# per call. SQLite is single-writer anyway; this removes per-call connect churn.
_shared_db: aiosqlite.Connection | None = None
_db_init_lock = asyncio.Lock()


async def _get_db() -> aiosqlite.Connection:
    global _shared_db
    if _shared_db is None:
        async with _db_init_lock:
            if _shared_db is None:
                conn = await aiosqlite.connect(DB_PATH, timeout=30)
                await conn.execute("PRAGMA journal_mode=WAL")     # concurrent reads
                await conn.execute("PRAGMA busy_timeout=5000")
                _shared_db = conn
    return _shared_db


@contextlib.asynccontextmanager
async def _conn():
    """Yield the shared connection (kept open for the process lifetime)."""
    db = await _get_db()
    yield db


async def close():
    """Close the shared connection (called on app shutdown)."""
    global _shared_db
    if _shared_db is not None:
        await _shared_db.close()
        _shared_db = None


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
    async with _conn() as db:
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
                rec_settings     TEXT,    -- JSON: per-profile recommendation tuning
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
            -- "Liked" (👍) — a positive taste signal that boosts similar recs.
            CREATE TABLE IF NOT EXISTS liked (
                profile_id INTEGER NOT NULL DEFAULT 1,
                tmdb_id    INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                title      TEXT,
                liked_at   INTEGER NOT NULL,
                PRIMARY KEY (profile_id, tmdb_id, media_type)
            );
            CREATE INDEX IF NOT EXISTS idx_shows_cached   ON shows(cached_at);
            CREATE INDEX IF NOT EXISTS idx_seasons_cached ON seasons(cached_at);
        """)
        # Migrate legacy tables to add profile_id BEFORE creating the profile index
        await _migrate_add_profiles(db)
        # Add rec_settings to profiles created before tuning existed
        if await _table_exists(db, "profiles") and not await _has_column(db, "profiles", "rec_settings"):
            await db.execute("ALTER TABLE profiles ADD COLUMN rec_settings TEXT")
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
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, emoji, jellyfin_user_id, plex_token, trakt_token FROM profiles ORDER BY id"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_profile(profile_id: int) -> dict | None:
    async with _conn() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, name, emoji, jellyfin_user_id, plex_token, trakt_token FROM profiles WHERE id=?",
            (profile_id,)
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_profile(name: str, emoji: str = "👤", jellyfin_user_id: str | None = None,
                         plex_token: str | None = None, trakt_token: str | None = None) -> dict:
    async with _conn() as db:
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
    async with _conn() as db:
        await db.execute(f"UPDATE profiles SET {cols} WHERE id=?", (*sets.values(), profile_id))
        await db.commit()


async def upsert_default_profile(name: str = "Me", emoji: str = "🍿",
                                 jellyfin_user_id: str | None = None) -> dict:
    """
    Guarantee the default profile (id 1) exists with the given name/emoji and
    Jellyfin link. Creates it if missing, otherwise updates those fields. Used by
    the setup wizard so finishing setup always leaves a usable, linked profile.
    """
    async with _conn() as db:
        async with db.execute("SELECT 1 FROM profiles WHERE id=1") as cur:
            exists = await cur.fetchone() is not None
        if exists:
            await db.execute(
                "UPDATE profiles SET name=?, emoji=?, jellyfin_user_id=? WHERE id=1",
                (name, emoji, jellyfin_user_id or None),
            )
        else:
            await db.execute(
                "INSERT INTO profiles (id, name, emoji, jellyfin_user_id, created_at) VALUES (1, ?, ?, ?, ?)",
                (name, emoji, jellyfin_user_id or None, int(time.time())),
            )
        await db.commit()
    return await get_profile(1)


async def delete_profile(profile_id: int):
    async with _conn() as db:
        for t in ("watch_state", "dismissed", "watchlist", "liked"):
            await db.execute(f"DELETE FROM {t} WHERE profile_id=?", (profile_id,))
        await db.execute("DELETE FROM profiles WHERE id=?", (profile_id,))
        await db.commit()


async def all_profile_ids() -> list[int]:
    async with _conn() as db:
        async with db.execute("SELECT id FROM profiles ORDER BY id") as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_rec_settings(profile_id: int) -> dict:
    """Per-profile recommendation tuning ({} when unset)."""
    async with _conn() as db:
        async with db.execute("SELECT rec_settings FROM profiles WHERE id=?", (profile_id,)) as cur:
            row = await cur.fetchone()
    if not row or not row[0]:
        return {}
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return {}


async def set_rec_settings(profile_id: int, settings: dict):
    async with _conn() as db:
        await db.execute(
            "UPDATE profiles SET rec_settings=? WHERE id=?",
            (json.dumps(settings), profile_id)
        )
        await db.commit()


# ── Dismissals ("not interested") ─────────────────────────────────────────────

async def add_dismissed(profile_id: int, tmdb_id: int, media_type: str, title: str = ""):
    async with _conn() as db:
        await db.execute(
            "INSERT OR REPLACE INTO dismissed (profile_id, tmdb_id, media_type, title, dismissed_at) VALUES (?,?,?,?,?)",
            (profile_id, tmdb_id, "tv" if media_type == "tv" else "movie", title, int(time.time()))
        )
        await db.commit()


async def remove_dismissed(profile_id: int, tmdb_id: int):
    async with _conn() as db:
        await db.execute("DELETE FROM dismissed WHERE profile_id=? AND tmdb_id=?", (profile_id, tmdb_id))
        await db.commit()


async def get_dismissed_ids(profile_id: int) -> list[int]:
    async with _conn() as db:
        async with db.execute("SELECT tmdb_id FROM dismissed WHERE profile_id=?", (profile_id,)) as cur:
            return [r[0] for r in await cur.fetchall()]


# ── Liked (👍 positive taste signal) ──────────────────────────────────────────

async def add_liked(profile_id: int, tmdb_id: int, media_type: str, title: str = ""):
    async with _conn() as db:
        await db.execute(
            "INSERT OR REPLACE INTO liked (profile_id, tmdb_id, media_type, title, liked_at) VALUES (?,?,?,?,?)",
            (profile_id, tmdb_id, "tv" if media_type == "tv" else "movie", title, int(time.time()))
        )
        await db.commit()


async def remove_liked(profile_id: int, tmdb_id: int):
    async with _conn() as db:
        await db.execute("DELETE FROM liked WHERE profile_id=? AND tmdb_id=?", (profile_id, tmdb_id))
        await db.commit()


async def get_liked_ids(profile_id: int) -> list[int]:
    async with _conn() as db:
        async with db.execute("SELECT tmdb_id FROM liked WHERE profile_id=?", (profile_id,)) as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_liked_for_recommendations(profile_id: int) -> list[dict]:
    """Liked titles shaped like watch history, for taste-profiling + seeding."""
    async with _conn() as db:
        async with db.execute(
            "SELECT tmdb_id, media_type, title FROM liked WHERE profile_id=?", (profile_id,)
        ) as cur:
            rows = await cur.fetchall()
    return [{"tmdb_id": t, "media_type": mt, "title": title or "", "genres": []}
            for t, mt, title in rows]


# ── Watchlist ─────────────────────────────────────────────────────────────────

async def add_watchlist(profile_id: int, item: dict):
    async with _conn() as db:
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
    async with _conn() as db:
        await db.execute("DELETE FROM watchlist WHERE profile_id=? AND tmdb_id=?", (profile_id, tmdb_id))
        await db.commit()


async def get_watchlist(profile_id: int) -> list[dict]:
    async with _conn() as db:
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
    async with _conn() as db:
        async with db.execute("SELECT tmdb_id FROM watchlist WHERE profile_id=?", (profile_id,)) as cur:
            return [r[0] for r in await cur.fetchall()]


async def get_dismissed_full(profile_id: int) -> list[dict]:
    """Dismissed items with title + poster (from the shows cache when available)."""
    async with _conn() as db:
        async with db.execute(
            "SELECT tmdb_id, media_type, title, dismissed_at FROM dismissed WHERE profile_id=? ORDER BY dismissed_at DESC",
            (profile_id,)
        ) as cur:
            rows = await cur.fetchall()

    shows = await get_shows_bulk([r[0] for r in rows])   # one query instead of N
    items = []
    for tmdb_id, media_type, title, _ in rows:
        cached = shows.get(tmdb_id)
        poster = cached.get("poster_url") if cached else None
        if cached:
            title = title or cached.get("title") or cached.get("name")
        items.append({
            "tmdb_id": tmdb_id, "media_type": media_type,
            "title": title or "Unknown", "poster_url": poster,
        })
    return items


# ── Watch state (local source of truth) ───────────────────────────────────────

async def mark_watched(profile_id: int, media_type: str, tmdb_id: int, season: int = -1,
                       episode: int = -1, title: str = "", source: str = "user"):
    async with _conn() as db:
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
    async with _conn() as db:
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
    async with _conn() as db:
        await db.executemany(
            """INSERT OR IGNORE INTO watch_state
               (profile_id, media_type, tmdb_id, season_number, episode_number, title, watched_at, source)
               VALUES (?,?,?,?,?,?,?,?)""",
            full_rows
        )
        await db.commit()


async def replace_watched_source(profile_id: int, source: str, rows: list[tuple]):
    """
    Replace ALL of a profile's watch rows for one external source with a fresh
    set, atomically (delete then insert). Unlike sync_watched_bulk this REMOVES
    the source's old rows, so switching or unlinking an account doesn't leave the
    previous account's data behind. Other sources (manual marks = 'user', Netflix
    import = 'netflix', Plex, Trakt) are untouched.
    Pass rows=[] to simply clear the source. Each row:
    (media_type, tmdb_id, season, episode, title).
    """
    now = int(time.time())
    full = [(profile_id, r[0], r[1], r[2], r[3], r[4], now, source) for r in rows]
    async with _conn() as db:
        await db.execute(
            "DELETE FROM watch_state WHERE profile_id=? AND source=?", (profile_id, source)
        )
        if full:
            await db.executemany(
                """INSERT OR IGNORE INTO watch_state
                   (profile_id, media_type, tmdb_id, season_number, episode_number, title, watched_at, source)
                   VALUES (?,?,?,?,?,?,?,?)""",
                full,
            )
        await db.commit()


async def unmark_watched(profile_id: int, media_type: str, tmdb_id: int, season: int = -1, episode: int = -1):
    async with _conn() as db:
        await db.execute(
            """DELETE FROM watch_state
               WHERE profile_id=? AND media_type=? AND tmdb_id=? AND season_number=? AND episode_number=?""",
            (profile_id, media_type, tmdb_id, season, episode)
        )
        await db.commit()


async def unmark_season(profile_id: int, tmdb_id: int, season: int):
    """Remove a season-level mark and all its episode rows."""
    async with _conn() as db:
        await db.execute(
            "DELETE FROM watch_state WHERE profile_id=? AND tmdb_id=? AND season_number=? AND media_type='episode'",
            (profile_id, tmdb_id, season)
        )
        await db.commit()


async def unmark_show(profile_id: int, tmdb_id: int):
    async with _conn() as db:
        await db.execute("DELETE FROM watch_state WHERE profile_id=? AND tmdb_id=?", (profile_id, tmdb_id))
        await db.commit()


async def get_watch_state(profile_id: int) -> dict:
    """Returns the full local watch state for the frontend."""
    async with _conn() as db:
        async with db.execute(
            "SELECT media_type, tmdb_id, season_number, episode_number, watched_at FROM watch_state WHERE profile_id=?",
            (profile_id,)
        ) as cur:
            rows = await cur.fetchall()

        # Movie marks, explicit show-level "Seen" marks, and per-episode rows.
        movie_ids: set[int] = set()
        show_marked: set[int] = set()
        episodes = []
        season_counts: dict[tuple[int, int], int] = {}
        watched_by_show: dict[int, set] = {}
        last_watched: dict[int, int] = {}   # tmdb_id -> most recent watched_at (for sorting)

        for media_type, tmdb_id, season, episode, watched_at in rows:
            if watched_at and watched_at > last_watched.get(tmdb_id, 0):
                last_watched[tmdb_id] = watched_at
            if media_type == "movie":
                movie_ids.add(tmdb_id)
            elif media_type == "show":
                show_marked.add(tmdb_id)
            elif media_type == "episode":
                episodes.append({"tmdb_id": tmdb_id, "season": season, "episode": episode})
                season_counts[(tmdb_id, season)] = season_counts.get((tmdb_id, season), 0) + 1
                watched_by_show.setdefault(tmdb_id, set()).add((season, episode))

        seasons = [
            {"tmdb_id": tid, "season": sn, "episodes_watched": cnt}
            for (tid, sn), cnt in season_counts.items()
        ]

        # Evaluate every show with episode data OR an explicit show-level mark, so a
        # "finished" show can resurface in Watching when a new episode airs.
        eval_ids = list(set(watched_by_show) | show_marked)
        shows_cache: dict[int, dict] = {}
        seasons_cache: dict[tuple[int, int], dict] = {}
        if eval_ids:
            qmarks = ",".join("?" * len(eval_ids))
            async with db.execute(f"SELECT tmdb_id, data FROM shows WHERE tmdb_id IN ({qmarks})", eval_ids) as cur:
                for tid, data in await cur.fetchall():
                    shows_cache[tid] = json.loads(data)
            async with db.execute(f"SELECT tmdb_id, season_number, data FROM seasons WHERE tmdb_id IN ({qmarks})", eval_ids) as cur:
                for tid, sn, data in await cur.fetchall():
                    seasons_cache[(tid, sn)] = json.loads(data)

    today = time.strftime("%Y-%m-%d")
    complete_ids: list[int] = []
    resurfaced: set[int] = set()   # show-marked titles with a NEW unwatched aired episode
    for tmdb_id in eval_ids:
        show = shows_cache.get(tmdb_id)
        if not show or not show.get("seasons"):
            continue
        watched_set = watched_by_show.get(tmdb_id, set())
        saw_any_aired = False
        unwatched_aired = False     # positive evidence of an aired-but-unwatched episode
        cache_complete = True       # every season present in the cache
        for s in show["seasons"]:
            sn = s.get("season_number")
            if sn is None or sn < 1:
                continue
            season_data = seasons_cache.get((tmdb_id, sn))
            if not season_data:
                cache_complete = False
                continue            # keep scanning other seasons for positive evidence
            for e in season_data.get("episodes", []):
                ad = e.get("air_date")
                if ad and ad <= today:
                    saw_any_aired = True
                    if (sn, e["episode_number"]) not in watched_set:
                        unwatched_aired = True
        # A scheduled upcoming episode (returning series) also counts as "new
        # episode coming" — so a caught-up show you've watched stays in Watching.
        has_upcoming = bool(show.get("next_episode_to_air"))
        if tmdb_id in show_marked:
            # Resurface on positive evidence — a missing cache alone won't unmark it.
            if unwatched_aired or has_upcoming:
                resurfaced.add(tmdb_id)
        elif cache_complete and saw_any_aired and not unwatched_aired and not has_upcoming:
            complete_ids.append(tmdb_id)

    # Full = movies + show-level marks that have NO new unwatched aired episode.
    tmdb_ids = list(movie_ids | (show_marked - resurfaced))

    return {
        "tmdb_ids": tmdb_ids,
        "complete_tmdb_ids": complete_ids,
        "seasons": seasons,
        "episodes": episodes,
        "last_watched": last_watched,
    }


async def get_watched_library(profile_id: int) -> list[dict]:
    """
    Fully-watched items for the Watched page: movies + explicit show-level marks.
    Returns [{tmdb_id, media_type('movie'|'tv'), title}], most-recent first.
    """
    async with _conn() as db:
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
    async with _conn() as db:
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


async def max_watched_season_by_show(profile_id: int) -> dict[int, int]:
    """
    tmdb_id -> the highest season number this profile has any watched episode in.
    Used to detect "a new season is out that you haven't started".
    """
    async with _conn() as db:
        async with db.execute(
            "SELECT tmdb_id, MAX(season_number) FROM watch_state "
            "WHERE profile_id=? AND media_type='episode' GROUP BY tmdb_id",
            (profile_id,)
        ) as cur:
            return {tid: season for tid, season in await cur.fetchall()}


async def get_watch_state_stats(profile_id: int) -> dict:
    async with _conn() as db:
        async with db.execute(
            "SELECT source, COUNT(*) FROM watch_state WHERE profile_id=? GROUP BY source", (profile_id,)
        ) as cur:
            rows = await cur.fetchall()
    return {source or "unknown": count for source, count in rows}


# ── Generic key/value cache ───────────────────────────────────────────────────

async def cache_get(key: str, ttl_key: str) -> dict | list | None:
    ttl = TTL.get(ttl_key, 3600)
    async with _conn() as db:
        async with db.execute("SELECT data, cached_at FROM cache WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    data, cached_at = row
    if time.time() - cached_at > ttl:
        return None
    return json.loads(data)


async def cache_set(key: str, value: dict | list):
    async with _conn() as db:
        await db.execute(
            "INSERT OR REPLACE INTO cache (key, data, cached_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), int(time.time()))
        )
        await db.commit()


async def cache_age(key: str) -> int | None:
    """Returns age in seconds, or None if not cached."""
    async with _conn() as db:
        async with db.execute("SELECT cached_at FROM cache WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return int(time.time() - row[0])


# ── Shows ─────────────────────────────────────────────────────────────────────

async def get_show(tmdb_id: int, allow_stale: bool = False) -> dict | None:
    async with _conn() as db:
        async with db.execute("SELECT data, cached_at FROM shows WHERE tmdb_id=?", (tmdb_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    # allow_stale serves the cached copy regardless of age — used by the Watching
    # page, where season counts barely change and a fast load matters more than
    # freshness (the background prefetch refreshes it anyway).
    if not allow_stale and time.time() - row[1] > TTL["show"]:
        return None
    return json.loads(row[0])


async def cached_show_ids() -> set[int]:
    """tmdb_ids currently in the show cache (any age). Lets the warmer skip
    already-cached shows with a single query."""
    async with _conn() as db:
        async with db.execute("SELECT tmdb_id FROM shows") as cur:
            return {r[0] for r in await cur.fetchall()}


async def get_shows_bulk(tmdb_ids: list[int]) -> dict[int, dict]:
    """
    Bulk-fetch cached show/movie data (any age) for many ids in one query —
    used by pages that show hundreds of items (Watched library) so they read
    posters from cache instead of fetching each from TMDB on the request path.
    """
    out: dict[int, dict] = {}
    if not tmdb_ids:
        return out
    async with _conn() as db:
        # Chunk under SQLite's parameter limit (~999).
        for i in range(0, len(tmdb_ids), 800):
            chunk = tmdb_ids[i:i + 800]
            qmarks = ",".join("?" * len(chunk))
            async with db.execute(
                f"SELECT tmdb_id, data FROM shows WHERE tmdb_id IN ({qmarks})", chunk
            ) as cur:
                for tid, data in await cur.fetchall():
                    out[tid] = json.loads(data)
    return out


async def set_show(tmdb_id: int, media_type: str, data: dict):
    async with _conn() as db:
        await db.execute(
            "INSERT OR REPLACE INTO shows (tmdb_id, media_type, data, cached_at) VALUES (?,?,?,?)",
            (tmdb_id, media_type, json.dumps(data), int(time.time()))
        )
        await db.commit()


# ── Seasons ───────────────────────────────────────────────────────────────────

async def get_season(tmdb_id: int, season_number: int) -> dict | None:
    async with _conn() as db:
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
    async with _conn() as db:
        await db.execute(
            "INSERT OR REPLACE INTO seasons (tmdb_id, season_number, data, cached_at) VALUES (?,?,?,?)",
            (tmdb_id, season_number, json.dumps(data), int(time.time()))
        )
        await db.commit()


# ── Utilities ─────────────────────────────────────────────────────────────────

async def get_all_cached_show_ids() -> list[tuple[int, str]]:
    async with _conn() as db:
        async with db.execute("SELECT tmdb_id, media_type FROM shows") as cur:
            return await cur.fetchall()


async def wipe_synced_data():
    """
    Clear all synced + cached data so it rebuilds cleanly from source.
    Used when the linked Jellyfin account changes (setup wizard). Deletes
    watch state and the TMDB/recommendation caches; keeps user-curated data
    (profiles, dismissed titles, watchlist).
    """
    async with _conn() as db:
        for table in ("watch_state", "shows", "seasons", "cache"):
            await db.execute(f"DELETE FROM {table}")
        await db.commit()


async def purge_stale(older_than_days: int = 30):
    cutoff = int(time.time()) - (older_than_days * 86400)
    async with _conn() as db:
        await db.execute("DELETE FROM shows   WHERE cached_at < ?", (cutoff,))
        await db.execute("DELETE FROM seasons WHERE cached_at < ?", (cutoff,))
        await db.execute("DELETE FROM cache   WHERE cached_at < ?", (cutoff,))
        await db.commit()


async def get_cache_stats() -> dict:
    async with _conn() as db:
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
