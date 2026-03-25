"""Bot control endpoints: start, stop, emergency stop, config."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import AuthDep
from app.core.data.state import StateStore
from app.core.redis import get_redis

router = APIRouter(prefix="/api/v1/bot", tags=["controls"])


class ConfigUpdate(BaseModel):
    funding_rate_entry_threshold: float | None = None
    funding_rate_exit_threshold: float | None = None
    min_opportunity_score: float | None = None
    max_exposure_per_exchange: float | None = None
    max_exposure_per_pair: float | None = None
    max_daily_drawdown: float | None = None


async def _get_state() -> StateStore:
    r = await get_redis()
    return StateStore(redis=r)


StateDep = Annotated[StateStore, Depends(_get_state)]


@router.get("/status")
async def get_bot_status(_auth: AuthDep, state: StateDep) -> dict:
    """Get current bot status."""
    status_data = await state.get_bot_status()
    return {"status": status_data or {"status": "unknown"}}


@router.post("/start")
async def start_bot(_auth: AuthDep, state: StateDep) -> dict:
    """Start the trading bot.

    In production this would trigger the scheduler. Currently
    sets state to 'running' -- the scheduler reads this on its loop.
    """
    await state.set_bot_status("running")
    return {"message": "Bot start signal sent", "status": "running"}


@router.post("/stop")
async def stop_bot(_auth: AuthDep, state: StateDep) -> dict:
    """Graceful stop: finish current cycle, then pause."""
    await state.set_bot_status("stopping")
    return {"message": "Bot stop signal sent", "status": "stopping"}


@router.post("/emergency-stop")
async def emergency_stop(_auth: AuthDep, state: StateDep) -> dict:
    """Immediate halt via circuit breaker."""
    await state.set_bot_status("emergency_stopped")
    return {
        "message": "Emergency stop triggered",
        "status": "emergency_stopped",
    }


@router.patch("/config")
async def update_config(
    _auth: AuthDep,
    body: ConfigUpdate,
    state: StateDep,
) -> dict:
    """Update runtime configuration.

    Only non-None fields are applied.
    In production this writes to Redis and the bot picks up
    changes on its next evaluation tick.
    """
    r = await get_redis()
    updates = body.model_dump(exclude_none=True)

    if updates:
        str_updates = {k: str(v) for k, v in updates.items()}
        await r.hset("bot:config", mapping=str_updates)

    current = await r.hgetall("bot:config")
    return {"message": "Config updated", "config": current}
