"""
Tests for user update endpoint (PATCH /auth/me).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import create_user_with_credentials
from app.models import User
from app.auth import verify_password, create_jwt


@pytest.mark.unit
def test_update_email_only(test_client: TestClient, test_db: Session):
    """Test updating only the email address."""
    # Create a user and get token
    user = create_user_with_credentials(
        test_db,
        email="oldemail@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Update email
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newemail@example.com"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["user"]["email"] == "newemail@example.com"
    assert data["message"] == "User updated successfully"

    # Verify in database
    test_db.refresh(user)
    assert user.email == "newemail@example.com"


@pytest.mark.unit
def test_update_password_only(test_client: TestClient, test_db: Session):
    """Test updating only the password."""
    # Create a user
    user = create_user_with_credentials(
        test_db,
        email="passupdate@example.com",
        password="oldpassword"
    )
    token = create_jwt(str(user.id))

    # Update password
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "newpassword123"}
    )

    assert response.status_code == 200

    # Verify old password no longer works
    test_db.refresh(user)
    assert verify_password("oldpassword", user.password_hash) is False

    # Verify new password works
    assert verify_password("newpassword123", user.password_hash) is True


@pytest.mark.unit
def test_update_email_and_password(test_client: TestClient, test_db: Session):
    """Test updating both email and password simultaneously."""
    # Create a user
    user = create_user_with_credentials(
        test_db,
        email="both@example.com",
        password="oldpass"
    )
    token = create_jwt(str(user.id))

    # Update both
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "newboth@example.com",
            "password": "newpass123"
        }
    )

    assert response.status_code == 200
    data = response.json()

    assert data["user"]["email"] == "newboth@example.com"

    # Verify in database
    test_db.refresh(user)
    assert user.email == "newboth@example.com"
    assert verify_password("newpass123", user.password_hash) is True


@pytest.mark.unit
def test_update_email_normalization(test_client: TestClient, test_db: Session):
    """Test that updated email is normalized (lowercase, trimmed)."""
    user = create_user_with_credentials(
        test_db,
        email="normalize@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Update with uppercase and whitespace
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "  NEWUPPER@EXAMPLE.COM  "}
    )

    assert response.status_code == 200
    data = response.json()

    # Should be normalized
    assert data["user"]["email"] == "newupper@example.com"

    test_db.refresh(user)
    assert user.email == "newupper@example.com"


@pytest.mark.unit
def test_update_email_uniqueness_check(test_client: TestClient, test_db: Session):
    """Test that email uniqueness is enforced on update."""
    # Create two users
    user1 = create_user_with_credentials(
        test_db,
        email="user1@example.com",
        password="password123"
    )
    create_user_with_credentials(
        test_db,
        email="user2@example.com",
        password="password123"
    )

    token = create_jwt(str(user1.id))

    # Try to update user1's email to user2's email
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "user2@example.com"}
    )

    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.unit
def test_update_email_to_same_email(test_client: TestClient, test_db: Session):
    """Test updating email to the same email (should succeed)."""
    user = create_user_with_credentials(
        test_db,
        email="same@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Update to same email
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "same@example.com"}
    )

    # Should succeed (no conflict with self)
    assert response.status_code == 200


@pytest.mark.unit
def test_update_no_fields_provided(test_client: TestClient, test_db: Session):
    """Test update with no fields provided (should fail)."""
    user = create_user_with_credentials(
        test_db,
        email="nofields@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Send empty update
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={}
    )

    assert response.status_code == 400
    assert "at least one field" in response.json()["detail"].lower()


@pytest.mark.unit
def test_update_with_null_values(test_client: TestClient, test_db: Session):
    """Test update with explicit null values (should be treated as not provided)."""
    user = create_user_with_credentials(
        test_db,
        email="nulltest@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Send nulls for both fields
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": None, "password": None}
    )

    # Should fail because no actual values provided
    assert response.status_code == 400


@pytest.mark.unit
def test_update_without_auth(test_client: TestClient):
    """Test update without authentication."""
    response = test_client.patch(
        "/auth/me",
        json={"email": "new@example.com"}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_update_with_invalid_token(test_client: TestClient):
    """Test update with invalid JWT token."""
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token"},
        json={"email": "new@example.com"}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_update_invalid_email_format(test_client: TestClient, test_db: Session):
    """Test update with invalid email format."""
    user = create_user_with_credentials(
        test_db,
        email="valid@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "notanemail"}
    )

    # Should return 422 for validation error
    assert response.status_code == 422


@pytest.mark.unit
def test_update_password_is_hashed(test_client: TestClient, test_db: Session):
    """Test that updated password is properly hashed."""
    user = create_user_with_credentials(
        test_db,
        email="hashtest@example.com",
        password="oldpassword"
    )
    token = create_jwt(str(user.id))

    new_password = "newsecurepassword"

    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": new_password}
    )

    assert response.status_code == 200

    # Verify password is hashed (not stored in plain text)
    test_db.refresh(user)
    assert user.password_hash != new_password
    assert user.password_hash.startswith("$2b$")  # bcrypt prefix
    assert verify_password(new_password, user.password_hash) is True


@pytest.mark.unit
def test_update_can_login_with_new_password(test_client: TestClient, test_db: Session):
    """Test that user can login with new password after update."""
    # Create user
    create_user_with_credentials(
        test_db,
        email="loginafter@example.com",
        password="oldpassword"
    )

    # Login with old password
    login1 = test_client.post(
        "/auth/login",
        json={"email": "loginafter@example.com", "password": "oldpassword"}
    )
    assert login1.status_code == 200
    token = login1.json()["token"]

    # Update password
    update_response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": "newpassword123"}
    )
    assert update_response.status_code == 200

    # Login with new password
    login2 = test_client.post(
        "/auth/login",
        json={"email": "loginafter@example.com", "password": "newpassword123"}
    )
    assert login2.status_code == 200

    # Old password should not work
    login3 = test_client.post(
        "/auth/login",
        json={"email": "loginafter@example.com", "password": "oldpassword"}
    )
    assert login3.status_code == 401


@pytest.mark.unit
def test_update_email_case_insensitive_uniqueness(test_client: TestClient, test_db: Session):
    """Test that email uniqueness check is case-insensitive."""
    user1 = create_user_with_credentials(
        test_db,
        email="user1@example.com",
        password="password123"
    )
    create_user_with_credentials(
        test_db,
        email="existing@example.com",
        password="password123"
    )

    token = create_jwt(str(user1.id))

    # Try to update to existing email with different case
    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "EXISTING@EXAMPLE.COM"}
    )

    assert response.status_code == 400


@pytest.mark.unit
def test_update_very_long_password(test_client: TestClient, test_db: Session):
    """Test updating to a very long password (>72 chars for bcrypt)."""
    user = create_user_with_credentials(
        test_db,
        email="longpass@example.com",
        password="short"
    )
    token = create_jwt(str(user.id))

    # Password longer than bcrypt's 72-byte limit
    long_password = "a" * 200

    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"password": long_password}
    )

    assert response.status_code == 200

    # Verify it works (SHA-256 preprocessing should handle this)
    test_db.refresh(user)
    assert verify_password(long_password, user.password_hash) is True


@pytest.mark.unit
def test_update_returns_updated_user_data(test_client: TestClient, test_db: Session):
    """Test that update response contains updated user data."""
    user = create_user_with_credentials(
        test_db,
        email="returndata@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    response = test_client.patch(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "updated@example.com"}
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "message" in data
    assert "user" in data
    assert data["user"]["email"] == "updated@example.com"
    assert str(data["user"]["id"]) == str(user.id)
    assert "password_hash" not in data["user"]  # Should not expose password
