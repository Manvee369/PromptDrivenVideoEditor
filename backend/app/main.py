"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_jobs import router as jobs_router
from app.core.config import settings
from app.core.logger import get_logger
from app.jobs.janitor import start_periodic_sweep

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan: spin up the disk janitor on startup, cancel it on shutdown."""
    janitor_task = await start_periodic_sweep()
    try:
        yield
    finally:
        if janitor_task is not None:
            janitor_task.cancel()
            try:
                await janitor_task
            except Exception:
                pass


app = FastAPI(
    title="Prompt-Driven Video Editor",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — origins are configured via PDVE_ALLOWED_ORIGINS_CSV (comma-separated).
# Defaults to localhost:3000 for the dev frontend; never run with "*" in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job pipeline routes
app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])


@app.get("/health")
def health():
    return {"status": "ok"}
