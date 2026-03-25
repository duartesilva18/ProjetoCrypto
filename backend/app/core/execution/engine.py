"""Execution engine: routes signals to the correct executor (paper/live).

Provides a unified interface regardless of execution mode.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod

import structlog

from app.core.strategy.signals import Signal, SignalType

logger = structlog.get_logger(__name__)


class ExecutionMode(enum.StrEnum):
    PAPER = "paper"
    LIVE = "live"


class ExecutionResult:
    """Outcome of executing a signal."""

    __slots__ = ("success", "position_id", "mode", "error", "details")

    def __init__(
        self,
        success: bool,
        position_id: str = "",
        mode: str = "paper",
        error: str = "",
        details: dict | None = None,
    ) -> None:
        self.success = success
        self.position_id = position_id
        self.mode = mode
        self.error = error
        self.details = details or {}


class BaseExecutor(ABC):
    """Interface that both PaperExecutor and LiveExecutor implement."""

    @abstractmethod
    async def execute_entry(self, signal: Signal) -> ExecutionResult:
        """Open a new hedged position."""

    @abstractmethod
    async def execute_exit(self, signal: Signal) -> ExecutionResult:
        """Close an existing position."""

    @abstractmethod
    def get_open_positions(self) -> list[dict]:
        """Return all open positions as dicts."""

    async def execute(self, signal: Signal) -> ExecutionResult:
        if signal.type == SignalType.ENTRY:
            return await self.execute_entry(signal)
        if signal.type == SignalType.EXIT:
            return await self.execute_exit(signal)
        return ExecutionResult(success=True, mode="hold")
