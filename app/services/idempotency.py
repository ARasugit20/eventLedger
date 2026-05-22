import redis

from app.config import settings

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def claim_idempotency_key(key: str) -> bool:
    """Redis SET NX — fast dedupe before DB insert. May expire before DB row exists."""
    client = get_redis()
    return bool(
        client.set(
            f"idempotency:{key}",
            "1",
            nx=True,
            ex=settings.idempotency_ttl_seconds,
        )
    )


def release_idempotency_key(key: str) -> None:
    get_redis().delete(f"idempotency:{key}")
