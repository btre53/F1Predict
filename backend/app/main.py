"""F1Predict FastAPI application entrypoint.

Run locally:  uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.config import get_settings

settings = get_settings()
log = logging.getLogger("f1predict")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the weekly post-race refresh scheduler when enabled.

    Disabled by default (F1P_REFRESH_ENABLED) so dev/tests never hit FastF1. When
    on, a BackgroundScheduler runs app.etl.refresh off the event loop after race
    weekends — pulling new races, recalibrating, and busting caches. This is the
    "don't forget to update the model" job, shipped inside the app.
    """
    scheduler = None
    if settings.refresh_enabled:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        from app.etl.refresh import refresh

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            refresh,
            CronTrigger(
                day_of_week=settings.refresh_day_of_week, hour=settings.refresh_hour
            ),
            id="post_race_refresh",
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        log.info(
            "Post-race refresh scheduled: %s %02d:00 UTC",
            settings.refresh_day_of_week,
            settings.refresh_hour,
        )
    ws_mgr = None
    if settings.live_ws_enabled:
        from app.etl.clob_ws import get_manager

        ws_mgr = get_manager()
        ws_mgr.start()
        log.info("Live CLOB WebSocket feed enabled")
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        if ws_mgr is not None:
            await ws_mgr.stop()


app = FastAPI(
    title="F1Predict API",
    version=__version__,
    description=(
        "Stochastic F1 race simulation, prediction, replay and strategy "
        "evaluation. See docs/science/ for the models."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root() -> dict:
    return {"service": settings.app_name, "version": __version__, "docs": "/docs"}
