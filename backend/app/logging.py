from __future__ import annotations

import logging
import sys

import structlog

REDACTED_FIELDS = frozenset(
    {
        "api_key",
        "api_secret",
        "password",
        "passphrase",
        "jwt_secret",
        "token",
        "authorization",
    }
)


def _redact_sensitive(
    _logger: object,
    _method: str,
    event_dict: dict,
) -> dict:
    for key in event_dict:
        if key.lower() in REDACTED_FIELDS:
            event_dict[key] = "***REDACTED***"
    return event_dict


def setup_logging(log_level: str = "INFO", *, json_output: bool = True) -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _redact_sensitive,
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    for noisy in ("uvicorn.access", "asyncio", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
