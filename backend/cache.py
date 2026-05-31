"""Simple in-memory cache with timestamps."""
import time
from typing import Any

_store: dict[str, tuple[Any, float]] = {}


def set(key: str, value: Any, ttl_seconds: int = 3600):
    _store[key] = (value, time.time() + ttl_seconds)


def get(key: str) -> Any | None:
    entry = _store.get(key)
    if not entry:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        del _store[key]
        return None
    return value


def is_stale(key: str) -> bool:
    return get(key) is None


def age_seconds(key: str) -> int | None:
    entry = _store.get(key)
    if not entry:
        return None
    _, expires_at = entry
    # We don't store created_at, so approximate from ttl
    return None
