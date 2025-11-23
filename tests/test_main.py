"""
Tests for main application endpoints and middleware.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_root_endpoint(test_client: TestClient):
    """Test root endpoint."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert "Kafka API" in response.json()["message"]

@pytest.mark.unit
def test_healthcheck_healthy(test_client: TestClient):
    """Test healthcheck when all services are healthy."""
    # Mock database and kafka checks
    with patch("app.main._check_database", return_value={"healthy": True}), \
         patch("app.main._check_kafka", return_value={"healthy": True}):
        
        response = test_client.get("/healthcheck")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

@pytest.mark.unit
def test_healthcheck_unhealthy(test_client: TestClient):
    """Test healthcheck when a service is unhealthy."""
    with patch("app.main._check_database", return_value={"healthy": False}), \
         patch("app.main._check_kafka", return_value={"healthy": True}):
        
        response = test_client.get("/healthcheck")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

@pytest.mark.unit
def test_healthcheck_kafka_unhealthy(test_client: TestClient):
    """Test healthcheck when Kafka is unhealthy."""
    with patch("app.main._check_database", return_value={"healthy": True}), \
         patch("app.main._check_kafka", return_value={"healthy": False}):
        
        response = test_client.get("/healthcheck")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

@pytest.mark.unit
def test_healthcheck_both_unhealthy(test_client: TestClient):
    """Test healthcheck when both services are unhealthy."""
    with patch("app.main._check_database", return_value={"healthy": False}), \
         patch("app.main._check_kafka", return_value={"healthy": False}):
        
        response = test_client.get("/healthcheck")
        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

@pytest.mark.unit
def test_healthcheck_services_detail(test_client: TestClient):
    """Test healthcheck returns service details."""
    with patch("app.main._check_database", return_value={"healthy": True, "message": "OK"}), \
         patch("app.main._check_kafka", return_value={"healthy": True, "message": "OK"}):
        
        response = test_client.get("/healthcheck")
        assert response.status_code == 200
        assert "services" in response.json()
        assert "database" in response.json()["services"]
        assert "kafka" in response.json()["services"]

@pytest.mark.unit
def test_middleware_extracts_user_id(test_client: TestClient, test_db):
    """Test that middleware extracts user ID from JWT."""
    from tests.conftest import create_user_with_credentials
    from app.auth import create_jwt
    
    user = create_user_with_credentials(test_db, "middleware@example.com", "password123")
    token = create_jwt(str(user.id))
    
    # Make a request that would use rate limiting
    response = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    # Should succeed (middleware should have extracted user_id)
    assert response.status_code == 200

@pytest.mark.unit
def test_check_database_function(test_client: TestClient):
    """Test _check_database function directly."""
    from app.main import _check_database

    # Should return healthy status (using test database)
    result = _check_database(request_id="test-request-id")
    assert "healthy" in result
    assert "message" in result

@pytest.mark.unit
def test_check_kafka_function(test_client: TestClient):
    """Test _check_kafka function directly."""
    from app.main import _check_kafka
    from unittest.mock import patch

    # Mock Kafka admin client
    with patch("app.main.get_admin_client") as mock_get_admin:
        mock_admin = MagicMock()
        mock_admin.list_topics.return_value = []
        mock_get_admin.return_value = mock_admin

        result = _check_kafka(request_id="test-request-id")
        assert "healthy" in result
        assert "message" in result


@pytest.mark.unit
def test_check_database_failure():
    """Test _check_database when database connection fails."""
    from app.main import _check_database
    from unittest.mock import patch

    # Mock database engine to raise exception
    with patch("app.main.get_engine") as mock_engine:
        mock_engine.return_value.connect.side_effect = Exception("Database connection failed")

        result = _check_database(request_id="test-request-id")
        assert result["healthy"] is False
        assert "Database connection failed" in result["message"]


@pytest.mark.unit
def test_check_kafka_failure():
    """Test _check_kafka when Kafka connection fails."""
    from app.main import _check_kafka
    from unittest.mock import patch

    # Mock Kafka admin client to raise exception
    with patch("app.main.get_admin_client") as mock_get_admin:
        mock_admin = MagicMock()
        mock_admin.list_topics.side_effect = Exception("Kafka connection failed")
        mock_get_admin.return_value = mock_admin

        result = _check_kafka(request_id="test-request-id")
        assert result["healthy"] is False
        assert "Kafka connection failed" in result["message"]


@pytest.mark.unit
def test_rate_limit_handler():
    """Test rate limit exception handler."""
    from app.main import rate_limit_handler, app
    from slowapi.errors import RateLimitExceeded
    from slowapi.wrappers import Limit
    from fastapi import Request
    from unittest.mock import MagicMock
    import asyncio

    # Create a mock request
    mock_request = MagicMock(spec=Request)
    mock_request.state = MagicMock()
    mock_request.state.view_rate_limit = None
    mock_request.app = app

    # Create mock limit object
    mock_limit = MagicMock(spec=Limit)
    mock_limit.error_message = None
    mock_limit.limit = "100/minute"

    # Create rate limit exception
    exc = RateLimitExceeded(mock_limit)

    # Call handler
    response = asyncio.run(rate_limit_handler(mock_request, exc))

    assert response.status_code == 429
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Reset" in response.headers
    assert "Retry-After" in response.headers


@pytest.mark.unit
def test_rate_limit_handler_with_hour_period():
    """Test rate limit handler with 'hour' period."""
    from app.main import rate_limit_handler, app
    from slowapi.errors import RateLimitExceeded
    from slowapi.wrappers import Limit
    from fastapi import Request
    from unittest.mock import MagicMock, patch
    import asyncio

    # Create a mock request
    mock_request = MagicMock(spec=Request)
    mock_request.state = MagicMock()
    mock_request.state.view_rate_limit = None
    mock_request.app = app

    # Patch settings to use 'hour' period
    with patch("app.main.settings") as mock_settings:
        mock_settings.rate_limit_requests = 100
        mock_settings.rate_limit_period = "hour"

        mock_limit = MagicMock(spec=Limit)
        mock_limit.error_message = None
        mock_limit.limit = "100/hour"
        exc = RateLimitExceeded(mock_limit)
        response = asyncio.run(rate_limit_handler(mock_request, exc))

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "3600"


@pytest.mark.unit
def test_rate_limit_handler_with_second_period():
    """Test rate limit handler with 'second' period."""
    from app.main import rate_limit_handler, app
    from slowapi.errors import RateLimitExceeded
    from slowapi.wrappers import Limit
    from fastapi import Request
    from unittest.mock import MagicMock, patch
    import asyncio

    mock_request = MagicMock(spec=Request)
    mock_request.state = MagicMock()
    mock_request.state.view_rate_limit = None
    mock_request.app = app

    with patch("app.main.settings") as mock_settings:
        mock_settings.rate_limit_requests = 10
        mock_settings.rate_limit_period = "second"

        mock_limit = MagicMock(spec=Limit)
        mock_limit.error_message = None
        mock_limit.limit = "10/second"
        exc = RateLimitExceeded(mock_limit)
        response = asyncio.run(rate_limit_handler(mock_request, exc))

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"


@pytest.mark.unit
def test_rate_limit_handler_inject_headers_failure():
    """Test rate limit handler when header injection fails."""
    from app.main import rate_limit_handler, app
    from slowapi.errors import RateLimitExceeded
    from slowapi.wrappers import Limit
    from fastapi import Request
    from unittest.mock import MagicMock
    import asyncio

    mock_request = MagicMock(spec=Request)
    mock_request.state = MagicMock()
    mock_request.state.request_id = "test-request-id"
    mock_request.url.path = "/test"
    mock_request.method = "GET"

    # Provide rate_limit_info but make injection fail
    mock_request.state.view_rate_limit = {"some": "data"}
    mock_request.app.state.limiter._inject_headers = MagicMock(side_effect=AttributeError("Injection failed"))

    mock_limit = MagicMock(spec=Limit)
    mock_limit.error_message = None
    mock_limit.limit = "100/minute"
    exc = RateLimitExceeded(mock_limit)
    response = asyncio.run(rate_limit_handler(mock_request, exc))

    # Should still return proper response even if injection fails
    assert response.status_code == 429
    assert "X-RateLimit-Limit" in response.headers


@pytest.mark.unit
def test_startup_event():
    """Test startup event handler."""
    from app.main import startup_event
    import asyncio

    # Should complete without errors
    asyncio.run(startup_event())


@pytest.mark.unit
def test_shutdown_event():
    """Test shutdown event handler."""
    from app.main import shutdown_event
    import asyncio

    # Should complete without errors
    asyncio.run(shutdown_event())

