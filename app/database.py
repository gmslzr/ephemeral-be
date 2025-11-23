from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from typing import Generator
from app.config import settings

Base = declarative_base()

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine with connection pooling"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=10,  # Number of connections to maintain
            max_overflow=20,  # Additional connections beyond pool_size
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,  # Recycle connections after 1 hour
            echo=False  # Set to True for SQL query logging
        )
    return _engine


def get_session_local():
    """Get or create session factory"""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def get_db() -> Generator:
    """Dependency for getting database session"""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

