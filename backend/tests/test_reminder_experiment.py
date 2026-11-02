"""Tests for the reminder experiment: every reader gets group A or B, once, for good."""

from collections import Counter

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.experiment import VARIANTS, assign_variant
from app.models import Translation, User


@pytest.fixture
def translation(db):
    """A translation for test readers (CI's database starts empty)."""
    translation = Translation(code="TST", name="Test Translation", license="Public domain")
    db.add(translation)
    db.flush()
    return translation


def register(client, device_id="experiment-device-1"):
    """Sign up a test reader and return the reply."""
    return client.post(
        "/users",
        json={
            "device_id": device_id,
            "timezone": "Africa/Lagos",
            "wake_time": "06:00",
            "translation": "TST",
        },
    )


def test_a_new_reader_is_put_in_a_group(client, db, translation):
    reply = register(client).json()

    assert reply["reminder_variant"] in VARIANTS
    user = db.scalar(select(User).where(User.device_id == "experiment-device-1"))
    assert user.reminder_variant == reply["reminder_variant"]


def test_the_app_can_read_its_group(client, translation):
    reply = register(client).json()
    headers = {"Authorization": f"Bearer {reply['token']}"}

    me = client.get("/users/me", headers=headers).json()
    assert me["reminder_variant"] == reply["reminder_variant"]


def test_the_group_comes_from_the_coin(client, translation, monkeypatch):
    # Registration must use the coin flip, not pick a group of its own
    monkeypatch.setattr("app.routers.users.assign_variant", lambda: "B")

    assert register(client).json()["reminder_variant"] == "B"


def test_the_group_never_changes(client, translation):
    reply = register(client).json()
    headers = {"Authorization": f"Bearer {reply['token']}"}
    group = reply["reminder_variant"]
    other = "B" if group == "A" else "A"

    # Changing settings, even sending a group, leaves the group as it was
    change = {"wake_time": "05:15", "reminder_variant": other}
    client.patch("/users/me", json=change, headers=headers)

    assert client.get("/users/me", headers=headers).json()["reminder_variant"] == group


def test_the_coin_is_fair():
    flips = Counter(assign_variant() for _ in range(10_000))

    assert set(flips) == set(VARIANTS)
    # A fair coin lands within 300 of 5,000 heads in all but about 1 in 10^9 runs (6 sd)
    assert abs(flips["A"] - 5_000) < 300


def test_the_database_allows_only_a_or_b(db, translation):
    db.add(
        User(
            device_id="experiment-device-c",
            token_hash="c" * 64,
            timezone="Africa/Lagos",
            wake_time="06:00",
            translation_id=translation.id,
            reminder_variant="C",
        )
    )

    with pytest.raises(IntegrityError, match="users_reminder_variant_check"):
        db.flush()
