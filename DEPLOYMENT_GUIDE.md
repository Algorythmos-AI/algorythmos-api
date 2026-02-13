# Deployment Guide

Complete guide for deploying the PDF Usage Extraction Service to production.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Database Setup](#database-setup)
3. [Environment Configuration](#environment-configuration)
4. [Vercel Deployment](#vercel-deployment)
5. [Database Migrations](#database-migrations)
6. [Monitoring Setup](#monitoring-setup)
7. [Security Hardening](#security-hardening)
8. [Performance Tuning](#performance-tuning)
9. [Troubleshooting](#troubleshooting)
10. [Rollback Procedures](#rollback-procedures)

---

## Prerequisites

### Required Services

- **Vercel Account**: For serverless deployment
- **PostgreSQL Database**: Neon, Railway, Supabase, or self-hosted
- **Prometheus/Grafana**: For monitoring (optional but recommended)
- **Vendor Service**: Upstream processing service (configured separately)

### Required Tools

```bash
# Install Vercel CLI
npm install -g vercel

# Install Python 3.11+
# macOS:
brew install python@3.11

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Canonical Runtime

The only deployable ASGI runtime is `app.py` exported `app`.

- Local: `uv run uvicorn app:app --reload`
- Docker: `uvicorn app:app --host 0.0.0.0 --port 8080`
- Vercel: `api/index.py` re-exports the same canonical app object
- `service.py` is a compatibility shim only; do not add routes/auth/business logic there

---

## Database Setup

### Option 1: Neon (Recommended for Serverless)

Neon provides PostgreSQL with connection pooling and branching.

1. **Create Account**: https://neon.tech
2. **Create Project**:
   ```bash
   # Via CLI
   neonctl projects create --name api-algorythmos
   ```
3. **Get Connection String**:
   ```bash
   neonctl connection-string main
   # Returns: postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb
   ```
4. **Enable Pooling**: Neon automatically provides pooled connections

### Option 2: Railway

1. **Create Account**: https://railway.app
2. **Create PostgreSQL Service**:
   - Click "New Project" → "Provision PostgreSQL"
3. **Get Connection URL**:
   - Click on PostgreSQL service → "Connect" → Copy `DATABASE_URL`
4. **Connection String Format**:
   ```
   postgresql://postgres:password@containers-us-west-xxx.railway.app:5432/railway
   ```

### Option 3: Supabase

1. **Create Project**: https://supabase.com
2. **Get Connection String**:
   - Settings → Database → Connection String → "URI"
3. **Use Connection Pooler**:
   ```
   postgresql://postgres.xxx:[password]@aws-0-us-east-1.pooler.supabase.com:6543/postgres
   ```

### Option 4: Self-Hosted PostgreSQL

```bash
# Install PostgreSQL
# macOS:
brew install postgresql@15
brew services start postgresql@15

# Create database
createdb api_algorythmos

# Create user
psql -c "CREATE USER api_user WITH PASSWORD 'secure_password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE api_algorythmos TO api_user;"

# Connection string
# postgresql://api_user:secure_password@localhost:5432/api_algorythmos
```

### Connection String Format

Convert to asyncpg format:

```python
# Original
postgresql://user:pass@host:5432/dbname

# For application
postgresql+asyncpg://user:pass@host:5432/dbname
```

### Database Verification

```bash
# Test connection
psql "postgresql://user:pass@host:5432/dbname" -c "SELECT version();"

# Check tables (after migration)
psql "postgresql://user:pass@host:5432/dbname" -c "\dt"
```

---

## Environment Configuration

### Required Environment Variables

Create a `.env` file for local development:

```bash
# API Configuration
ALG_API_KEY=your-secret-api-key-min-32-chars
ENV=production

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname

# Distributed operational state (required in production)
REDIS_URL=redis://redis.internal:6379/0
STATE_BACKEND=redis

# Vendor Service
VENDOR_BASE_URL=https://vendor.example.com
VENDOR_API_KEY=vendor-api-key
VENDOR_WEBHOOK_SECRET=your-webhook-secret-min-32-chars

# Rate Limiting (optional)
RATE_PER_MIN=100

# File Limits (optional)
MAX_FILE_MB=10
RUN_MAX_FILES=50
RUN_MAX_FILE_BYTES=10485760

# CORS (optional)
CORS_ORIGINS=https://app.algorythmos.com,https://admin.algorythmos.com
```

Operational state policy:
1. `ENV=production` requires `REDIS_URL`.
2. `STATE_BACKEND=memory` is forbidden in production.
3. Idempotency/replay/job state is SQL-backed and must persist across restarts.

### Generate Secure Secrets

```bash
# API Key (32 chars minimum)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Webhook Secret (32 chars minimum)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Environment-Specific Configuration

**Development:**
```bash
ENV=development
DATABASE_URL=sqlite+aiosqlite:///./dev.db
DEBUG=true
```

**Staging:**
```bash
ENV=staging
DATABASE_URL=postgresql+asyncpg://...staging-db...
VENDOR_BASE_URL=https://vendor-staging.example.com
```

**Production:**
```bash
ENV=production
DATABASE_URL=postgresql+asyncpg://...production-db...
VENDOR_BASE_URL=https://vendor.example.com
LOG_LEVEL=INFO
```

---

## Vercel Deployment

### Step 1: Prepare Project

```bash
# Clone repository
git clone https://github.com/skalaliya/api-algorythmos.git
cd api-algorythmos

# Install dependencies
uv pip install -r requirements.txt

# Run tests locally
uv run pytest tests/
```

### Step 2: Configure Vercel

Create `vercel.json` (already exists):

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/api/(.*)",
      "dest": "api/index.py"
    }
  ],
  "env": {
    "PYTHON_VERSION": "3.11"
  }
}
```

### Step 3: Deploy to Vercel

```bash
# Login to Vercel
vercel login

# Link project (first time)
vercel link

# Set environment variables
vercel env add ALG_API_KEY
# Paste your API key when prompted
# Select: Production, Preview, Development

vercel env add DATABASE_URL
# Paste your database URL

vercel env add VENDOR_BASE_URL
vercel env add VENDOR_API_KEY
vercel env add VENDOR_WEBHOOK_SECRET

# Deploy to preview
vercel

# Deploy to production
vercel --prod
```

### Step 4: Configure Custom Domain (Optional)

```bash
# Add domain
vercel domains add api.algorythmos.com

# Configure DNS
# Add CNAME record: api -> cname.vercel-dns.com
```

### Step 5: Verify Deployment

```bash
# Test health endpoint
curl https://api-algorythmos.vercel.app/api/alg/healthz

# Test with API key
curl https://api-algorythmos.vercel.app/api/alg/version \
  -H "X-Api-Key: your-api-key" \
  -H "X-Tenant-Id: test"
```

---

## Database Migrations

### Initial Setup

```bash
# Install Alembic (included in requirements.txt)
uv pip install alembic

# Verify migration files exist
ls alembic/versions/
# Should show: 202410052101_create_runs.py

# Set DATABASE_URL
export DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/dbname"

# Validate migration graph has exactly one head
alembic heads
```

### Run Migrations

```bash
# Run all pending migrations
alembic upgrade head

# Verify tables created
psql $DATABASE_URL -c "\dt"
# Should show: runs table
```

Migration policy:
1. Apply `alembic upgrade head` before starting or releasing the app.
2. Never rely on app startup to create/alter tables.
3. Keep a single Alembic head at all times.

### Migration Commands

```bash
# Check current version
alembic current

# Show migration history
alembic history

# Upgrade to specific version
alembic upgrade <revision>

# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision>

# Show SQL without running
alembic upgrade head --sql
```

### Create New Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add new column"

# Create blank migration
alembic revision -m "Custom migration"

# Merge multiple heads (if branches diverged)
alembic merge <head1> <head2> -m "merge heads"

# Edit migration file
vim alembic/versions/<timestamp>_add_new_column.py

# Test migration
alembic upgrade head
```

### CI Guardrail (Single Head)

CI enforces exactly one Alembic head via:

```bash
HEAD_COUNT=$(python -m alembic heads | grep -c "(head)")
test "$HEAD_COUNT" -eq 1
```

### Migration Best Practices

1. **Test locally first** with development database
2. **Backup production database** before migrating
3. **Run migrations during low-traffic** windows
4. **Have rollback plan** ready

---

## Async Worker Deployment

`/parse/async` only enqueues durable parser jobs. A worker process must run in each environment.

For incident response and queue triage, use `docs/ASYNC_OPERATIONS_RUNBOOK.md`.

### Worker command

```bash
python scripts/parse_worker.py
```

One-shot mode for smoke/debug:

```bash
python scripts/parse_worker.py --once
```

### Dead-letter replay

Replay one run:

```bash
python scripts/replay_dead_letter_parser_runs.py --tenant-id <tenant> --run-id <run_id>
```

Replay a batch:

```bash
python scripts/replay_dead_letter_parser_runs.py --tenant-id <tenant> --limit 100
```
5. **Monitor application** after migration

### Backup Before Migration

```bash
# PostgreSQL backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore if needed
psql $DATABASE_URL < backup_20251019_103000.sql
```

---

## Monitoring Setup

### Prometheus Configuration

Add scrape config to `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'api-algorythmos'
    metrics_path: '/api/metrics'
    scheme: 'https'
    static_configs:
      - targets: ['api.algorythmos.com']
    basic_auth:
      username: 'prometheus'
      password: 'your-prometheus-password'
    scrape_interval: 30s
    scrape_timeout: 10s
```

### Grafana Dashboard

Import dashboard JSON or create panels:

**HTTP Request Rate:**
```promql
rate(http_requests_total[5m])
```

**HTTP Request Duration (p95):**
```promql
histogram_quantile(0.95, 
  rate(http_request_duration_seconds_bucket[5m])
)
```

**Run Success Rate:**
```promql
rate(runs_succeeded_total[5m]) / 
  (rate(runs_succeeded_total[5m]) + rate(runs_failed_total[5m]))
```

**Vendor Latency:**
```promql
histogram_quantile(0.95,
  rate(vendor_request_duration_seconds_bucket[5m])
)
```

### Alert Rules

Create `alerts.yml`:

```yaml
groups:
  - name: api_algorythmos
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }}"

      - alert: SlowRequests
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket[5m])
          ) > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Slow requests detected"
          description: "P95 latency is {{ $value }}s"

      - alert: HighRunFailureRate
        expr: |
          rate(runs_failed_total[5m]) /
          (rate(runs_succeeded_total[5m]) + rate(runs_failed_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High run failure rate"
```

### Log Aggregation

**Structured Logging:**
All logs are JSON-formatted with request context:

```json
{
  "timestamp": "2025-10-19T10:30:00Z",
  "level": "INFO",
  "message": "Run created",
  "context": {
    "request_id": "req_abc123",
    "tenant_id": "tenant_xyz",
    "run_id": "run_def456",
    "processor": "demo"
  }
}
```

**Vercel Logs:**
```bash
# View real-time logs
vercel logs --follow

# Filter by function
vercel logs --function api/index.py

# Download logs
vercel logs --output logs.txt
```

### Health Checks

**Uptime Monitoring:**
```bash
# Pingdom, UptimeRobot, or custom script
curl -f https://api.algorythmos.com/api/alg/healthz || alert
```

**Synthetic Monitoring:**
```bash
# scripts/smoke-test.sh
API_BASE=https://api.algorythmos.com/api ./scripts/smoke-test.sh
```

---

## Security Hardening

### API Key Management

1. **Rotate keys regularly** (every 90 days)
2. **Use separate keys** per environment
3. **Store in secret manager**: Vercel Secrets, AWS Secrets Manager, etc.
4. **Audit key usage** via logs

### Database Security

```sql
-- Create read-only user for reporting
CREATE USER readonly_user WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE api_algorythmos TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- Enable SSL connections
ALTER DATABASE api_algorythmos SET ssl TO on;
```

### Network Security

**Vercel Configuration:**
- Enable "Require Authentication Headers" in project settings
- Configure IP allowlist if needed
- Enable DDoS protection

**Database:**
- Use connection pooling
- Enable SSL/TLS
- Restrict access by IP (if self-hosted)

### CORS Configuration

```python
# config.py - Restrict origins in production
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "https://app.algorythmos.com,https://admin.algorythmos.com"
)
```

### Webhook Security

Vendor webhooks use HMAC-SHA256 validation:

```python
# Generate webhook secret
import secrets
webhook_secret = secrets.token_urlsafe(32)
print(webhook_secret)  # Store in VENDOR_WEBHOOK_SECRET
```

### Rate Limiting

Implement at infrastructure level:

**Vercel Pro:**
- Configure Edge Config rate limits

**Cloudflare:**
```
# Rate limit: 100 req/min per IP
cf-rate-limit: 100,60
```

**nginx:**
```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;

location /api/ {
    limit_req zone=api burst=20;
    proxy_pass http://backend;
}
```

---

## Performance Tuning

### Database Optimization

**Connection Pool Size:**
```python
# app/database.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Base connections
    max_overflow=10,       # Additional connections
    pool_pre_ping=True,    # Verify connections
    pool_recycle=3600,     # Recycle after 1 hour
)
```

**Indexes:**
```sql
-- Add indexes for common queries
CREATE INDEX idx_runs_created_at ON runs(created_at DESC);
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_tenant_processor ON runs(tenant_id, processor);
CREATE INDEX idx_runs_idempotency ON runs(idempotency_key) WHERE idempotency_key IS NOT NULL;
```

**Query Optimization:**
```sql
-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM runs WHERE status = 'queued' ORDER BY created_at DESC LIMIT 50;

-- Update table statistics
ANALYZE runs;
```

### Application Optimization

**Async Processing:**
```python
# Use background tasks for long operations
@app.post("/processors/{name}/runs")
async def create_run(background_tasks: BackgroundTasks):
    # Queue vendor submission
    background_tasks.add_task(submit_to_vendor, run)
    return run
```

**Caching:**
```python
# Cache processor configs
from functools import lru_cache

@lru_cache(maxsize=100)
def get_processor_config(name: str):
    return load_config(name)
```

**Response Compression:**
```python
# Enable gzip in middleware
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

### Vercel Configuration

**Function Settings:**
```json
{
  "functions": {
    "api/index.py": {
      "maxDuration": 60,
      "memory": 1024
    }
  }
}
```

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

**Symptom:** `could not connect to server`

**Solutions:**
```bash
# Verify connection string
psql "$DATABASE_URL" -c "SELECT 1"

# Check SSL requirement
# Add ?sslmode=require if needed
DATABASE_URL="postgresql+asyncpg://...?sslmode=require"

# Test from Vercel
vercel logs | grep "database"
```

#### 2. Migration Failures

**Symptom:** `Target database is not up to date`

**Solutions:**
```bash
# Check current version
alembic current

# Force to specific version
alembic stamp head

# Rollback and retry
alembic downgrade -1
alembic upgrade head
```

#### 3. High Latency

**Symptom:** Slow API responses

**Solutions:**
```bash
# Check database queries
# Add logging
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Monitor metrics
curl https://api.algorythmos.com/api/metrics | grep duration

# Check vendor latency
# Look for vendor_request_duration_seconds metric
```

#### 4. Memory Issues

**Symptom:** Function timeouts, OOM errors

**Solutions:**
```json
// Increase memory in vercel.json
{
  "functions": {
    "api/index.py": {
      "memory": 3008
    }
  }
}
```

### Debug Mode

```bash
# Enable debug logging
export DEBUG=true
export LOG_LEVEL=DEBUG

# Run locally
uv run uvicorn app:app --reload

# Check logs
tail -f logs/app.log
```

### Health Checks

```bash
# Basic health
curl https://api.algorythmos.com/api/alg/healthz

# Database health
curl https://api.algorythmos.com/api/alg/version \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant-Id: test"

# Full smoke test
API_BASE=https://api.algorythmos.com/api \
ALG_API_KEY=$API_KEY \
./scripts/smoke-test.sh
```

---

## Rollback Procedures

### Application Rollback

**Vercel Rollback:**
```bash
# List recent deployments
vercel ls

# Promote previous deployment
vercel promote <deployment-url>

# Or redeploy previous commit
git checkout <previous-commit>
vercel --prod
```

### Database Rollback

**Downgrade Migration:**
```bash
# Backup first
pg_dump $DATABASE_URL > backup_before_rollback.sql

# Downgrade one version
alembic downgrade -1

# Downgrade to specific version
alembic downgrade <revision>

# Verify
alembic current
```

**Full Database Restore:**
```bash
# Restore from backup
psql $DATABASE_URL < backup_20251019_103000.sql

# Reset migration version
alembic stamp <revision>
```

### Incident Response Checklist

1. **Identify issue**: Check logs, metrics, alerts
2. **Assess impact**: How many users affected?
3. **Communicate**: Update status page
4. **Mitigate**: Rollback or hotfix
5. **Verify**: Run smoke tests
6. **Monitor**: Watch metrics for 30 minutes
7. **Post-mortem**: Document and prevent recurrence

---

## Production Checklist

Before going live, verify:

### Infrastructure
- [ ] Database provisioned (PostgreSQL)
- [ ] Connection pooling enabled
- [ ] Backups configured (daily minimum)
- [ ] SSL/TLS enabled
- [ ] Firewall rules configured

### Application
- [ ] All tests passing (`uv run pytest tests/`)
- [ ] Environment variables set in Vercel
- [ ] API keys rotated from development
- [ ] Webhook secret configured
- [ ] CORS origins restricted
- [ ] Rate limiting configured
- [ ] Error tracking enabled (Sentry, etc.)

### Database
- [ ] Migrations run (`alembic upgrade head`)
- [ ] Indexes created
- [ ] Connection limits appropriate
- [ ] Monitoring queries run

### Monitoring
- [ ] Prometheus scraping configured
- [ ] Grafana dashboards created
- [ ] Alert rules defined
- [ ] On-call rotation established
- [ ] Runbooks documented

### Security
- [ ] API keys secured
- [ ] Database credentials rotated
- [ ] SSL certificates valid
- [ ] CORS configured
- [ ] Rate limiting tested
- [ ] Security headers enabled

### Documentation
- [ ] README.md updated
- [ ] API_REFERENCE.md reviewed
- [ ] Runbooks created
- [ ] Architecture diagrams current
- [ ] Contact information updated

### Testing
- [ ] Load testing completed
- [ ] Smoke tests passing
- [ ] Integration tests passing
- [ ] Failover tested
- [ ] Rollback procedure tested

---

## Support & Resources

- **Documentation**: [README.md](./README.md)
- **API Reference**: [API_REFERENCE.md](./API_REFERENCE.md)
- **Changelog**: [CHANGELOG.md](./CHANGELOG.md)
- **Issues**: GitHub Issues
- **Monitoring**: Grafana Dashboard
- **Status Page**: https://status.algorythmos.com

---

## Next Steps

1. Complete [Production Checklist](#production-checklist)
2. Run smoke tests: `./scripts/smoke-test.sh`
3. Deploy to staging first
4. Perform load testing
5. Deploy to production
6. Monitor for 24 hours
7. Document any issues
8. Schedule post-deployment review

**Happy Deploying! 🚀**
