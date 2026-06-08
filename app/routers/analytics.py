"""REST endpoints that expose analytics SQL views as JSON.

What: Read-only business KPIs from Postgres views (no ORM models changed).
Why: Lets dashboards and recruiters query duplicate rate, latency, volume without raw SQL.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])

DEFAULT_HEALTH = {
    "total_events_all_time": 0,
    "events_last_24h": 0,
    "total_processed": 0,
    "total_failed": 0,
    "currently_pending": 0,
    "overall_success_rate_pct": 0,
    "p95_latency_seconds": 0,
}


def _serialize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def _row_to_dict(row) -> dict[str, Any]:
    return {key: _serialize(val) for key, val in dict(row._mapping).items()}


@router.get("/health")
def system_health(db: Session = Depends(get_db)):
    """System health KPIs — single-row summary from analytics_system_health."""
    row = db.execute(text("SELECT * FROM analytics_system_health")).first()
    return _row_to_dict(row) if row else DEFAULT_HEALTH.copy()


@router.get("/duplicate-rate")
def duplicate_rate(db: Session = Depends(get_db)):
    """Duplicate retry rate by event type from ingest_attempts log."""
    rows = db.execute(text("SELECT * FROM analytics_duplicate_rate")).all()
    return [_row_to_dict(r) for r in rows]


@router.get("/latency")
def processing_latency(db: Session = Depends(get_db)):
    """Processing latency percentiles (p50/p95/p99) by event type."""
    rows = db.execute(text("SELECT * FROM analytics_processing_latency")).all()
    return [_row_to_dict(r) for r in rows]


@router.get("/daily-volume")
def daily_volume(db: Session = Depends(get_db)):
    """Daily ingest volume for the last 30 days."""
    rows = db.execute(
        text(
            """
            SELECT * FROM analytics_daily_ingest
            WHERE ingest_date >= NOW() - INTERVAL '30 days'
            ORDER BY ingest_date DESC
            """
        )
    ).all()
    return [_row_to_dict(r) for r in rows]
