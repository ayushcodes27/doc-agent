"""
Database Session and Engine Configuration for DocAgent
======================================================
Provides SQLAlchemy 2.0 engine, scoped sessions, connection pooling,
and graceful SQLite fallback when PostgreSQL is not running locally.
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session
from config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base for all ORM models."""
    pass


def _create_database_engine():
    """Create SQLAlchemy engine with auto-fallback to local SQLite if Postgres is unreachable."""
    database_url = settings.DATABASE_URL
    
    # If SQLite explicitly requested
    if database_url.startswith("sqlite"):
        return create_engine(database_url, connect_args={"check_same_thread": False})
    
    # Try PostgreSQL first
    try:
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
            connect_args={"connect_timeout": 2} if "postgresql" in database_url else {}
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Connected successfully to PostgreSQL database.")
        return engine
    except Exception as e:
        logger.warning(
            f"PostgreSQL unreachable at {database_url} ({e}). "
            "Falling back to local SQLite database (sqlite:///./docagent.db)."
        )
        sqlite_url = "sqlite:///./docagent.db"
        return create_engine(sqlite_url, connect_args={"check_same_thread": False})


engine = _create_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all database tables defined in models."""
    from db import models  # Ensure all models are registered
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database session injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for standalone scripts, background workers, and evaluation tests."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
