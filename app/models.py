from sqlalchemy import Column, String, Boolean, ForeignKey, BigInteger, Date, Text, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    usage_counters = relationship("UsageCounter", back_populates="user", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    
    user = relationship("User", back_populates="projects")
    topics = relationship("Topic", back_populates="project", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="project", cascade="all, delete-orphan")
    usage_counters = relationship("UsageCounter", back_populates="project", cascade="all, delete-orphan")


class Topic(Base):
    __tablename__ = "topics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name = Column(Text, nullable=False)
    kafka_topic_name = Column(Text, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    project = relationship("Project", back_populates="topics")


class ApiKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    name = Column(Text, nullable=False)
    secret_hash = Column(Text, nullable=False)
    lookup_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hex digest (64 chars)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    user = relationship("User", back_populates="api_keys")
    project = relationship("Project", back_populates="api_keys")


class UsageCounter(Base):
    __tablename__ = "usage_counters"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    date = Column(Date, nullable=False)
    messages_in = Column(BigInteger, nullable=False, default=0)
    messages_out = Column(BigInteger, nullable=False, default=0)
    bytes_in = Column(BigInteger, nullable=False, default=0)
    bytes_out = Column(BigInteger, nullable=False, default=0)
    
    user = relationship("User", back_populates="usage_counters")
    project = relationship("Project", back_populates="usage_counters")
    
    __table_args__ = (UniqueConstraint("user_id", "project_id", "date", name="uq_user_project_date"),)


class GlobalUsageCounter(Base):
    __tablename__ = "global_usage_counters"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True)
    messages_in = Column(BigInteger, nullable=False, default=0)
    bytes_in = Column(BigInteger, nullable=False, default=0)

