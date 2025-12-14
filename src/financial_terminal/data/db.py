from __future__ import annotations

from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def get_engine(db_path: Path | str | None = None):
    """
    Create a SQLAlchemy engine for the local SQLite database.
    """
    uri = f"sqlite:///{Path(db_path or 'financial_terminal.db').resolve()}"
    return create_engine(uri, echo=False, future=True)


def get_session(engine=None) -> Session:
    """
    Provide a Session bound to the given engine.
    """
    engine = engine or get_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return SessionLocal()


def session_scope(engine=None) -> Iterator[Session]:
    """
    Context manager for session scope; commits on success, rolls back on error.
    """
    session = get_session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
