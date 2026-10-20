

"""Response and request shapes for the API (what JSON goes in and out)."""

from datetime import time
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanOut(BaseModel):
    """One reading plan, as the app sees it."""

    # Allow building this schema straight from a SQLAlchemy row
    model_config = ConfigDict(from_attributes=True)

    # Three fields id, name, and description, all required
    id: int
    name: str
    description: str


class UserCreate(BaseModel):
    """What a phone sends when it registers."""

    # Random ID the app makes on first launch
    device_id: str = Field(min_length=8, max_length=64)
    # A time zone name, e.g. "Africa/Lagos"
    timezone: str
    # When the reader wants their reminder, e.g. "05:30"
    wake_time: time
    # Which translation to read in, by code
    translation: str = "KJV"

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str) -> str:
        """Reject names that aren't real time zones, e.g. "Mars/Olympus"."""
        if value not in available_timezones():
            raise ValueError(f"unknown time zone: {value}")
        return value


class UserCreated(BaseModel):
    """The reply to a registration. This is the only time the token is ever sent."""

    id: int
    timezone: str
    wake_time: time
    token: str
