"""Home Assistant notification integration."""
import httpx
from config import settings


async def send_notification(title: str, message: str, data: dict | None = None) -> bool:
    if not settings.ha_url or not settings.ha_token:
        return False

    service = settings.ha_notification_service
    domain, service_name = service.split(".", 1)
    url = f"{settings.ha_url.rstrip('/')}/api/services/{domain}/{service_name}"

    payload = {"title": title, "message": message}
    if data:
        payload["data"] = data

    async with httpx.AsyncClient() as client:
        r = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.ha_token}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        return r.status_code in (200, 201)


async def ping() -> bool:
    if not settings.ha_url or not settings.ha_token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(
                f"{settings.ha_url.rstrip('/')}/api/",
                headers={"Authorization": f"Bearer {settings.ha_token}"},
            )
            return r.status_code == 200
    except Exception:
        return False
