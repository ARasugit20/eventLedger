import importlib
import os
import subprocess
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

os.environ.setdefault("LOG_LEVEL", "WARNING")

USE_EXTERNAL = os.environ.get("USE_EXTERNAL_SERVICES") == "1"


def _reload_app_modules():
    import app.config
    import app.db
    import app.services.idempotency as idempotency

    importlib.reload(app.config)
    importlib.reload(app.db)
    idempotency._redis_client = None


@pytest.fixture(scope="session")
def postgres_url():
    if USE_EXTERNAL:
        url = os.environ.get(
            "DATABASE_URL",
            "postgresql://eventledger:eventledger@localhost:5432/eventledger",
        )
        os.environ["DATABASE_URL"] = url
        yield url
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as postgres:
        os.environ["DATABASE_URL"] = postgres.get_connection_url()
        yield os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def redis_url():
    if USE_EXTERNAL:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        os.environ["REDIS_URL"] = url
        yield url
        return

    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as redis_container:
        host = redis_container.get_container_host_ip()
        port = redis_container.get_exposed_port(6379)
        os.environ["REDIS_URL"] = f"redis://{host}:{port}/0"
        yield os.environ["REDIS_URL"]


@pytest.fixture(scope="session")
def app_engine(postgres_url, redis_url):
    _reload_app_modules()
    from app.config import settings
    from app.db import Base

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=os.environ.copy(),
    )
    engine = create_engine(settings.database_url)
    from analytics.apply import apply_analytics_views

    apply_analytics_views(engine)
    yield engine
    if not USE_EXTERNAL:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def clean_state(app_engine, redis_url):
    from app.services.idempotency import get_redis

    _reload_app_modules()
    with app_engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE ingest_attempts RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE events RESTART IDENTITY CASCADE"))
        conn.commit()
    get_redis().flushdb()
    yield


@pytest.fixture
def client(app_engine):
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def sample_event():
    return {
        "idempotency_key": "order-8821-create",
        "event_type": "order.created",
        "payload": {"sku": "X1", "quantity": 2, "customer_id": "c-99"},
    }
