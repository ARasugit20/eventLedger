"""Scheduled DLQ health sweep for EventLedger.

What: Calls the API analytics endpoint and logs durable DLQ stats.
Why: Surfaces poison-message backlog on a fixed cadence without touching ingestion.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import httpx
from airflow import DAG
from airflow.operators.python import PythonOperator

logger = logging.getLogger(__name__)

API_URL = os.environ.get("EVENTLEDGER_API_URL", "http://api:8000")
MAX_OLDEST_AGE_SECONDS = float(os.environ.get("DLQ_MAX_OLDEST_AGE_SECONDS", "86400"))


def dlq_health_sweep() -> dict:
    """Fetch DLQ analytics and fail when the API is unreachable or age exceeds threshold."""
    response = httpx.get(f"{API_URL}/analytics/dlq", timeout=30.0)
    response.raise_for_status()
    stats = response.json()
    count = int(stats.get("count", 0))
    oldest_age = float(stats.get("oldest_item_age_seconds", 0.0))
    logger.info(
        "DLQ health sweep: count=%s oldest_age_seconds=%s",
        count,
        oldest_age,
    )
    if count > 0 and oldest_age > MAX_OLDEST_AGE_SECONDS:
        raise RuntimeError(
            f"DLQ oldest item age {oldest_age}s exceeds threshold {MAX_OLDEST_AGE_SECONDS}s"
        )
    return stats


with DAG(
    dag_id="eventledger_dlq_health_sweep",
    description="Poll durable DLQ analytics every five minutes",
    schedule="*/5 * * * *",
    start_date=datetime(2026, 1, 1, tzinfo=UTC),
    catchup=False,
    tags=["eventledger", "dlq"],
) as dag:
    PythonOperator(
        task_id="dlq_health_sweep",
        python_callable=dlq_health_sweep,
    )
