"""
Tests for get current user endpoint (GET /auth/me).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import create_user_with_credentials
from app.auth import create_jwt
from app.models import ApiKey
from app.auth import hash_password, generate_lookup_hash


@pytest.mark.unit
def test_get_me_with_valid_jwt(test_client: TestClient, test_db: Session):
    """Test GET /auth/me with valid JWT token."""
    # Create a user
    user = create_user_with_credentials(
        test_db,
        email="getme@example.com",
        password="password123"
    )

    # Get JWT token
    token = create_jwt(str(user.id))

    # Request /auth/me with JWT
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["email"] == "getme@example.com"
    assert str(data["id"]) == str(user.id)
    assert data["is_active"] is True
    assert "created_at" in data


@pytest.mark.unit
def test_get_me_after_signup(test_client: TestClient):
    """Test GET /auth/me using token from signup."""
    # Signup
    signup_response = test_client.post(
        "/auth/signup",
        json={
            "email": "signupme@example.com",
            "password": "password123"
        }
    )

    assert signup_response.status_code == 200
    token = signup_response.json()["token"]

    # Use token to get user info
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "signupme@example.com"


@pytest.mark.unit
def test_get_me_after_login(test_client: TestClient, test_db: Session):
    """Test GET /auth/me using token from login."""
    # Create user
    create_user_with_credentials(
        test_db,
        email="loginme@example.com",
        password="password123"
    )

    # Login
    login_response = test_client.post(
        "/auth/login",
        json={
            "email": "loginme@example.com",
            "password": "password123"
        }
    )

    assert login_response.status_code == 200
    token = login_response.json()["token"]

    # Use token to get user info
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "loginme@example.com"


@pytest.mark.unit
def test_get_me_without_auth(test_client: TestClient):
    """Test GET /auth/me without authentication header."""
    response = test_client.get("/auth/me")

    assert response.status_code == 401
    assert "not authenticated" in response.json()["detail"].lower()


@pytest.mark.unit
def test_get_me_with_invalid_jwt(test_client: TestClient):
    """Test GET /auth/me with invalid JWT token."""
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token.here"}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_get_me_with_expired_jwt(test_client: TestClient, test_db: Session):
    """Test GET /auth/me with malformed JWT token."""
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer notajwt"}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_get_me_with_missing_bearer_prefix(test_client: TestClient, test_db: Session):
    """Test GET /auth/me with token missing 'Bearer' prefix."""
    user = create_user_with_credentials(
        test_db,
        email="nobear@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Send token without 'Bearer' prefix
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": token}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_get_me_with_api_key(test_client: TestClient, test_db: Session):
    """Test GET /auth/me with API key authentication."""
    # Create a user with project
    user = create_user_with_credentials(
        test_db,
        email="apikeyuser@example.com",
        password="password123"
    )

    # Get user's default project
    from app.models import Project
    project = test_db.query(Project).filter(
        Project.user_id == user.id,
        Project.is_default == True
    ).first()

    # Create an API key
    secret = "test-api-key-secret-12345"
    api_key = ApiKey(
        user_id=user.id,
        project_id=project.id,
        name="Test API Key",
        secret_hash=hash_password(secret),
        lookup_hash=generate_lookup_hash(secret)
    )
    test_db.add(api_key)
    test_db.commit()

    # Request /auth/me with API key
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"ApiKey {secret}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "apikeyuser@example.com"


@pytest.mark.unit
def test_get_me_with_invalid_api_key(test_client: TestClient):
    """Test GET /auth/me with invalid API key."""
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": "ApiKey invalid-key"}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_get_me_inactive_user(test_client: TestClient, test_db: Session):
    """Test that inactive users cannot access /auth/me."""
    # Create inactive user
    user = create_user_with_credentials(
        test_db,
        email="inactive@example.com",
        password="password123",
        is_active=False
    )

    # Get JWT token (before user was deactivated)
    token = create_jwt(str(user.id))

    # Try to access /auth/me
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Should be unauthorized because user is inactive
    assert response.status_code == 401


@pytest.mark.unit
def test_get_me_wrong_auth_scheme(test_client: TestClient):
    """Test GET /auth/me with wrong authentication scheme."""
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": "Basic dXNlcjpwYXNz"}  # Basic auth instead of Bearer
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_get_me_empty_auth_header(test_client: TestClient):
    """Test GET /auth/me with empty authorization header."""
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": ""}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_get_me_returns_correct_fields(test_client: TestClient, test_db: Session):
    """Test that /auth/me returns all expected fields."""
    user = create_user_with_credentials(
        test_db,
        email="fields@example.com",
        password="password123"
    )

    token = create_jwt(str(user.id))

    response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # Check all required fields are present
    required_fields = ["id", "email", "created_at", "is_active"]
    for field in required_fields:
        assert field in data, f"Missing field: {field}"

    # Check password_hash is NOT exposed
    assert "password_hash" not in data
    assert "password" not in data
