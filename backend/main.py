from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
from routers import recommendations, upcoming, status, details, watched, ai_recommendations, library, profiles, requests, setup, stats
import scheduler
import prefetch
import database
import asyncio
import logging
import os

# Show our INFO-level sync/prefetch logs (Python defaults to WARNING otherwise).
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
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
    await database.close()


app = FastAPI(title="Show Recommendation App", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

_routers = (recommendations, upcoming, status, details, watched,
            ai_recommendations, library, profiles, requests, setup, stats)

# Root paths (e.g. /watched) — used by the Vite dev server and the Docker nginx,
# both of which strip the /api prefix before forwarding here.
for _r in _routers:
    app.include_router(_r.router)

# Mirror every router under /api so a single uvicorn process can serve both the
# API and the built frontend with no reverse proxy (native / Raspberry Pi deploy).
for _r in _routers:
    app.include_router(_r.router, prefix="/api")


@app.post("/cache/refresh")
async def manual_refresh():
    """Manually trigger a full cache refresh."""
    asyncio.create_task(prefetch.refresh_all())
    return {"status": "refresh started in background"}


@app.get("/cache/status")
async def cache_status():
    """Show what's in the SQLite cache and how old it is."""
    return await database.get_cache_stats()


# Serve the built single-page app when frontend/dist exists (produced by
# `npm run build`). With no build present we fall back to the JSON API root so
# the dev server / Docker setup are unaffected.
FRONTEND_DIST = (Path(__file__).parent.parent / "frontend" / "dist").resolve()

if FRONTEND_DIST.is_dir():
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Never let the SPA fallback swallow an unmatched API/cache call.
        if full_path.startswith(("api/", "cache/")):
            raise HTTPException(status_code=404)
        candidate = (FRONTEND_DIST / full_path).resolve()
        # Serve a real build artifact (JS/CSS/images) when one exists…
        if full_path and FRONTEND_DIST in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        # …otherwise hand back index.html so client-side routing works.
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def root():
        return {"message": "Show Recommendation API", "docs": "/docs"}
