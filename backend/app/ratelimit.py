

"""Rate limiting: stop one client from flooding an endpoint."""

import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status


class RateLimiter:
    """Allow at most `limit` requests per `window_seconds` from each client.

    A sliding window: each client's recent request times are kept, and any older than
    the window are dropped before counting. Kept in memory, so it is per server process
    and resets on restart; several servers would share one store such as Redis instead.
    """

    def __init__(
        self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic
    ):
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        """Count one request from `key`, or refuse it with 429 if it is over the limit."""
        now = self.clock()
        hits = self.hits[key]
        # Forget requests that have slid out of the window
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            # Seconds until the oldest request leaves the window and a slot frees up
            retry_after = math.ceil(hits[0] + self.window_seconds - now)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "too many requests, try again later",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)

    def reset(self) -> None:
        """Forget every client (used between tests)."""
        self.hits.clear()


# Sign-ups: 5 per hour from one address is plenty for a real person
signup_limiter = RateLimiter(limit=5, window_seconds=3600)


def limit_signups(request: Request) -> None:
    """Dependency for POST /users: count the sign-up against the caller's address."""
    signup_limiter.check(request.client.host if request.client else "unknown")
