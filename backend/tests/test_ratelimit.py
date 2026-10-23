

"""Tests for rate limiting."""

import pytest
from fastapi import HTTPException

from app.ratelimit import RateLimiter


class FakeClock:
    """A clock the test moves by hand, so no test has to wait."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


def test_allows_up_to_the_limit(clock):
    limiter = RateLimiter(limit=3, window_seconds=60, clock=clock)

    for _ in range(3):
        limiter.check("1.2.3.4")


def test_refuses_one_over_the_limit(clock):
    limiter = RateLimiter(limit=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.check("1.2.3.4")

    with pytest.raises(HTTPException) as refused:
        limiter.check("1.2.3.4")

    assert refused.value.status_code == 429
    assert refused.value.headers["Retry-After"] == "60"


def test_allows_again_once_the_window_slides_on(clock):
    limiter = RateLimiter(limit=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.check("1.2.3.4")

    clock.now += 61

    limiter.check("1.2.3.4")


def test_retry_after_counts_down(clock):
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.check("1.2.3.4")
    clock.now += 45

    with pytest.raises(HTTPException) as refused:
        limiter.check("1.2.3.4")

    assert refused.value.headers["Retry-After"] == "15"


def test_each_client_has_its_own_allowance(clock):
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.check("1.2.3.4")

    limiter.check("5.6.7.8")


def test_sixth_signup_in_an_hour_is_429(client, world):
    def sign_up(number):
        return client.post(
            "/users",
            json={
                "device_id": f"ratelimit-device-{number}",
                "timezone": "Africa/Lagos",
                "wake_time": "06:00",
                "translation": "TST",
            },
        )

    for number in range(5):
        assert sign_up(number).status_code == 201

    refused = sign_up(5)

    assert refused.status_code == 429
    assert "Retry-After" in refused.headers
