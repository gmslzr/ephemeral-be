"""
Tests for usage endpoints (GET /usage, GET /usage/projects) and quota service helpers.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import date
from app.models import UsageCounter, Project
from app.auth import create_jwt
from app.quota_service import (
    get_usage_metrics,
    calculate_usage_metrics,
    FREE_TIER_MESSAGES_LIMIT,
    FREE_TIER_BYTES_LIMIT
)
from tests.conftest import create_user_with_credentials


# Unit tests for quota service helpers

@pytest.mark.unit
def test_get_usage_metrics_single_project(test_db: Session):
    """Test get_usage_metrics for a single project."""
    user = create_user_with_credentials(test_db, "usage1@example.com", "password123")
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create usage counter
    usage_counter = UsageCounter(
        user_id=user.id,
        project_id=project.id,
        date=date.today(),
        messages_in=100,
        messages_out=50,
        bytes_in=1024 * 1024,  # 1MB
        bytes_out=512 * 1024   # 512KB
    )
    test_db.add(usage_counter)
    test_db.commit()
    
    result = get_usage_metrics(
        db=test_db,
        user_id=str(user.id),
        project_id=str(project.id)
    )
    
    assert result["messages_in"] == 100
    assert result["messages_out"] == 50
    assert result["bytes_in"] == 1024 * 1024
    assert result["bytes_out"] == 512 * 1024
    assert result["is_aggregated"] is False


@pytest.mark.unit
def test_get_usage_metrics_no_counter(test_db: Session):
    """Test get_usage_metrics when no usage counter exists (returns zeros)."""
    user = create_user_with_credentials(test_db, "usage2@example.com", "password123")
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    result = get_usage_metrics(
        db=test_db,
        user_id=str(user.id),
        project_id=str(project.id)
    )
    
    assert result["messages_in"] == 0
    assert result["messages_out"] == 0
    assert result["bytes_in"] == 0
    assert result["bytes_out"] == 0
    assert result["is_aggregated"] is False


@pytest.mark.unit
def test_get_usage_metrics_aggregated(test_db: Session):
    """Test get_usage_metrics aggregated across multiple projects."""
    user = create_user_with_credentials(test_db, "usage3@example.com", "password123")
    project1 = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create second project
    project2 = Project(user_id=user.id, name="Project 2", is_default=False)
    test_db.add(project2)
    test_db.flush()
    
    # Create usage counters for both projects
    usage1 = UsageCounter(
        user_id=user.id,
        project_id=project1.id,
        date=date.today(),
        messages_in=100,
        messages_out=50,
        bytes_in=1024 * 1024,
        bytes_out=512 * 1024
    )
    usage2 = UsageCounter(
        user_id=user.id,
        project_id=project2.id,
        date=date.today(),
        messages_in=200,
        messages_out=75,
        bytes_in=2 * 1024 * 1024,
        bytes_out=1024 * 1024
    )
    test_db.add(usage1)
    test_db.add(usage2)
    test_db.commit()
    
    result = get_usage_metrics(
        db=test_db,
        user_id=str(user.id),
        project_id=None  # Aggregate
    )
    
    assert result["messages_in"] == 300  # 100 + 200
    assert result["messages_out"] == 125  # 50 + 75
    assert result["bytes_in"] == 3 * 1024 * 1024  # 1MB + 2MB
    assert result["bytes_out"] == 1536 * 1024  # 512KB + 1MB
    assert result["is_aggregated"] is True


@pytest.mark.unit
def test_get_usage_metrics_aggregated_no_counters(test_db: Session):
    """Test aggregated usage when no counters exist (returns zeros)."""
    user = create_user_with_credentials(test_db, "usage4@example.com", "password123")
    
    result = get_usage_metrics(
        db=test_db,
        user_id=str(user.id),
        project_id=None
    )
    
    assert result["messages_in"] == 0
    assert result["messages_out"] == 0
    assert result["bytes_in"] == 0
    assert result["bytes_out"] == 0
    assert result["is_aggregated"] is True


@pytest.mark.unit
def test_calculate_usage_metrics_normal(test_db: Session):
    """Test calculate_usage_metrics with normal usage (<80%)."""
    result = calculate_usage_metrics(
        messages_used=5000,
        bytes_used=50 * 1024 * 1024  # 50MB
    )
    
    assert result["messages_used"] == 5000
    assert result["messages_limit"] == FREE_TIER_MESSAGES_LIMIT
    assert result["messages_remaining"] == 5000
    assert result["messages_percentage"] == 50.0
    assert result["messages_warning"] is False
    
    assert result["bytes_used"] == 50 * 1024 * 1024
    assert result["bytes_limit"] == FREE_TIER_BYTES_LIMIT
    assert result["bytes_remaining"] == 50 * 1024 * 1024
    assert result["bytes_percentage"] == 50.0
    assert result["bytes_warning"] is False


@pytest.mark.unit
def test_calculate_usage_metrics_warning_threshold(test_db: Session):
    """Test calculate_usage_metrics at warning threshold (>=80%)."""
    result = calculate_usage_metrics(
        messages_used=8000,  # 80%
        bytes_used=80 * 1024 * 1024  # 80MB
    )
    
    assert result["messages_percentage"] == 80.0
    assert result["messages_warning"] is True
    assert result["bytes_percentage"] == 80.0
    assert result["bytes_warning"] is True


@pytest.mark.unit
def test_calculate_usage_metrics_exceeded(test_db: Session):
    """Test calculate_usage_metrics when quota exceeded (>100%)."""
    result = calculate_usage_metrics(
        messages_used=12000,  # 120%
        bytes_used=120 * 1024 * 1024  # 120MB
    )
    
    assert result["messages_percentage"] == 120.0
    assert result["messages_remaining"] == 0  # Capped at 0
    assert result["messages_warning"] is True
    
    assert result["bytes_percentage"] == 120.0
    assert result["bytes_remaining"] == 0
    assert result["bytes_warning"] is True


@pytest.mark.unit
def test_calculate_usage_metrics_zero_usage(test_db: Session):
    """Test calculate_usage_metrics with zero usage."""
    result = calculate_usage_metrics(
        messages_used=0,
        bytes_used=0
    )
    
    assert result["messages_used"] == 0
    assert result["messages_remaining"] == FREE_TIER_MESSAGES_LIMIT
    assert result["messages_percentage"] == 0.0
    assert result["messages_warning"] is False
    
    assert result["bytes_used"] == 0
    assert result["bytes_remaining"] == FREE_TIER_BYTES_LIMIT
    assert result["bytes_percentage"] == 0.0
    assert result["bytes_warning"] is False


@pytest.mark.unit
def test_calculate_usage_metrics_exact_limit(test_db: Session):
    """Test calculate_usage_metrics at exact limit."""
    result = calculate_usage_metrics(
        messages_used=FREE_TIER_MESSAGES_LIMIT,
        bytes_used=FREE_TIER_BYTES_LIMIT
    )
    
    assert result["messages_percentage"] == 100.0
    assert result["messages_remaining"] == 0
    assert result["messages_warning"] is True
    
    assert result["bytes_percentage"] == 100.0
    assert result["bytes_remaining"] == 0
    assert result["bytes_warning"] is True


# Integration tests for GET /usage endpoint

@pytest.mark.unit
def test_get_usage_jwt_aggregated(test_client: TestClient, test_db: Session):
    """Test GET /usage with JWT auth and no project_id (aggregated)."""
    user = create_user_with_credentials(test_db, "usagejwt1@example.com", "password123")
    token = create_jwt(str(user.id))
    
    response = test_client.get(
        "/usage",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_project_specific"] is False
    assert "usage" in data
    usage = data["usage"]
    assert usage["user_id"] == str(user.id)
    assert usage["total_projects"] == 1
    assert "inbound" in usage
    assert "outbound" in usage
    assert usage["projects"] is None  # Summary view doesn't include breakdown


@pytest.mark.unit
def test_get_usage_jwt_with_project_id(test_client: TestClient, test_db: Session):
    """Test GET /usage with JWT auth and project_id parameter."""
    user = create_user_with_credentials(test_db, "usagejwt2@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create usage counter
    usage_counter = UsageCounter(
        user_id=user.id,
        project_id=project.id,
        date=date.today(),
        messages_in=100,
        messages_out=50,
        bytes_in=1024 * 1024,
        bytes_out=512 * 1024
    )
    test_db.add(usage_counter)
    test_db.commit()
    
    response = test_client.get(
        f"/usage?project_id={project.id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_project_specific"] is True
    usage = data["usage"]
    assert usage["project_id"] == str(project.id)
    assert usage["project_name"] == "Default Project"
    assert usage["inbound"]["messages_used"] == 100
    assert usage["outbound"]["messages_used"] == 50


@pytest.mark.unit
def test_get_usage_jwt_invalid_project_id(test_client: TestClient, test_db: Session):
    """Test GET /usage with invalid project_id returns 404."""
    user = create_user_with_credentials(test_db, "usagejwt3@example.com", "password123")
    token = create_jwt(str(user.id))
    import uuid
    fake_project_id = str(uuid.uuid4())
    
    response = test_client.get(
        f"/usage?project_id={fake_project_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.unit
def test_get_usage_api_key_project_specific(test_client: TestClient, test_db: Session):
    """Test GET /usage with API key auth (project-specific)."""
    user = create_user_with_credentials(test_db, "usageapikey@example.com", "password123")
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create API key
    from app.models import ApiKey
    from app.auth import hash_password
    api_key = ApiKey(
        user_id=user.id,
        project_id=project.id,
        name="Test Key",
        secret_hash=hash_password("test-secret-key")
    )
    test_db.add(api_key)
    test_db.commit()
    
    # Create usage counter
    usage_counter = UsageCounter(
        user_id=user.id,
        project_id=project.id,
        date=date.today(),
        messages_in=200,
        messages_out=100,
        bytes_in=2 * 1024 * 1024,
        bytes_out=1024 * 1024
    )
    test_db.add(usage_counter)
    test_db.commit()
    
    response = test_client.get(
        "/usage",
        headers={"Authorization": "ApiKey test-secret-key"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_project_specific"] is True
    usage = data["usage"]
    assert usage["project_id"] == str(project.id)
    assert usage["inbound"]["messages_used"] == 200


@pytest.mark.unit
def test_get_usage_no_usage_yet(test_client: TestClient, test_db: Session):
    """Test GET /usage when no usage counter exists (returns zeros)."""
    user = create_user_with_credentials(test_db, "usagenone@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    response = test_client.get(
        f"/usage?project_id={project.id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    usage = data["usage"]
    assert usage["inbound"]["messages_used"] == 0
    assert usage["inbound"]["messages_remaining"] == FREE_TIER_MESSAGES_LIMIT
    assert usage["outbound"]["messages_used"] == 0


@pytest.mark.unit
def test_get_usage_multiple_projects_aggregated(test_client: TestClient, test_db: Session):
    """Test GET /usage aggregates across multiple projects."""
    user = create_user_with_credentials(test_db, "usagemulti@example.com", "password123")
    token = create_jwt(str(user.id))
    project1 = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create second project
    project2 = Project(user_id=user.id, name="Project 2", is_default=False)
    test_db.add(project2)
    test_db.flush()
    
    # Create usage counters
    usage1 = UsageCounter(
        user_id=user.id,
        project_id=project1.id,
        date=date.today(),
        messages_in=100,
        messages_out=50,
        bytes_in=1024 * 1024,
        bytes_out=512 * 1024
    )
    usage2 = UsageCounter(
        user_id=user.id,
        project_id=project2.id,
        date=date.today(),
        messages_in=200,
        messages_out=75,
        bytes_in=2 * 1024 * 1024,
        bytes_out=1024 * 1024
    )
    test_db.add(usage1)
    test_db.add(usage2)
    test_db.commit()
    
    response = test_client.get(
        "/usage",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_project_specific"] is False
    usage = data["usage"]
    assert usage["total_projects"] == 2
    assert usage["inbound"]["messages_used"] == 300  # 100 + 200
    assert usage["outbound"]["messages_used"] == 125  # 50 + 75


# Integration tests for GET /usage/projects endpoint

@pytest.mark.unit
def test_get_usage_projects_jwt(test_client: TestClient, test_db: Session):
    """Test GET /usage/projects with JWT auth returns detailed breakdown."""
    user = create_user_with_credentials(test_db, "usageproj1@example.com", "password123")
    token = create_jwt(str(user.id))
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create usage counter
    usage_counter = UsageCounter(
        user_id=user.id,
        project_id=project.id,
        date=date.today(),
        messages_in=100,
        messages_out=50,
        bytes_in=1024 * 1024,
        bytes_out=512 * 1024
    )
    test_db.add(usage_counter)
    test_db.commit()
    
    response = test_client.get(
        "/usage/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user.id)
    assert data["total_projects"] == 1
    assert data["projects"] is not None
    assert len(data["projects"]) == 1
    assert data["projects"][0]["project_id"] == str(project.id)
    assert data["projects"][0]["inbound"]["messages_used"] == 100


@pytest.mark.unit
def test_get_usage_projects_api_key_forbidden(test_client: TestClient, test_db: Session):
    """Test GET /usage/projects with API key auth returns 403."""
    user = create_user_with_credentials(test_db, "usageproj2@example.com", "password123")
    project = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create API key
    from app.models import ApiKey
    from app.auth import hash_password
    api_key = ApiKey(
        user_id=user.id,
        project_id=project.id,
        name="Test Key",
        secret_hash=hash_password("test-secret-key")
    )
    test_db.add(api_key)
    test_db.commit()
    
    response = test_client.get(
        "/usage/projects",
        headers={"Authorization": "ApiKey test-secret-key"}
    )
    
    assert response.status_code == 403
    assert "JWT authentication" in response.json()["detail"]


@pytest.mark.unit
def test_get_usage_projects_multiple_projects(test_client: TestClient, test_db: Session):
    """Test GET /usage/projects with multiple projects."""
    user = create_user_with_credentials(test_db, "usageproj3@example.com", "password123")
    token = create_jwt(str(user.id))
    project1 = test_db.query(Project).filter(Project.user_id == user.id).first()
    
    # Create second project
    project2 = Project(user_id=user.id, name="Project 2", is_default=False)
    test_db.add(project2)
    test_db.flush()
    
    # Create usage counters
    usage1 = UsageCounter(
        user_id=user.id,
        project_id=project1.id,
        date=date.today(),
        messages_in=100,
        messages_out=50,
        bytes_in=1024 * 1024,
        bytes_out=512 * 1024
    )
    usage2 = UsageCounter(
        user_id=user.id,
        project_id=project2.id,
        date=date.today(),
        messages_in=200,
        messages_out=75,
        bytes_in=2 * 1024 * 1024,
        bytes_out=1024 * 1024
    )
    test_db.add(usage1)
    test_db.add(usage2)
    test_db.commit()
    
    response = test_client.get(
        "/usage/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_projects"] == 2
    assert len(data["projects"]) == 2
    assert data["inbound"]["messages_used"] == 300  # Aggregated
    assert data["outbound"]["messages_used"] == 125  # Aggregated
    
    # Check per-project breakdown
    project_ids = [p["project_id"] for p in data["projects"]]
    assert str(project1.id) in project_ids
    assert str(project2.id) in project_ids


@pytest.mark.unit
def test_get_usage_projects_no_projects(test_client: TestClient, test_db: Session):
    """Test GET /usage/projects with user that has no projects."""
    # Create user without default project
    from app.models import User
    from app.auth import hash_password
    user = User(
        email="noproj@example.com",
        password_hash=hash_password("password123"),
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    
    token = create_jwt(str(user.id))
    
    response = test_client.get(
        "/usage/projects",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_projects"] == 0
    assert data["projects"] == []
    assert data["inbound"]["messages_used"] == 0
    assert data["outbound"]["messages_used"] == 0

