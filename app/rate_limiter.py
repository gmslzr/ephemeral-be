from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from app.config import settings


def get_rate_limit_key(request: Request) -> str:
    """
    Extract rate limit key from request.
    Uses user ID from request state if authenticated, otherwise falls back to IP address.
    The user_id should be set in request.state by middleware (for JWT) or endpoint dependencies (for API keys).
    """
    # Check if user_id was set in request state (by middleware or endpoint dependencies)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"
    
    # Fall back to IP address for unauthenticated requests
    return get_remote_address(request)


# Create limiter instance with custom key function
limiter = Limiter(key_func=get_rate_limit_key)


def set_user_id_in_request(request: Request, user_id: str) -> None:
    """
    Helper function to set user_id in request state.
    This should be called in endpoint functions after authentication but before rate limiting check.
    Note: Due to slowapi's decorator execution order, this needs to be set via middleware
    or before the endpoint is called.
    """
    request.state.user_id = user_id

