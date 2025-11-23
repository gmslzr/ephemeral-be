"""
Tests for topics endpoints (GET /topics, POST /topics/{topic_name}/publish, GET /topics/{topic_name}/stream).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import MagicMock, patch
import json
import time
from datetime import datetime, date

from tests.conftest import create_user_with_credentials
from app.auth import create_jwt
from app.models import Project, Topic, User, ApiKey, UsageCounter
from app.auth import hash_password, generate_lookup_hash

@pytest.mark.unit
def test_list_topics_jwt_auth(test_client: TestClient, test_db: Session):
    """Test listing topics with JWT authentication."""
    # Create user
    user = create_user_with_credentials(test_db, "listtopics@example.com", "password123")
    token = create_jwt(str(user.id))
    
    # Should have default topic from user creation
    response = test_client.get(
        "/topics",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "topics" in data
    assert len(data["topics"]) == 1
    assert data["topics"][0]["name"] == "events"
    assert data["topics"][0]["kafka_topic_name"] == f"user_{user.id}_events"

@pytest.mark.unit
def test_list_topics_api_key_auth(test_client: TestClient, test_db: Session):
    """Test listing topics with API key authentication (scoped to project)."""
    # Create user
    user = create_user_with_credentials(test_db, "apitopics@example.com", "password123")
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create API key
    secret = "test-api-key-secret"
    api_key = ApiKey(
        user_id=user.id,
        project_id=project.id,
        name="Test Key",
        secret_hash=hash_password(secret),
        lookup_hash=generate_lookup_hash(secret)
    )
    test_db.add(api_key)
    test_db.commit()
    
    # Create another project and topic (should NOT be visible)
    project2 = Project(user_id=user.id, name="Project 2", is_default=False)
    test_db.add(project2)
    test_db.flush()
    topic2 = Topic(project_id=project2.id, name="topic2", kafka_topic_name="p2_events")
    test_db.add(topic2)
    test_db.commit()
    
    # List topics with API key
    response = test_client.get(
        "/topics",
        headers={"Authorization": f"ApiKey {secret}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should only see topics from the project associated with the API key
    assert len(data["topics"]) == 1
    assert data["topics"][0]["name"] == "events"  # From default project
    
@pytest.mark.unit
def test_publish_message_success(test_client: TestClient, test_db: Session, mock_kafka):
    """Test successful message publishing."""
    user = create_user_with_credentials(test_db, "publish@example.com", "password123")
    token = create_jwt(str(user.id))
    
    response = test_client.post(
        "/topics/events/publish",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messages": [
                {"value": {"foo": "bar"}},
                {"value": {"test": 123}}
            ]
        }
    )
    
    assert response.status_code == 200
    assert response.json()["success"] is True
    
    # Verify Kafka producer was called
    assert mock_kafka['producer'].send.called
    assert mock_kafka['producer'].send.call_count == 2

@pytest.mark.unit
def test_publish_topic_not_found(test_client: TestClient, test_db: Session):
    """Test publishing to non-existent topic."""
    user = create_user_with_credentials(test_db, "notfound@example.com", "password123")
    token = create_jwt(str(user.id))
    
    response = test_client.post(
        "/topics/nonexistent/publish",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"value": {"foo": "bar"}}]}
    )
    
    assert response.status_code == 404

@pytest.mark.unit
def test_publish_payload_too_large(test_client: TestClient, test_db: Session):
    """Test publishing message exceeding size limit."""
    user = create_user_with_credentials(test_db, "large@example.com", "password123")
    token = create_jwt(str(user.id))
    
    # Create payload > 64KB
    large_data = "x" * (64 * 1024 + 10)
    
    response = test_client.post(
        "/topics/events/publish",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"value": {"data": large_data}}]}
    )
    
    assert response.status_code == 413
    assert "exceeds maximum payload size" in response.json()["detail"]

@pytest.mark.unit
def test_publish_quota_exceeded(test_client: TestClient, test_db: Session):
    """Test publishing when quota is exceeded."""
    user = create_user_with_credentials(test_db, "quota@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Manually set usage to near limit
    # Query and update existing counter if it exists, or create new one
    usage = test_db.query(UsageCounter).filter(
        UsageCounter.user_id == user.id,
        UsageCounter.project_id == project.id,
        UsageCounter.date == date.today()
    ).first()
    
    if usage:
        usage.messages_in = 10000  # Limit is 10,000
    else:
        # For SQLite, we need to handle auto-increment differently
        # Get max id and increment
        max_id = test_db.query(UsageCounter.id).order_by(UsageCounter.id.desc()).first()
        next_id = (max_id[0] + 1) if max_id else 1
        usage = UsageCounter(
            id=next_id,
            user_id=user.id,
            project_id=project.id,
            date=date.today(),
            messages_in=10000,
            messages_out=0,
            bytes_in=0,
            bytes_out=0
        )
        test_db.add(usage)
    test_db.commit()
    
    response = test_client.post(
        "/topics/events/publish",
        headers={"Authorization": f"Bearer {token}"},
        json={"messages": [{"value": {"foo": "bar"}}]}
    )
    
    assert response.status_code == 429
    assert "limit exceeded" in response.json()["detail"]

@pytest.mark.unit
def test_stream_connection_limit(test_client: TestClient, test_db: Session):
    """Test streaming connection limits (max 2 per user)."""
    user = create_user_with_credentials(test_db, "stream@example.com", "password123")
    token = create_jwt(str(user.id))
    
    # Mock register_connection to simulate limit reached
    with patch("app.routers.topics.register_connection", return_value=(False, "")):
        response = test_client.get(
            "/topics/events/stream",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 429
        assert "Maximum 2 active stream connections" in response.json()["detail"]

@pytest.mark.unit
def test_stream_topic_not_found(test_client: TestClient, test_db: Session):
    """Test streaming from non-existent topic."""
    user = create_user_with_credentials(test_db, "stream404@example.com", "password123")
    token = create_jwt(str(user.id))
    
    response = test_client.get(
        "/topics/nonexistent/stream",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404

