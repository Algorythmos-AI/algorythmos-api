# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- **Production build guard.** A production build fails unless `ENV=prod` and the
  settings pass the production validator, so a misconfigured deploy is never
  promoted and the previous one keeps serving. Settings validation errors no longer
  echo their input, which contained every secret. See
  `docs/runbooks/production-mode.md`.
- **Data retention.** Documents and derived data are removed 30 days after creation,
  soft-deleted rows 7 days after deletion, expired idempotency and replay rows once
  expired (`docs/DATA-RETENTION.md`). A daily Vercel Cron calls
  `GET /api/internal/cron/retention`, which requires `CRON_SECRET`, runs only on the
  production deployment, takes a Postgres advisory lock, and defaults to
  `RETENTION_MODE=report` (counts only, deletes nothing).
- Production requires `CRON_SECRET`.
- Functions pinned to `iad1`, the database's region; EU move documented in
  `docs/runbooks/eu-region-migration.md`.
- **Tenant binding.** The tenant now comes from the credential, not the caller:
  the service key acts for `ALG_TENANT_ID` (plus the deprecated
  `ALG_STATIC_KEY_ALLOWED_TENANTS`), a personal `alg_` key for its tenant, a Google
  user for their own tenant (`GOOGLE_TENANT_MAP`, else per user; users of a public
  mail domain never share one). `X-Tenant-Id` is optional and must match
  (`403 TENANT_MISMATCH`). Rate limits and idempotency use the bound tenant.
- Personal `alg_` keys and Google ID tokens are accepted on data routes.
- Production requires `ALG_TENANT_ID` and refuses a `*` tenant allow-list.
- Migration `20260928_tenant_binding` (expand-only): nullable `tenant_id` on
  `users` and `api_keys`, assigned on first use. See `docs/runbooks/tenant-binding.md`.
- API keys are compared in constant time; a non-matching Bearer token falls through to
  `X-API-Key` instead of shadowing it.
- Idempotent responses are only replayed to an authenticated caller, and the cache key
  includes a fingerprint of the credential. Previously a cached response could be read
  without a key.
- Rate limits count authenticated requests only, exactly once per request, at
  `RATE_PER_MIN`. Previously unauthenticated requests counted against a tenant's quota
  and each request was counted twice.
- `/extract/path` and `/jobs` `input_path` are confined to `LOCAL_EXTRACT_BASE_DIR`
  and disabled in production and wherever that setting is unset.
- `/jobs` `webhook_url` must be https and resolve to a public address; checked again
  before sending, redirects not followed.
- `/metrics` requires the API key.
- `/openapi.json` declares the `ApiKeyAuth` and `BearerAuth` security schemes and no
  longer returns internal error text.
- CORS: no default origins, an explicit header list, no credentialed requests.
- Production refuses to start with `*` or local CORS origins, the default
  `WEBHOOK_SECRET`, or `LOCAL_EXTRACT_BASE_DIR`; legacy vendor signatures default off.
- Google sign-in honours `GOOGLE_ALLOWED_DOMAINS` / `GOOGLE_ALLOWED_EMAILS`; with
  neither set it is closed in production.
- `REDIS_URL` also reads `KV_URL` / `UPSTASH_REDIS_URL` from managed integrations.
- Removed committed personal documents and a derived usage export from the tree and the
  deploy bundle; test fixtures are now synthetic invoices generated at test time.
- Removed scripts that embedded an API key; tests fall back to a dummy key only.
- Bumped `python-multipart` to 0.0.31 and `anyio` to 4.14.2 (published advisories).
- Tests no longer walk real directories such as `/tmp` on the machine running them.

### Changed
- The Redis rate-limit store closes its client with `aclose()`; `close()` is deprecated in redis-py.
- `/frontend`: Next.js 16 and ESLint 10. ESLint config moved to the flat `eslint.config.mjs` (ESLint 10 no longer reads `.eslintrc`); `next lint`, removed in Next.js 16, is replaced by `eslint app components lib`. The new `react-hooks/set-state-in-effect` rule is off until the pages' mount-time data loading is refactored.
- CI rebuilt (`ci.yml`): pinned actions, read-only token, Python 3.12 to match the Vercel
  runtime, bug-class lint gate, single Alembic head, Redis integration, a production-guard
  check, Docker smoke. The org secret scan and `pip-audit` run in `security.yml`.
- Test toolchain pinned in `dev-requirements.txt`; `respx` moved out of runtime requirements.
- `pytest.ini` enables pytest-asyncio auto mode and registers the `integration` marker.
- Tests already failing on `main` are listed in `tests/known_failures.txt` and run as
  non-strict xfail; the list may only shrink.
- The test suite creates every table once per run, so a fresh checkout no longer fails
  by test order. It refuses a non-SQLite `DATABASE_URL`, since its fixtures drop and
  recreate tables. The CI Postgres job passes `DATABASE_URL` to the migration step only.
- Added Dependabot, `SECURITY.md`, a PR template and a working pre-commit configuration.

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
      - targets: ['api.algorythmos.com:443']
    metrics_path: '/api/metrics'
    scheme: 'https'
```

## Support

- **Documentation**: See README.md for detailed usage
- **Issues**: https://github.com/skalaliya/api-algorythmos/issues
- **Production Issues**: Contact support team
