from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Project, Topic
from app.schemas import SignupRequest, LoginRequest, AuthResponse, UserResponse, UserUpdateRequest, UserUpdateResponse, UserDeleteResponse
from app.auth import hash_password, verify_password, create_jwt, decode_jwt
from app.dependencies import get_current_user
from app.kafka_service import create_user_topic, delete_user_topics
from app.rate_limiter import limiter
from app.config import settings
from app.logger import logger
from datetime import datetime
import uuid
import secrets
import string

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse)
def signup(http_request: Request, request: SignupRequest, db: Session = Depends(get_db)):
    """Sign up a new user"""
    request_id = getattr(http_request.state, "request_id", None)
    
    # Normalize email (lowercase and strip whitespace)
    email = request.email.strip().lower()
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        logger.log_auth(
            event="signup",
            status="email_exists",
            request_id=request_id,
            email=email,
            path=http_request.url.path,
            method=http_request.method
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash password
    password_hash = hash_password(request.password)
    
    # Create user
    user = User(
        email=email,
        password_hash=password_hash,
        is_active=True
    )
    db.add(user)
    db.flush()  # Flush to get user.id
    
    # Create default project
    project = Project(
        user_id=user.id,
        name="Default Project",
        is_default=True
    )
    db.add(project)
    db.flush()  # Flush to get project.id
    
    # Create Kafka topic
    kafka_error = None
    try:
        kafka_topic_name = create_user_topic(str(user.id))
    except Exception as e:
        # If Kafka topic creation fails, we still want to create the user
        # Use a placeholder name that can be updated later
        kafka_topic_name = f"user_{user.id}_events"
        kafka_error = str(e)
        logger.log_internal(
            level="WARN",
            event="kafka_topic_creation_failed",
            request_id=request_id,
            path=http_request.url.path,
            method=http_request.method,
            user_id=str(user.id),
            error=kafka_error
        )
    
    # Generate a unique 10-digit alphanumeric logical name for the topic
    topic_logical_name = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(10))
    
    # Create default topic with generated logical name
    topic = Topic(
        project_id=project.id,
        name=topic_logical_name,
        kafka_topic_name=kafka_topic_name
    )
    db.add(topic)
    
    db.commit()
    db.refresh(user)
    
    # Create JWT
    token = create_jwt(str(user.id))
    
    # Log successful signup
    logger.log_auth(
        event="signup",
        status="ok" if kafka_error is None else "kafka_error",
        request_id=request_id,
        user_id=str(user.id),
        email=email,
        path=http_request.url.path,
        method=http_request.method,
        error=kafka_error
    )
    
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            created_at=user.created_at,
            is_active=user.is_active
        )
    )


@router.post("/login", response_model=AuthResponse)
def login(http_request: Request, request: LoginRequest, db: Session = Depends(get_db)):
    """Log in a user"""
    request_id = getattr(http_request.state, "request_id", None)
    
    # Normalize email (lowercase and strip whitespace) for case-insensitive login
    email = request.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        logger.log_auth(
            event="login",
            status="invalid_credentials",
            request_id=request_id,
            path=http_request.url.path,
            method=http_request.method
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(request.password, user.password_hash):
        logger.log_auth(
            event="login",
            status="invalid_credentials",
            request_id=request_id,
            path=http_request.url.path,
            method=http_request.method
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Create JWT
    token = create_jwt(str(user.id))
    
    # Log successful login
    logger.log_auth(
        event="login",
        status="ok",
        request_id=request_id,
        user_id=str(user.id),
        email=email,
        path=http_request.url.path,
        method=http_request.method
    )
    
    return AuthResponse(
        token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            created_at=user.created_at,
            is_active=user.is_active
        )
    )


@router.get("/me", response_model=UserResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def get_me(
    request: Request,
    user_project: tuple = Depends(get_current_user)
):
    """Get current user info"""
    user, _ = user_project
    return UserResponse(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        is_active=user.is_active
    )


@router.patch("/me", response_model=UserUpdateResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def update_me(
    request: Request,
    update_request: UserUpdateRequest,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's email and/or password"""
    user, _ = user_project
    
    # Validate that at least one field is provided
    if update_request.email is None and update_request.password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field (email or password) must be provided"
        )
    
    # Update email if provided
    if update_request.email is not None:
        # Normalize email (lowercase and strip whitespace)
        new_email = update_request.email.strip().lower()
        
        # Check if email is already taken by another user
        existing_user = db.query(User).filter(
            User.email == new_email,
            User.id != user.id
        ).first()
        
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        user.email = new_email
    
    # Update password if provided
    if update_request.password is not None:
        # Hash the new password
        user.password_hash = hash_password(update_request.password)
    
    db.commit()
    db.refresh(user)
    
    return UserUpdateResponse(
        user=UserResponse(
            id=user.id,
            email=user.email,
            created_at=user.created_at,
            is_active=user.is_active
        )
    )


@router.delete("/me", response_model=UserDeleteResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def delete_me(
    request: Request,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deactivate current user account and delete all Kafka topics"""
    user, _ = user_project
    
    # Delete all Kafka topics for the user's projects
    request_id = getattr(request.state, "request_id", None)
    try:
        delete_user_topics(str(user.id), db)
    except Exception as e:
        # Log error but don't fail user deletion if Kafka deletion fails
        logger.log_internal(
            level="ERROR",
            event="kafka_topic_deletion_failed",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            user_id=str(user.id),
            error=str(e)
        )
    
    # Perform logical delete by setting is_active = False
    user.is_active = False
    db.commit()
    
    return UserDeleteResponse()

