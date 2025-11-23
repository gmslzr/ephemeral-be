"""
Tests for dependency injection modules (auth dependencies).
"""
import pytest
from unittest.mock import MagicMock, patch
from app.dependencies import get_current_user_jwt, get_current_user_api_key, get_current_user
from fastapi.security import HTTPAuthorizationCredentials
from app.models import User, ApiKey
from app.auth import hash_password, generate_lookup_hash

@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_current_user_jwt_valid():
    """Test getting user from valid JWT."""
    mock_db = MagicMock()
    user = User(id="123", is_active=True)
    mock_db.query.return_value.filter.return_value.first.return_value = user
    
    with patch('app.dependencies.decode_jwt', return_value="123"):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")
        result = await get_current_user_jwt(creds, mock_db)
        
        assert result is not None
        assert result[0] == user
        assert result[1] is None  # No project ID for JWT

@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_current_user_jwt_invalid():
    """Test getting user from invalid JWT."""
    mock_db = MagicMock()
    with patch('app.dependencies.decode_jwt', return_value=None):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad_token")
        result = await get_current_user_jwt(creds, mock_db)
        assert result is None

@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_current_user_api_key_valid():
    """Test getting user from valid API key."""
    mock_db = MagicMock()
    secret = "secret123"
    lookup_hash = generate_lookup_hash(secret)
    secret_hash = hash_password(secret)
    
    user = User(id="u1", is_active=True)
    api_key = ApiKey(user_id="u1", project_id="p1", secret_hash=secret_hash, lookup_hash=lookup_hash)
    
    # Mock query chain
    # First query: ApiKey via lookup_hash
    mock_db.query.return_value.join.return_value.filter.return_value.first.return_value = api_key
    # Second query: User
    mock_db.query.return_value.filter.return_value.first.return_value = user
    
    result = await get_current_user_api_key(f"ApiKey {secret}", mock_db)
    
    assert result is not None
    assert result[0] == user
    assert result[1] == "p1"

@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_current_user_precedence():
    """Test that JWT takes precedence over API key."""
    jwt_res = (User(id="u1"), None)
    api_res = (User(id="u2"), "p2")
    request = MagicMock()
    
    # Both provided
    result = await get_current_user(request, jwt_res, api_res)
    assert result == jwt_res
    
    # Only API key
    result = await get_current_user(request, None, api_res)
    assert result == api_res

