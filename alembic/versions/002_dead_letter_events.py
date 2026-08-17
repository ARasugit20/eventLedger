"""Add dead_letter_events table for durable DLQ analytics

Revision ID: 002
Revises: 001
Create Date: 2026-08-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dead_letter_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_message_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("delivery_count", sa.Integer(), nullable=False),
        sa.Column(
            "moved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("source_message_id", name="uq_dead_letter_events_source_message_id"),
    )
    op.create_index("ix_dead_letter_events_event_id", "dead_letter_events", ["event_id"])
    op.create_index("ix_dead_letter_events_moved_at", "dead_letter_events", ["moved_at"])


def downgrade() -> None:
    op.drop_index("ix_dead_letter_events_moved_at", table_name="dead_letter_events")
    op.drop_index("ix_dead_letter_events_event_id", table_name="dead_letter_events")
    op.drop_table("dead_letter_events")
