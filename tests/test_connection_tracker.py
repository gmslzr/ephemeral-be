"""
Tests for connection tracker module.
"""
import pytest
import threading
from app.connection_tracker import (
    register_connection,
    unregister_connection,
    get_all_active_connections,
    _connections
)

@pytest.fixture(autouse=True)
def clear_connections():
    """Clear connections before each test."""
    _connections.clear()
    yield
    _connections.clear()

@pytest.mark.unit
def test_register_connection_success():
    """Test successful connection registration."""
    user_id = "user1"
    success, conn_id = register_connection(user_id, "topic1")
    
    assert success is True
    assert conn_id
    assert len(_connections[user_id]) == 1

@pytest.mark.unit
def test_register_connection_limit():
    """Test connection limit (max 2)."""
    user_id = "user1"
    
    # 1st connection
    s1, c1 = register_connection(user_id, "topic1")
    assert s1
    
    # 2nd connection
    s2, c2 = register_connection(user_id, "topic1")
    assert s2
    
    # 3rd connection (should fail)
    s3, c3 = register_connection(user_id, "topic1")
    assert s3 is False
    assert c3 == ""
    
    assert len(_connections[user_id]) == 2

@pytest.mark.unit
def test_unregister_connection():
    """Test unregistering a connection."""
    user_id = "user1"
    s1, c1 = register_connection(user_id, "topic1")
    
    unregister_connection(user_id, c1)
    
    # Set should be empty and key deleted
    assert user_id not in _connections

@pytest.mark.unit
def test_get_all_active_connections():
    """Test retrieving all active connections."""
    register_connection("u1", "t1")
    register_connection("u2", "t2")
    
    all_conns = get_all_active_connections()
    
    assert len(all_conns) == 2
    assert "u1" in all_conns
    assert "u2" in all_conns
    assert all_conns["u1"][0]["topic_name"] == "t1"

@pytest.mark.unit
def test_thread_safety():
    """Test thread safety under concurrent access."""
    errors = []
    
    def worker():
        try:
            user_id = f"user_{threading.get_ident()}"
            s, c = register_connection(user_id, "t")
            if s:
                get_all_active_connections()
                unregister_connection(user_id, c)
        except Exception as e:
            errors.append(e)
            
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    assert len(errors) == 0

