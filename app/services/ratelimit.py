"""
Simple sliding-window rate limiter for /api/v1/ping
100 requests per 10 seconds per IP.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

from app.utils.errors import error_body

# ip → deque of timestamps
_hits: dict[str, deque[float]] = defaultdict(deque)
WINDOW = 10.0          # seconds
LIMIT = 100


def check_rate_limit(request: Request) -> JSONResponse | None:
    """
    Returns a 429 response if rate limited, otherwise None.
    """
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    q = _hits[ip]

    # Drop old timestamps
    while q and now - q[0] > WINDOW:
        q.popleft()

    if len(q) >= LIMIT:
        retry_after = int(WINDOW - (now - q[0])) + 1
        return JSONResponse(
            status_code=429,
            content=error_body("RATE_LIMITED", "Too many requests"),
            headers={"Retry-After": str(retry_after)},
        )

    q.append(now)
    return None