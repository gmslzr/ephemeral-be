from fastapi import FastAPI, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.routers import auth, topics, api_keys, admin, projects, usage
from app.database import get_engine
from app.kafka_service import get_admin_client
from app.config import settings
from app.rate_limiter import limiter
from slowapi.errors import RateLimitExceeded
from app.dependencies import get_current_user_jwt, get_current_user_api_key
from app.logger import logger
from sqlalchemy import text
from typing import Dict, Any, Optional, Tuple
from app.models import User
import uuid
import traceback

app = FastAPI(
    title="Kafka API",
    description="FastAPI backend for Kafka message publishing and streaming",
    version="1.0.0"
)

# Add rate limiter state to app
app.state.limiter = limiter


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to generate and track request IDs"""
    
    async def dispatch(self, request: Request, call_next):
        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in request state
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response


# Add request ID middleware first (before other middleware)
app.add_middleware(RequestIDMiddleware)

# CORS middleware
# In production, configure CORS_ORIGINS environment variable with comma-separated allowed origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Configured via CORS_ORIGINS env var
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-API-Key", "X-Request-ID"],
)


class UserExtractionMiddleware(BaseHTTPMiddleware):
    """Middleware to extract user ID from authenticated requests and set in request.state"""
    
    async def dispatch(self, request: Request, call_next):
        # Only try to extract user for paths that need rate limiting (exclude public endpoints)
        if request.url.path not in ["/", "/healthcheck", "/docs", "/openapi.json", "/redoc"]:
            try:
                # Try to extract user from JWT (simpler and most common)
                authorization = request.headers.get("Authorization", "")
                if authorization.startswith("Bearer "):
                    try:
                        from app.auth import decode_jwt
                        from app.database import get_session_local
                        token = authorization.split(" ", 1)[1]
                        user_id = decode_jwt(token)
                        if user_id:
                            # Get database session
                            SessionLocal = get_session_local()
                            db = SessionLocal()
                            try:
                                user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
                                if user:
                                    request.state.user_id = str(user.id)
                            finally:
                                db.close()
                    except Exception:
                        # If extraction fails, limiter will use IP
                        pass
                # Note: API key extraction is complex (requires bcrypt verification)
                # It will be handled at the endpoint level via dependencies
            except Exception:
                # If anything fails, limiter will use IP
                pass
        
        response = await call_next(request)
        return response


# Add user extraction middleware (before rate limiting, so user_id is in state)
app.add_middleware(UserExtractionMiddleware)

# Add rate limit exception handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """
    Handle rate limit exceeded exceptions.
    Returns 429 status code with appropriate message and rate limit headers.
    """
    # Get rate limit information from request state
    rate_limit_info = getattr(request.state, "view_rate_limit", None)
    
    # Get rate limit details from the exception message if available
    # Format: "ratelimit 100 per 1 minute (user:...) exceeded at endpoint: ..."
    limit_value = settings.rate_limit_requests
    limit_period = settings.rate_limit_period
    
    response = JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "error": "rate_limit_exceeded"
        }
    )
    
    # Try to inject headers using slowapi's method if rate_limit_info exists
    if rate_limit_info:
        try:
            response = request.app.state.limiter._inject_headers(
                response,
                rate_limit_info
            )
        except (AttributeError, Exception) as e:
            # Log the failure and fall back to manual header injection
            request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
            logger.log_internal(
                level="WARNING",
                event="rate_limit_header_injection_failed",
                request_id=request_id,
                path=request.url.path,
                method=request.method,
                error=str(e)
            )
    
    # Manually add rate limit headers (always set them, even if slowapi didn't)
    response.headers["X-RateLimit-Limit"] = str(limit_value)
    response.headers["X-RateLimit-Remaining"] = "0"
    
    # Calculate reset time based on the period (default: 1 minute = 60 seconds)
    reset_seconds = 60  # Default for "minute"
    if "hour" in limit_period.lower():
        reset_seconds = 3600
    elif "second" in limit_period.lower():
        reset_seconds = 1
    
    # Set reset time (current time + reset period)
    import time
    reset_at = int(time.time()) + reset_seconds
    response.headers["X-RateLimit-Reset"] = str(reset_at)
    response.headers["Retry-After"] = str(reset_seconds)
    
    return response


# Global exception handler for unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions with structured logging"""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    user_id = getattr(request.state, "user_id", None)
    
    # Format stacktrace
    error_trace = traceback.format_exc()
    
    # Log the exception
    logger.log_internal(
        level="ERROR",
        event="unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        error=f"{type(exc).__name__}: {str(exc)}",
        user_id=user_id,
        stacktrace=error_trace
    )
    
    # Return generic error response
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error": "internal_error"
        }
    )


# Include routers with /api prefix
app.include_router(auth.router)
app.include_router(topics.router)
app.include_router(api_keys.router)
app.include_router(admin.router)
app.include_router(projects.router)
app.include_router(usage.router)


@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    request_id = str(uuid.uuid4())
    logger.log_internal(
        level="INFO",
        event="startup",
        request_id=request_id,
        path="/",
        method="SYSTEM"
    )
    # Database connection is lazy-loaded, so no action needed here


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    request_id = str(uuid.uuid4())
    logger.log_internal(
        level="INFO",
        event="shutdown",
        request_id=request_id,
        path="/",
        method="SYSTEM"
    )


@app.get("/")
def read_root():
    return {"message": "Kafka API", "version": "1.0.0"}


@app.get("/healthcheck")
@limiter.exempt  # Exempt healthcheck from rate limiting
def healthcheck(request: Request):
    """
    Health check endpoint that verifies database and Kafka connectivity.
    Returns 200 if both services are healthy, 503 if any service is unhealthy.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "services": {}
    }
    overall_healthy = True
    
    # Check database connectivity
    db_status = _check_database(request_id)
    health_status["services"]["database"] = db_status
    if not db_status["healthy"]:
        overall_healthy = False
    
    # Check Kafka connectivity
    kafka_status = _check_kafka(request_id)
    health_status["services"]["kafka"] = kafka_status
    if not kafka_status["healthy"]:
        overall_healthy = False
    
    # Update overall status
    health_status["status"] = "healthy" if overall_healthy else "unhealthy"
    
    # Return appropriate status code
    status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        content=health_status,
        status_code=status_code
    )


def _check_database(request_id: str) -> Dict[str, Any]:
    """Check database connectivity"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        
        return {
            "healthy": True,
            "message": "Database connection successful"
        }
    except Exception as e:
        logger.log_internal(
            level="ERROR",
            event="database_health_check",
            request_id=request_id,
            path="/healthcheck",
            method="GET",
            error=str(e)
        )
        return {
            "healthy": False,
            "message": f"Database connection failed: {str(e)}"
        }


def _check_kafka(request_id: str) -> Dict[str, Any]:
    """Check Kafka connectivity"""
    try:
        # Use admin client to list topics - this verifies cluster connectivity
        # This operation requires a connection to Kafka brokers
        admin_client = get_admin_client()
        admin_client.list_topics()
        
        # If we got here, connection is successful
        return {
            "healthy": True,
            "message": "Kafka connection successful"
        }
            
    except Exception as e:
        logger.log_internal(
            level="ERROR",
            event="kafka_health_check",
            request_id=request_id,
            path="/healthcheck",
            method="GET",
            error=str(e)
        )
        return {
            "healthy": False,
            "message": f"Kafka connection failed: {str(e)}"
        }

