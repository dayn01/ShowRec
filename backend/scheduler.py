"""
APScheduler jobs:
  - Daily: check Trakt calendar for upcoming episodes, notify via Home Assistant
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from integrations import trakt, homeassistant, overseerr
from config import settings
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def _tz():
    """Resolve settings.timezone to a tzinfo for the daily cron jobs, falling
    back to UTC (with a warning) if the name is invalid or tz data is missing."""
    try:
        return ZoneInfo(settings.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Invalid timezone %r; daily notifications will run in UTC", settings.timezone)
        return ZoneInfo("UTC")


async def check_requests_ready():
    """Notify (via Home Assistant) when an Overseerr request flips to 'available'."""
    import database
    if not overseerr.is_configured() or not (settings.ha_url and settings.ha_token):
        return

    current = await overseerr.get_all_statuses()      # {tmdb_id: status}
    if not current:
        return
    current_s = {str(k): v for k, v in current.items()}

    prev = await database.cache_get("request_state", "request_state") or {}
    # First run (no baseline) just records state — don't blast a notification for
    # everything already on the server.
    if prev:
        newly = [int(tid) for tid, status in current_s.items()
                 if status == "available" and prev.get(tid) and prev.get(tid) != "available"]
        if newly:
            shows = await database.get_shows_bulk(newly)
            lines = [
                (shows.get(tid) or {}).get("title") or (shows.get(tid) or {}).get("name") or f"TMDB #{tid}"
                for tid in newly[:10]
            ]
            count = len(newly)
            await homeassistant.send_notification(
                title=f"🎉 {count} request{'s' if count != 1 else ''} ready to watch",
                message="\n".join(lines),
            )
            logger.info(f"Notified: {count} request(s) now available")

    await database.cache_set("request_state", current_s)


async def check_new_seasons():
    """Notify (via Home Assistant) when a NEW season lands for a show you follow —
    both shows you've finished (the For You 'returning' detection) and shows on your
    watchlist. Diffs a stored baseline so each new season pings exactly once."""
    import database, prefetch
    from datetime import date
    if not (settings.ha_url and settings.ha_token):
        return

    pid = 1  # notify for the default (owner) profile, like the episode check
    today = date.today().isoformat()
    current: dict[str, int] = {}            # tmdb_id -> season number
    labels: dict[str, tuple[str, str]] = {}  # tmdb_id -> (title, reason)
    wl_keys: set[str] = set()                # which entries came from the watchlist

    # 1) Watched shows with a season beyond what you've seen (returning series).
    dismissed = set(await database.get_dismissed_ids(pid))
    try:
        for r in await prefetch._returning_shows(pid, dismissed):
            if not r.get("id"):
                continue
            k = str(r["id"])
            current[k] = r.get("next_season")
            labels[k] = (r["title"], r.get("reason", "new season"))
    except Exception as e:
        logger.warning(f"New-season check (watched) failed: {e}")

    # 2) Watchlist TV shows whose latest aired season has advanced.
    try:
        wl = await database.get_watchlist(pid)
        cache = await database.get_shows_bulk([w["tmdb_id"] for w in wl if w.get("media_type") == "tv"])
        for w in wl:
            if w.get("media_type") != "tv":
                continue
            show = cache.get(w["tmdb_id"])
            if not show:
                continue
            sn, _ = database.latest_aired_season(show, today)
            k = str(w["tmdb_id"])
            if sn and k not in current:     # a watched-returning entry takes precedence
                current[k] = sn
                labels[k] = (w.get("title") or show.get("title") or "A show", f"Season {sn} is out")
                wl_keys.add(k)
    except Exception as e:
        logger.warning(f"New-season check (watchlist) failed: {e}")

    if not current:
        return

    prev = await database.cache_get("new_season_notify", "new_season_notify") or {}
    # First run records the baseline only. Watchlist entries also notify only once
    # we have a prior season for them, so we don't blast already-out seasons the
    # first time a watchlist show is tracked.
    if prev:
        newly = [
            k for k, v in current.items()
            if (k in prev and prev[k] != v) or (k not in wl_keys and prev.get(k) != v)
        ]
        if newly:
            lines = [f"{labels[k][0]} · {labels[k][1]}" for k in newly[:10]]
            count = len(newly)
            await homeassistant.send_notification(
                title=f"📺 New season{'s' if count != 1 else ''} for {count} show{'s' if count != 1 else ''} you follow",
                message="\n".join(lines),
            )
            logger.info(f"Notified: {count} show(s) with a new season")

    await database.cache_set("new_season_notify", current)


async def check_upcoming_episodes():
    logger.info("Checking upcoming episodes...")
    import database
    today_str = __import__("datetime").date.today().isoformat()

    # Use cached combined data first
    cached = await database.cache_get("p1:upcoming", "upcoming")  # notify for default profile
    if cached:
        calendar = cached.get("episodes", [])
    else:
        try:
            calendar = await trakt.get_calendar_shows(days=7)
        except Exception as e:
            logger.error(f"Trakt calendar fetch failed: {e}")
            return

    if not calendar:
        return

    today_entries = [e for e in calendar if e.get("first_aired", "").startswith(today_str)]

    if not today_entries:
        return

    lines = []
    for entry in today_entries[:5]:
        show = entry.get("show", {}).get("title", "Unknown")
        ep = entry.get("episode", {})
        ep_title = ep.get("title", "")
        s = ep.get("season")
        e = ep.get("number")
        # Only format S/E when both are ints — a missing number would crash :02d.
        se = f" S{s:02d}E{e:02d}" if isinstance(s, int) and isinstance(e, int) else ""
        lines.append(f"{show}{se} — {ep_title}")

    message = "\n".join(lines)
    count = len(today_entries)
    await homeassistant.send_notification(
        title=f"📺 {count} episode{'s' if count != 1 else ''} airing today",
        message=message,
    )
    logger.info(f"Sent HA notification for {count} episodes")


def start():
    # All jobs are coroutines, so AsyncIOScheduler runs them on the app's event
    # loop — the same loop the API uses, so they share the one SQLite connection
    # instead of each spinning up a separate loop in a worker thread.
    import prefetch
    tz = _tz()  # daily checks fire at local wall-clock, not UTC
    scheduler.add_job(check_upcoming_episodes, "cron", hour=8, minute=0, timezone=tz, id="daily_episodes")
    scheduler.add_job(check_new_seasons, "cron", hour=9, minute=0, timezone=tz, id="new_seasons")
    scheduler.add_job(prefetch.refresh_all, "interval", hours=6, id="full_refresh")
    scheduler.add_job(prefetch.sync_all_watch_states, "interval", minutes=15, id="light_sync")
    scheduler.add_job(check_requests_ready, "interval", minutes=30, id="requests_ready")
    scheduler.start()
    logger.info("Scheduler started (%s) — episode check 08:00, new-season check 09:00, light sync 15m, full refresh 6h, request-ready 30m", tz)
