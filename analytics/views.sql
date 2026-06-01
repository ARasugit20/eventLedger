-- ============================================================
-- EventLedger Analytics Layer
-- Business questions answered from SQL (dbt mart-style views)
--
-- Schema note: `events` stores one row per unique idempotency_key.
-- Duplicate HTTP retries are logged in `ingest_attempts` (append-only).
-- ============================================================

CREATE SCHEMA IF NOT EXISTS analytics;

-- Append-only log of every POST /events attempt (new + duplicate).
CREATE TABLE IF NOT EXISTS ingest_attempts (
    id          BIGSERIAL PRIMARY KEY,
    idempotency_key VARCHAR(255) NOT NULL,
    event_type  VARCHAR(128) NOT NULL,
    was_duplicate BOOLEAN NOT NULL DEFAULT FALSE,
    http_status SMALLINT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_ingest_attempts_event_type ON ingest_attempts (event_type);
CREATE INDEX IF NOT EXISTS ix_ingest_attempts_created_at ON ingest_attempts (created_at);

-- 1. Daily ingest volume
-- Q: How many events per day, and what is the failure rate?
CREATE OR REPLACE VIEW analytics_daily_ingest AS
SELECT
    DATE_TRUNC('day', created_at) AS ingest_date,
    COUNT(*) AS total_events,
    COUNT(*) FILTER (WHERE status = 'processed') AS processed,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    COUNT(*) FILTER (WHERE status IN ('received', 'processing')) AS pending,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'failed')::numeric
        / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS failure_rate_pct
FROM events
GROUP BY 1
ORDER BY 1 DESC;

-- 2. Duplicate rate by event type (from ingest attempt log)
-- Q: Which event types see the most idempotency retries?
CREATE OR REPLACE VIEW analytics_duplicate_rate AS
SELECT
    event_type,
    COUNT(*) AS total_attempts,
    COUNT(*) FILTER (WHERE was_duplicate) AS duplicate_attempts,
    COUNT(*) FILTER (WHERE NOT was_duplicate) AS new_attempts,
    COUNT(DISTINCT idempotency_key) AS unique_idempotency_keys,
    ROUND(
        COUNT(*) FILTER (WHERE was_duplicate)::numeric
        / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS duplicate_rate_pct
FROM ingest_attempts
GROUP BY 1
ORDER BY duplicate_rate_pct DESC;

-- 3. Processing latency percentiles by event type
-- Q: What is p50/p95/p99 processing time?
CREATE OR REPLACE VIEW analytics_processing_latency AS
SELECT
    event_type,
    COUNT(*) FILTER (WHERE status = 'processed') AS processed_count,
    ROUND(
        (PERCENTILE_CONT(0.50) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (processed_at - created_at))
        ))::numeric,
        3
    ) AS p50_seconds,
    ROUND(
        (PERCENTILE_CONT(0.95) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (processed_at - created_at))
        ))::numeric,
        3
    ) AS p95_seconds,
    ROUND(
        (PERCENTILE_CONT(0.99) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (processed_at - created_at))
        ))::numeric,
        3
    ) AS p99_seconds,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (processed_at - created_at)))::numeric,
        3
    ) AS avg_seconds
FROM events
WHERE status = 'processed'
  AND processed_at IS NOT NULL
GROUP BY 1
ORDER BY p95_seconds DESC NULLS LAST;

-- 4. Event type breakdown (last 7 days)
-- Q: What is the event mix and daily trend by type?
CREATE OR REPLACE VIEW analytics_event_type_summary AS
SELECT
    event_type,
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*) AS event_count,
    COUNT(*) FILTER (WHERE status = 'processed') AS success_count,
    COUNT(*) FILTER (WHERE status = 'failed') AS failure_count
FROM events
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY 1, 2
ORDER BY 1, 2 DESC;

-- 5. System health KPIs (single-row snapshot)
-- Q: What is the current state of the ingestion system?
CREATE OR REPLACE VIEW analytics_system_health AS
SELECT
    COUNT(*) AS total_events_all_time,
    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS events_last_24h,
    COUNT(*) FILTER (WHERE status = 'processed') AS total_processed,
    COUNT(*) FILTER (WHERE status = 'failed') AS total_failed,
    COUNT(*) FILTER (WHERE status IN ('received', 'processing')) AS currently_pending,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'processed')::numeric
        / NULLIF(COUNT(*), 0) * 100,
        2
    ) AS overall_success_rate_pct,
    ROUND(
        (PERCENTILE_CONT(0.95) WITHIN GROUP (
            ORDER BY EXTRACT(EPOCH FROM (processed_at - created_at))
        ) FILTER (WHERE status = 'processed' AND processed_at IS NOT NULL))::numeric,
        3
    ) AS p95_latency_seconds
FROM events;
