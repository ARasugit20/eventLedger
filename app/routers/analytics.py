"""REST endpoints that expose analytics SQL views as JSON.

What: Read-only business KPIs from Postgres views (no ORM models changed).
Why: Lets dashboards and recruiters query duplicate rate, latency, volume without raw SQL.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _row_to_dict(row) -> dict:
    return dict(row._mapping)


@router.get("/health")
def system_health(db: Session = Depends(get_db)):
    """System health KPIs — single-row summary from analytics_system_health."""
    row = db.execute(text("SELECT * FROM analytics_system_health")).first()
    return _row_to_dict(row) if row else {}


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
