"""
Tests for database module.
"""
import pytest
from app.database import get_engine, get_session_local, get_db
from sqlalchemy.orm import Session

@pytest.mark.unit
def test_get_engine_singleton():
    """Test that get_engine returns a singleton."""
    e1 = get_engine()
    e2 = get_engine()
    assert e1 is e2

@pytest.mark.unit
def test_get_session_local_singleton():
    """Test that get_session_local returns a singleton factory."""
    s1 = get_session_local()
    s2 = get_session_local()
    assert s1 is s2

@pytest.mark.unit
def test_get_db_yields_session():
    """Test that get_db yields a valid session."""
    # We need to mock get_session_local to avoid connecting to real DB in unit tests
    # if not using sqlite memory. But config uses sqlite memory for testing usually?
    # Actually get_engine reads settings.database_url.
    # In unit tests environment it might be better to rely on mocked engine.
    
    # However, simply calling next(get_db()) works if config is valid.
    # Since we are in unit test environment, let's just check it yields something.
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)
    session.close()

