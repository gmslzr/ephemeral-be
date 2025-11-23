from kafka import KafkaProducer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError
from typing import List, Optional
from sqlalchemy.orm import Session
import json
from app.config import settings
from app.logger import logger
import uuid

_admin_client = None
_producer = None


def get_admin_client():
    """Get or create Kafka admin client"""
    global _admin_client
    if _admin_client is None:
        try:
            _admin_client = KafkaAdminClient(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(",")
            )
        except Exception as e:
            request_id = str(uuid.uuid4())
            logger.log_internal(
                level="ERROR",
                event="kafka_connection",
                request_id=request_id,
                path="/",
                method="SYSTEM",
                error=f"Failed to create Kafka admin client: {str(e)}"
            )
            raise
    return _admin_client


def get_producer():
    """Get or create Kafka producer"""
    global _producer
    if _producer is None:
        try:
            _producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
        except Exception as e:
            request_id = str(uuid.uuid4())
            logger.log_internal(
                level="ERROR",
                event="kafka_connection",
                request_id=request_id,
                path="/",
                method="SYSTEM",
                error=f"Failed to create Kafka producer: {str(e)}"
            )
            raise
    return _producer


def create_user_topic(user_id: str) -> str:
    """Create a Kafka topic for a user and return the topic name"""
    topic_name = f"user_{user_id}_events"
    
    admin_client = get_admin_client()
    
    topic = NewTopic(
        name=topic_name,
        num_partitions=1,
        replication_factor=1,
        topic_configs={
            "retention.ms": str(24 * 60 * 60 * 1000)  # 24 hours in milliseconds
        }
    )
    
    try:
        admin_client.create_topics([topic])
        logger.info(f"Created Kafka topic: {topic_name}")
    except TopicAlreadyExistsError:
        logger.info(f"Topic already exists: {topic_name}")
    except Exception as e:
        logger.error(f"Error creating topic {topic_name}: {e}")
        raise
    
    return topic_name


def create_project_topic(project_id: str) -> str:
    """Create a Kafka topic for a project and return the topic name"""
    topic_name = f"project_{project_id}_events"
    
    admin_client = get_admin_client()
    
    topic = NewTopic(
        name=topic_name,
        num_partitions=1,
        replication_factor=1,
        topic_configs={
            "retention.ms": str(24 * 60 * 60 * 1000)  # 24 hours in milliseconds
        }
    )
    
    request_id = str(uuid.uuid4())
    try:
        admin_client.create_topics([topic])
        logger.log_internal(
            level="INFO",
            event="kafka_topic_created",
            request_id=request_id,
            path="/",
            method="SYSTEM",
            topic_name=topic_name
        )
    except TopicAlreadyExistsError:
        logger.log_internal(
            level="INFO",
            event="kafka_topic_exists",
            request_id=request_id,
            path="/",
            method="SYSTEM",
            topic_name=topic_name
        )
    except Exception as e:
        logger.log_internal(
            level="ERROR",
            event="kafka_topic_creation_failed",
            request_id=request_id,
            path="/",
            method="SYSTEM",
            error=f"Error creating topic {topic_name}: {str(e)}"
        )
        raise
    
    return topic_name


def publish_messages(topic_name: str, messages: List[dict]) -> None:
    """Publish messages to a Kafka topic"""
    producer = get_producer()
    request_id = str(uuid.uuid4())
    
    for message in messages:
        try:
            future = producer.send(topic_name, value=message.get("value", {}))
            # Wait for the message to be sent (optional, for error checking)
            future.get(timeout=10)
        except Exception as e:
            logger.log_internal(
                level="ERROR",
                event="kafka_publish_failed",
                request_id=request_id,
                path="/",
                method="SYSTEM",
                topic_name=topic_name,
                error=str(e)
            )
            raise
    
    # Flush to ensure all messages are sent
    producer.flush()


def delete_topic(topic_name: str) -> None:
    """Delete a Kafka topic permanently"""
    admin_client = get_admin_client()
    request_id = str(uuid.uuid4())
    
    try:
        admin_client.delete_topics([topic_name])
        logger.log_internal(
            level="INFO",
            event="kafka_topic_deleted",
            request_id=request_id,
            path="/",
            method="SYSTEM",
            topic_name=topic_name
        )
    except Exception as e:
        logger.log_internal(
            level="ERROR",
            event="kafka_topic_deletion_failed",
            request_id=request_id,
            path="/",
            method="SYSTEM",
            topic_name=topic_name,
            error=str(e)
        )
        raise


def delete_user_topics(user_id: str, db: Session) -> None:
    """Delete all Kafka topics for a user's projects permanently"""
    from app.models import Project, Topic
    from uuid import UUID
    
    # Convert string user_id to UUID for database query
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
    
    # Get all projects for the user
    projects = db.query(Project).filter(Project.user_id == user_uuid).all()
    
    request_id = str(uuid.uuid4())
    if not projects:
        logger.log_internal(
            level="INFO",
            event="kafka_topics_deletion_skipped",
            request_id=request_id,
            path="/",
            method="SYSTEM",
            user_id=user_id,
            reason="no_projects"
        )
        return
    
    # Get all topic names from all user's projects
    project_ids = [p.id for p in projects]
    topics = db.query(Topic).filter(Topic.project_id.in_(project_ids)).all()
    
    if not topics:
        logger.log_internal(
            level="INFO",
            event="kafka_topics_deletion_skipped",
            request_id=request_id,
            path="/",
            method="SYSTEM",
            user_id=user_id,
            reason="no_topics"
        )
        return
    
    # Delete each Kafka topic permanently
    # Log errors but don't fail the entire operation if one topic fails
    deleted_count = 0
    failed_count = 0
    
    for topic in topics:
        try:
            delete_topic(topic.kafka_topic_name)
            deleted_count += 1
        except Exception as e:
            failed_count += 1
            logger.log_internal(
                level="ERROR",
                event="kafka_topic_deletion_failed",
                request_id=request_id,
                path="/",
                method="SYSTEM",
                user_id=user_id,
                topic_name=topic.kafka_topic_name,
                error=str(e)
            )
    
    logger.log_internal(
        level="INFO",
        event="kafka_topics_deletion_completed",
        request_id=request_id,
        path="/",
        method="SYSTEM",
        user_id=user_id,
        deleted_count=deleted_count,
        failed_count=failed_count
    )

