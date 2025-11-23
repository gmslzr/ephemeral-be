"""
Tests for configuration module.
"""
import pytest
from app.config import Settings

@pytest.mark.unit
def test_cors_origins_parsing():
    """Test parsing of CORS origins string to list."""
    settings = Settings(
        database_url="sqlite://",
        jwt_secret="x" * 32,
        CORS_ORIGINS="http://a.com,http://b.com"
    )
    
    assert len(settings.cors_origins) == 2
    assert "http://a.com" in settings.cors_origins
    assert "http://b.com" in settings.cors_origins

@pytest.mark.unit
def test_jwt_secret_validation():
    """Test validation of JWT secret length."""
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite://",
            jwt_secret="short"
        )

