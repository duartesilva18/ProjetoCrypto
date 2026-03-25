"""Telegram notification service for key bot events.

Sends alerts via the Telegram Bot API for:
- Position opened / closed
- Funding payment applied
- Circuit breaker triggered
- Errors and critical events
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

_MAX_MESSAGE_LENGTH = 4000


class TelegramNotifier:
    """Async Telegram bot notifier."""

    def __init__(
        self,
        bot_token: str = "",
        chat_id: str = "",
    ) -> None:
        settings = get_settings()
        self._token = bot_token or getattr(settings, "telegram_bot_token", "")
        self._chat_id = chat_id or getattr(settings, "telegram_chat_id", "")
        self._client: httpx.AsyncClient | None = None
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._chat_id)

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if not self.is_configured:
            logger.info("telegram_not_configured")
            return
        self._client = httpx.AsyncClient(timeout=10.0)
        self._running = True
        self._task = asyncio.create_task(self._send_loop(), name="telegram_notifier")
        logger.info("telegram_notifier_started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        logger.info("telegram_notifier_stopped")

    async def send(self, message: str) -> None:
        """Queue a message for sending."""
        if not self.is_configured:
            return
        truncated = message[:_MAX_MESSAGE_LENGTH]
        try:
            self._queue.put_nowait(truncated)
        except asyncio.QueueFull:
            logger.warning("telegram_queue_full")

    async def notify_position_opened(
        self, exchange: str, symbol: str, side: str, size_usd: float, rate: float
    ) -> None:
        msg = (
            f"📈 *Position Opened*\n"
            f"Exchange: `{exchange}`\n"
            f"Symbol: `{symbol}`\n"
            f"Side: `{side}`\n"
            f"Size: `${size_usd:,.2f}`\n"
            f"Rate: `{rate:.6f}`"
        )
        await self.send(msg)

    async def notify_position_closed(
        self, exchange: str, symbol: str, funding_collected: float
    ) -> None:
        msg = (
            f"📉 *Position Closed*\n"
            f"Exchange: `{exchange}`\n"
            f"Symbol: `{symbol}`\n"
            f"Funding collected: `${funding_collected:,.4f}`"
        )
        await self.send(msg)

    async def notify_funding_payment(
        self, exchange: str, symbol: str, payment: float, total: float
    ) -> None:
        msg = (
            f"💰 *Funding Payment*\n"
            f"Exchange: `{exchange}`\n"
            f"Symbol: `{symbol}`\n"
            f"Payment: `${payment:,.6f}`\n"
            f"Total collected: `${total:,.4f}`"
        )
        await self.send(msg)

    async def notify_circuit_breaker(self, reason: str) -> None:
        msg = f"🚨 *Circuit Breaker Triggered*\nReason: `{reason}`"
        await self.send(msg)

    async def notify_error(self, component: str, error: str) -> None:
        msg = f"⚠️ *Error*\nComponent: `{component}`\nError: `{error}`"
        await self.send(msg)

    async def _send_loop(self) -> None:
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        while self._running:
            try:
                message = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            if self._client is None:
                continue

            try:
                resp = await self._client.post(
                    url,
                    json={
                        "chat_id": self._chat_id,
                        "text": message,
                        "parse_mode": "Markdown",
                    },
                )
                if resp.status_code != 200:
                    logger.warning("telegram_send_failed", status=resp.status_code)
            except Exception as exc:
                logger.warning("telegram_send_error", error=str(exc))

            await asyncio.sleep(0.1)
