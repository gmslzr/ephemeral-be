"""
Test configuration and fixtures for FastAPI Kafka Backend tests.
"""
import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, TypeDecorator, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from unittest.mock import Mock, MagicMock, patch
import os
import uuid

from app.database import Base, get_db
from app.auth import hash_password
from app.kafka_service import get_admin_client, get_producer


# Test database URL (in-memory SQLite)
TEST_DATABASE_URL = "sqlite:///:memory:"


# Cross-database UUID type for testing
class GUID(TypeDecorator):
    """
    Platform-independent GUID type.
    Uses PostgreSQL's UUID type, otherwise uses CHAR(36), storing as stringified hex values.
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == 'postgresql':
            return str(value) if isinstance(value, uuid.UUID) else value
        else:
            if isinstance(value, uuid.UUID):
                return str(value)
            return value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                value = uuid.UUID(value)
            return value


# Patch the PostgreSQL UUID type before importing models
import sqlalchemy.dialects.postgresql
from sqlalchemy import Integer
sqlalchemy.dialects.postgresql.UUID = lambda as_uuid=True: GUID()

# Patch BigInteger to use Integer for SQLite (autoincrement compatibility)
from sqlalchemy import BigInteger as SA_BigInteger
class BigIntegerCompat(TypeDecorator):
    """BigInteger that uses Integer for SQLite (autoincrement compatibility)"""
    impl = Integer
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(SA_BigInteger())
        else:
            return dialect.type_descriptor(Integer())

# Monkey-patch BigInteger in sqlalchemy module before models import
import sqlalchemy
_original_BigInteger = sqlalchemy.BigInteger
sqlalchemy.BigInteger = BigIntegerCompat

# Now import models with patched types
from app.models import User, Project, Topic


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    Create an in-memory SQLite database for testing.
    This fixture is function-scoped, so each test gets a fresh database.
    """
    # Create engine with StaticPool to maintain in-memory DB across connections
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def mock_kafka():
    """
    Mock Kafka services to avoid external dependencies during tests.
    """
    # Mock admin client
    mock_admin = MagicMock()
    mock_admin.create_topics.return_value = None
    mock_admin.delete_topics.return_value = None
    mock_admin.list_topics.return_value = []

    # Mock producer
    mock_prod = MagicMock()
    mock_future = MagicMock()
    mock_future.get.return_value = None
    mock_prod.send.return_value = mock_future
    mock_prod.flush.return_value = None

    # Patch both Kafka service functions
    with patch('app.kafka_service.get_admin_client', return_value=mock_admin), \
         patch('app.kafka_service.get_producer', return_value=mock_prod):
        yield {
            'admin': mock_admin,
            'producer': mock_prod
        }


@pytest.fixture(scope="function")
def test_client(test_db: Session, mock_kafka) -> TestClient:
    """
    Create a FastAPI TestClient with overridden dependencies.
    """
    # Import app here to avoid name conflicts
    from app.main import app as fastapi_app
    from app.rate_limiter import limiter
    
    # Disable rate limiting for tests
    original_enabled = limiter.enabled
    limiter.enabled = False

    # Override database dependency
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db

    # Create test client
    client = TestClient(fastapi_app)

    yield client

    # Clean up overrides
    fastapi_app.dependency_overrides.clear()
    limiter.enabled = original_enabled


@pytest.fixture
def test_user(test_db: Session) -> User:
    """
    Create a test user in the database.
    """
    user = User(
        email="test@example.com",
        password_hash=hash_password("testpassword123"),
        is_active=True
    )
    test_db.add(user)
    test_db.flush()

    # Create default project
    project = Project(
        user_id=user.id,
        name="Default Project",
        is_default=True
    )
    test_db.add(project)
    test_db.flush()

    # Create default topic
    topic = Topic(
        project_id=project.id,
        name="events",
        kafka_topic_name=f"user_{user.id}_events"
    )
    test_db.add(topic)

    test_db.commit()
    test_db.refresh(user)

    return user


@pytest.fixture
def test_user_inactive(test_db: Session) -> User:
    """
    Create an inactive test user in the database.
    """
    user = User(
        email="inactive@example.com",
        password_hash=hash_password("testpassword123"),
        is_active=False
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    return user


@pytest.fixture
def auth_headers(test_client: TestClient) -> dict:
    """
    Generate JWT authentication headers for the test user.
    Creates a new user and logs in to get a valid JWT token.
    """
    # Signup to create user
    signup_response = test_client.post(
        "/auth/signup",
        json={
            "email": "authuser@example.com",
            "password": "authpassword123"
        }
    )
    assert signup_response.status_code == 200
    token = signup_response.json()["token"]

    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_for_user(test_client: TestClient):
    """
    Factory fixture to generate JWT headers for a specific user.
    Returns a function that takes email and password and returns headers.
    """
    def _get_headers(email: str, password: str) -> dict:
        login_response = test_client.post(
            "/auth/login",
            json={"email": email, "password": password}
        )
        if login_response.status_code != 200:
            # Try signup if login fails
            signup_response = test_client.post(
                "/auth/signup",
                json={"email": email, "password": password}
            )
            assert signup_response.status_code == 200
            token = signup_response.json()["token"]
        else:
            token = login_response.json()["token"]

        return {"Authorization": f"Bearer {token}"}

    return _get_headers


@pytest.fixture
def multiple_users(test_db: Session):
    """
    Create multiple test users with projects and topics.
    """
    users = []
    for i in range(3):
        user = User(
            email=f"user{i}@example.com",
            password_hash=hash_password(f"password{i}"),
            is_active=True
        )
        test_db.add(user)
        test_db.flush()

        project = Project(
            user_id=user.id,
            name=f"Project {i}",
            is_default=True
        )
        test_db.add(project)
        test_db.flush()

        topic = Topic(
            project_id=project.id,
            name=f"topic{i}",
            kafka_topic_name=f"user_{user.id}_events"
        )
        test_db.add(topic)

        users.append(user)

    test_db.commit()
    for user in users:
        test_db.refresh(user)

    return users


# Helper functions for tests

def create_user_with_credentials(
    db: Session,
    email: str,
    password: str,
    is_active: bool = True
) -> User:
    """Helper to create a user with specific credentials."""
    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        is_active=is_active
    )
    db.add(user)
    db.flush()

    # Create default project
    project = Project(
        user_id=user.id,
        name="Default Project",
        is_default=True
    )
    db.add(project)
    db.flush()

    # Create default topic
    topic = Topic(
        project_id=project.id,
        name="events",
        kafka_topic_name=f"user_{user.id}_events"
    )
    db.add(topic)

    db.commit()
    db.refresh(user)

    return user
