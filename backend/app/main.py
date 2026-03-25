from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes.auth import router as auth_router
from app.api.routes.controls import router as controls_router
from app.api.routes.events import router as events_router
from app.api.routes.funding import router as funding_router
from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.positions import router as positions_router
from app.api.websocket import websocket_endpoint
from app.config import get_settings
from app.core.database import engine
from app.core.redis import close_redis, get_redis
from app.logging import setup_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_output=True)

    logger.info(
        "bot_starting",
        mode=settings.bot_mode,
        symbols=settings.watched_symbols_list,
    )

    r = await get_redis()
    await r.ping()
    logger.info("redis_connected")

    yield

    logger.info("bot_shutting_down")
    await close_redis()
    await engine.dispose()
    logger.info("bot_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_output=False)

    application = FastAPI(
        title="ProjetoCrypto - Funding Rate Arbitrage Bot",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ────────────────────────────────
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(funding_router)
    application.include_router(positions_router)
    application.include_router(metrics_router)
    application.include_router(events_router)
    application.include_router(controls_router)

    # ── WebSocket ─────────────────────────────
    application.add_api_websocket_route("/ws", websocket_endpoint)

    # ── Prometheus ────────────────────────────
    @application.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    # ── Middleware ─────────────────────────────
    @application.middleware("http")
    async def log_requests(request: Request, call_next):
        response = await call_next(request)
        if request.url.path not in ("/health", "/metrics"):
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
            )
        return response

    return application


app = create_app()
