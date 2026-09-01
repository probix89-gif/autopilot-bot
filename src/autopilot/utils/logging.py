"""Logging configuration."""

import logging
import sys

from autopilot.config import get_settings

_settings = get_settings()


def setup_logging(level: str | None = None) -> None:
    log_level = (level or _settings.LOG_LEVEL or "INFO").upper()
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = [handler]
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)