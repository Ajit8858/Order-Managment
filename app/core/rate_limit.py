import time

from fastapi import HTTPException, Request, status

from app.config import settings
from app.redis_client import redis_client


async def rate_limiter(request: Request) -> None:
    """Simple fixed-window rate limiter keyed by client IP + route.

    Uses a Redis INCR + EXPIRE pair, which is O(1) and atomic enough for
    this purpose (a rare race just lets one extra request through).
    """
    client_ip = request.client.host if request.client else "unknown"
    window = int(time.time() // 60)  # 1-minute buckets
    key = f"ratelimit:{client_ip}:{request.url.path}:{window}"

    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, 60)

    if current > settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again shortly.",
        )
