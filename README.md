# Ephemeral: A Tiny Kafka SaaS That Shouldn't Exist.

A fun-sized service that lets users spawn a Kafka topic on demand. For free.

Spin up a topic. Produce. Consume. Blow it up. Repeat.

Shamelessly inspired by [The Kafka Guy](https://www.linkedin.com/posts/stanislavkozlovski_kafka-apachekafka-kafkacosts-activity-7395803182750216192-o_27).

Vibecoded on a lazy weekend using ChatGPT & Cursor.

## Why?

Sometimes you don't need:
- A horizontally scalable cluster engineered for theoretical peak throughput.
- A Kubernetes cluster to print 'Hello World'.
- 99.9999% availability.
- A 30-min deployment that fails on step 15.
- A credit card.

Sometimes all you need is:
- A shipped product.
- 1 topic.
- 1 tiny API.
- An [enshitification](https://www.urbandictionary.com/define.php?term=Enshitification)-free environment.

## Features

- **User Authentication**: Sign up, login with JWT tokens
- **Kafka Integration**: Automatic topic creation per user
- **Message Publishing**: Publish messages to user's Kafka topic via HTTP API
- **Streaming Consumption**: Real-time message streaming via Server-Sent Events (SSE)
- **API Keys**: Generate API keys for programmatic access
- **Quota Management**: Per-user and cluster-wide quota enforcement
- **Connection Limits**: Maximum 2 active stream connections per user

## Tech Stack

- FastAPI
- PostgreSQL
- Kafka (kafka-python)
- SQLAlchemy with Alembic migrations
- JWT authentication

## Prerequisites

- Python 3.11+
- PostgreSQL database
- Kafka cluster (or local Kafka instance)
- Virtual environment (recommended)

## Setup

### 1. Clone and Install Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/kafka_api_db
JWT_SECRET=your-secret-key-change-this-in-production
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

**Important**: Change `JWT_SECRET` to a secure random string in production.

### 3. Database Setup

```bash
# Run migrations to create database schema
alembic upgrade head
```

This will create the following tables:
- `users` - User accounts
- `projects` - User projects (each user gets a default project)
- `topics` - Logical topics (each user gets a default "events" topic)
- `api_keys` - API keys for authentication
- `usage_counters` - Per-user/project daily usage tracking
- `global_usage_counters` - Cluster-wide daily usage tracking

### 4. Start the Server

```bash
# Run with uvicorn
uvicorn app.main:app --reload

# Or specify host and port
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

API documentation (Swagger UI): `http://localhost:8000/docs`

### Quick Reference

- **Public**: `/`, `/healthcheck`
- **Authentication**: `/auth/signup`, `/auth/login`, `/auth/me`, `/auth/me` (PATCH, DELETE)
- **Projects**: `/projects` (GET, POST), `/projects/{id}` (PATCH, DELETE)
- **Topics**: `/topics` (GET), `/topics/{name}/publish` (POST), `/topics/{name}/stream` (GET, SSE)
- **API Keys**: `/api-keys` (GET, POST), `/api-keys/{id}` (DELETE)
- **Usage**: `/usage` (GET), `/usage/projects` (GET)
- **Admin**: `/admin/active-streams` (GET)

### Authentication Methods

1. **JWT Token** (for humans):
   ```
   Authorization: Bearer <jwt_token>
   ```

2. **API Key** (for robots):
   ```
   Authorization: Bearer <api_key_secret>
   ```
   Note: API keys are project-specific and scoped to that project's resources.

All authenticated endpoints require one of the above authentication methods.

## Quota Limits

### Free Tier
- **Messages**: 10,000 per day (inbound or outbound)
- **Bytes**: 100 MB per day (inbound or outbound)

### If this ever hits we're done.
- **Total Messages In**: 200,000 per day
- **Total Bytes In**: 2 GB per day

When limits are exceeded, the API returns `429 Too Many Requests` with an appropriate error message.

## Testing

### Using curl

```bash
# Sign up
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass123"}'

# Save the token from response
TOKEN="your-jwt-token-here"

# Publish messages
curl -X POST http://localhost:8000/topics/events/publish \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"value": {"test": "message"}}]}'

# Stream messages (SSE)
curl -N http://localhost:8000/topics/events/stream \
  -H "Authorization: Bearer $TOKEN"
```

### Using Python requests

```python
import requests

BASE_URL = "http://localhost:8000"

# Sign up
response = requests.post(f"{BASE_URL}/auth/signup", json={
    "email": "test@example.com",
    "password": "testpass123"
})
token = response.json()["token"]

# Publish
headers = {"Authorization": f"Bearer {token}"}
requests.post(
    f"{BASE_URL}/topics/events/publish",
    headers=headers,
    json={"messages": [{"value": {"test": "data"}}]}
)

# Stream (using requests with stream=True)
response = requests.get(
    f"{BASE_URL}/topics/events/stream",
    headers=headers,
    stream=True
)
for line in response.iter_lines():
    if line:
        print(line.decode('utf-8'))
```

## Project Structure

```
api-01-kf/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Environment configuration
│   ├── database.py             # SQLAlchemy setup
│   ├── models.py               # Database models
│   ├── schemas.py              # Pydantic schemas
│   ├── auth.py                 # Password hashing & JWT
│   ├── dependencies.py         # FastAPI dependencies
│   ├── kafka_service.py        # Kafka admin & producer
│   ├── quota_service.py        # Quota checking
│   ├── connection_tracker.py  # Stream connection tracking
│   └── routers/
│       ├── auth.py             # Auth endpoints
│       ├── topics.py            # Topic endpoints
│       └── api_keys.py          # API key endpoints
├── migrations/                 # Alembic migrations
├── alembic.ini                 # Alembic config
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Development

### Running Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Code Style

Seriously vibecoded.

## License

What license?

