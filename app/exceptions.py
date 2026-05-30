"""Custom exceptions for domain-specific HTTP errors.

What: IdempotencyConflictError when the same key is reused with a different body.
Why: Separates "duplicate OK" (200) from "key abuse" (409) for clear client behavior.
"""


class IdempotencyConflictError(Exception):
    """Same idempotency key reused with a different request body."""

    def __init__(self, idempotency_key: str):
        self.idempotency_key = idempotency_key
        super().__init__(f"Idempotency key '{idempotency_key}' already used with different payload")
