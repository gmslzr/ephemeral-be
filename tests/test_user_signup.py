"""
Tests for user signup endpoint (POST /auth/signup).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, Project, Topic
from app.auth import verify_password


@pytest.mark.unit
def test_signup_success(test_client: TestClient, test_db: Session):
    """Test successful user signup."""
    response = test_client.post(
        "/auth/signup",
        json={
            "email": "newuser@example.com",
            "password": "securepassword123"
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "token" in data
    assert "user" in data
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["is_active"] is True
    assert "id" in data["user"]
    assert "created_at" in data["user"]

    # Verify user was created in database
    user = test_db.query(User).filter(User.email == "newuser@example.com").first()
    assert user is not None
    assert user.is_active is True
    assert verify_password("securepassword123", user.password_hash)


@pytest.mark.unit
def test_signup_creates_default_project(test_client: TestClient, test_db: Session):
    """Test that signup creates a default project for the user."""
    response = test_client.post(
        "/auth/signup",
        json={
            "email": "projectuser@example.com",
            "password": "password123"
        }
    )

    assert response.status_code == 200
    user_id = response.json()["user"]["id"]

    # Verify default project was created
    project = test_db.query(Project).filter(
        Project.user_id == user_id,
        Project.is_default == True
    ).first()

    assert project is not None
    assert project.name == "Default Project"
    assert project.is_default is True


@pytest.mark.unit
def test_signup_creates_kafka_topic(test_client: TestClient, test_db: Session):
    """Test that signup creates a Kafka topic and database Topic record."""
    response = test_client.post(
        "/auth/signup",
        json={
            "email": "kafkauser@example.com",
            "password": "password123"
        }
    )

    assert response.status_code == 200
    user_id = response.json()["user"]["id"]

    # Get the default project
    project = test_db.query(Project).filter(
        Project.user_id == user_id,
        Project.is_default == True
    ).first()

    assert project is not None

    # Verify topic was created
    topic = test_db.query(Topic).filter(Topic.project_id == project.id).first()
    assert topic is not None
    assert topic.kafka_topic_name == f"user_{user_id}_events"
    # Topic name should be a 10-character random string
    assert len(topic.name) == 10


@pytest.mark.unit
def test_signup_email_normalization(test_client: TestClient, test_db: Session):
    """Test that email is normalized (lowercase, stripped) during signup."""
    response = test_client.post(
        "/auth/signup",
        json={
            "email": "  UPPERCASE@EXAMPLE.COM  ",
            "password": "password123"
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Email should be lowercase and trimmed
    assert data["user"]["email"] == "uppercase@example.com"

    # Verify in database
    user = test_db.query(User).filter(User.email == "uppercase@example.com").first()
    assert user is not None


@pytest.mark.unit
def test_signup_duplicate_email(test_client: TestClient, test_db: Session):
    """Test that duplicate email addresses are rejected."""
    email = "duplicate@example.com"

    # First signup should succeed
    response1 = test_client.post(
        "/auth/signup",
        json={"email": email, "password": "password123"}
    )
    assert response1.status_code == 200

    # Second signup with same email should fail
    response2 = test_client.post(
        "/auth/signup",
        json={"email": email, "password": "differentpassword"}
    )
    assert response2.status_code == 400
    assert "already registered" in response2.json()["detail"].lower()


@pytest.mark.unit
def test_signup_duplicate_email_case_insensitive(test_client: TestClient):
    """Test that email uniqueness check is case-insensitive."""
    # First signup with lowercase
    response1 = test_client.post(
        "/auth/signup",
        json={"email": "case@example.com", "password": "password123"}
    )
    assert response1.status_code == 200

    # Second signup with uppercase should fail
    response2 = test_client.post(
        "/auth/signup",
        json={"email": "CASE@EXAMPLE.COM", "password": "password456"}
    )
    assert response2.status_code == 400


@pytest.mark.unit
def test_signup_invalid_email_format(test_client: TestClient):
    """Test that invalid email formats are rejected."""
    invalid_emails = [
        "notanemail",
        "@example.com",
        "user@",
        "user @example.com",
        "",
    ]

    for invalid_email in invalid_emails:
        response = test_client.post(
            "/auth/signup",
            json={"email": invalid_email, "password": "password123"}
        )
        # Should return 422 Unprocessable Entity for validation error
        assert response.status_code == 422, f"Failed for email: {invalid_email}"


@pytest.mark.unit
def test_signup_password_is_hashed(test_client: TestClient, test_db: Session):
    """Test that passwords are properly hashed using bcrypt."""
    plain_password = "myplainpassword123"

    response = test_client.post(
        "/auth/signup",
        json={
            "email": "hashtest@example.com",
            "password": plain_password
        }
    )

    assert response.status_code == 200
    user_id = response.json()["user"]["id"]

    # Get user from database
    user = test_db.query(User).filter(User.id == user_id).first()
    assert user is not None

    # Password hash should not match plain password
    assert user.password_hash != plain_password

    # Password hash should start with bcrypt prefix
    assert user.password_hash.startswith("$2b$")

    # Should be able to verify with correct password
    assert verify_password(plain_password, user.password_hash) is True

    # Should fail with wrong password
    assert verify_password("wrongpassword", user.password_hash) is False


@pytest.mark.unit
def test_signup_jwt_token_is_valid(test_client: TestClient):
    """Test that the JWT token returned by signup is valid."""
    response = test_client.post(
        "/auth/signup",
        json={
            "email": "jwttest@example.com",
            "password": "password123"
        }
    )

    assert response.status_code == 200
    token = response.json()["token"]

    # Use the token to access a protected endpoint
    auth_response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert auth_response.status_code == 200
    assert auth_response.json()["email"] == "jwttest@example.com"


@pytest.mark.unit
def test_signup_missing_email(test_client: TestClient):
    """Test signup with missing email field."""
    response = test_client.post(
        "/auth/signup",
        json={"password": "password123"}
    )
    assert response.status_code == 422


@pytest.mark.unit
def test_signup_missing_password(test_client: TestClient):
    """Test signup with missing password field."""
    response = test_client.post(
        "/auth/signup",
        json={"email": "test@example.com"}
    )
    assert response.status_code == 422


@pytest.mark.unit
def test_signup_empty_request_body(test_client: TestClient):
    """Test signup with empty request body."""
    response = test_client.post("/auth/signup", json={})
    assert response.status_code == 422


@pytest.mark.unit
def test_signup_very_long_password(test_client: TestClient, test_db: Session):
    """Test signup with very long password (should work due to SHA-256 preprocessing)."""
    # Create a password longer than bcrypt's 72-byte limit
    long_password = "a" * 200

    response = test_client.post(
        "/auth/signup",
        json={
            "email": "longpass@example.com",
            "password": long_password
        }
    )

    assert response.status_code == 200

    # Verify password can be verified
    user = test_db.query(User).filter(User.email == "longpass@example.com").first()
    assert verify_password(long_password, user.password_hash) is True
