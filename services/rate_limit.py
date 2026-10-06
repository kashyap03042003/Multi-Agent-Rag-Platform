import logging
import time
from functools import lru_cache
import redis
from config.settings import settings

logger = logging.getLogger(__name__)
WINDOW_SECONDS = 60


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, socket_timeout=2)


def allow(client_id: str) -> bool:
    if not settings.redis_url:
        return True
    key = f"ratelimit:{client_id}:{int(time.time() // WINDOW_SECONDS)}"
    try:
        pipe = get_redis().pipeline()
        pipe.incr(key)
        pipe.expire(key, WINDOW_SECONDS, nx=True)
        count, _ = pipe.execute()
    except redis.RedisError:
        # Fail open: a limiter outage should not take the product down.
        logger.exception("Rate limiter unavailable; allowing request")
        return True
    return count <= settings.rate_limit_per_minute
