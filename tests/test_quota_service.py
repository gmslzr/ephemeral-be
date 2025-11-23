"""
Tests for quota service (check_quota, increment_usage).
"""
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch
from datetime import date
from app.quota_service import (
    check_quota,
    increment_usage,
    FREE_TIER_MESSAGES_LIMIT,
    FREE_TIER_BYTES_LIMIT,
    MAX_TOTAL_MESSAGES_IN
)
from app.models import UsageCounter, GlobalUsageCounter

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.mark.unit
def test_check_quota_within_limits(mock_db):
    """Test checking quota when within limits."""
    # Setup mocks
    # Mock global counter
    mock_global = MagicMock(messages_in=0, bytes_in=0)
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        mock_global,  # Global check
        MagicMock(messages_in=0, bytes_in=0)  # User check
    ]
    
    # Should not raise exception
    check_quota(mock_db, "user1", "proj1", "in", 100, 1)

@pytest.mark.unit
def test_check_quota_user_message_limit_exceeded(mock_db):
    """Test when user message limit exceeded."""
    mock_global = MagicMock(messages_in=0, bytes_in=0)
    mock_user_usage = MagicMock(messages_in=FREE_TIER_MESSAGES_LIMIT, bytes_in=0)
    
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        mock_global,
        mock_user_usage
    ]
    
    with pytest.raises(HTTPException) as exc:
        check_quota(mock_db, "user1", "proj1", "in", 100, 1)
    
    assert exc.value.status_code == 429
    assert "daily message limit reached" in exc.value.detail

@pytest.mark.unit
def test_check_quota_user_bytes_limit_exceeded(mock_db):
    """Test when user bytes limit exceeded."""
    mock_global = MagicMock(messages_in=0, bytes_in=0)
    mock_user_usage = MagicMock(messages_in=0, bytes_in=FREE_TIER_BYTES_LIMIT)
    
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        mock_global,
        mock_user_usage
    ]
    
    with pytest.raises(HTTPException) as exc:
        check_quota(mock_db, "user1", "proj1", "in", 100, 1)
    
    assert exc.value.status_code == 429
    assert "daily bytes limit reached" in exc.value.detail

@pytest.mark.unit
def test_check_quota_global_limit_exceeded(mock_db):
    """Test when global cluster limit exceeded."""
    mock_global = MagicMock(messages_in=MAX_TOTAL_MESSAGES_IN, bytes_in=0)
    
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = mock_global
    
    with pytest.raises(HTTPException) as exc:
        check_quota(mock_db, "user1", "proj1", "in", 100, 1)
    
    assert exc.value.status_code == 429
    assert "Cluster-wide" in exc.value.detail

@pytest.mark.unit
def test_check_quota_creates_counters_if_missing(mock_db):
    """Test that counters are created if they don't exist."""
    # Create proper mock objects with numeric attributes
    mock_global_new = MagicMock(messages_in=0, bytes_in=0)
    mock_user_new = MagicMock(messages_in=0, bytes_in=0)
    
    # Return None first (missing), then return new object (created)
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        None, mock_global_new,  # Global: missing -> created
        None, mock_user_new     # User: missing -> created
    ]
    
    check_quota(mock_db, "user1", "proj1", "in", 100, 1)
    
    # Verify add() was called to create new counters
    assert mock_db.add.call_count == 2

@pytest.mark.unit
def test_increment_usage(mock_db):
    """Test incrementing usage counters."""
    mock_global = MagicMock(messages_in=0, bytes_in=0)
    mock_user = MagicMock(messages_in=0, bytes_in=0)
    
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        mock_global,
        mock_user
    ]
    
    increment_usage(mock_db, "user1", "proj1", "in", 100, 1)
    
    assert mock_global.messages_in == 1
    assert mock_global.bytes_in == 100
    assert mock_user.messages_in == 1
    assert mock_user.bytes_in == 100
    assert mock_db.commit.called

@pytest.mark.unit
def test_check_quota_outbound_direction(mock_db):
    """Test quota check for outbound direction."""
    mock_user_usage = MagicMock(messages_out=0, bytes_out=0)
    
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = mock_user_usage
    
    # Should not raise exception
    check_quota(mock_db, "user1", "proj1", "out", 100, 1)

@pytest.mark.unit
def test_check_quota_exact_limit(mock_db):
    """Test quota check at exact limit (should pass)."""
    mock_global = MagicMock(messages_in=FREE_TIER_MESSAGES_LIMIT - 1, bytes_in=0)
    mock_user = MagicMock(messages_in=FREE_TIER_MESSAGES_LIMIT - 1, bytes_in=0)
    
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        mock_global,
        mock_user
    ]
    
    # Should pass (at limit - 1, adding 1 message)
    check_quota(mock_db, "user1", "proj1", "in", 0, 1)

@pytest.mark.unit
def test_check_quota_outbound_bytes_limit(mock_db):
    """Test outbound bytes limit exceeded."""
    mock_user = MagicMock(messages_out=0, bytes_out=FREE_TIER_BYTES_LIMIT)
    
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = mock_user
    
    with pytest.raises(HTTPException) as exc:
        check_quota(mock_db, "user1", "proj1", "out", 100, 1)
    
    assert exc.value.status_code == 429
    assert "bytes limit reached" in exc.value.detail

@pytest.mark.unit
def test_increment_usage_outbound(mock_db):
    """Test incrementing usage for outbound direction."""
    mock_user = MagicMock(messages_out=0, bytes_out=0)

    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = mock_user

    increment_usage(mock_db, "user1", "proj1", "out", 100, 1)

    assert mock_user.messages_out == 1
    assert mock_user.bytes_out == 100
    assert mock_db.commit.called


@pytest.mark.unit
def test_check_quota_global_bytes_limit_exceeded(mock_db):
    """Test when global bytes limit exceeded (not messages)."""
    from app.quota_service import MAX_TOTAL_BYTES_IN

    mock_global = MagicMock(messages_in=0, bytes_in=MAX_TOTAL_BYTES_IN)

    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = mock_global

    with pytest.raises(HTTPException) as exc:
        check_quota(mock_db, "user1", "proj1", "in", 1000, 1)

    assert exc.value.status_code == 429
    assert "Cluster-wide daily bytes limit exceeded" in exc.value.detail


@pytest.mark.unit
def test_check_quota_outbound_message_limit_exceeded(mock_db):
    """Test when outbound message limit exceeded."""
    mock_user = MagicMock(messages_out=FREE_TIER_MESSAGES_LIMIT, bytes_out=0)

    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = mock_user

    with pytest.raises(HTTPException) as exc:
        check_quota(mock_db, "user1", "proj1", "out", 100, 1)

    assert exc.value.status_code == 429
    assert "daily message limit reached" in exc.value.detail


@pytest.mark.unit
def test_increment_usage_creates_global_counter(mock_db):
    """Test increment_usage creates global counter if missing."""
    mock_global_new = MagicMock(messages_in=0, bytes_in=0)
    mock_user = MagicMock(messages_in=0, bytes_in=0)

    # Return None first (missing), then return new object (created)
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        None, mock_global_new,  # Global: missing -> created
        mock_user               # User: exists
    ]

    increment_usage(mock_db, "user1", "proj1", "in", 100, 1)

    # Verify add() was called to create global counter
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.unit
def test_increment_usage_creates_user_counter(mock_db):
    """Test increment_usage creates user counter if missing."""
    mock_global = MagicMock(messages_in=0, bytes_in=0)
    mock_user_new = MagicMock(messages_in=0, bytes_in=0)

    # Return None for user counter (missing), then return new object (created)
    mock_db.query.return_value.filter.return_value.with_for_update.return_value.first.side_effect = [
        mock_global,            # Global: exists
        None, mock_user_new     # User: missing -> created
    ]

    increment_usage(mock_db, "user1", "proj1", "in", 100, 1)

    # Verify add() was called to create user counter
    assert mock_db.add.call_count >= 1
    assert mock_db.commit.called

