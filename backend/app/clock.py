

"""Dates and times as the reader sees them, in their own time zone."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def local_today(timezone: str, now: datetime | None = None) -> date:
    """Today's date where the reader lives. In Lagos it may already be tomorrow."""
    # "now" can be passed in, so tests can pick a moment; otherwise use the real time
    now = now or datetime.now(UTC)
    return now.astimezone(ZoneInfo(timezone)).date()
