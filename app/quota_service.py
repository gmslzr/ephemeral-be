from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.models import UsageCounter, GlobalUsageCounter
from datetime import date
from typing import Literal, Dict, Any, Optional

# Free tier limits per user/project
FREE_TIER_MESSAGES_LIMIT = 10_000
FREE_TIER_BYTES_LIMIT = 100 * 1024 * 1024  # 100MB

# Global/cluster-wide limits (panic brake)
MAX_TOTAL_MESSAGES_IN = 200_000
MAX_TOTAL_BYTES_IN = 2_000_000_000  # 2GB


def check_quota(
    db: Session,
    user_id: str,
    project_id: str,
    direction: Literal["in", "out"],
    bytes_count: int,
    message_count: int
) -> None:
    """
    Check if user/project is within quota limits.
    Raises HTTPException with 429 if quota exceeded.
    Also checks global/cluster-wide limits for inbound traffic.
    """
    today = date.today()
    
    # Check global limits for inbound traffic (panic brake)
    # Use SELECT FOR UPDATE to prevent race conditions
    if direction == "in":
        global_counter = db.query(GlobalUsageCounter).filter(
            GlobalUsageCounter.date == today
        ).with_for_update(nowait=True).first()
        
        if not global_counter:
            global_counter = GlobalUsageCounter(
                date=today,
                messages_in=0,
                bytes_in=0
            )
            db.add(global_counter)
            db.commit()  # Commit to get auto-increment ID in SQLite
            # Re-query with lock after creation
            global_counter = db.query(GlobalUsageCounter).filter(
                GlobalUsageCounter.date == today
            ).with_for_update(nowait=True).first()
        
        # Check global message limit
        if global_counter.messages_in + message_count > MAX_TOTAL_MESSAGES_IN:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Cluster-wide daily message limit exceeded. Please try again later."
            )
        
        # Check global bytes limit
        if global_counter.bytes_in + bytes_count > MAX_TOTAL_BYTES_IN:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Cluster-wide daily bytes limit exceeded. Please try again later."
            )
    
    # Check per-user/project limits
    # Use SELECT FOR UPDATE to prevent race conditions
    usage_counter = db.query(UsageCounter).filter(
        and_(
            UsageCounter.user_id == user_id,
            UsageCounter.project_id == project_id,
            UsageCounter.date == today
        )
    ).with_for_update(nowait=True).first()
    
    if not usage_counter:
        usage_counter = UsageCounter(
            user_id=user_id,
            project_id=project_id,
            date=today,
            messages_in=0,
            messages_out=0,
            bytes_in=0,
            bytes_out=0
        )
        db.add(usage_counter)
        db.flush()
        # Re-query with lock after creation
        usage_counter = db.query(UsageCounter).filter(
            and_(
                UsageCounter.user_id == user_id,
                UsageCounter.project_id == project_id,
                UsageCounter.date == today
            )
        ).with_for_update(nowait=True).first()
    
    # Check per-user limits based on direction
    if direction == "in":
        if usage_counter.messages_in + message_count > FREE_TIER_MESSAGES_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Free tier limit exceeded: daily message limit reached"
            )
        if usage_counter.bytes_in + bytes_count > FREE_TIER_BYTES_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Free tier limit exceeded: daily bytes limit reached"
            )
    else:  # direction == "out"
        if usage_counter.messages_out + message_count > FREE_TIER_MESSAGES_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Free tier limit exceeded: daily message limit reached"
            )
        if usage_counter.bytes_out + bytes_count > FREE_TIER_BYTES_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Free tier limit exceeded: daily bytes limit reached"
            )


def increment_usage(
    db: Session,
    user_id: str,
    project_id: str,
    direction: Literal["in", "out"],
    bytes_count: int,
    message_count: int
) -> None:
    """Increment usage counters after successful operation"""
    today = date.today()
    
    # Update global counter for inbound traffic
    # Use SELECT FOR UPDATE to ensure consistency (though check_quota should have locked it)
    if direction == "in":
        global_counter = db.query(GlobalUsageCounter).filter(
            GlobalUsageCounter.date == today
        ).with_for_update(nowait=True).first()
        
        if not global_counter:
            global_counter = GlobalUsageCounter(
                date=today,
                messages_in=0,
                bytes_in=0
            )
            db.add(global_counter)
            try:
                db.flush()
            except Exception:
                # SQLite may need commit for autoincrement
                db.commit()
            global_counter = db.query(GlobalUsageCounter).filter(
                GlobalUsageCounter.date == today
            ).with_for_update(nowait=True).first()
        
        global_counter.messages_in += message_count
        global_counter.bytes_in += bytes_count
    
    # Update per-user/project counter
    # Use SELECT FOR UPDATE to ensure consistency (though check_quota should have locked it)
    usage_counter = db.query(UsageCounter).filter(
        and_(
            UsageCounter.user_id == user_id,
            UsageCounter.project_id == project_id,
            UsageCounter.date == today
        )
    ).with_for_update(nowait=True).first()
    
    if not usage_counter:
        usage_counter = UsageCounter(
            user_id=user_id,
            project_id=project_id,
            date=today,
            messages_in=0,
            messages_out=0,
            bytes_in=0,
            bytes_out=0
        )
        db.add(usage_counter)
        try:
            db.flush()
        except Exception:
            # SQLite may need commit for autoincrement
            db.commit()
        usage_counter = db.query(UsageCounter).filter(
            and_(
                UsageCounter.user_id == user_id,
                UsageCounter.project_id == project_id,
                UsageCounter.date == today
            )
        ).with_for_update(nowait=True).first()
    
    if direction == "in":
        usage_counter.messages_in += message_count
        usage_counter.bytes_in += bytes_count
    else:  # direction == "out"
        usage_counter.messages_out += message_count
        usage_counter.bytes_out += bytes_count
    
    db.commit()


def get_usage_metrics(
    db: Session,
    user_id: str,
    project_id: Optional[str] = None,
    target_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Get usage metrics for a user/project combination.
    
    Args:
        db: Database session
        user_id: User ID
        project_id: Optional project ID. If None, aggregates across all user's projects
        target_date: Optional date. If None, uses today
    
    Returns:
        Dictionary with usage data ready for schema conversion
    """
    if target_date is None:
        target_date = date.today()
    
    # If project_id is provided, get single project usage
    if project_id:
        usage_counter = db.query(UsageCounter).filter(
            and_(
                UsageCounter.user_id == user_id,
                UsageCounter.project_id == project_id,
                UsageCounter.date == target_date
            )
        ).first()
        
        if not usage_counter:
            # Return zero usage
            return {
                "messages_in": 0,
                "messages_out": 0,
                "bytes_in": 0,
                "bytes_out": 0,
                "is_aggregated": False
            }
        
        return {
            "messages_in": usage_counter.messages_in,
            "messages_out": usage_counter.messages_out,
            "bytes_in": usage_counter.bytes_in,
            "bytes_out": usage_counter.bytes_out,
            "is_aggregated": False
        }
    else:
        # Aggregate across all user's projects
        result = db.query(
            func.sum(UsageCounter.messages_in).label("messages_in"),
            func.sum(UsageCounter.messages_out).label("messages_out"),
            func.sum(UsageCounter.bytes_in).label("bytes_in"),
            func.sum(UsageCounter.bytes_out).label("bytes_out")
        ).filter(
            and_(
                UsageCounter.user_id == user_id,
                UsageCounter.date == target_date
            )
        ).first()
        
        return {
            "messages_in": result.messages_in or 0,
            "messages_out": result.messages_out or 0,
            "bytes_in": result.bytes_in or 0,
            "bytes_out": result.bytes_out or 0,
            "is_aggregated": True
        }


def calculate_usage_metrics(
    messages_used: int,
    bytes_used: int,
    messages_limit: int = FREE_TIER_MESSAGES_LIMIT,
    bytes_limit: int = FREE_TIER_BYTES_LIMIT
) -> Dict[str, Any]:
    """
    Calculate usage metrics with warnings.
    
    Returns dict suitable for UsageMetrics schema.
    """
    messages_remaining = max(0, messages_limit - messages_used)
    messages_percentage = (messages_used / messages_limit * 100) if messages_limit > 0 else 0.0
    
    bytes_remaining = max(0, bytes_limit - bytes_used)
    bytes_percentage = (bytes_used / bytes_limit * 100) if bytes_limit > 0 else 0.0
    
    return {
        "messages_used": messages_used,
        "messages_limit": messages_limit,
        "messages_remaining": messages_remaining,
        "messages_percentage": round(messages_percentage, 2),
        "messages_warning": messages_percentage >= 80.0,
        
        "bytes_used": bytes_used,
        "bytes_limit": bytes_limit,
        "bytes_remaining": bytes_remaining,
        "bytes_percentage": round(bytes_percentage, 2),
        "bytes_warning": bytes_percentage >= 80.0
    }

