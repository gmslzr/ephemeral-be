"""
Tests for project endpoints (GET /projects, POST /projects, PATCH /projects/{id}, DELETE /projects/{id}).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models import Project, Topic
from app.auth import create_jwt
from tests.conftest import create_user_with_credentials

@pytest.mark.unit
def test_list_projects(test_client: TestClient, test_db: Session):
    """Test listing projects."""
    user = create_user_with_credentials(test_db, "listproj@example.com", "password123")
    token = create_jwt(str(user.id))
    
    # Add extra project
    p2 = Project(user_id=user.id, name="Project 2", is_default=False)
    test_db.add(p2)
    test_db.commit()
    
    response = test_client.get(
        "/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["projects"]) == 2
    names = [p["name"] for p in data["projects"]]
    assert "Default Project" in names
    assert "Project 2" in names

@pytest.mark.unit
def test_create_project_success(test_client: TestClient, test_db: Session, mock_kafka):
    """Test creating a new project."""
    user = create_user_with_credentials(test_db, "createproj@example.com", "password123")
    token = create_jwt(str(user.id))
    
    response = test_client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={}  # Empty body as name is auto-generated
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["name"]) == 10  # Auto-generated 10-char name
    assert data["is_default"] is False
    
    # Verify topic created
    project_id = data["id"]
    topic = test_db.query(Topic).filter(Topic.project_id == project_id).first()
    assert topic is not None
    assert topic.kafka_topic_name == f"project_{project_id}_events"
    
    # Verify Kafka admin called
    assert mock_kafka['admin'].create_topics.called

@pytest.mark.unit
def test_update_project_name(test_client: TestClient, test_db: Session):
    """Test updating project name."""
    user = create_user_with_credentials(test_db, "updateproj@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    response = test_client.patch(
        f"/projects/{project.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Name"}
    )
    
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"
    
    test_db.refresh(project)
    assert project.name == "New Name"

@pytest.mark.unit
def test_update_project_not_found(test_client: TestClient, test_db: Session):
    """Test updating non-existent project."""
    user = create_user_with_credentials(test_db, "upproj404@example.com", "password123")
    token = create_jwt(str(user.id))
    import uuid
    
    response = test_client.patch(
        f"/projects/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Name"}
    )
    
    assert response.status_code == 404

@pytest.mark.unit
def test_delete_project_success(test_client: TestClient, test_db: Session, mock_kafka):
    """Test deleting a project."""
    user = create_user_with_credentials(test_db, "delproj@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    project_id = str(project.id)
    
    response = test_client.delete(
        f"/projects/{project_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    
    # Verify deleted from DB
    assert test_db.query(Project).filter(Project.id == project_id).first() is None
    
    # Verify Kafka topic deletion called
    assert mock_kafka['admin'].delete_topics.called

@pytest.mark.unit
def test_delete_project_not_found(test_client: TestClient, test_db: Session):
    """Test deleting non-existent project."""
    user = create_user_with_credentials(test_db, "delproj404@example.com", "password123")
    token = create_jwt(str(user.id))
    import uuid
    
    response = test_client.delete(
        f"/projects/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404

