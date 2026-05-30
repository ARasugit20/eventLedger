"""Prometheus metrics for EventLedger observability.

What: Counters, histograms, and gauges exposed at GET /metrics.
Why: Lets you answer "how many events?", "how slow is processing?", "how big is the backlog?"
Key metrics:
  - events_ingested_total{result="new|duplicate"} — ingest volume
  - event_processing_duration_seconds — worker latency
  - events_pending_processing — count of events not yet processed
"""

from prometheus_client import Counter, Gauge, Histogram

events_ingested_total = Counter(
    "events_ingested_total",
    "Events accepted by POST /events",
    ["result"],
)
event_processing_duration_seconds = Histogram(
    "event_processing_duration_seconds",
    "Time spent processing one event in the worker",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
events_pending_processing = Gauge(
    "events_pending_processing",
    "Events waiting in received or processing status",
)
