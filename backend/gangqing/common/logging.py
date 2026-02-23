from __future__ import annotations

import logging
from typing import Any

import structlog

from gangqing.common.redaction import redact_sensitive


def _drop_none_values(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    return {k: v for k, v in event_dict.items() if v is not None}


def _redact_event_dict(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    return redact_sensitive(event_dict)


def configure_logging(*, log_level: str, log_format: str) -> None:
    """Configure structlog for GangQing.

    Requirements:
    - JSON structured logs in production
    - Context propagation via contextvars (requestId/tenantId/projectId/...)
    - Redaction to avoid leaking secrets
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    logging.basicConfig(level=level)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        _redact_event_dict,
        _drop_none_values,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
