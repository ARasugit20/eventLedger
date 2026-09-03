"""Add processing_lease_until column for worker crash recovery

Revision ID: 003
Revises: 002
Create Date: 2026-09-03

When a worker claims an event (received -> processing), set processing_lease_until
to now() + PROCESSING_LEASE_SECONDS. A background sweep resets any row where
processing_lease_until < now() back to 'received' so it can be reclaimed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "events",
        sa.Column(
            "processing_lease_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="If status='processing' and this is in the past, worker crashed; reset to 'received'",
        ),
    )
    op.create_index(
        "ix_events_processing_lease",
        "events",
        ["processing_lease_until"],
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    op.drop_index("ix_events_processing_lease", table_name="events")
    op.drop_column("events", "processing_lease_until")
