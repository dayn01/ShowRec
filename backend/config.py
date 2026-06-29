from pydantic_settings import BaseSettings
from typing import Optional
from pathlib import Path

ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    tmdb_api_key: str = ""
    trakt_client_id: str = ""
    trakt_client_secret: str = ""
    trakt_access_token: str = ""

    jellyfin_url: Optional[str] = None
    jellyfin_api_key: Optional[str] = None
    jellyfin_user_id: Optional[str] = None
    # Optional: the stable Jellyfin username. The user id is volatile (it changes
    # if Jellyfin is reinstalled/migrated); with a username set, the app re-resolves
    # and repairs a stale user id automatically instead of silently breaking.
    jellyfin_username: Optional[str] = None

    plex_url: Optional[str] = None
    plex_token: Optional[str] = None

    # Overseerr — optional. When unset, the request feature stays hidden/disabled.
    overseerr_url: Optional[str] = None
    overseerr_api_key: Optional[str] = None

    ha_url: Optional[str] = None
    ha_token: Optional[str] = None
    ha_notification_service: str = "notify.notify"

    anthropic_api_key: Optional[str] = None
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    tastedive_api_key: Optional[str] = None

    class Config:
        env_file = str(ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"   # tolerate unrelated env vars (TUNNEL_TOKEN, COMPOSE_FILE, …)


settings = Settings()
