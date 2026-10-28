

"""Structured logs: one JSON line per request, easy for people and machines to search."""

import json
import logging
import time
from datetime import UTC, datetime

from fastapi import Request

logger = logging.getLogger("morning_manna")

# Extra fields a log line may carry, beyond time, level and message
FIELDS = ("method", "path", "status", "duration_ms", "error")


class JsonFormatter(logging.Formatter):
    """Turn a log record into one line of JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        entry.update({field: getattr(record, field) for field in FIELDS if hasattr(record, field)})
        return json.dumps(entry)


def configure_logging() -> None:
    """Send our logs to the terminal as JSON lines. Safe to call more than once."""
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


async def log_requests(request: Request, call_next):
    """Log every request: what was asked, how it ended, and how long it took.

    Only the method and path are logged, never headers or the query string,
    so a reader's token can never end up in the logs.
    """
    start = time.perf_counter()
    status = 500  # If the endpoint crashes, the request still gets a log line
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
