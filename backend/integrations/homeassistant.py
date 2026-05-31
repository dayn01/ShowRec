"""Home Assistant notification integration."""
import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)


def _service_url() -> str | None:
    if not settings.ha_url or not settings.ha_token:
        return None
    service = (settings.ha_notification_service or "notify.notify").strip()
    if "." not in service:
        service = f"notify.{service}"
    domain, service_name = service.split(".", 1)
    return f"{settings.ha_url.strip().rstrip('/')}/api/services/{domain.strip()}/{service_name.strip()}"


async def send_notification(title: str, message: str, data: dict | None = None) -> bool:
    """Returns True on success. Logs the reason on failure."""
    url = _service_url()
    if not url:
        logger.warning("HA notify skipped — HA_URL or HA_TOKEN not configured")
        return False

    payload = {"title": title, "message": message}
    if data:
        payload["data"] = data

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url, json=payload,
                headers={"Authorization": f"Bearer {settings.ha_token.strip()}",
                         "Content-Type": "application/json"},
            )
        if r.status_code in (200, 201):
            return True
        logger.warning(f"HA notify failed: {r.status_code} {r.text[:200]} (url={url})")
        return False
    except Exception as e:
        logger.warning(f"HA notify error: {e} (url={url})")
        return False


async def send_test() -> dict:
    """Diagnostic: send a test notification and return the full result."""
    url = _service_url()
    if not url:
        return {"ok": False, "error": "HA_URL or HA_TOKEN not set in .env"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                url,
                json={"title": "📺 ShowRec test", "message": "If you see this, notifications work!"},
                headers={"Authorization": f"Bearer {settings.ha_token.strip()}",
                         "Content-Type": "application/json"},
            )
        return {
            "ok": r.status_code in (200, 201),
            "status_code": r.status_code,
            "url": url,
            "service": settings.ha_notification_service,
            "response": r.text[:300],
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}


async def ping() -> bool:
    if not settings.ha_url or not settings.ha_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{settings.ha_url.strip().rstrip('/')}/api/",
                headers={"Authorization": f"Bearer {settings.ha_token.strip()}"},
            )
            return r.status_code == 200
    except Exception:
        return False
