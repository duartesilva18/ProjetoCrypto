from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_redis

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: DbDep) -> dict:
    checks: dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("readiness_check_failed", component="database", error=str(exc))
        checks["database"] = "error"

    try:
        r = await get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        logger.error("readiness_check_failed", component="redis", error=str(exc))
        checks["redis"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
