from __future__ import annotations

import contextlib
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
from app.core.data.collector import DataCollector
from app.core.data.state import StateStore
from app.core.data.ws_feed import WebSocketFeedManager
from app.core.database import engine, get_db_session_factory
from app.core.exchange.factory import create_all_connectors
from app.core.execution.paper import PaperExecutor
from app.core.redis import close_redis, get_redis
from app.core.risk.circuit_breaker import CircuitBreaker
from app.core.risk.limits import RiskLimits
from app.core.risk.manager import PortfolioSnapshot, RiskManager
from app.core.strategy.carry import CarryStrategy
from app.core.strategy.funding_arb import FundingArbStrategy
from app.core.strategy.grid import GridStrategy
from app.logging import setup_logging
from app.services.event_logger import EventLogger
from app.services.funding_loop import FundingPaymentLoop
from app.services.multi_scheduler import MultiStrategyScheduler
from app.services.notifier import TelegramNotifier

logger = structlog.get_logger(__name__)

_collector: DataCollector | None = None
_scheduler: MultiStrategyScheduler | None = None
_paper_executor: PaperExecutor | None = None
_funding_loop: FundingPaymentLoop | None = None
_ws_feed: WebSocketFeedManager | None = None
_notifier: TelegramNotifier | None = None


def get_paper_executor() -> PaperExecutor | None:
    return _paper_executor


def get_notifier() -> TelegramNotifier | None:
    return _notifier


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    global _collector, _scheduler, _paper_executor, _funding_loop, _ws_feed, _notifier
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

    state = StateStore(redis=r)
    await state.set_bot_status("starting")

    _notifier = TelegramNotifier()
    await _notifier.start()

    try:
        connectors = await create_all_connectors()
        logger.info("exchanges_connected", exchanges=list(connectors.keys()))
    except Exception:
        logger.warning("exchange_connect_partial", exc_info=True)
        connectors = {}

    if connectors:
        db_factory = get_db_session_factory()
        event_logger = EventLogger(db_session_factory=db_factory)

        _collector = DataCollector(
            connectors=connectors,
            state=state,
            symbols=settings.watched_symbols_list,
            db_session_factory=db_factory,
        )
        await _collector.start()
        logger.info("data_collector_started")

        _ws_feed = WebSocketFeedManager(state=state, symbols=settings.watched_symbols_list)
        await _ws_feed.start()
        logger.info("ws_feed_started")

        limits = RiskLimits(
            max_exposure_per_exchange=settings.max_exposure_per_exchange,
            max_exposure_per_pair=settings.max_exposure_per_pair,
            max_daily_drawdown=settings.max_daily_drawdown,
            max_daily_drawdown_hard=settings.max_daily_drawdown_hard,
        )
        breaker = CircuitBreaker(limits)
        risk_manager = RiskManager(limits=limits, circuit_breaker=breaker)

        paper_capital = 10_000.0
        risk_manager.update_portfolio(PortfolioSnapshot(total_capital=paper_capital))

        funding_strategy = FundingArbStrategy(
            symbols=settings.watched_symbols_list,
            entry_threshold=settings.funding_rate_entry_threshold,
            exit_threshold=settings.funding_rate_exit_threshold,
            min_score=settings.min_opportunity_score,
        )
        grid_strategy = GridStrategy(symbols=settings.watched_symbols_list)
        carry_strategy = CarryStrategy(symbols=settings.watched_symbols_list)

        _paper_executor = PaperExecutor(state=state)

        _funding_loop = FundingPaymentLoop(
            executor=_paper_executor,
            state=state,
            db_session_factory=db_factory,
            interval_seconds=settings.funding_loop_interval_seconds,
            event_logger=event_logger,
        )
        await _funding_loop.start()
        logger.info("funding_loop_started")

        _scheduler = MultiStrategyScheduler(
            funding_strategy=funding_strategy,
            grid_strategy=grid_strategy,
            carry_strategy=carry_strategy,
            risk_manager=risk_manager,
            executor=_paper_executor,
            state=state,
            event_logger=event_logger,
        )
        await _scheduler.start()
        logger.info(
            "multi_scheduler_started",
            paper_capital=paper_capital,
            strategies=["funding_arb", "grid", "carry"],
        )
    else:
        await state.set_bot_status("idle", reason="no_exchange_connectors")
        logger.warning("no_connectors_available")

    yield

    logger.info("bot_shutting_down")
    if _scheduler and _scheduler.is_running:
        await _scheduler.stop()
    if _funding_loop and _funding_loop.is_running:
        await _funding_loop.stop()
    if _ws_feed and _ws_feed.is_running:
        await _ws_feed.stop()
    if _collector and _collector.is_running:
        await _collector.stop()
    if _notifier and _notifier.is_running:
        await _notifier.stop()

    for conn in connectors.values():
        with contextlib.suppress(Exception):
            await conn.disconnect()

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
