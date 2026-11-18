import json
import logging
from typing import Any, Optional

from apps.api.config import settings

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore

_client = None


async def get_valkey():
    global _client
    if redis is None:
        logger.warning("redis library not installed, Valkey disabled")
        return None
    if _client is None:
        url = getattr(settings, "valkey_url", getattr(settings, "redis_url", "redis://localhost:6379/0"))
        try:
            _client = redis.from_url(url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
            await _client.ping()
            logger.info(f"Valkey connected at {url}")
        except Exception as e:
            logger.warning(f"Valkey unavailable at {url}: {e}")
            _client = None
    return _client


async def cache_get(key: str) -> Optional[Any]:
    client = await get_valkey()
    if not client:
        return None
    try:
        val = await client.get(key)
        if val:
            return json.loads(val)
    except Exception as e:
        logger.debug(f"cache_get failed {key}: {e}")
    return None


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    client = await get_valkey()
    if not client:
        return
    try:
        await client.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logger.debug(f"cache_set failed {key}: {e}")


async def cache_delete(pattern: str) -> None:
    client = await get_valkey()
    if not client:
        return
    try:
        # Use scan for pattern
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)
    except Exception:
        pass


async def acquire_lock(key: str, ttl: int = 60) -> bool:
    client = await get_valkey()
    if not client:
        return True  # If Valkey unavailable, allow job to run (no distributed lock)
    try:
        # SET NX with expiry
        result = await client.set(f"lock:{key}", "1", nx=True, ex=ttl)
        return bool(result)
    except Exception:
        return True


async def release_lock(key: str) -> None:
    client = await get_valkey()
    if not client:
        return
    try:
        await client.delete(f"lock:{key}")
    except Exception:
        pass
