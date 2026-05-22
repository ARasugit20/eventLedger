"""Initial events table

Revision ID: 001
Revises:
Create Date: 2026-05-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

event_status = postgresql.ENUM(
    "received", "processing", "processed", "failed", name="event_status", create_type=False
)


def upgrade() -> None:
    op.execute("CREATE TYPE event_status AS ENUM ('received', 'processing', 'processed', 'failed')")
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", event_status, nullable=False, server_default="received"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_events_idempotency_key"),
    )
    op.create_index("ix_events_idempotency_key", "events", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_events_idempotency_key", table_name="events")
    op.drop_table("events")
    op.execute("DROP TYPE event_status")
