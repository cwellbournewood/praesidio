"""Structlog configuration. JSON in non-dev, key=value in dev."""
from __future__ import annotations

import logging

import structlog

from ..config import Settings


def configure_logging(settings: Settings) -> None:
    level = getattr(logging, settings.section_log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.dev.ConsoleRenderer()
        if settings.is_development
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger("section")
