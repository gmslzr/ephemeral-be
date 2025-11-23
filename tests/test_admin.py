"""
Tests for admin endpoints (GET /admin/active-streams).
"""
import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.connection_tracker import register_connection, unregister_connection, _connections, _lock
import uuid

@pytest.mark.unit
def test_get_active_streams_unauthorized(test_client: TestClient):
    """Test accessing admin endpoint without key."""
    response = test_client.get("/admin/active-streams")
    assert response.status_code == 401

@pytest.mark.unit
def test_get_active_streams_invalid_key(test_client: TestClient):
    """Test accessing admin endpoint with invalid key."""
    response = test_client.get(
        "/admin/active-streams",
        headers={"X-Admin-API-Key": "wrong-key"}
    )
    assert response.status_code == 401

@pytest.mark.unit
def test_get_active_streams_success(test_client: TestClient):
    """Test getting active streams with valid admin key."""
    # Set admin key (if not set in env, mock settings or set here if possible)
    # Note: Settings are loaded at import, so we rely on default or mocked settings
    # Assuming settings.admin_api_key might be empty string by default which causes 500
    
    # We'll mock the dependency verify_admin_api_key or settings
    # But easier to just patch settings
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(settings, "admin_api_key", "secret-admin-key")
        
        response = test_client.get(
            "/admin/active-streams",
            headers={"X-Admin-API-Key": "secret-admin-key"}
        )
        
        assert response.status_code == 200
        assert "users" in response.json()

@pytest.mark.unit
def test_get_active_streams_with_data(test_client: TestClient):
    """Test active streams data format."""
    # Register a fake connection
    user_id = str(uuid.uuid4())
    success, conn_id = register_connection(user_id, "test-topic")
    assert success
    
    try:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(settings, "admin_api_key", "secret-admin-key")
            
            response = test_client.get(
                "/admin/active-streams",
                headers={"X-Admin-API-Key": "secret-admin-key"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Find our user
            user_data = next((u for u in data["users"] if u["user_id"] == user_id), None)
            assert user_data is not None
            assert user_data["active_streams_count"] == 1
            assert user_data["active_streams"][0]["topic_name"] == "test-topic"
            
    finally:
        unregister_connection(user_id, conn_id)

