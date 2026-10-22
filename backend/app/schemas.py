

"""Response and request shapes for the API (what JSON goes in and out)."""

from datetime import date, datetime, time
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator


def check_timezone(value: str) -> str:
    """Reject names that aren't real time zones, e.g. "Mars/Olympus". Shared by the schemas."""
    if value not in available_timezones():
        raise ValueError(f"unknown time zone: {value}")
    return value


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
        return check_timezone(value)


class UserCreated(BaseModel):
    """The reply to a registration. This is the only time the token is ever sent."""

    id: int
    timezone: str
    wake_time: time
    token: str


class UserOut(BaseModel):
    """A reader's own settings, as the app sees them. Never includes the token."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    timezone: str
    wake_time: time


class UserUpdate(BaseModel):
    """What a phone may change about its reader. Every field is optional: send only what changes."""

    timezone: str | None = None
    wake_time: time | None = None

    @field_validator("timezone")
    @classmethod
    def timezone_must_exist(cls, value: str | None) -> str | None:
        return value if value is None else check_timezone(value)

class UserPlanCreate(BaseModel):
    """What a phone sends to start a reading plan."""

    plan_id: int


class UserPlanOut(BaseModel):
    """One reader's enrolment in one plan."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    start_date: date
    current_day: int


class VerseOut(BaseModel):
    """One verse of today's passage."""

    model_config = ConfigDict(from_attributes=True)

    chapter: int
    verse: int
    text: str


class TodayOut(BaseModel):
    """This morning's reading: where the reader is in their plan, and the passage itself."""

    plan_name: str
    day_number: int
    total_days: int
    # True once every day of the plan has been read; then there is no passage
    completed: bool
    # e.g. "John 3:16-21". Empty when the plan is completed.
    reference: str | None = None
    verses: list[VerseOut] = []


class ReadingOut(BaseModel):
    """One sitting with one day's passage."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_day_id: int
    opened_at: datetime
    # Empty until the reader finishes ###DO NOT DELETE None ###
    completed_at: datetime | None
