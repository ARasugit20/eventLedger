"""Analytics SQL views and ingest attempt log.

What: dbt-style views over the events table plus ingest_attempts for duplicate rate.
Why: Answer business questions (volume, latency, duplicates) from SQL, not only infra metrics.
Apply: run via `make analytics-apply` or automatically on API startup.
"""
