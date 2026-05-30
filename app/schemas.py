"""Pydantic schemas for API request/response bodies.

What: Validated JSON shapes for POST /events and GET responses.
Why: FastAPI uses these to validate input and document OpenAPI automatically.
Key types: EventCreate (ingest body), EventResponse (single event), HealthResponse.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import EventStatus


class EventCreate(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    event_type: str = Field(..., min_length=1, max_length=128)
    payload: dict


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    idempotency_key: str
    event_type: str
    payload: dict
    status: EventStatus
    result: dict | None
    error_message: str | None
    created_at: datetime
    processed_at: datetime | None


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
