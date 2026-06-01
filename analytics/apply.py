"""Apply analytics SQL views to PostgreSQL."""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine


def apply_analytics_views(engine: Engine) -> None:
    """Run analytics/views.sql idempotently (CREATE OR REPLACE)."""
    sql_path = Path(__file__).resolve().parent / "views.sql"
    script = sql_path.read_text()
    # Execute as one script; Postgres handles multiple statements.
    with engine.connect() as conn:
        conn.execute(text(script))
        conn.commit()
