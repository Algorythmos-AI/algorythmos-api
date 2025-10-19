# PDF Usage Extraction Service

Production-ready FastAPI microservice that extracts structured internet usage data from telecom PDF invoices. Features provider-specific extractors (Orange France + generic fallback), async processing with SQLAlchemy persistence, idempotency-safe API, Prometheus metrics, and robust error handling. Deployed on Vercel at https://api.algorythmos.fr.

## ✨ Key Features

- 🔄 **Dual-mode file input**: Upload files directly or reference pre-uploaded paths
- 🔐 **Idempotency support**: Safe request retries with `Idempotency-Key` header
- 📊 **Database persistence**: SQLAlchemy async with PostgreSQL/SQLite support
- 📈 **Observability**: Prometheus metrics for monitoring and alerting
- 🔔 **Webhook callbacks**: HMAC-SHA256 secured notifications
- ⚡ **Retry logic**: Exponential backoff with jitter for vendor requests
- 🎯 **Cursor pagination**: Efficient runs listing with filtering
- 🏷️ **OpenAPI docs**: Comprehensive auto-generated API documentation

## 🚀 Quick Start

### Local Development

1. **Setup environment**:
   ```bash
   # Copy example environment file
   cp .env.example .env
   # Edit .env with your API key and settings
   ```

2. **Install dependencies**:
   ```bash
   # Using uv (recommended)
   make install
   # OR using pip/venv
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -e .[dev]
   ```

3. **Start development server**:
   ```bash
   make dev
   # OR directly
   uvicorn app:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Test the API**:
   ```bash
   curl http://localhost:8000/api/alg/healthz
   # Should return: {"status":"ok"}
   ```

Visit `http://localhost:8000/docs` for the interactive API documentation.

### Testing

```bash
# Run all tests with coverage
make test

# Run tests without coverage (faster)
make test-fast

# Run specific test file
pytest tests/test_smoke.py -v
```

## 📡 API Usage

All protected endpoints require authentication via the `X-Api-Key` header and tenant identification via `X-Tenant-Id`.

### Health & Monitoring

```bash
# API health check (public)
curl http://localhost:8000/api/alg/healthz

# Vendor connectivity check (public)
curl http://localhost:8000/api/vendor/healthz

# Prometheus metrics (public)
curl http://localhost:8000/api/metrics
```

### Processor Runs API (Recommended)

The processor runs API provides idempotency, persistence, and webhook support.

#### Create Run (File Upload Mode)
```bash
curl -X POST "http://localhost:8000/api/processors/demo/runs" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme" \
     -H "Idempotency-Key: unique-request-id-123" \
     -F "files=@/path/facture.pdf"
```

#### Create Run (JSON Mode - Pre-uploaded File)
```bash
curl -X POST "http://localhost:8000/api/processors/demo/runs" \
     -H "Content-Type: application/json" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme" \
     -H "Idempotency-Key: unique-request-id-456" \
     -d '{"input_path": "s3://bucket/file.pdf"}'
```

#### Get Run Status
```bash
curl -X GET "http://localhost:8000/api/processors/demo/runs/{run_id}" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme"
```

#### List Runs (Paginated)
```bash
# List all runs
curl -X GET "http://localhost:8000/api/processors/demo/runs?limit=20" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme"

# Filter by status
curl -X GET "http://localhost:8000/api/processors/demo/runs?status=succeeded&limit=10" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme"

# Paginate with cursor
curl -X GET "http://localhost:8000/api/processors/demo/runs?cursor=2025-10-19T12:00:00Z&limit=20" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme"
```

### Legacy Extraction Endpoints

#### Upload PDFs
```bash
curl -X POST "http://localhost:8000/api/extract/upload" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme" \
     -F "files=@/path/facture.pdf"
```

#### Process File Path
```bash
curl -X POST "http://localhost:8000/api/extract/path" \
     -H "Content-Type: application/json" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme" \
     -d '{"input_path": "/path/to/pdfs", "debug": true}'
```

### Async Jobs
```bash
# Create background job
curl -X POST "http://localhost:8000/api/jobs" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme" \
     -H "Content-Type: application/json" \
     -d '{"input_path": "/data/batch", "webhook_url": "https://webhooks.site/acme"}'

# Check job status
curl -X GET "http://localhost:8000/api/jobs/{job_id}" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme"
```

### Idempotency

All processor run endpoints support idempotency to prevent duplicate processing:

```bash
# Same idempotency key = same run ID (safe retries)
IDEM_KEY="order-123-retry-1"
curl -X POST "http://localhost:8000/api/processors/demo/runs" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme" \
     -H "Idempotency-Key: $IDEM_KEY" \
     -F "files=@/path/file.pdf"

# Retry with same key returns the same run
curl -X POST "http://localhost:8000/api/processors/demo/runs" \
     -H "X-Api-Key: $API_KEY" \
     -H "X-Tenant-Id: acme" \
     -H "Idempotency-Key: $IDEM_KEY" \
     -F "files=@/path/file.pdf"
```

**Idempotency guarantees:**
- Same `Idempotency-Key` + tenant + processor → same run ID
- Prevents duplicate processing on network retries
- Thread-safe with database constraints
- Works for both file upload and JSON modes

### Response Format

#### Processor Run Response
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "processor_name": "demo",
  "status": "queued",
  "created_at": "2025-10-19T12:00:00Z",
  "updated_at": "2025-10-19T12:00:00Z",
  "tenant_id": "acme",
  "output": null,
  "error": null,
  "vendor_job_id": "vendor-job-123"
}
```

#### List Runs Response (Paginated)
```json
{
  "items": [
    {
      "id": "run-1",
      "processor_name": "demo",
      "status": "succeeded",
      "created_at": "2025-10-19T12:00:00Z",
      "updated_at": "2025-10-19T12:01:00Z",
      "tenant_id": "acme",
      "has_output": true,
      "has_error": false,
      "vendor_job_id": "vendor-123"
    }
  ],
  "next_cursor": "2025-10-19T11:59:00Z"
}
```

#### Extraction Response (Legacy)
```json
{
  "count": 2,
  "records": [
    {
      "provider": "Orange",
      "file": "facture_123.pdf",
      "invoice_date": "2025-09-08",
      "period_start": "2025-08-09",
      "period_end": "2025-09-08", 
      "internet_gb": 15.5,
      "currency": "EUR",
      "confidence": 0.85,
      "doc_type": "telco_invoice"
    }
  ],
  "warnings": []
}
```

#### Error Response
```json
{
  "detail": {
    "code": "FILE_TOO_LARGE",
    "message": "File exceeds 10485760 bytes limit"
  }
}
```

## 🛠 Development

### Code Quality

```bash
# Format code
make fmt

# Lint code 
make lint

# Install pre-commit hooks
make pre-commit-install

# Run pre-commit on all files
make pre-commit-run
```

### Available Make Commands

```bash
make help           # Show all available commands
make install        # Install dependencies  
make dev            # Start development server
make test           # Run tests with coverage
make fmt            # Format code (black, isort, ruff)
make lint           # Lint code
make clean          # Clean build artifacts
make deploy-check   # Verify deployment readiness
```

## 🚀 Deployment

### Production Readiness Checklist

Before deploying to production, ensure:

- ✅ Database migrations applied (`alembic upgrade head`)
- ✅ Environment variables configured (see below)
- ✅ Webhook secret generated (32+ characters)
- ✅ API keys rotated from defaults
- ✅ Metrics endpoint accessible for monitoring
- ✅ Health checks passing (`/api/alg/healthz`, `/api/vendor/healthz`)
- ✅ Smoke tests passing (`make test-smoke`)

### Vercel (Production)

1. **Connect GitHub repository** to Vercel

2. **Set environment variables** in Vercel dashboard:
   ```bash
   # Required
   ALG_API_KEY=your_secure_api_key_32chars_minimum
   DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
   VENDOR_WEBHOOK_SECRET=your_webhook_secret_32chars_minimum
   VENDOR_BASE_URL=https://vendor-api.example.com
   
   # Optional
   CORS_ORIGINS=https://app.algorythmos.fr,https://staging.algorythmos.fr
   LOG_LEVEL=INFO
   RUN_MAX_FILES=50
   RUN_MAX_FILE_BYTES=10485760
   ```

3. **Deploy**:
   ```bash
   # Test locally with Vercel
   vercel dev
   
   # Deploy to production
   vercel --prod
   ```

4. **Database migrations**:
   ```bash
   # Run migrations on production database
   DATABASE_URL="postgresql://..." alembic upgrade head
   ```

5. **Custom domain**: Add CNAME record pointing to your Vercel deployment

6. **Monitor deployment**:
   ```bash
   # Check health
   curl https://api.algorythmos.fr/api/alg/healthz
   
   # Verify metrics
   curl https://api.algorythmos.fr/api/metrics
   ```

### Local Vercel Development

```bash
# Install Vercel CLI
npm i -g vercel

# Test Vercel functions locally
vercel dev

# The API will be available at http://localhost:3000/api/*
curl http://localhost:3000/api/alg/healthz
```

### Docker (Alternative)

```bash
# Build image
make docker-build

# Run container
make docker-run

# Manual commands
docker build -t api-algorythmos .
docker run --rm -p 8080:8080 --env-file .env api-algorythmos
```

## �️ Database Setup

The service uses SQLAlchemy async for persistence with support for PostgreSQL (production) and SQLite (development).

### Local Development (SQLite)
```bash
# SQLite database is created automatically
# Location: ./data/app.db
make dev
```

### Production (PostgreSQL)
```bash
# Set DATABASE_URL environment variable
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/dbname"

# Run migrations
alembic upgrade head
```

### Database Schema
```sql
-- runs table
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    processor TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    status TEXT NOT NULL,
    vendor_job_id TEXT,
    idempotency_key TEXT,
    output JSON,
    error JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tenant_id, processor, idempotency_key)
);
```

## 📊 Metrics & Observability

### Prometheus Metrics

The service exposes Prometheus-compatible metrics at `/api/metrics`:

```bash
# Scrape metrics
curl http://localhost:8000/api/metrics
```

#### Available Metrics

**HTTP Requests:**
- `http_requests_total{method, path, status_code}` - Total HTTP requests
- `http_request_duration_seconds{method, path}` - Request latency histogram

**Run Lifecycle:**
- `runs_started_total{processor}` - Total runs initiated
- `runs_succeeded_total{processor}` - Successfully completed runs
- `runs_failed_total{processor}` - Failed runs

**Vendor Operations:**
- `vendor_latency{method, endpoint, status_code}` - Vendor API latency

### Grafana Dashboards

Example PromQL queries:

```promql
# Request rate by endpoint
rate(http_requests_total[5m])

# Error rate
rate(http_requests_total{status_code=~"5.."}[5m])

# P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Run success rate
rate(runs_succeeded_total[5m]) / rate(runs_started_total[5m])
```

### Logging

Structured JSON logging with request context:

```json
{
  "ts": "2025-10-19T12:00:00Z",
  "level": "INFO",
  "logger": "pdf_usage_extractor",
  "message": "Processor run queued",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "processor": "demo",
  "tenant_id": "acme",
  "request_id": "req-abc123",
  "file_count": 1,
  "input_mode": "multipart"
}
```

## 🔔 Webhook Callbacks

Configure webhook URLs to receive processing completion notifications.

### Webhook Payload

```json
{
  "event": "run.completed",
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "processor": "demo",
  "status": "succeeded",
  "output": {
    "records": [...],
    "count": 5
  },
  "created_at": "2025-10-19T12:00:00Z",
  "completed_at": "2025-10-19T12:01:30Z"
}
```

### Webhook Security

Webhooks are secured with HMAC-SHA256 signatures:

```python
import hmac
import hashlib

# Verify webhook signature
def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)

# Headers received:
# X-Vendor-Signature: sha256=abc123...
# X-Vendor-Event-ID: evt-unique-id
# X-Vendor-Timestamp: 1697712000
```

**Security features:**
- HMAC-SHA256 signatures in `X-Vendor-Signature` header
- Replay protection with event IDs
- Timestamp validation (5-minute window)
- Configurable via `VENDOR_WEBHOOK_SECRET` env var

## �🔒 Security & Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ALG_API_KEY` | *required* | API authentication key |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | Database connection string |
| `VENDOR_WEBHOOK_SECRET` | *required* | Secret for webhook HMAC signatures |
| `CORS_ORIGINS` | `https://app.algorythmos.fr` | Allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `RUN_MAX_FILES` | `50` | Maximum files per run |
| `RUN_MAX_FILE_BYTES` | `10485760` | Maximum file size (10MB) |
| `VENDOR_BASE_URL` | *required* | Upstream vendor service URL |

### API Key Security

- All protected endpoints require `x-api-key` header
- Public endpoints: `/api/alg/healthz`, `/version`
- Use strong, unique API keys (min 32 characters)
- Rotate keys regularly

### Rate Limiting

- Applied per tenant (`x-tenant-id`) per minute window
- Returns HTTP 429 when exceeded
- Configure via `RATE_PER_MIN` environment variable

### File Validation

- Only PDF files accepted (`application/pdf`)
- Maximum file size enforced (default: 25MB)
- Empty files rejected with HTTP 400
- Corrupt PDFs handled gracefully

## 📊 Processing Limits & Guidelines

### File Size Limits
- **Individual files**: 25MB (configurable)
- **Batch uploads**: Multiple files supported
- **Large files**: Use direct S3 upload + callback for >25MB

### Timeouts
- **Processing timeout**: 45 seconds per request
- **Webhook timeout**: 10 seconds
- **Vercel function limit**: 60 seconds max

### Performance Tips
- Use background jobs (`/api/jobs`) for large batches
- Process files in smaller chunks (<10 files per request)
- Enable debug mode sparingly (impacts performance)

## 🧪 Testing Strategy

### Test Structure
```
tests/
├── test_smoke.py                    # Health checks, basic functionality
├── test_uploads.py                  # Upload scenarios and edge cases
├── test_stage3_runs.py              # Processor runs API
├── test_stage4_uploads.py           # File upload with vendor streaming
├── test_stage5_webhook_security.py  # Webhook HMAC verification
├── test_stage6a_db.py               # Database persistence
├── test_stage6b_observability.py    # Metrics and request IDs
├── test_stage7_idempotency.py       # Idempotency key handling
├── test_stage7_vendor_retries.py    # Exponential backoff and retries
├── test_stage8_runs_index.py        # Pagination and filtering
├── conftest.py                      # Shared fixtures
└── data/
    ├── sample.pdf                   # Valid test PDF
    └── corrupt_test.pdf             # Invalid PDF for error testing
```

### Test Coverage

**Core Functionality:**
- ✅ Health endpoint accessibility
- ✅ Authentication (valid/invalid/missing API keys)
- ✅ File validation (empty, wrong type, oversized, corrupt)
- ✅ Error handling with structured responses
- ✅ Request context (IDs, headers)

**Advanced Features:**
- ✅ Database persistence and transactions
- ✅ Idempotency key deduplication
- ✅ Concurrent request race conditions
- ✅ Webhook signature validation (HMAC-SHA256)
- ✅ Vendor retry logic (exponential backoff, Retry-After)
- ✅ Metrics collection (Prometheus format)
- ✅ Cursor-based pagination
- ✅ Status filtering

### Running Tests

```bash
# All tests with coverage
make test

# Fast tests (no coverage)
make test-fast

# Specific test stages
uv run pytest tests/test_stage3_runs.py -v            # Runs API
uv run pytest tests/test_stage7_idempotency.py -v    # Idempotency
uv run pytest tests/test_stage8_runs_index.py -v     # Pagination

# Integration smoke tests
./scripts/smoke-test.sh                               # Full smoke test
./scripts/smoke_vendor_health.sh                      # Vendor connectivity

# Coverage report
pytest --cov=. --cov-report=html --cov-report=term
open htmlcov/index.html
```

### Smoke Test Stages

The smoke test suite validates production readiness:

```bash
# Run all stages
./scripts/all_gates.sh

# Individual stages
./scripts/stage2_gate.sh   # Config constants
./scripts/stage3_gate.sh   # Runs API
./scripts/stage4_gate.sh   # File uploads
./scripts/stage5_gate.sh   # Webhook security
./scripts/stage6a_gate.sh  # Database
./scripts/stage6b_gate.sh  # Observability
./scripts/stage6c_gate.sh  # OpenAPI docs
./scripts/stage7_gate.sh   # Idempotency & retries
./scripts/stage8_gate.sh   # Pagination
```

### Test Fixtures

Key fixtures available in `conftest.py`:

- `app_client` - AsyncClient for API testing
- `auth_headers` - Valid authentication headers
- `fake_vendor` - Mocked vendor service (respx)
- `db_session` - Async database session
- `fast_sleep` - Accelerated sleep for retry testing

## 🏗 Architecture

### Project Structure
```
.
├── app.py                      # Main FastAPI application
├── config.py                   # Pydantic settings management
├── service.py                  # Legacy service (reference)
├── api/
│   └── index.py               # Vercel serverless adapter
├── app/
│   ├── database.py            # SQLAlchemy async setup
│   └── models.py              # Database models (Run, Upload)
├── pdf_usage_extractor/       # Core extraction logic
│   ├── extractors/            # Provider-specific extractors
│   │   ├── base.py           # Base extractor interface
│   │   ├── orange.py         # Orange France extractor
│   │   └── generic_telco.py  # Generic fallback
│   ├── router.py             # Extraction router logic
│   └── schemas.py            # Pydantic models
├── vendor_libs/               # Vendor integration
│   ├── services/
│   │   └── vendor.py         # Vendor API client
│   └── utils/
│       ├── http.py           # Retry logic with backoff
│       ├── security.py       # HMAC webhook validation
│       ├── idempotency.py    # Idempotency key handling
│       ├── observability.py  # Prometheus metrics
│       └── runstore.py       # In-memory run storage
├── alembic/                   # Database migrations
│   ├── env.py
│   └── versions/
├── tests/                     # Comprehensive test suite
│   ├── conftest.py           # Shared fixtures
│   ├── test_stage*.py        # Stage-gated tests
│   └── data/                 # Test fixtures
└── scripts/                   # Deployment scripts
    ├── smoke-test.sh         # Integration tests
    └── *_gate.sh             # Stage validation scripts
```

### Key Components

**FastAPI Application (`app.py`):**
- Multi-modal endpoints (file upload + JSON reference)
- Idempotency-aware request handling
- Database-backed run persistence
- Prometheus metrics integration
- OpenAPI documentation with tags

**Database Layer (`app/`):**
- SQLAlchemy async with PostgreSQL/SQLite
- Async session management
- Models: `Run`, `Upload`
- Migrations via Alembic

**Vendor Integration (`vendor_libs/`):**
- HTTP client with exponential backoff
- HMAC-SHA256 webhook security
- Retry logic with jitter
- Observable with metrics

**Extraction Engine (`pdf_usage_extractor/`):**
- Modular extractor pattern
- Provider-specific logic (Orange, generic)
- Confidence-scored results
- PDF validation and parsing

### Middleware Stack

1. **RequestIDMiddleware**: Injects unique request ID for tracing
2. **MetricsMiddleware**: Prometheus metrics collection (HTTP requests, latency)
3. **AuthMiddleware**: API key validation with tenant context
4. **CORSMiddleware**: Cross-origin resource sharing

### Data Flow

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ POST /processors/demo/runs
       │ (files or JSON + Idempotency-Key)
       ▼
┌──────────────────────┐
│  FastAPI Endpoint    │
│  - Validate input    │
│  - Check idempotency │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Database (SQLite/   │
│  PostgreSQL)         │
│  - Create/update run │
│  - Unique constraint │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Vendor Service      │
│  - Upload files      │
│  - Create job        │
│  - Retry on failure  │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  Webhook Callback    │
│  - HMAC validation   │
│  - Update run status │
│  - Store results     │
└──────────────────────┘
```

### Request Processing

1. **Authentication**: Validate `X-Api-Key` and `X-Tenant-Id`
2. **Idempotency Check**: Query database for existing run with same key
3. **Input Validation**: Check file type, size, PDF magic bytes
4. **Database Transaction**: Create placeholder run record (prevents races)
5. **Vendor Upload**: Stream files to vendor service with retries
6. **Job Creation**: Create vendor processing job
7. **Database Update**: Update run with vendor job ID
8. **Response**: Return run ID and status to client
9. **Async Processing**: Vendor processes files
10. **Webhook**: Vendor calls back with results (HMAC verified)
11. **Database Finalize**: Update run with output/error

## 🔧 Troubleshooting

### Common Issues

**"Database is locked" (SQLite)**
```bash
# SQLite doesn't handle high concurrency well
# Switch to PostgreSQL for production:
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/dbname"
```

**"Idempotency key already used"**
```bash
# This is expected behavior - same key returns same run
# Use unique keys for each distinct request
# Format: "{order_id}-{retry_count}" or "{timestamp}-{random}"
```

**"Webhook signature validation failed"**
```bash
# Ensure VENDOR_WEBHOOK_SECRET matches on both sides
# Check that signature is in format: sha256=<hex>
# Verify timestamp is within 5-minute window
```

**"Vendor request timed out"**
```bash
# Check vendor service health:
curl http://localhost:8000/api/vendor/healthz

# Retry logic will automatically handle temporary failures
# Check metrics for retry patterns:
curl http://localhost:8000/api/metrics | grep vendor_latency
```

**"File too large" errors**
```bash
# Adjust limits via environment variables:
export RUN_MAX_FILE_BYTES=20971520  # 20MB
export RUN_MAX_FILES=100

# Or configure in .env file
```

### Debug Mode

Enable detailed logging:

```bash
export LOG_LEVEL=DEBUG
make dev
```

Debug output includes:
- SQL queries
- Request/response payloads
- Retry attempts
- Webhook payloads

### Health Checks

```bash
# API health
curl http://localhost:8000/api/alg/healthz
# Expected: {"status":"ok"}

# Vendor connectivity
curl http://localhost:8000/api/vendor/healthz
# Expected: {"status":"ok","vendor":"available"}

# Database connectivity
curl http://localhost:8000/api/processors/demo/runs?limit=1
# Expected: {"items":[],"next_cursor":null} or actual data
```

### Performance Tuning

**Database Connection Pool:**
```python
# config.py or environment
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
```

**File Upload Optimization:**
```bash
# Process files in smaller batches
# Recommended: 5-10 files per request for best performance
```

**Metrics Collection:**
```bash
# Disable metrics in development if causing overhead
export ENABLE_METRICS=false
```

## 🤝 Contributing

1. **Setup development environment**:
   ```bash
   make install
   make pre-commit-install
   ```

2. **Make changes** with tests:
   ```bash
   # Create feature branch
   git checkout -b feature/my-feature
   
   # Make changes and add tests
   # Edit files...
   
   # Run tests
   make test
   ```

3. **Run quality checks**:
   ```bash
   make fmt      # Format code
   make lint     # Check style
   make test     # Run all tests
   ```

4. **Submit PR** with clear description:
   - Describe the change and motivation
   - Link related issues
   - Include test evidence (passing tests, screenshots)
   - Update documentation if needed

### Code Style

- **Formatter**: Black (120 char line length)
- **Import sorting**: isort with Black profile  
- **Linting**: Ruff with strict settings
- **Type hints**: Required for public APIs
- **Docstrings**: Google style for classes and functions

### Testing Requirements

- All new features must include tests
- Maintain >80% code coverage
- Add integration tests for API changes
- Include edge cases and error scenarios
- Update smoke tests if changing contracts

### Commit Message Format

```
type(scope): brief description

Longer explanation if needed.

Closes #123
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`

## 📜 License

This project is proprietary software. All rights reserved.
