import redis
from config.settings import settings

STREAM = "ingest:events"
GROUP = "ingest-workers"
DLQ = "ingest:dlq"


def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=30)


def ensure_group(r: redis.Redis) -> None:
    try:
        r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def publish(r: redis.Redis, path: str, action: str) -> str:
    return r.xadd(STREAM, {"path": path, "action": action})
