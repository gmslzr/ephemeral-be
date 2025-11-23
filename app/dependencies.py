from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional, Tuple
from app.database import get_db
from app.models import User, ApiKey
from app.auth import decode_jwt, verify_password, generate_lookup_hash

security = HTTPBearer(auto_error=False)


async def get_current_user_jwt(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[Tuple[User, Optional[str]]]:
    """Extract user from JWT token"""
    if not credentials:
        return None
    
    token = credentials.credentials
    user_id = decode_jwt(token)
    if not user_id:
        return None
    
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return None
    
    return (user, None)  # (user, project_id) - project_id is None for JWT


async def get_current_user_api_key(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[Tuple[User, str]]:
    """Extract user from API key"""
    if not authorization:
        return None
    
    try:
        auth_type, secret = authorization.split(" ", 1)
        if auth_type.lower() != "apikey":
            return None
    except ValueError:
        return None
    
    # Fast O(1) API key lookup using SHA-256 lookup hash
    lookup_hash = generate_lookup_hash(secret)
    
    # O(1) database index lookup instead of O(n) iteration
    api_key = db.query(ApiKey).join(User).filter(
        ApiKey.lookup_hash == lookup_hash,
        User.is_active == True
    ).first()
    
    if api_key and verify_password(secret, api_key.secret_hash):
        # Only 1 bcrypt check instead of N!
        # Update last_used_at
        from datetime import datetime
        api_key.last_used_at = datetime.utcnow()
        db.commit()
        
        # User is already loaded from join, but verify it's active
        user = db.query(User).filter(User.id == api_key.user_id, User.is_active == True).first()
        if user:
            return (user, str(api_key.project_id))
    
    # Fallback for existing API keys without lookup_hash (backward compatibility)
    # This is O(n) but only runs for old keys that haven't been migrated
    api_keys = db.query(ApiKey).join(User).filter(
        ApiKey.lookup_hash.is_(None),  # Only check keys without lookup_hash
        User.is_active == True
    ).all()
    
    for api_key in api_keys:
        if verify_password(secret, api_key.secret_hash):
            # Update last_used_at and backfill lookup_hash for future lookups
            from datetime import datetime
            api_key.last_used_at = datetime.utcnow()
            api_key.lookup_hash = lookup_hash  # Backfill for next time
            db.commit()
            
            user = db.query(User).filter(User.id == api_key.user_id, User.is_active == True).first()
            if user:
                return (user, str(api_key.project_id))
    
    return None


async def get_current_user(
    request: Request,
    jwt_result: Optional[Tuple[User, Optional[str]]] = Depends(get_current_user_jwt),
    api_key_result: Optional[Tuple[User, str]] = Depends(get_current_user_api_key),
) -> Tuple[User, Optional[str]]:
    """Get current user from either JWT or API key (JWT takes precedence)"""
    if jwt_result:
        user, project_id = jwt_result
        # Set user_id in request state for rate limiting (if not already set by middleware)
        if not hasattr(request.state, "user_id"):
            request.state.user_id = str(user.id)
        return jwt_result
    
    if api_key_result:
        user, project_id = api_key_result
        # Set user_id in request state for rate limiting (API keys may not be handled by middleware)
        request.state.user_id = str(user.id)
        return api_key_result
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )

