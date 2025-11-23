from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import secrets
from app.database import get_db
from app.models import ApiKey, Project
from app.schemas import ApiKeyCreateRequest, ApiKeyResponse, ApiKeyCreateResponse
from app.dependencies import get_current_user
from app.auth import hash_password, generate_lookup_hash
from app.rate_limiter import limiter
from app.config import settings

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyResponse])
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def list_api_keys(
    request: Request,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all API keys for the current user"""
    user, _ = user_project
    
    api_keys = db.query(ApiKey).filter(ApiKey.user_id == user.id).all()
    return [ApiKeyResponse(
        id=key.id,
        user_id=key.user_id,
        project_id=key.project_id,
        name=key.name,
        created_at=key.created_at,
        last_used_at=key.last_used_at
    ) for key in api_keys]


@router.post("", response_model=ApiKeyCreateResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def create_api_key(
    http_request: Request,
    request: ApiKeyCreateRequest,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new API key"""
    user, _ = user_project
    
    # Verify project belongs to user
    project = db.query(Project).filter(
        Project.id == request.project_id,
        Project.user_id == user.id
    ).first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Generate random secret (32 bytes, URL-safe base64)
    secret = secrets.token_urlsafe(32)
    secret_hash = hash_password(secret)  # For security (slow bcrypt)
    lookup_hash = generate_lookup_hash(secret)  # For fast DB lookup (SHA-256)
    
    # Create API key
    api_key = ApiKey(
        user_id=user.id,
        project_id=request.project_id,
        name=request.name,
        secret_hash=secret_hash,
        lookup_hash=lookup_hash
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    
    return ApiKeyCreateResponse(
        id=api_key.id,
        user_id=api_key.user_id,
        project_id=api_key.project_id,
        name=api_key.name,
        secret=secret,  # Return plain secret only once
        created_at=api_key.created_at
    )


@router.delete("/{api_key_id}")
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def delete_api_key(
    request: Request,
    api_key_id: str,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an API key"""
    user, _ = user_project
    
    api_key = db.query(ApiKey).filter(
        ApiKey.id == api_key_id,
        ApiKey.user_id == user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    db.delete(api_key)
    db.commit()
    
    return {"message": "API key deleted successfully"}

