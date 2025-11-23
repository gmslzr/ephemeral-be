"""
Unit tests for Kafka service module.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.kafka_service import (
    get_admin_client,
    get_producer,
    create_user_topic,
    create_project_topic,
    publish_messages,
    delete_topic,
    delete_user_topics
)
from kafka.errors import TopicAlreadyExistsError
from app.models import Project, Topic
from unittest.mock import Mock

@pytest.mark.unit
def test_get_admin_client_singleton():
    """Test that get_admin_client returns a singleton."""
    with patch('app.kafka_service.KafkaAdminClient') as mock_client:
        client1 = get_admin_client()
        client2 = get_admin_client()
        
        assert client1 is client2
        # Should be called once (or zero if already initialized by other tests)
        # Since we're mocking the class, if it was None it would call it.
        # Note: global state might be dirty from other tests, so exact count check is tricky
        # unless we reset the global variable.

@pytest.mark.unit
def test_create_user_topic_success(mock_kafka):
    """Test successful user topic creation."""
    user_id = "12345"
    topic_name = create_user_topic(user_id)
    
    assert topic_name == f"user_{user_id}_events"
    assert mock_kafka['admin'].create_topics.called
    # Verify arguments
    args = mock_kafka['admin'].create_topics.call_args[0][0]
    assert len(args) == 1
    assert args[0].name == topic_name
    assert args[0].topic_configs["retention.ms"] == "86400000"

@pytest.mark.unit
def test_create_user_topic_already_exists(mock_kafka):
    """Test user topic creation when topic already exists."""
    mock_kafka['admin'].create_topics.side_effect = TopicAlreadyExistsError()
    
    user_id = "exists"
    # Should not raise exception
    topic_name = create_user_topic(user_id)
    assert topic_name == f"user_{user_id}_events"

@pytest.mark.unit
def test_publish_messages_success(mock_kafka):
    """Test publishing messages."""
    messages = [{"value": {"foo": "bar"}}]
    publish_messages("test-topic", messages)
    
    assert mock_kafka['producer'].send.called
    assert mock_kafka['producer'].flush.called

@pytest.mark.unit
def test_publish_messages_failure(mock_kafka):
    """Test publishing failure."""
    mock_kafka['producer'].send.side_effect = Exception("Kafka Error")
    
    with pytest.raises(Exception) as exc:
        publish_messages("test-topic", [{"value": {}}])
    
    assert "Kafka Error" in str(exc.value)

@pytest.mark.unit
def test_delete_topic_success(mock_kafka):
    """Test topic deletion."""
    delete_topic("test-topic")
    assert mock_kafka['admin'].delete_topics.called
    args = mock_kafka['admin'].delete_topics.call_args[0][0]
    assert args == ["test-topic"]

@pytest.mark.unit
def test_delete_user_topics(mock_kafka):
    """Test deleting all topics for a user."""
    # Mock DB session and objects
    mock_db = MagicMock()
    import uuid
    
    # Setup projects and topics with valid UUIDs
    proj1 = Mock(id=uuid.uuid4())
    proj2 = Mock(id=uuid.uuid4())
    mock_db.query.return_value.filter.return_value.all.side_effect = [
        [proj1, proj2],  # Projects query
        [
            Mock(kafka_topic_name="topic1"),
            Mock(kafka_topic_name="topic2")
        ]  # Topics query
    ]
    
    user_id = str(uuid.uuid4())
    delete_user_topics(user_id, mock_db)
    
    # Should call delete_topic for each topic
    assert mock_kafka['admin'].delete_topics.call_count == 2
    # Check calls
    calls = mock_kafka['admin'].delete_topics.call_args_list
    assert calls[0][0][0] == ["topic1"]
    assert calls[1][0][0] == ["topic2"]

