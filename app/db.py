"""Database connection and session management.

What: SQLAlchemy engine, session factory, and FastAPI `get_db` dependency.
Why: Every API request gets its own DB session that is closed after the response.
Key exports: `engine`, `SessionLocal`, `get_db`, `Base` (for Alembic/models).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
