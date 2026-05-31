from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from routers import recommendations, upcoming, status, details, watched, ai_recommendations, library, profiles
import scheduler
import prefetch
import database
import asyncio
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init SQLite DB
    await database.init()

    # Start scheduler
    scheduler.start()

    # Run full background refresh (recommendations, trending, AI picks, shows, seasons)
    asyncio.create_task(prefetch.refresh_all())

    yield
    scheduler.scheduler.shutdown()


app = FastAPI(title="Show Recommendation App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recommendations.router)
app.include_router(upcoming.router)
app.include_router(status.router)
app.include_router(details.router)
app.include_router(watched.router)
app.include_router(ai_recommendations.router)
app.include_router(library.router)
app.include_router(profiles.router)


@app.get("/")
def root():
    return {"message": "Show Recommendation API", "docs": "/docs"}


@app.post("/cache/refresh")
async def manual_refresh():
    """Manually trigger a full cache refresh."""
    asyncio.create_task(prefetch.refresh_all())
    return {"status": "refresh started in background"}


@app.get("/cache/status")
async def cache_status():
    """Show what's in the SQLite cache and how old it is."""
    return await database.get_cache_stats()
