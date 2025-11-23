from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import secrets
import string
import logging
from app.database import get_db
from app.models import Project, Topic
from app.schemas import (
    ProjectCreateRequest,
    ProjectUpdateRequest,
    ProjectResponse,
    ProjectsListResponse,
    ProjectDeleteResponse
)
from app.dependencies import get_current_user
from app.kafka_service import create_project_topic, delete_topic
from app.rate_limiter import limiter
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectsListResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def list_projects(
    request: Request,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all projects for the current user"""
    user, project_id = user_project
    
    # If using API key auth, project_id will be set, but we still return all user's projects
    # If using JWT auth, project_id will be None
    projects = db.query(Project).filter(Project.user_id == user.id).all()
    
    return ProjectsListResponse(
        projects=[ProjectResponse(
            id=project.id,
            user_id=project.user_id,
            name=project.name,
            created_at=project.created_at,
            is_default=project.is_default
        ) for project in projects]
    )


@router.post("", response_model=ProjectResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def create_project(
    http_request: Request,
    request: ProjectCreateRequest,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new project with auto-generated name"""
    user, project_id = user_project
    
    # Require JWT auth (project_id should be None for JWT auth)
    # API keys are project-specific, so creating a project via API key doesn't make sense
    if project_id is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Projects can only be created using JWT authentication"
        )
    
    # Generate unique 10-character alphanumeric string for project name
    project_name = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
    
    # Create project in database
    project = Project(
        user_id=user.id,
        name=project_name,
        is_default=False
    )
    db.add(project)
    db.flush()  # Flush to get project.id
    
    # Create Kafka topic
    try:
        kafka_topic_name = create_project_topic(str(project.id))
    except Exception as e:
        # If Kafka topic creation fails, we still want to create the project
        # Use a placeholder name that can be updated later
        kafka_topic_name = f"project_{project.id}_events"
        logger.warning(f"Failed to create Kafka topic for project {project.id}: {e}")
    
    # Generate unique 10-character alphanumeric logical name for topic
    topic_logical_name = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
    
    # Create topic with generated logical name
    topic = Topic(
        project_id=project.id,
        name=topic_logical_name,
        kafka_topic_name=kafka_topic_name
    )
    db.add(topic)
    
    db.commit()
    db.refresh(project)
    
    return ProjectResponse(
        id=project.id,
        user_id=project.user_id,
        name=project.name,
        created_at=project.created_at,
        is_default=project.is_default
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def update_project(
    request: Request,
    project_id: str,
    update_request: ProjectUpdateRequest,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update project name"""
    user, _ = user_project
    
    # Verify project belongs to user
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Update project name
    project.name = update_request.name
    db.commit()
    db.refresh(project)
    
    return ProjectResponse(
        id=project.id,
        user_id=project.user_id,
        name=project.name,
        created_at=project.created_at,
        is_default=project.is_default
    )


@router.delete("/{project_id}", response_model=ProjectDeleteResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def delete_project(
    request: Request,
    project_id: str,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a project and its associated topic and Kafka topic"""
    user, _ = user_project
    
    # Verify project belongs to user
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Get topic associated with project
    topic = db.query(Topic).filter(Topic.project_id == project.id).first()
    
    # Delete Kafka topic if it exists
    if topic:
        try:
            delete_topic(topic.kafka_topic_name)
        except Exception as e:
            # Log error but don't fail project deletion if Kafka deletion fails
            logger.error(f"Failed to delete Kafka topic {topic.kafka_topic_name} for project {project.id}: {e}")
    
    # Delete project (cascade will auto-delete Topic, ApiKey, UsageCounter records)
    db.delete(project)
    db.commit()
    
    return ProjectDeleteResponse()

