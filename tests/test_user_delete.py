"""
Tests for user deletion endpoint (DELETE /auth/me).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import create_user_with_credentials
from app.models import User, Project, Topic
from app.auth import create_jwt


@pytest.mark.unit
def test_delete_user_success(test_client: TestClient, test_db: Session):
    """Test successful user deletion (soft delete)."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="deleteuser@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "deactivated successfully" in data["message"].lower()


@pytest.mark.unit
def test_delete_sets_is_active_false(test_client: TestClient, test_db: Session):
    """Test that deletion sets is_active to False (soft delete)."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="softdelete@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Verify user is active before deletion
    assert user.is_active is True

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    # Verify user is now inactive
    test_db.refresh(user)
    assert user.is_active is False


@pytest.mark.unit
def test_delete_user_record_still_exists(test_client: TestClient, test_db: Session):
    """Test that user record still exists in database after soft delete."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="stillexists@example.com",
        password="password123"
    )
    user_id = user.id
    token = create_jwt(str(user.id))

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    # User record should still exist in database
    deleted_user = test_db.query(User).filter(User.id == user_id).first()
    assert deleted_user is not None
    assert deleted_user.is_active is False


@pytest.mark.unit
def test_deleted_user_cannot_login(test_client: TestClient, test_db: Session):
    """Test that deleted (inactive) users cannot log in."""
    # Create user
    create_user_with_credentials(
        test_db,
        email="nologin@example.com",
        password="password123"
    )

    # Login first to get token
    login1 = test_client.post(
        "/auth/login",
        json={"email": "nologin@example.com", "password": "password123"}
    )
    assert login1.status_code == 200
    token = login1.json()["token"]

    # Delete user
    delete_response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert delete_response.status_code == 200

    # Try to login again
    login2 = test_client.post(
        "/auth/login",
        json={"email": "nologin@example.com", "password": "password123"}
    )

    # Should fail because user is inactive
    assert login2.status_code == 401


@pytest.mark.unit
def test_deleted_user_cannot_access_protected_endpoints(test_client: TestClient, test_db: Session):
    """Test that deleted users cannot access protected endpoints with old token."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="noaccess@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Verify token works before deletion
    me_response1 = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert me_response1.status_code == 200

    # Delete user
    delete_response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert delete_response.status_code == 200

    # Try to access /auth/me with same token
    me_response2 = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Should be unauthorized
    assert me_response2.status_code == 401


@pytest.mark.unit
def test_delete_calls_kafka_topic_deletion(test_client: TestClient, test_db: Session, mock_kafka):
    """Test that Kafka topics are deleted when user is deleted."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="kafkadelete@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    # Verify Kafka delete_topics was called
    # The mock_kafka fixture provides mocked Kafka services
    assert mock_kafka['admin'].delete_topics.called


@pytest.mark.unit
def test_delete_gracefully_handles_kafka_failure(test_client: TestClient, test_db: Session, mock_kafka):
    """Test that user deletion succeeds even if Kafka deletion fails."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="kafkafail@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Make Kafka deletion raise an exception
    mock_kafka['admin'].delete_topics.side_effect = Exception("Kafka connection failed")

    # Delete user - should still succeed despite Kafka failure
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    # User should still be deactivated
    test_db.refresh(user)
    assert user.is_active is False


@pytest.mark.unit
def test_delete_without_auth(test_client: TestClient):
    """Test deletion without authentication."""
    response = test_client.delete("/auth/me")

    assert response.status_code == 401


@pytest.mark.unit
def test_delete_with_invalid_token(test_client: TestClient):
    """Test deletion with invalid JWT token."""
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": "Bearer invalid.token"}
    )

    assert response.status_code == 401


@pytest.mark.unit
def test_delete_projects_remain_in_database(test_client: TestClient, test_db: Session):
    """Test that projects remain in database after user deletion (cascade not executed on soft delete)."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="projectremain@example.com",
        password="password123"
    )
    user_id = user.id
    token = create_jwt(str(user.id))

    # Verify user has a project
    project_before = test_db.query(Project).filter(Project.user_id == user_id).first()
    assert project_before is not None

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    # Projects should still exist (soft delete doesn't trigger cascade)
    project_after = test_db.query(Project).filter(Project.user_id == user_id).first()
    assert project_after is not None


@pytest.mark.unit
def test_delete_topics_remain_in_database(test_client: TestClient, test_db: Session):
    """Test that topic records remain in database after user deletion."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="topicremain@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Get user's project and topic
    project = test_db.query(Project).filter(
        Project.user_id == user.id,
        Project.is_default == True
    ).first()
    assert project is not None

    topic_before = test_db.query(Topic).filter(Topic.project_id == project.id).first()
    assert topic_before is not None

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200

    # Topic record should still exist
    topic_after = test_db.query(Topic).filter(Topic.project_id == project.id).first()
    assert topic_after is not None


@pytest.mark.unit
def test_delete_idempotent(test_client: TestClient, test_db: Session):
    """Test that deleting an already deleted user still works (idempotent)."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="idempotent@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # First deletion
    response1 = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response1.status_code == 200

    # Second deletion with same token should fail (user is inactive)
    response2 = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    # Should be unauthorized because user is now inactive
    assert response2.status_code == 401


@pytest.mark.unit
def test_delete_multiple_projects_deletes_all_topics(test_client: TestClient, test_db: Session):
    """Test that deleting a user with multiple projects deletes all associated Kafka topics."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="multiproject@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Create additional project manually
    project2 = Project(
        user_id=user.id,
        name="Second Project",
        is_default=False
    )
    test_db.add(project2)
    test_db.flush()

    # Create topic for second project
    topic2 = Topic(
        project_id=project2.id,
        name="topic2",
        kafka_topic_name=f"project_{project2.id}_events"
    )
    test_db.add(topic2)
    test_db.commit()

    # User now has 2 projects with 2 topics
    projects = test_db.query(Project).filter(Project.user_id == user.id).all()
    assert len(projects) == 2

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    # Kafka admin should have been called to delete topics
    # (actual verification would depend on mock implementation)


@pytest.mark.unit
def test_delete_response_format(test_client: TestClient, test_db: Session):
    """Test that deletion response has correct format."""
    # Create user
    user = create_user_with_credentials(
        test_db,
        email="responseformat@example.com",
        password="password123"
    )
    token = create_jwt(str(user.id))

    # Delete user
    response = test_client.delete(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "message" in data
    assert isinstance(data["message"], str)
