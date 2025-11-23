from pydantic import BaseModel, EmailStr
from typing import Optional, List, Union
from datetime import datetime, date
from uuid import UUID


# Auth schemas
class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    created_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None


class UserUpdateResponse(BaseModel):
    message: str = "User updated successfully"
    user: UserResponse


class UserDeleteResponse(BaseModel):
    message: str = "User account deactivated successfully"


# Topic schemas
class MessageValue(BaseModel):
    value: dict


class PublishRequest(BaseModel):
    messages: list[MessageValue]


class PublishResponse(BaseModel):
    success: bool
    message: str = "Messages published successfully"


class TopicResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    kafka_topic_name: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class TopicsListResponse(BaseModel):
    topics: list[TopicResponse]


# API Key schemas
class ApiKeyCreateRequest(BaseModel):
    name: str
    project_id: UUID


class ApiKeyResponse(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    name: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ApiKeyCreateResponse(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID
    name: str
    secret: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# Admin schemas
class ActiveStreamInfo(BaseModel):
    connection_id: str
    topic_name: str


class UserActiveStreams(BaseModel):
    user_id: UUID
    active_streams: List[ActiveStreamInfo]
    active_streams_count: int


class ActiveStreamsResponse(BaseModel):
    users: List[UserActiveStreams]


# Project schemas
class ProjectCreateRequest(BaseModel):
    """Empty request body - project name is auto-generated"""
    pass


class ProjectUpdateRequest(BaseModel):
    name: str


class ProjectResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    created_at: datetime
    is_default: bool
    
    class Config:
        from_attributes = True


class ProjectsListResponse(BaseModel):
    projects: list[ProjectResponse]


class ProjectDeleteResponse(BaseModel):
    message: str = "Project deleted successfully"


# Usage schemas
class UsageMetrics(BaseModel):
    """Usage metrics for a single direction (inbound/outbound)"""
    messages_used: int
    messages_limit: int
    messages_remaining: int
    messages_percentage: float  # 0.0 to 100.0
    
    bytes_used: int
    bytes_limit: int
    bytes_remaining: int
    bytes_percentage: float  # 0.0 to 100.0
    
    # Warning flags
    messages_warning: bool  # True if >=80% used
    bytes_warning: bool  # True if >=80% used


class ProjectUsageResponse(BaseModel):
    """Usage for a specific project"""
    project_id: UUID
    project_name: str
    date: date  # The date this usage is for (typically today)
    
    inbound: UsageMetrics
    outbound: UsageMetrics


class UserUsageResponse(BaseModel):
    """Aggregated usage across all user's projects"""
    user_id: UUID
    date: date
    total_projects: int
    
    # Aggregated metrics across all projects
    inbound: UsageMetrics
    outbound: UsageMetrics
    
    # Per-project breakdown (optional, can be excluded for summary view)
    projects: Optional[List[ProjectUsageResponse]] = None


class UsageResponse(BaseModel):
    """Main usage response - can be project-specific or user-aggregated"""
    usage: Union[ProjectUsageResponse, UserUsageResponse]
    is_project_specific: bool