"""FastAPI HTTP API — routes, middleware, and error handlers.

What: Exposes POST/GET /events, /health, and /metrics.
Why: Thin layer that validates JSON, calls services, and returns HTTP status codes.
Key routes: ingest_event (201 new / 200 duplicate), get_event, list_all_events, health.
"""

import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.exceptions import IdempotencyConflictError
from app.metrics import events_ingested_total
from app.models import EventStatus
from app.schemas import EventCreate, EventListResponse, EventResponse, HealthResponse
from app.services.events import create_event, get_event_by_id, list_events, refresh_pending_gauge
from app.services.idempotency import get_redis

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":%(message)s}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="EventLedger",
    description="Idempotent event ingestion and async processing API",
    version="1.0.0",
    lifespan=lifespan,
)

# Prometheus scrapes this path; separate from business routes.
app.mount("/metrics", make_asgi_app())


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        '{"path":"%s","method":"%s","status_code":%s,"latency_ms":%s}',
        request.url.path,
        request.method,
        response.status_code,
        latency_ms,
    )
    return response


@app.exception_handler(IdempotencyConflictError)
async def idempotency_conflict_handler(request: Request, exc: IdempotencyConflictError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    from sqlalchemy import text

    db_status = "ok"
    redis_status = "ok"

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        refresh_pending_gauge(db)
        db.close()
    except Exception:
        db_status = "error"

    try:
        get_redis().ping()
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=overall, database=db_status, redis=redis_status)


@app.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def ingest_event(body: EventCreate, response: Response, db: Session = Depends(get_db)):
    start = time.perf_counter()
    event, is_duplicate = create_event(db, body)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)

    # Track new vs duplicate ingests for dashboards and alerting.
    events_ingested_total.labels(result="duplicate" if is_duplicate else "new").inc()

    logger.info(
        '{"event_id":"%s","idempotency_key":"%s","duplicate":%s,"latency_ms":%s}',
        event.id,
        event.idempotency_key,
        str(is_duplicate).lower(),
        latency_ms,
    )
    if is_duplicate:
        response.status_code = status.HTTP_200_OK
    return event


@app.get("/events/{event_id}", response_model=EventResponse)
def get_event(event_id: UUID, db: Session = Depends(get_db)):
    event = get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


@app.get("/events", response_model=EventListResponse)
def list_all_events(
    status_filter: EventStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = list_events(db, status=status_filter, limit=limit, offset=offset)
    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
