"""Application settings loaded from environment variables.

What: Central config (database URL, Redis URL, stream names, TTLs).
Why: Keeps secrets and hostnames out of code; one place to read env vars.
Key export: `settings` singleton used by db, redis, worker, and API.
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def _settings_model_config() -> SettingsConfigDict:
    if os.environ.get("TESTING") == "1":
        return SettingsConfigDict(extra="ignore")
    return SettingsConfigDict(env_file=".env", extra="ignore")


class Settings(BaseSettings):
    model_config = _settings_model_config()

    database_url: str = "postgresql://eventledger:eventledger@localhost:5432/eventledger"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    event_stream: str = "eventledger:stream"
    dlq_stream: str = "eventledger:stream:dlq"
    consumer_group: str = "eventledger-workers"
    idempotency_ttl_seconds: int = 86400
    max_delivery_attempts: int = 3
    pending_idle_ms: int = 60000


settings = Settings()
