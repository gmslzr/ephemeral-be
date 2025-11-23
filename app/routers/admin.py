from fastapi import APIRouter, Depends, HTTPException, status, Header
from typing import Optional
from app.connection_tracker import get_all_active_connections
from app.schemas import ActiveStreamsResponse, UserActiveStreams, ActiveStreamInfo
from app.config import settings
from uuid import UUID

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_api_key(admin_api_key: Optional[str] = Header(None, alias="X-Admin-API-Key")) -> None:
    """Verify admin API key"""
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API key not configured"
        )
    
    if not admin_api_key or admin_api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin API key"
        )


@router.get("/active-streams", response_model=ActiveStreamsResponse)
def get_active_streams(_: None = Depends(verify_admin_api_key)):
    """
    Get all active streams for all users.
    Requires admin API key in X-Admin-API-Key header.
    """
    all_connections = get_all_active_connections()
    
    users = []
    for user_id_str, connections in all_connections.items():
        try:
            user_id = UUID(user_id_str)
        except ValueError:
            # Skip invalid user IDs
            continue
        
        active_streams = [
            ActiveStreamInfo(
                connection_id=conn["connection_id"],
                topic_name=conn["topic_name"]
            )
            for conn in connections
        ]
        
        users.append(
            UserActiveStreams(
                user_id=user_id,
                active_streams=active_streams,
                active_streams_count=len(active_streams)
            )
        )
    
    return ActiveStreamsResponse(users=users)

