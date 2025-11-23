"""
Tests for API key endpoints (GET /api-keys, POST /api-keys, DELETE /api-keys/{api_key_id}).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import ApiKey, Project
from app.auth import create_jwt, hash_password, generate_lookup_hash
from tests.conftest import create_user_with_credentials

@pytest.mark.unit
def test_list_api_keys(test_client: TestClient, test_db: Session):
    """Test listing API keys."""
    user = create_user_with_credentials(test_db, "listkeys@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create some keys manually
    for i in range(2):
        key = ApiKey(
            user_id=user.id,
            project_id=project.id,
            name=f"Key {i}",
            secret_hash="hash",
            lookup_hash=f"lookup{i}"
        )
        test_db.add(key)
    test_db.commit()
    
    response = test_client.get(
        "/api-keys",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Key 0"
    assert data[1]["name"] == "Key 1"
    assert "secret" not in data[0]  # Should never return secret in list

@pytest.mark.unit
def test_create_api_key_success(test_client: TestClient, test_db: Session):
    """Test creating a new API key."""
    user = create_user_with_credentials(test_db, "createkey@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    response = test_client.post(
        "/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "New API Key",
            "project_id": str(project.id)
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New API Key"
    assert "secret" in data  # Should return secret once on creation
    assert len(data["secret"]) > 20
    
    # Verify in DB
    key = test_db.query(ApiKey).filter(ApiKey.id == data["id"]).first()
    assert key is not None
    assert key.lookup_hash is not None
    assert key.secret_hash is not None

@pytest.mark.unit
def test_create_api_key_invalid_project(test_client: TestClient, test_db: Session):
    """Test creating API key for non-existent project."""
    user = create_user_with_credentials(test_db, "badproject@example.com", "password123")
    token = create_jwt(str(user.id))
    import uuid
    
    response = test_client.post(
        "/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Bad Project Key",
            "project_id": str(uuid.uuid4())
        }
    )
    
    assert response.status_code == 404

@pytest.mark.unit
def test_delete_api_key_success(test_client: TestClient, test_db: Session):
    """Test deleting an API key."""
    user = create_user_with_credentials(test_db, "deletekey@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create key
    key = ApiKey(
        user_id=user.id,
        project_id=project.id,
        name="To Delete",
        secret_hash="hash",
        lookup_hash="lookup"
    )
    test_db.add(key)
    test_db.commit()
    test_db.refresh(key)
    key_id = str(key.id)
    
    response = test_client.delete(
        f"/api-keys/{key_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    
    # Verify deleted
    deleted_key = test_db.query(ApiKey).filter(ApiKey.id == key_id).first()
    assert deleted_key is None

@pytest.mark.unit
def test_delete_api_key_not_found(test_client: TestClient, test_db: Session):
    """Test deleting non-existent API key."""
    user = create_user_with_credentials(test_db, "del404@example.com", "password123")
    token = create_jwt(str(user.id))
    import uuid
    
    response = test_client.delete(
        f"/api-keys/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404

@pytest.mark.unit
def test_delete_other_user_api_key(test_client: TestClient, test_db: Session):
    """Test attempting to delete another user's API key."""
    user1 = create_user_with_credentials(test_db, "user1@example.com", "password123")
    user2 = create_user_with_credentials(test_db, "user2@example.com", "password123")
    token1 = create_jwt(str(user1.id))
    
    project2 = test_db.query(Project).filter(Project.user_id == user2.id).first()
    
    # User 2 creates key
    key = ApiKey(
        user_id=user2.id,
        project_id=project2.id,
        name="User 2 Key",
        secret_hash="hash",
        lookup_hash="lookup"
    )
    test_db.add(key)
    test_db.commit()
    test_db.refresh(key)
    
    # User 1 tries to delete it
    response = test_client.delete(
        f"/api-keys/{key.id}",
        headers={"Authorization": f"Bearer {token1}"}
    )
    
    assert response.status_code == 404  # Should return 404 as if it doesn't exist
    
    # Verify still exists
    assert test_db.query(ApiKey).filter(ApiKey.id == key.id).first() is not None

