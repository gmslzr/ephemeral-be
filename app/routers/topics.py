from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from kafka import KafkaConsumer
import json
from datetime import datetime
from app.database import get_db
from app.models import Project, Topic
from app.schemas import PublishRequest, PublishResponse, TopicResponse, TopicsListResponse
from app.dependencies import get_current_user
from app.kafka_service import publish_messages
from app.quota_service import check_quota, increment_usage
from app.connection_tracker import register_connection, unregister_connection
from app.config import settings
from app.rate_limiter import limiter
from app.logger import logger
import asyncio
import threading
import time
from queue import Queue, Empty

router = APIRouter(prefix="/topics", tags=["topics"])

# Maximum payload size per message: 64KB
MAX_PAYLOAD_SIZE = 64 * 1024  # 65536 bytes


@router.get("", response_model=TopicsListResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def list_topics(
    request: Request,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all topics accessible by the current user"""
    user, project_id = user_project
    
    if project_id is None:
        # JWT auth: return all topics from all user's projects
        projects = db.query(Project).filter(Project.user_id == user.id).all()
        project_ids = [p.id for p in projects]
        
        if not project_ids:
            return TopicsListResponse(topics=[])
        
        topics = db.query(Topic).filter(Topic.project_id.in_(project_ids)).all()
    else:
        # API key auth: return topics from the specific project
        # Verify project belongs to user
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == user.id
        ).first()
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        topics = db.query(Topic).filter(Topic.project_id == project_id).all()
    
    return TopicsListResponse(
        topics=[TopicResponse(
            id=topic.id,
            project_id=topic.project_id,
            name=topic.name,
            kafka_topic_name=topic.kafka_topic_name,
            created_at=topic.created_at
        ) for topic in topics]
    )


@router.post("/{topic_name}/publish", response_model=PublishResponse)
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def publish(
    http_request: Request,
    topic_name: str,
    request: PublishRequest,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Publish messages to a topic"""
    user, project_id = user_project
    
    # If project_id is None (JWT auth), find default project
    if project_id is None:
        project = db.query(Project).filter(
            Project.user_id == user.id,
            Project.is_default == True
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Default project not found"
            )
        project_id = project.id
    else:
        # Verify project belongs to user
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == user.id
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
    
    # Find topic - try by logical name first, then by kafka_topic_name
    topic = db.query(Topic).filter(
        Topic.name == topic_name,
        Topic.project_id == project_id
    ).first()
    
    # If not found by logical name, try kafka_topic_name
    if not topic:
        topic = db.query(Topic).filter(
            Topic.kafka_topic_name == topic_name,
            Topic.project_id == project_id
        ).first()
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    request_id = getattr(http_request.state, "request_id", None)
    user_id = str(user.id)
    
    # Validate payload size for each message (64KB limit)
    for i, msg in enumerate(request.messages):
        message_bytes = len(json.dumps(msg.value).encode('utf-8'))
        if message_bytes > MAX_PAYLOAD_SIZE:
            logger.log_publish(
                user_id=user_id,
                topic_name=topic_name,
                bytes=message_bytes,
                status="validation_error",
                request_id=request_id,
                path=http_request.url.path,
                method=http_request.method,
                error=f"Message at index {i} exceeds maximum payload size of {MAX_PAYLOAD_SIZE // 1024}KB (size: {message_bytes} bytes)"
            )
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Message at index {i} exceeds maximum payload size of {MAX_PAYLOAD_SIZE // 1024}KB (size: {message_bytes} bytes)"
            )
    
    # Calculate bytes and message count
    message_count = len(request.messages)
    bytes_count = sum(len(json.dumps(msg.value).encode('utf-8')) for msg in request.messages)
    
    # Check quotas
    try:
        check_quota(
            db=db,
            user_id=user_id,
            project_id=str(project_id),
            direction="in",
            bytes_count=bytes_count,
            message_count=message_count
        )
    except HTTPException as e:
        if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            logger.log_publish(
                user_id=user_id,
                topic_name=topic_name,
                bytes=bytes_count,
                status="quota_exceeded",
                request_id=request_id,
                path=http_request.url.path,
                method=http_request.method,
                error=e.detail
            )
        raise
    
    # Publish to Kafka
    try:
        messages_data = [{"value": msg.value} for msg in request.messages]
        publish_messages(topic.kafka_topic_name, messages_data)
    except Exception as e:
        error_msg = str(e)
        logger.log_publish(
            user_id=user_id,
            topic_name=topic_name,
            bytes=bytes_count,
            status="kafka_error",
            request_id=request_id,
            path=http_request.url.path,
            method=http_request.method,
            error=error_msg
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish messages"
        )
    
    # Increment usage counters
    increment_usage(
        db=db,
        user_id=user_id,
        project_id=str(project_id),
        direction="in",
        bytes_count=bytes_count,
        message_count=message_count
    )
    
    # Log successful publish
    logger.log_publish(
        user_id=user_id,
        topic_name=topic_name,
        bytes=bytes_count,
        status="ok",
        request_id=request_id,
        path=http_request.url.path,
        method=http_request.method
    )
    
    return PublishResponse(success=True)


@router.get("/{topic_name}/stream")
@limiter.limit(f"{settings.rate_limit_requests}/{settings.rate_limit_period}")
def stream(
    request: Request,
    topic_name: str,
    user_project: tuple = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stream messages from a topic using SSE"""
    request_id = getattr(request.state, "request_id", None)
    user_id = str(user.id)
    user, project_id = user_project
    
    # If project_id is None (JWT auth), find default project
    if project_id is None:
        project = db.query(Project).filter(
            Project.user_id == user.id,
            Project.is_default == True
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Default project not found"
            )
        project_id = project.id
    else:
        # Verify project belongs to user
        project = db.query(Project).filter(
            Project.id == project_id,
            Project.user_id == user.id
        ).first()
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
    
    # Find topic - try by logical name first, then by kafka_topic_name
    topic = db.query(Topic).filter(
        Topic.name == topic_name,
        Topic.project_id == project_id
    ).first()
    
    # If not found by logical name, try kafka_topic_name
    if not topic:
        topic = db.query(Topic).filter(
            Topic.kafka_topic_name == topic_name,
            Topic.project_id == project_id
        ).first()
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found"
        )
    
    # Check connection limit
    success, connection_id = register_connection(user_id, topic.name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum 2 active stream connections allowed per user"
        )
    
    # Log stream start
    logger.log_stream(
        event="stream",
        user_id=user_id,
        topic_name=topic_name,
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        status="start"
    )
    
    # Create consumer
    consumer = None
    stream_ended = False
    stream_end_reason = None
    try:
        def safe_deserializer(m):
            """Safely deserialize Kafka message value, handling empty/invalid JSON"""
            if m is None:
                return None
            try:
                decoded = m.decode('utf-8')
                if not decoded or not decoded.strip():
                    return None
                return json.loads(decoded)
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as e:
                # Log deserialization errors but don't fail the stream
                logger.log_internal(
                    level="WARN",
                    event="message_deserialization_failed",
                    request_id=request_id,
                    path=request.url.path,
                    method=request.method,
                    user_id=user_id,
                    error=f"Failed to deserialize message value: {e}"
                )
                return None
        
        consumer = KafkaConsumer(
            topic.kafka_topic_name,
            bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
            group_id=f"user_{user.id}_stream_{connection_id}",
            auto_offset_reset='latest',
            value_deserializer=safe_deserializer,
            enable_auto_commit=True,
            consumer_timeout_ms=1000,  # Poll timeout: 1 second
            max_poll_records=1,  # Process one message at a time
            session_timeout_ms=30000,  # 30 seconds
            heartbeat_interval_ms=10000  # 10 seconds
        )
        
        # Queue for messages and heartbeat signals
        message_queue = Queue()
        stop_event = threading.Event()
        
        def kafka_consumer_thread():
            """Thread that polls Kafka and puts messages in queue"""
            try:
                last_heartbeat_time = time.time()
                heartbeat_interval = 20  # seconds - send every 20s to keep connection alive for up to 1 minute
                
                while not stop_event.is_set():
                    # Poll with timeout
                    message_pack = consumer.poll(timeout_ms=1000)
                    if message_pack:
                        for topic_partition, messages in message_pack.items():
                            for message in messages:
                                if message.value is not None:
                                    message_queue.put(('message', message))
                    
                    # Send periodic heartbeat signal every 20 seconds
                    current_time = time.time()
                    if current_time - last_heartbeat_time >= heartbeat_interval:
                        message_queue.put(('heartbeat', None))
                        last_heartbeat_time = current_time
                        
            except Exception as e:
                error_msg = str(e)
                logger.log_stream(
                    event="stream",
                    user_id=user_id,
                    topic_name=topic_name,
                    request_id=request_id,
                    path=request.url.path,
                    method=request.method,
                    status="kafka_error",
                    error=error_msg
                )
                if not stop_event.is_set():
                    message_queue.put(('error', error_msg))
            finally:
                # Only close consumer when thread is stopping
                try:
                    if consumer:
                        consumer.close()
                except Exception as e:
                    # Ignore close errors
                    pass
        
        # Start Kafka consumer thread
        consumer_thread = threading.Thread(target=kafka_consumer_thread, daemon=True)
        consumer_thread.start()
        
        def generate():
            nonlocal stream_ended, stream_end_reason
            last_heartbeat = time.time()
            heartbeat_interval = 20  # seconds - send every 20s to keep connection alive for up to 1 minute
            
            try:
                # Send initial connection confirmation
                yield f": connected\n\n"
                
                while not stop_event.is_set():
                    try:
                        # Get message or heartbeat from queue with timeout
                        item_type, item_data = message_queue.get(timeout=1)
                        
                        if item_type == 'message':
                            message = item_data
                            value = message.value
                            timestamp = datetime.utcnow().isoformat()
                            
                            # Format as SSE
                            sse_data = json.dumps({
                                "value": value,
                                "timestamp": timestamp
                            })
                            
                            # Calculate bytes for quota tracking
                            bytes_count = len(sse_data.encode('utf-8'))
                            
                            # Check quota before sending
                            try:
                                from app.database import get_session_local
                                SessionLocal = get_session_local()
                                quota_db = SessionLocal()
                                try:
                                    check_quota(
                                        db=quota_db,
                                        user_id=user_id,
                                        project_id=str(project_id),
                                        direction="out",
                                        bytes_count=bytes_count,
                                        message_count=1
                                    )
                                    
                                    # Increment usage
                                    increment_usage(
                                        db=quota_db,
                                        user_id=user_id,
                                        project_id=str(project_id),
                                        direction="out",
                                        bytes_count=bytes_count,
                                        message_count=1
                                    )
                                    
                                    yield f"data: {sse_data}\n\n"
                                finally:
                                    quota_db.close()
                            except HTTPException as e:
                                # Quota exceeded, stop streaming
                                if e.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                                    stream_ended = True
                                    stream_end_reason = "quota_exceeded"
                                    logger.log_stream(
                                        event="stream",
                                        user_id=user_id,
                                        topic_name=topic_name,
                                        request_id=request_id,
                                        path=request.url.path,
                                        method=request.method,
                                        status="quota_exceeded",
                                        error=e.detail
                                    )
                                yield f"data: {json.dumps({'error': 'Quota exceeded'})}\n\n"
                                break
                        
                        elif item_type == 'heartbeat':
                            # Send SSE comment (heartbeat) to keep connection alive
                            yield f": heartbeat {datetime.utcnow().isoformat()}\n\n"
                            last_heartbeat = time.time()
                        
                        elif item_type == 'error':
                            stream_ended = True
                            stream_end_reason = "kafka_error"
                            yield f"data: {json.dumps({'error': 'Consumer error'})}\n\n"
                            break
                    
                    except Empty:
                        # Queue timeout - send periodic heartbeat if needed
                        current_time = time.time()
                        if current_time - last_heartbeat >= heartbeat_interval:
                            yield f": heartbeat {datetime.utcnow().isoformat()}\n\n"
                            last_heartbeat = current_time
                        continue
                    
            except GeneratorExit:
                # Client disconnected
                stream_ended = True
                stream_end_reason = "client_disconnect"
            except Exception as e:
                stream_ended = True
                stream_end_reason = "error"
                logger.log_stream(
                    event="stream",
                    user_id=user_id,
                    topic_name=topic_name,
                    request_id=request_id,
                    path=request.url.path,
                    method=request.method,
                    status="error",
                    error=str(e)
                )
            finally:
                # Signal thread to stop
                stop_event.set()
                # Wait a bit for thread to finish, but don't block indefinitely
                consumer_thread.join(timeout=2)
                # Clean up connection
                unregister_connection(user_id, connection_id)
                
                # Log stream end if not already logged
                if stream_ended:
                    logger.log_stream(
                        event="stream",
                        user_id=user_id,
                        topic_name=topic_name,
                        request_id=request_id,
                        path=request.url.path,
                        method=request.method,
                        status="end",
                        reason=stream_end_reason
                    )
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    except Exception as e:
        unregister_connection(user_id, connection_id)
        logger.log_stream(
            event="stream",
            user_id=user_id,
            topic_name=topic_name,
            request_id=request_id,
            path=request.url.path,
            method=request.method,
            status="kafka_error",
            error=str(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create stream"
        )

