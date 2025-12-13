<div align="center">

# 📄 Generic Document Processing API

### Production-Ready FastAPI Microservice for Intelligent Document Processing

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-00a393.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![SQLAlchemy 2.0](https://img.shields.io/badge/SQLAlchemy-2.0+-red.svg)](https://www.sqlalchemy.org/)
[![Tests](https://img.shields.io/badge/tests-150%2B%20passing-success.svg)](./tests)
[![Coverage](https://img.shields.io/badge/coverage-95%25-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)]()

[🚀 Quick Start](#-quick-start) • [📡 API Usage](#-api-usage) • [📚 Documentation](https://api-algorythmos.fr/docs) • [🧪 Testing](#-testing-strategy)

---

### 🎯 Key Highlights

| Feature | Description |
|---------|-------------|
| 🔐 **Multi-tenant** | Complete tenant isolation with Bearer auth + API keys |
| ⚡ **13 File Formats** | PDF, DOCX, XLSX, CSV, JSON, XML, HTML, MD, PNG, JPG, TIFF, TXT, RTF |
| 🤖 **LLM-Powered** | Summarization, extraction, Q&A (OpenAI/Anthropic) |
| 📊 **Production Ready** | Rate limiting, idempotency, metrics, CI/CD |
| ✅ **100% API Parity** | All 8 sprints delivered (150+ tests, zero gaps) |
| 🚀 **Live Deploy** | [api-algorythmos.fr](https://api-algorythmos.fr) |

</div>

---

---

## ✨ Features Overview

<table>
<tr>
<td width="50%">

### 📝 Core Processing
- ✅ **13 File Formats**: PDF, DOCX, XLSX, CSV, JSON, XML, HTML, Markdown, PNG, JPG, TIFF, TXT, RTF
- ✅ **Smart Extraction**: Regex-based field extraction with validation
- ✅ **Auto-Classification**: Document type detection & categorization
- ✅ **Intelligent Splitting**: Chunk-based segmentation
- ✅ **Full Parsing**: Blocks, chunks, metadata extraction
- ✅ **LLM Integration**: Summarization, entities, Q&A

</td>
<td width="50%">

### 🏢 Enterprise Features
- ✅ **Multi-tenant**: Complete data isolation per tenant
- ✅ **Flexible Auth**: Bearer tokens + API keys
- ✅ **Version Control**: Processor versions with rollback
- ✅ **Workflow Engine**: Multi-step pipelines + corrections
- ✅ **Evaluation**: Bulk evaluation with ground truth
- ✅ **Webhooks**: HMAC-secured callbacks

</td>
</tr>
<tr>
<td width="50%">

### 🔒 Security & Reliability
- ✅ **Rate Limiting**: Per-tenant throttling (60/min)
- ✅ **Idempotency**: 24h cache with unique keys
- ✅ **CORS Support**: Configurable origins
- ✅ **Tenant Isolation**: Row-level security
- ✅ **API Key Rotation**: Secure key management

</td>
<td width="50%">

### 📊 Observability & Ops
- ✅ **Prometheus Metrics**: Request/latency/errors
- ✅ **Structured Logging**: JSON with request context
- ✅ **Health Checks**: Service + vendor connectivity
- ✅ **CI/CD Pipeline**: Automated testing + security audits
- ✅ **OpenAPI Docs**: Interactive Swagger UI

</td>
</tr>
</table>

---

## 🚀 Quick Start

### Prerequisites
```bash
✅ Python 3.12+
✅ Git
✅ curl (for testing)
```

### Installation

#### 1️⃣ Clone Repository
```bash
git clone https://github.com/skalaliya/api-algorythmos.git
cd api-algorythmos
```

#### 2️⃣ Install Dependencies
```bash
# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

#### 3️⃣ Configure Environment
```bash
# Create .env file
cat > .env << EOF
ALG_API_KEY=your-api-key-min-32-chars-here
DATABASE_URL=sqlite+aiosqlite:///./dev.db
CORS_ORIGINS=http://localhost:3000
LOG_LEVEL=INFO
EOF

# Or export directly
export ALG_API_KEY="your-api-key-min-32-chars"
export DATABASE_URL="sqlite+aiosqlite:///./dev.db"
```

#### 4️⃣ Setup Database
```bash
# Run migrations to create tables
uv run alembic upgrade head
```

#### 5️⃣ Start Server
```bash
# Development mode (auto-reload enabled)
uv run uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Server will start at: http://localhost:8000
```

#### 6️⃣ Test API
```bash
# Health check (public endpoint)
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# API documentation
open http://localhost:8000/docs
```

### 🎉 Success! Your API is running at:
- **API Base**: http://localhost:8000
- **Swagger UI**: http://localhost:8000/docs  
- **OpenAPI Schema**: http://localhost:8000/openapi.json
- **Health Check**: http://localhost:8000/health
- **Metrics**: http://localhost:8000/metrics

---

### Testing Installation

```bash
# Run full test suite
make test

# Run smoke tests only
make test-smoke

# Check coverage
make test-coverage
```

## 📡 API Usage

### 🔑 Authentication

All protected endpoints require authentication via headers:

<table>
<tr>
<th width="50%">API Key Auth</th>
<th width="50%">Bearer Token Auth</th>
</tr>
<tr>
<td>

```bash
curl -X GET https://api-algorythmos.fr/api/files \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: your-tenant"
```

</td>
<td>

```bash
curl -X GET https://api-algorythmos.fr/api/files \
  -H "Authorization: Bearer token" \
  -H "X-Tenant-ID: your-tenant"
```

</td>
</tr>
</table>

### 📋 Required Headers

| Header | Required | Description | Example |
|--------|:--------:|-------------|---------|
| `X-API-Key` or `Authorization` | ✅ | API key or Bearer token | `X-API-Key: alg_...` |
| `X-Tenant-ID` | ✅ | Tenant identifier | `X-Tenant-ID: acme-corp` |
| `x-extend-api-version` | ⚠️ | API version for compatibility | `x-extend-api-version: 2024-01-15` |
| `Idempotency-Key` | ⚠️ | Unique key for safe retries | `Idempotency-Key: req-123` |

### 🟢 Public Endpoints (No Auth Required)

```bash
# Health checks
GET  /health                  # ✅ Service health
GET  /api/alg/healthz         # ✅ API health  
GET  /api/vendor/healthz      # ✅ Vendor connectivity

# Documentation
GET  /docs                    # ✅ Swagger UI
GET  /openapi.json            # ✅ OpenAPI schema
GET  /version                 # ✅ API version

# Monitoring
GET  /metrics                 # ✅ Prometheus metrics
```

---

### 📊 Complete API Examples

#### 1. Upload & Process File

```bash
# Upload a PDF file for processing
curl -X POST "https://api-algorythmos.fr/api/files" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -H "Idempotency-Key: upload-$(date +%s)" \
  -F "file=@document.pdf"

# Response
{
  "id": "file-abc123",
  "filename": "document.pdf", 
  "size": 245678,
  "format": "pdf",
  "mime_type": "application/pdf",
  "created_at": "2025-10-20T10:00:00Z"
}
```

#### 2. Create Extraction Schema

```bash
# Define fields to extract from documents
curl -X POST "https://api-algorythmos.fr/api/extraction_schemas" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Invoice Extractor",
    "description": "Extract invoice data",
    "fields": [
      {
        "name": "invoice_number",
        "type": "string",
        "pattern": "INV-\\d{6}",
        "required": true
      },
      {
        "name": "total_amount",
        "type": "number",
        "pattern": "\\$?\\d+\\.\\d{2}",
        "required": true
      }
    ]
  }'
```

#### 3. Parse Document (Async)

```bash
# Parse document and get structured output
curl -X POST "https://api-algorythmos.fr/api/parse" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{
    "file_id": "file-abc123",
    "schema_id": "schema-xyz789",
    "webhook_url": "https://your-app.com/webhook"
  }'

# Response
{
  "run_id": "run-def456",
  "status": "queued",
  "created_at": "2025-10-20T10:01:00Z"
}
```

#### 4. Check Processing Status

```bash
# Poll for results
curl -X GET "https://api-algorythmos.fr/api/parse/run-def456" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp"

# Response (completed)
{
  "id": "run-def456",
  "status": "succeeded",
  "output": {
    "invoice_number": "INV-123456",
    "total_amount": 1250.00,
    "confidence": 0.95
  },
  "completed_at": "2025-10-20T10:02:30Z"
}
```

#### 5. List Documents (Paginated)

```bash
# List with pagination
curl -X GET "https://api-algorythmos.fr/api/files?limit=20&offset=0" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp"

# Response
{
  "items": [
    {
      "id": "file-abc123",
      "filename": "document.pdf",
      "size": 245678,
      "created_at": "2025-10-20T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

#### 6. Delete Document

```bash
# Soft delete (marks as deleted)
curl -X DELETE "https://api-algorythmos.fr/api/files/file-abc123" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp"

# Response
{
  "status": "deleted",
  "id": "file-abc123"
}
```

---

### 🔄 Idempotency Example

```bash
# First request
curl -X POST "https://api-algorythmos.fr/api/parse" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -H "Idempotency-Key: order-123-v1" \
  -H "Content-Type: application/json" \
  -d '{"file_id": "file-abc123"}'
# Returns: {"run_id": "run-xyz", "status": "queued"}

# Retry with same key (network failure)
curl -X POST "https://api-algorythmos.fr/api/parse" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -H "Idempotency-Key: order-123-v1" \
  -H "Content-Type: application/json" \
  -d '{"file_id": "file-abc123"}'
# Returns: {"run_id": "run-xyz", "status": "queued"}  # ✅ Same run_id!

# ✅ Idempotency guarantees:
# - Same Idempotency-Key + tenant → same run_id
# - No duplicate processing
# - Safe retries on network failures
# - 24-hour cache window
```

---

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

---

### ⚠️ Engineering Notes: OpenAPI + SQLAlchemy on Vercel

> **Critical**: This project runs on Vercel and is subject to a known Pydantic v2 + SQLAlchemy incompatibility that breaks OpenAPI schema generation.

**Problem**: If you add SQLAlchemy session type annotations to FastAPI route handlers, the `/docs` page will fail with a 500 error on Vercel, while working perfectly fine locally.

```python
# ❌ NEVER DO THIS — Breaks OpenAPI on Vercel
async def handler(db: AsyncSession = Depends(get_session)):

# ✅ ALWAYS DO THIS — Works everywhere
async def handler(db = Depends(get_session)):
```

**Why it happens**:
- Pydantic v2 introspects type annotations during OpenAPI schema generation
- SQLAlchemy's `AsyncSession` has internal types (`_AsyncSessionBind`) that Pydantic cannot resolve
- Vercel's bundled runtime triggers this introspection more aggressively than local Python

**Enforcement**:
- A regression test (`tests/test_no_asyncsession_in_routes.py`) will fail if this rule is violated
- A pre-commit hook blocks commits containing the forbidden pattern
- Runtime behavior is identical with or without the annotation

See `agent.md` for full details.

---

## 🚀 Deployment

### 📋 Production Checklist

Before deploying, ensure:

- ✅ Database migrations applied (`alembic upgrade head`)
- ✅ Environment variables configured (see below)
- ✅ Webhook secret generated (32+ characters)
- ✅ API keys rotated from defaults
- ✅ Metrics endpoint accessible
- ✅ Health checks passing
- ✅ Smoke tests passing (`make test-smoke`)

---

### ☁️ Vercel Deployment (Recommended)

#### Step 1: Connect Repository
1. Go to [Vercel Dashboard](https://vercel.com/dashboard)
2. Click "New Project"
3. Import your GitHub repository

#### Step 2: Configure Environment Variables

```bash
# Required Variables
ALG_API_KEY=your_secure_api_key_32chars_minimum
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# Optional Variables  
CORS_ORIGINS=https://app.example.com,https://staging.example.com
LOG_LEVEL=INFO
RUN_MAX_FILES=50
RUN_MAX_FILE_BYTES=10485760
OPENAI_API_KEY=sk-...  # For LLM features
```

#### Step 3: Deploy

```bash
# Test locally with Vercel CLI
npm i -g vercel
vercel dev  # Access at http://localhost:3000

# Deploy to production
vercel --prod
```

#### Step 4: Run Migrations

```bash
# Connect to production database and run migrations
DATABASE_URL="postgresql://prod..." alembic upgrade head
```

#### Step 5: Verify Deployment

```bash
# Health check
curl https://your-app.vercel.app/health
# Expected: {"status": "healthy"}

# API docs
open https://your-app.vercel.app/docs
```

---

### 🐳 Docker Deployment (Alternative)

```bash
# Build image
docker build -t api-algorythmos:latest .

# Run container
docker run -d \
  --name api-algorythmos \
  -p 8080:8080 \
  -e ALG_API_KEY="your-key" \
  -e DATABASE_URL="postgresql://..." \
  api-algorythmos:latest

# Check health
curl http://localhost:8080/health
```

#### Docker Compose

```yaml
version: '3.8'
services:
  api:
    build: .
    ports:
      - "8080:8080"
    environment:
      - ALG_API_KEY=${ALG_API_KEY}
      - DATABASE_URL=postgresql://postgres:password@db:5432/api
    depends_on:
      - db
  
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: api
      POSTGRES_PASSWORD: password
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

---

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

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Application                       │
│                    (Web App / Mobile / CLI)                      │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │   X-API-Key / Bearer  │
                    │   X-Tenant-ID         │
                    │   Idempotency-Key     │
                    └───────────┬───────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────┐
│                      FastAPI Application                         │
│  ┌─────────────┬─────────────┬────────────┬──────────────────┐ │
│  │   Auth      │  Rate       │  Metrics   │   Request ID     │ │
│  │  Middleware │  Limiter    │ Collector  │   Middleware     │ │
│  └─────────────┴─────────────┴────────────┴──────────────────┘ │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │                    API Endpoints                          │ │
│  │  /files  /schemas  /extractors  /parse  /workflows       │ │
│  │  /processors  /evaluation  /health  /metrics             │ │
│  └───────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────┬──────────────────┘
                       │                      │
        ┌──────────────▼──────────┐  ┌────────▼────────────┐
        │   SQLAlchemy Async      │  │  LLM Integration    │
        │   (PostgreSQL/SQLite)   │  │  (OpenAI/Anthropic) │
        │                         │  │                     │
        │  • Files                │  │  • Summarization    │
        │  • Schemas              │  │  • Entity Extract   │
        │  • Processors           │  │  • Q&A              │
        │  • Runs                 │  │                     │
        │  • Workflows            │  └─────────────────────┘
        │  • Evaluations          │
        └─────────────────────────┘
```

### Data Flow

```
1. Client Request
   └─> 2. Authentication & Rate Limiting
       └─> 3. Route Handler
           └─> 4. Business Logic
               ├─> 5a. Database Operations
               │   └─> Save/Query Data
               ├─> 5b. File Processing
               │   └─> Extract/Parse/Classify
               └─> 5c. LLM Processing (optional)
                   └─> Summarize/Extract/Answer
                       └─> 6. Response
                           └─> 7. Metrics Collection
```

### Request Processing Pipeline

```mermaid
graph LR
    A[Client] -->|HTTP Request| B[CORS Middleware]
    B --> C[Request ID]
    C --> D[Auth Middleware]
    D --> E{Valid?}
    E -->|No| F[401 Unauthorized]
    E -->|Yes| G[Rate Limiter]
    G --> H{Exceeded?}
    H -->|Yes| I[429 Too Many]
    H -->|No| J[Route Handler]
    J --> K[Business Logic]
    K --> L[Database]
    K --> M[File Processing]
    K --> N[LLM]
    L --> O[Response]
    M --> O
    N --> O
    O --> P[Metrics]
    P --> Q[Client]
```

---

### Project Structure

```
api-algorythmos/
│
├── 📁 api/                          # Vercel serverless adapter
│   └── index.py                    # Entry point for Vercel functions
│
├── 📁 app/                          # Core application
│   ├── __init__.py                 # Dynamic app loader
│   ├── database.py                 # DB config & session management
│   └── models.py                   # Database models (Run, Upload)
│
├── 📁 document_processing/          # Document processing engine
│   ├── __init__.py
│   ├── models.py                   # 16 models (schemas, files, processors, etc.)
│   ├── schemas*.py                 # Pydantic schemas by resource
│   ├── middleware.py               # Auth & rate limiting
│   │
│   ├── 📁 services/                # Business logic
│   │   ├── schema_service.py      # Extraction schema management
│   │   ├── file_service.py        # File upload & storage
│   │   ├── parse_service.py       # Document parsing
│   │   ├── processor_service.py   # Processor version management
│   │   ├── workflow_service.py    # Workflow orchestration
│   │   ├── evaluation_service.py  # Evaluation framework
│   │   └── format_validator.py    # File format validation
│   │
│   └── 📁 routers/                 # API endpoints
│       ├── schemas.py             # /extraction_schemas
│       ├── extractors.py          # /extractors
│       ├── classifiers.py         # /classifiers
│       ├── splitters.py           # /splitters
│       ├── files.py               # /files
│       ├── parse.py               # /parse
│       ├── processors.py          # /processor_versions
│       ├── processor_runs.py      # /processor_runs
│       ├── workflows.py           # /workflow_runs
│       └── evaluation.py          # /evaluation_items
│
├── 📁 core/                         # Shared utilities
│   ├── config.py                   # Settings management
│   └── __init__.py
│
├── 📁 alembic/                      # Database migrations
│   ├── env.py
│   └── versions/                   # Migration files
│       ├── 001_initial.py
│       ├── 002_add_processors.py
│       └── ...
│
├── 📁 tests/                        # Comprehensive test suite
│   ├── conftest.py                 # Shared fixtures
│   ├── test_smoke.py               # Basic health checks
│   ├── test_phase1_crud.py         # CRUD operations
│   ├── test_phase2_*.py            # Extraction tests
│   ├── test_phase3_*.py            # Classification tests
│   ├── test_phase4_*.py            # File parsing tests
│   ├── test_phase5_*.py            # LLM integration tests
│   ├── test_phase6_*.py            # Production features
│   ├── test_phase7_*.py            # Advanced features
│   └── test_sprint8_*.py           # CI/CD & hardening
│
├── 📁 scripts/                      # Automation scripts
│   ├── smoke-test.sh               # Integration tests
│   ├── all_gates.sh                # Run all stage gates
│   └── stage*_gate.sh              # Individual stage validation
│
├── 📁 docs/                         # Documentation
│   ├── PARITY_GAP_MATRIX.md       # API parity tracking
│   ├── VERCEL_*.md                # Deployment guides
│   └── CLEANUP_COMPLETE.md        # Repo health reports
│
├── app.py                           # Main FastAPI application
├── database.py                      # Root-level DB config (serverless fix)
├── config.py                        # Legacy config (deprecated)
├── requirements.txt                 # Python dependencies
├── pyproject.toml                   # Project metadata & tools
├── alembic.ini                      # Alembic configuration
├── Makefile                         # Development commands
├── Dockerfile                       # Docker image definition
├── vercel.json                      # Vercel configuration
├── pytest.ini                       # Pytest configuration
└── README.md                        # This file
```

---

### Key Design Patterns

#### 1️⃣ Multi-Tenant Architecture
```python
# Every request includes tenant context
@router.get("/files")
async def list_files(tenant_id: str = Depends(get_tenant_id)):
    # Query filtered by tenant_id
    files = await session.query(File).filter(File.tenant_id == tenant_id)
    return files
```

#### 2️⃣ Service Layer Pattern
```python
# Routers → Services → Database
# Clean separation of concerns

# Router (API layer)
@router.post("/files")
async def upload_file(file: UploadFile):
    return await file_service.save_file(file)

# Service (business logic)
class FileService:
    async def save_file(self, file: UploadFile):
        # Validation, processing, storage
        ...
```

#### 3️⃣ Repository Pattern
```python
# Database access abstracted
class SchemaRepository:
    async def get_by_id(self, schema_id: str) -> Schema:
        ...
    
    async def list_by_tenant(self, tenant_id: str) -> List[Schema]:
        ...
```

#### 4️⃣ Idempotency Pattern
```python
# Same key = same result (safe retries)
async def create_run(
    processor: str,
    idempotency_key: Optional[str] = None
):
    if idempotency_key:
        existing = await get_run_by_key(idempotency_key)
        if existing:
            return existing  # Return cached result
    
    # Create new run
    run = await Run.create(...)
    return run
```

---

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
