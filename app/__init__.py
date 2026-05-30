"""EventLedger application package.

EventLedger accepts business events over HTTP, deduplicates them, stores an audit
trail in PostgreSQL, and processes them asynchronously via a Redis Stream worker.
"""
