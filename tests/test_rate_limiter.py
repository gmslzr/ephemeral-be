"""
Tests for rate limiter utilities.
"""
import pytest
from unittest.mock import MagicMock
from app.rate_limiter import get_rate_limit_key

@pytest.mark.unit
def test_get_rate_limit_key_authenticated():
    """Test key generation for authenticated user."""
    request = MagicMock()
    request.state.user_id = "123"
    
    key = get_rate_limit_key(request)
    assert key == "user:123"

@pytest.mark.unit
def test_get_rate_limit_key_anonymous():
    """Test key generation for anonymous user (IP based)."""
    request = MagicMock()
    del request.state.user_id  # Ensure no user_id
    # Mock client.host
    request.client.host = "10.0.0.1"
    request.headers.get.return_value = None  # No X-Forwarded-For
    
    key = get_rate_limit_key(request)
    assert key == "10.0.0.1"

