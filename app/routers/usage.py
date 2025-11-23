from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.database import get_db
from app.dependencies import get_current_user
from app.models import UsageCounter, Project
from app.schemas import (
    UsageResponse,
    ProjectUsageResponse,
    UserUsageResponse,
    UsageMetrics
)
from app.quota_service import (
    get_usage_metrics,
    calculate_usage_metrics,
    FREE_TIER_MESSAGES_LIMIT,
    FREE_TIER_BYTES_LIMIT
)
from app.rate_limiter import limiter
from app.config import settings

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("", response_model=UsageResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def get_usage(
    request: Request,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db),
    project_id: Optional[str] = Query(None, description="Optional project ID to get specific project usage")
):
    """
    Get quota usage information.
    
    - If using API key auth: returns usage for that specific project
    - If using JWT auth and project_id provided: returns usage for that project
    - If using JWT auth and no project_id: returns aggregated usage across all projects
    """
    user, api_key_project_id = user_project
    
    # Determine which project to query
    if api_key_project_id:
        # API key auth - always use the project from the API key
        effective_project_id = api_key_project_id
        is_project_specific = True
    elif project_id:
        # JWT auth with explicit project_id parameter
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
        effective_project_id = project_id
        is_project_specific = True
    else:
        # JWT auth without project_id - aggregate across all projects
        effective_project_id = None
        is_project_specific = False
    
    # Get usage data
    usage_data = get_usage_metrics(
        db=db,
        user_id=str(user.id),
        project_id=effective_project_id,
        target_date=None  # Uses today by default
    )
    
    if is_project_specific:
        # Get project name
        project = db.query(Project).filter(Project.id == effective_project_id).first()
        project_name = project.name if project else "Unknown"
        
        # Calculate metrics
        inbound_metrics = calculate_usage_metrics(
            messages_used=usage_data["messages_in"],
            bytes_used=usage_data["bytes_in"]
        )
        outbound_metrics = calculate_usage_metrics(
            messages_used=usage_data["messages_out"],
            bytes_used=usage_data["bytes_out"]
        )
        
        return UsageResponse(
            usage=ProjectUsageResponse(
                project_id=effective_project_id,
                project_name=project_name,
                date=date.today(),
                inbound=UsageMetrics(**inbound_metrics),
                outbound=UsageMetrics(**outbound_metrics)
            ),
            is_project_specific=True
        )
    else:
        # Aggregate across all projects
        # Get count of user's projects
        project_count = db.query(Project).filter(Project.user_id == user.id).count()
        
        # Calculate aggregated metrics
        inbound_metrics = calculate_usage_metrics(
            messages_used=usage_data["messages_in"],
            bytes_used=usage_data["bytes_in"]
        )
        outbound_metrics = calculate_usage_metrics(
            messages_used=usage_data["messages_out"],
            bytes_used=usage_data["bytes_out"]
        )
        
        return UsageResponse(
            usage=UserUsageResponse(
                user_id=user.id,
                date=date.today(),
                total_projects=project_count,
                inbound=UsageMetrics(**inbound_metrics),
                outbound=UsageMetrics(**outbound_metrics),
                projects=None  # Exclude per-project breakdown for summary
            ),
            is_project_specific=False
        )


@router.get("/projects", response_model=UserUsageResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def get_usage_with_projects(
    request: Request,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get aggregated usage with per-project breakdown.
    Requires JWT authentication (not available for API key auth).
    """
    user, api_key_project_id = user_project
    
    # API key auth not allowed for this endpoint (would be confusing)
    if api_key_project_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires JWT authentication"
        )
    
    target_date = date.today()
    
    # Get all user's projects
    projects = db.query(Project).filter(Project.user_id == user.id).all()
    
    # Get aggregated usage
    usage_data = get_usage_metrics(
        db=db,
        user_id=str(user.id),
        project_id=None,
        target_date=target_date
    )
    
    # Get per-project breakdown
    project_usages = []
    for project in projects:
        project_usage_data = get_usage_metrics(
            db=db,
            user_id=str(user.id),
            project_id=str(project.id),
            target_date=target_date
        )
        
        inbound_metrics = calculate_usage_metrics(
            messages_used=project_usage_data["messages_in"],
            bytes_used=project_usage_data["bytes_in"]
        )
        outbound_metrics = calculate_usage_metrics(
            messages_used=project_usage_data["messages_out"],
            bytes_used=project_usage_data["bytes_out"]
        )
        
        project_usages.append(
            ProjectUsageResponse(
                project_id=project.id,
                project_name=project.name,
                date=target_date,
                inbound=UsageMetrics(**inbound_metrics),
                outbound=UsageMetrics(**outbound_metrics)
            )
        )
    
    # Calculate aggregated metrics
    inbound_metrics = calculate_usage_metrics(
        messages_used=usage_data["messages_in"],
        bytes_used=usage_data["bytes_in"]
    )
    outbound_metrics = calculate_usage_metrics(
        messages_used=usage_data["messages_out"],
        bytes_used=usage_data["bytes_out"]
    )
    
    return UserUsageResponse(
        user_id=user.id,
        date=target_date,
        total_projects=len(projects),
        inbound=UsageMetrics(**inbound_metrics),
        outbound=UsageMetrics(**outbound_metrics),
        projects=project_usages
    )

