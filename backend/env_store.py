"""
Read/update the project .env file and apply changes to the live Settings object.

Used by the first-run setup wizard so the app can be configured from the UI
without SSH. Writes are line-preserving (comments + untouched keys stay put) and
atomic. The setup router treats "TMDB key present" as the lock, so nothing extra
is written here — meaning this never needs to write when .env is read-only
(e.g. the Docker mount); it only writes during the one-time wizard save.
"""
from pathlib import Path
from config import ENV_FILE, settings
import os
import tempfile

# Env keys the wizard is allowed to write, mapped to the Settings attribute they
# update in-memory. Anything not listed here is rejected (no arbitrary writes).
ALLOWED_KEYS: dict[str, str] = {
    "TMDB_API_KEY": "tmdb_api_key",
    "TRAKT_CLIENT_ID": "trakt_client_id",
    "TRAKT_CLIENT_SECRET": "trakt_client_secret",
    "TRAKT_ACCESS_TOKEN": "trakt_access_token",
    "JELLYFIN_URL": "jellyfin_url",
    "JELLYFIN_API_KEY": "jellyfin_api_key",
    "JELLYFIN_USER_ID": "jellyfin_user_id",
    "JELLYFIN_USERNAME": "jellyfin_username",
    "PLEX_URL": "plex_url",
    "PLEX_TOKEN": "plex_token",
    "OVERSEERR_URL": "overseerr_url",
    "OVERSEERR_API_KEY": "overseerr_api_key",
    "HA_URL": "ha_url",
    "HA_TOKEN": "ha_token",
    "HA_NOTIFICATION_SERVICE": "ha_notification_service",
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "REDDIT_CLIENT_ID": "reddit_client_id",
    "REDDIT_CLIENT_SECRET": "reddit_client_secret",
    "TASTEDIVE_API_KEY": "tastedive_api_key",
}

def _path() -> Path:
    return Path(ENV_FILE)


def read_all() -> dict[str, str]:
    """Parse the .env file into a dict (last value wins). Missing file -> {}."""
    p = _path()
    out: dict[str, str] = {}
    if not p.exists():
        return out
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip()
    return out


def get(key: str) -> str | None:
    return read_all().get(key)


def update(values: dict[str, str]) -> None:
    """
    Insert/replace the given KEY=VALUE pairs in .env, preserving every other
    line (comments, blank lines, untouched keys) and original ordering. Written
    atomically via a temp file + replace.
    """
    p = _path()
    existing_lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    remaining = dict(values)
    out_lines: list[str] = []

    for raw in existing_lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remaining:
                out_lines.append(f"{key}={remaining.pop(key)}")
                continue
        out_lines.append(raw)

    # Append any keys that weren't already present.
    for key, val in remaining.items():
        out_lines.append(f"{key}={val}")

    content = "\n".join(out_lines) + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def apply_to_settings(values: dict[str, str]) -> None:
    """
    Mutate the shared Settings object in place so changes take effect without a
    restart. Every module does `from config import settings`, so they all see
    these updates immediately. Unknown keys are ignored.
    """
    for key, val in values.items():
        attr = ALLOWED_KEYS.get(key)
        if attr is not None:
            setattr(settings, attr, val or None if attr != "tmdb_api_key" else val)
