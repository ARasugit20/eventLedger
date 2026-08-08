"""Prometheus metrics for EventLedger observability.

What: Counters, histograms, and gauges exposed at GET /metrics.
Why: Lets you answer "how many events?", "how slow is processing?", "how big is the backlog?"
Key metrics:
  - events_ingested_total{result="new|duplicate"} — ingest volume
  - event_processing_duration_seconds — worker latency
  - events_pending_processing — count of events not yet processed
  - worker_processing_failures_total — permanent handler failures
  - worker_retries_total — transient retries before DLQ
  - dlq_messages_total — poison messages moved to DLQ stream
  - stream_pending_messages — Redis PEL depth
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
worker_processing_failures_total = Counter(
    "worker_processing_failures_total",
    "Permanent worker processing failures",
)
worker_retries_total = Counter(
    "worker_retries_total",
    "Transient worker retries before ack or DLQ",
)
dlq_messages_total = Counter(
    "dlq_messages_total",
    "Messages moved to the dead-letter stream",
)
stream_pending_messages = Gauge(
    "stream_pending_messages",
    "Redis stream pending entries for the consumer group",
)
