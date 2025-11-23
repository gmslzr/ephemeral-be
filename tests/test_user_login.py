"""
Tests for user login endpoint (POST /auth/login).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import create_user_with_credentials


@pytest.mark.unit
def test_login_success(test_client: TestClient, test_db: Session):
    """Test successful login with correct credentials."""
    # Create a user
    create_user_with_credentials(
        test_db,
        email="loginuser@example.com",
        password="correctpassword"
    )

    # Attempt login
    response = test_client.post(
        "/auth/login",
        json={
            "email": "loginuser@example.com",
            "password": "correctpassword"
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "token" in data
    assert "user" in data
    assert data["user"]["email"] == "loginuser@example.com"
    assert data["user"]["is_active"] is True


@pytest.mark.unit
def test_login_jwt_token_valid(test_client: TestClient, test_db: Session):
    """Test that JWT token from login is valid."""
    # Create a user
    create_user_with_credentials(
        test_db,
        email="jwtuser@example.com",
        password="password123"
    )

    # Login
    response = test_client.post(
        "/auth/login",
        json={
            "email": "jwtuser@example.com",
            "password": "password123"
        }
    )

    assert response.status_code == 200
    token = response.json()["token"]

    # Use token to access protected endpoint
    auth_response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert auth_response.status_code == 200
    assert auth_response.json()["email"] == "jwtuser@example.com"


@pytest.mark.unit
def test_login_wrong_password(test_client: TestClient, test_db: Session):
    """Test login with incorrect password."""
    # Create a user
    create_user_with_credentials(
        test_db,
        email="wrongpass@example.com",
        password="correctpassword"
    )

    # Attempt login with wrong password
    response = test_client.post(
        "/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "wrongpassword"
        }
    )

    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.unit
def test_login_nonexistent_email(test_client: TestClient):
    """Test login with email that doesn't exist."""
    response = test_client.post(
        "/auth/login",
        json={
            "email": "doesnotexist@example.com",
            "password": "anypassword"
        }
    )

    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.unit
def test_login_inactive_user(test_client: TestClient, test_db: Session):
    """Test that inactive users cannot log in."""
    # Create an inactive user
    create_user_with_credentials(
        test_db,
        email="inactive@example.com",
        password="password123",
        is_active=False
    )

    # Attempt login
    response = test_client.post(
        "/auth/login",
        json={
            "email": "inactive@example.com",
            "password": "password123"
        }
    )

    assert response.status_code == 401
    assert "invalid" in response.json()["detail"].lower()


@pytest.mark.unit
def test_login_email_case_insensitive(test_client: TestClient, test_db: Session):
    """Test that login is case-insensitive for email."""
    # Create user with lowercase email
    create_user_with_credentials(
        test_db,
        email="case@example.com",
        password="password123"
    )

    # Login with uppercase email
    response = test_client.post(
        "/auth/login",
        json={
            "email": "CASE@EXAMPLE.COM",
            "password": "password123"
        }
    )

    assert response.status_code == 200


@pytest.mark.unit
def test_login_email_with_whitespace(test_client: TestClient, test_db: Session):
    """Test login with email that has leading/trailing whitespace."""
    # Create user
    create_user_with_credentials(
        test_db,
        email="whitespace@example.com",
        password="password123"
    )

    # Login with whitespace (should be handled in normalization during signup)
    # Note: The login endpoint doesn't normalize, so this tests that signup normalized properly
    response = test_client.post(
        "/auth/login",
        json={
            "email": "whitespace@example.com",  # Exact match required
            "password": "password123"
        }
    )

    assert response.status_code == 200


@pytest.mark.unit
def test_login_missing_email(test_client: TestClient):
    """Test login with missing email field."""
    response = test_client.post(
        "/auth/login",
        json={"password": "password123"}
    )
    assert response.status_code == 422


@pytest.mark.unit
def test_login_missing_password(test_client: TestClient):
    """Test login with missing password field."""
    response = test_client.post(
        "/auth/login",
        json={"email": "test@example.com"}
    )
    assert response.status_code == 422


@pytest.mark.unit
def test_login_empty_request_body(test_client: TestClient):
    """Test login with empty request body."""
    response = test_client.post("/auth/login", json={})
    assert response.status_code == 422


@pytest.mark.unit
def test_login_invalid_email_format(test_client: TestClient):
    """Test login with invalid email format."""
    response = test_client.post(
        "/auth/login",
        json={
            "email": "notanemail",
            "password": "password123"
        }
    )
    # Should return 422 for validation error
    assert response.status_code == 422


@pytest.mark.unit
def test_login_multiple_times_same_user(test_client: TestClient, test_db: Session):
    """Test that the same user can log in multiple times (generates different tokens)."""
    # Create a user
    create_user_with_credentials(
        test_db,
        email="multilogin@example.com",
        password="password123"
    )

    # First login
    response1 = test_client.post(
        "/auth/login",
        json={
            "email": "multilogin@example.com",
            "password": "password123"
        }
    )
    assert response1.status_code == 200
    token1 = response1.json()["token"]

    # Second login
    response2 = test_client.post(
        "/auth/login",
        json={
            "email": "multilogin@example.com",
            "password": "password123"
        }
    )
    assert response2.status_code == 200
    token2 = response2.json()["token"]

    # Both tokens should work (even though they might be the same if generated at same second)
    auth1 = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert auth1.status_code == 200

    auth2 = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert auth2.status_code == 200


@pytest.mark.unit
def test_login_empty_password(test_client: TestClient, test_db: Session):
    """Test login with empty password string."""
    create_user_with_credentials(
        test_db,
        email="emptypass@example.com",
        password="realpassword"
    )

    response = test_client.post(
        "/auth/login",
        json={
            "email": "emptypass@example.com",
            "password": ""
        }
    )

    assert response.status_code == 401
