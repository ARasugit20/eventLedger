from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://eventledger:eventledger@localhost:5432/eventledger"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    event_stream: str = "eventledger:stream"
    consumer_group: str = "eventledger-workers"
    idempotency_ttl_seconds: int = 86400


settings = Settings()
