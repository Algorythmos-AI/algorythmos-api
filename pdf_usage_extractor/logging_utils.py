from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

_DEFAULT_FORMAT = "%Y-%m-%dT%H:%M:%S"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - thin wrapper
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, _DEFAULT_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.args and isinstance(record.args, dict):
            payload.update(record.args)
        for key in ("context", "extra"):
            value = getattr(record, key, None)
            if isinstance(value, dict):
                payload.update(value)
        return json.dumps(payload, ensure_ascii=True)


def _resolve_level(debug: bool) -> int:
    if debug:
        return logging.DEBUG
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def get_logger(debug: bool = False) -> logging.Logger:
    """Return a module-level logger configured for structured logging."""
    logger = logging.getLogger("pdf_usage_extractor")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(_resolve_level(debug))
    logger.propagate = False
    return logger
