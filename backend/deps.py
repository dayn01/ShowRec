"""Shared FastAPI dependencies."""
from fastapi import Header


async def get_profile_id(x_profile_id: int | None = Header(default=None)) -> int:
    """Active profile for the request, from the X-Profile-Id header. Defaults to 1."""
    return x_profile_id or 1


def pkey(profile_id: int, key: str) -> str:
    """Per-profile cache key."""
    return f"p{profile_id}:{key}"
