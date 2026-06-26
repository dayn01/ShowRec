"""Viewing stats for the active profile — aggregates from the local watch state.
Read-only and works without any external integration (the data is already in
SQLite)."""
from fastapi import APIRouter, Depends
from deps import get_profile_id
import database

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def viewing_stats(pid: int = Depends(get_profile_id)):
    return await database.get_viewing_stats(pid)
