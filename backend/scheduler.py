"""
APScheduler jobs:
  - Daily: check Trakt calendar for upcoming episodes, notify via Home Assistant
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from integrations import trakt, homeassistant
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


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
        s = ep.get("season", "?")
        e = ep.get("number", "?")
        lines.append(f"{show} S{s:02d}E{e:02d} — {ep_title}")

    message = "\n".join(lines)
    count = len(today_entries)
    await homeassistant.send_notification(
        title=f"📺 {count} episode{'s' if count != 1 else ''} airing today",
        message=message,
    )
    logger.info(f"Sent HA notification for {count} episodes")


def start():
    scheduler.add_job(check_upcoming_episodes, "cron", hour=8, minute=0, id="daily_episodes")
    scheduler.add_job(_full_refresh, "interval", hours=6, id="full_refresh")
    scheduler.start()
    logger.info("Scheduler started — episode check at 08:00, full refresh every 6h")


def _full_refresh():
    import asyncio
    import prefetch
    asyncio.run(prefetch.refresh_all())

    log.info(f"Show DB refresh complete — updated {len(tv_ids)} shows")
