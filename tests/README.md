# Test Suite for User Management

## Overview

Comprehensive unit tests for all user management functionality in the FastAPI Kafka Backend.

## Test Coverage

- **69 tests** covering all user management endpoints
- **100% coverage** on `app/auth.py` (password hashing, JWT)
- **94% coverage** on `app/routers/auth.py` (user endpoints)

## Running Tests

### Run all tests
```bash
pytest tests/
```

### Run specific test file
```bash
pytest tests/test_user_signup.py -v
```

### Run with coverage report
```bash
pytest tests/ --cov=app --cov-report=html
# View coverage report in htmlcov/index.html
```

### Run only user management tests
```bash
pytest tests/test_user_*.py -v
```

## Test Files

| File | Purpose | Tests |
|------|---------|-------|
| `test_user_signup.py` | User creation (POST /auth/signup) | 13 tests |
| `test_user_login.py` | User authentication (POST /auth/login) | 15 tests |
| `test_user_me.py` | Get current user (GET /auth/me) | 14 tests |
| `test_user_update.py` | Update user (PATCH /auth/me) | 14 tests |
| `test_user_delete.py` | Delete user (DELETE /auth/me) | 13 tests |

## Test Categories

### Signup Tests
- ✓ Successful user creation
- ✓ Default project and Kafka topic creation
- ✓ Email normalization (lowercase, trim)
- ✓ Duplicate email rejection
- ✓ Password hashing with bcrypt
- ✓ JWT token generation
- ✓ Invalid email format rejection
- ✓ Long password support (>72 chars)

### Login Tests
- ✓ Successful authentication
- ✓ JWT token validity
- ✓ Wrong password rejection
- ✓ Non-existent user rejection
- ✓ Inactive user rejection
- ✓ Case-insensitive email login
- ✓ Multiple login sessions

### Get User Tests
- ✓ JWT authentication
- ✓ API key authentication
- ✓ Invalid token rejection
- ✓ Inactive user rejection
- ✓ Correct field exposure (no password)

### Update Tests
- ✓ Email update
- ✓ Password update
- ✓ Combined email + password update
- ✓ Email normalization
- ✓ Email uniqueness validation
- ✓ Empty update rejection
- ✓ Password re-hashing
- ✓ Login with new credentials

### Delete Tests
- ✓ Soft delete (sets is_active=False)
- ✓ Kafka topic cleanup
- ✓ Graceful Kafka failure handling
- ✓ Deleted user cannot login
- ✓ Deleted user cannot access endpoints
- ✓ Database records remain (audit trail)

## Recent Fixes

### Email Normalization
- ✅ **FIXED**: Login endpoint now normalizes email to lowercase and trims whitespace (consistent with signup)
- All 69 tests now passing

## Fixtures

### Database
- `test_db`: In-memory SQLite database (fresh per test)
- `test_client`: FastAPI TestClient with mocked Kafka

### Mocks
- `mock_kafka`: Mocks Kafka admin client and producer
- Prevents external dependencies during tests

### Users
- `test_user`: Creates authenticated test user
- `auth_headers`: Generates JWT headers for requests
- `multiple_users`: Creates 3 test users with projects

## Notes

- All tests use in-memory SQLite for speed
- Kafka is fully mocked to avoid external dependencies
- UUID handling is patched for SQLite compatibility
- Each test gets a fresh database (function-scoped fixtures)
