"""One logging setup for the whole backend (standard library logging)."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

# Libraries that are too chatty at INFO.
_QUIET_LOGGERS = ("httpx", "httpcore", "openai", "sqlalchemy.engine")


def setup_logging(level: str = "INFO") -> None:
    # Adds a console handler only if none exists yet (keeps handlers from uvicorn, pytest, VS Code).
    logging.basicConfig(format=LOG_FORMAT)
    logging.getLogger().setLevel(level)
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
