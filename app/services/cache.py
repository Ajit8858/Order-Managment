import json
from typing import Any, Optional

from app.config import settings
from app.redis_client import redis_client

PRODUCT_KEY_PREFIX = "product:"
PRODUCT_LIST_PREFIX = "product_list:"


async def get_cached(key: str) -> Optional[Any]:
    raw = await redis_client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


async def set_cached(key: str, value: Any, ttl: int = settings.PRODUCT_CACHE_TTL_SECONDS) -> None:
    await redis_client.set(key, json.dumps(value, default=str), ex=ttl)


async def invalidate_product_cache(product_id: Optional[str] = None) -> None:
    """Invalidate a single product entry and every cached product listing page,
    since stock/price changes can affect any filtered/sorted page."""
    if product_id:
        await redis_client.delete(f"{PRODUCT_KEY_PREFIX}{product_id}")

    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor=cursor, match=f"{PRODUCT_LIST_PREFIX}*", count=100)
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0:
            break
