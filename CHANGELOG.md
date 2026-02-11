# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Database Persistence**: SQLAlchemy async with PostgreSQL/SQLite support
  - Run tracking with full lifecycle management
  - Upload history and metadata storage
  - Alembic migrations for schema management
  
- **Processor Runs API**: New `/processors/{name}/runs` endpoints
  - POST to create runs (dual-mode: file upload or JSON reference)
  - GET individual run status by ID
  - GET paginated list with cursor-based pagination
  - PATCH processor configuration
  
- **Idempotency Support**: `Idempotency-Key` header prevents duplicate processing
  - Database-backed deduplication
  - Race condition handling with unique constraints
  - Works for both file upload and JSON modes
  
- **Observability & Metrics**: Prometheus metrics integration
  - HTTP request tracking (count, duration, status codes)
  - Run lifecycle metrics (started, succeeded, failed)
  - Vendor latency tracking
  - `/api/metrics` endpoint for scraping
  - Request ID middleware for distributed tracing
  
- **Webhook Security**: HMAC-SHA256 signature validation
  - Configurable webhook secret
  - Replay protection with event IDs
  - Timestamp validation (5-minute window)
  - `/webhooks/vendor` endpoint for callbacks
  
- **Vendor Retry Logic**: Exponential backoff with jitter
  - Respects `Retry-After` headers (seconds and HTTP-date)
  - Configurable max attempts
  - Non-retriable status codes (4xx except 429)
  - Detailed retry logging
  
- **Cursor-Based Pagination**: Efficient listing for large datasets
  - `next_cursor` field for fetching subsequent pages
  - Status filtering (queued, processing, succeeded, failed)
  - Ordered by creation time (newest first)
  - `has_output` and `has_error` boolean flags
  
- **OpenAPI Enhancement**: Comprehensive API documentation
  - Tags for logical grouping (health, extraction, jobs, processors, webhooks)
  - Detailed endpoint descriptions
  - Parameter documentation
  - Response schema examples
  - Auto-generated Swagger UI at `/docs`

### Changed
- Header names standardized to `X-Api-Key` and `X-Tenant-Id` (case-insensitive)
- File size limits now configurable via `RUN_MAX_FILE_BYTES` environment variable
- Request/response logging now includes structured context (request_id, tenant_id, etc.)
- Error responses now include structured `detail` with `code` and `message` fields

### Fixed
- Database connection pooling for better concurrency
- Proper async context management for database sessions
- Race conditions in idempotency key handling
- Metrics registry cleanup on app reload (testing)

### Security
- HMAC-SHA256 webhook signature validation
- Replay attack prevention with event deduplication
- API key validation on all protected endpoints
- Tenant isolation in database queries

## [1.0.0] - 2025-09-01

### Added
- Initial production release
- FastAPI-based microservice
- Orange France PDF extractor
- Generic telco fallback extractor
- File upload API endpoints
- Background job processing
- Vercel deployment support
- Comprehensive test suite
- CORS middleware
- API key authentication
- Rate limiting

---

## Migration Guide

### From 1.0.0 to 2.0.0 (Unreleased)

#### Database Setup Required

New deployments need database setup:

```bash
# Create database (PostgreSQL recommended for production)
createdb api_algorythmos

# Set DATABASE_URL
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/api_algorythmos"

# Run migrations
alembic upgrade head
```

#### Environment Variables

New required variables:
- `DATABASE_URL` - Database connection string
- `VENDOR_WEBHOOK_SECRET` - Secret for webhook HMAC validation
- `VENDOR_BASE_URL` - Upstream vendor service URL

New optional variables:
- `RUN_MAX_FILES=50` - Maximum files per run
- `RUN_MAX_FILE_BYTES=10485760` - Maximum file size (bytes)

#### API Changes

**New endpoints:**
- `POST /processors/{name}/runs` - Create processor run (recommended)
- `GET /processors/{name}/runs/{id}` - Get run status
- `GET /processors/{name}/runs` - List runs with pagination
- `PATCH /processors/{name}` - Update processor config
- `POST /webhooks/vendor` - Receive vendor callbacks
- `GET /metrics` - Prometheus metrics

**Existing endpoints remain compatible:**
- `POST /extract/upload` - Still works as before
- `POST /extract/path` - Still works as before
- `POST /jobs` - Still works as before
- `GET /jobs/{id}` - Still works as before

**Recommended migration path:**
1. Use new `/processors/{name}/runs` endpoints for new integrations
2. Add `Idempotency-Key` headers to prevent duplicates
3. Configure webhooks for async notifications
4. Monitor metrics for observability

#### Idempotency Keys

Add idempotency keys to prevent duplicate processing:

```bash
# Before (no protection against duplicates)
curl -X POST .../processors/demo/runs \
  -F "files=@file.pdf"

# After (idempotent)
curl -X POST .../processors/demo/runs \
  -H "Idempotency-Key: order-123-retry-1" \
  -F "files=@file.pdf"
```

#### Webhook Setup

Configure webhook endpoint and secret:

```bash
# Set webhook secret
export VENDOR_WEBHOOK_SECRET="your-secret-32-chars-minimum"

# Vendor will POST to /webhooks/vendor with HMAC signature
```

#### Monitoring Setup

Add Prometheus scraping:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'api-algorythmos'
    static_configs:
      - targets: ['api.algorythmos.fr:443']
    metrics_path: '/api/metrics'
    scheme: 'https'
```

## Support

- **Documentation**: See README.md for detailed usage
- **Issues**: https://github.com/skalaliya/api-algorythmos/issues
- **Production Issues**: Contact support team
