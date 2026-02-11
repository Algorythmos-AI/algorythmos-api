# API Reference

Complete API documentation for the PDF Usage Extraction Service.

## Base URL

```
Production: https://api.algorythmos.fr/api
Local:      http://localhost:8080/api
```

## Authentication

All endpoints (except health checks) require authentication via API key.

### Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-Api-Key` | Yes* | API key for authentication |
| `X-Tenant-Id` | Yes* | Tenant identifier for multi-tenancy |
| `Idempotency-Key` | No | Unique key to prevent duplicate processing |
| `X-Request-ID` | No | Custom request ID (auto-generated if not provided) |

*Not required for public health endpoints

### Example

```bash
curl -H "X-Api-Key: your-api-key" \
     -H "X-Tenant-Id: tenant-123" \
     https://api.algorythmos.fr/api/alg/healthz
```

---

## Health & Monitoring

### GET /alg/healthz

Health check endpoint (public, no authentication required).

**Response:** `200 OK`

```json
{
  "status": "ok"
}
```

**Example:**

```bash
curl https://api.algorythmos.fr/api/alg/healthz
```

---

### GET /alg/version

Get service version information (public).

**Response:** `200 OK`

```json
{
  "version": "0.1.0",
  "env": "production"
}
```

---

### GET /metrics

Prometheus metrics endpoint for monitoring (public).

**Response:** `200 OK` (text/plain)

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/alg/healthz",status="200"} 42.0

# HELP http_request_duration_seconds HTTP request latency
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="POST",path="/processors/{name}/runs",le="0.1"} 15.0

# HELP runs_started_total Total processor runs started
# TYPE runs_started_total counter
runs_started_total{processor="demo"} 100.0
```

---

## Processor Runs API

Modern API for creating and managing extraction jobs.

### POST /processors/{name}/runs

Create a new processor run (recommended API).

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Processor name (e.g., "demo", "orange_france") |

**Headers:**

- `Content-Type`: Either `multipart/form-data` (file upload) or `application/json` (path reference)
- `Idempotency-Key`: Optional, prevents duplicate processing

**Request (File Upload Mode):**

```bash
curl -X POST https://api.algorythmos.fr/api/processors/demo/runs \
  -H "X-Api-Key: your-key" \
  -H "X-Tenant-Id: tenant-123" \
  -H "Idempotency-Key: order-456-retry-1" \
  -F "files=@invoice1.pdf" \
  -F "files=@invoice2.pdf"
```

**Request (JSON Mode - Pre-uploaded Files):**

```bash
curl -X POST https://api.algorythmos.fr/api/processors/demo/runs \
  -H "X-Api-Key: your-key" \
  -H "X-Tenant-Id: tenant-123" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-456-retry-1" \
  -d '{
    "input_path": "s3://bucket/invoices/order-456/",
    "provider_hint": "orange_france"
  }'
```

**JSON Body Schema (JSON Mode):**

```typescript
{
  "input_path": string,      // Required: Path to pre-uploaded files
  "provider_hint"?: string,  // Optional: Hint for provider selection
  "debug"?: boolean          // Optional: Enable debug mode (default: false)
}
```

**Response:** `201 Created`

```json
{
  "run_id": "run_abc123",
  "processor": "demo",
  "status": "queued",
  "created_at": "2025-10-19T10:30:00Z",
  "updated_at": "2025-10-19T10:30:00Z",
  "file_count": 2,
  "vendor_job_id": null,
  "output": null,
  "error": null
}
```

**Status Codes:**

- `201`: Run created successfully
- `400`: Invalid request (bad files, too many files, file too large)
- `401`: Missing or invalid API key
- `409`: Idempotency key conflict (run already exists with different parameters)
- `422`: Validation error
- `500`: Internal server error

**Limits:**

- Max files: 50 (configurable via `RUN_MAX_FILES`)
- Max file size: 10MB (configurable via `RUN_MAX_FILE_BYTES`)

---

### GET /processors/{name}/runs/{run_id}

Get the status and output of a specific run.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Processor name |
| `run_id` | string | Run ID returned from create endpoint |

**Response:** `200 OK`

```json
{
  "run_id": "run_abc123",
  "processor": "demo",
  "status": "succeeded",
  "created_at": "2025-10-19T10:30:00Z",
  "updated_at": "2025-10-19T10:32:15Z",
  "file_count": 2,
  "vendor_job_id": "vendor_xyz789",
  "output": {
    "records": [
      {
        "date": "2024-09-01",
        "usage_mb": 1024.5,
        "source_file": "invoice1.pdf"
      }
    ]
  },
  "error": null
}
```

**Status Values:**

- `queued`: Run created, waiting to be sent to vendor
- `processing`: Submitted to vendor, processing in progress
- `succeeded`: Processing completed successfully
- `failed`: Processing failed with error

**Status Codes:**

- `200`: Success
- `404`: Run not found
- `401`: Missing or invalid API key

---

### GET /processors/{name}/runs

List all runs for a processor with pagination and filtering.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Processor name |

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 50 | Number of runs to return (max 100) |
| `cursor` | string | null | Pagination cursor from previous response |
| `status` | string | null | Filter by status: queued, processing, succeeded, failed |

**Example:**

```bash
# Get first page
curl "https://api.algorythmos.fr/api/processors/demo/runs?limit=10" \
  -H "X-Api-Key: your-key" \
  -H "X-Tenant-Id: tenant-123"

# Get next page using cursor
curl "https://api.algorythmos.fr/api/processors/demo/runs?limit=10&cursor=eyJ0aW1lIjoiMjAyNS0xMC0xOVQxMDozMDowMFoiLCJpZCI6ImFiYzEyMyJ9" \
  -H "X-Api-Key: your-key" \
  -H "X-Tenant-Id: tenant-123"

# Filter by status
curl "https://api.algorythmos.fr/api/processors/demo/runs?status=succeeded" \
  -H "X-Api-Key: your-key" \
  -H "X-Tenant-Id: tenant-123"
```

**Response:** `200 OK`

```json
{
  "runs": [
    {
      "run_id": "run_abc123",
      "processor": "demo",
      "status": "succeeded",
      "created_at": "2025-10-19T10:30:00Z",
      "updated_at": "2025-10-19T10:32:15Z",
      "file_count": 2,
      "has_output": true,
      "has_error": false
    }
  ],
  "next_cursor": "eyJ0aW1lIjoiMjAyNS0xMC0xOVQxMDoyMDowMFoiLCJpZCI6ImRlZjQ1NiJ9",
  "has_more": true
}
```

**Response Fields:**

- `runs`: Array of run summaries (output/error not included for performance)
- `next_cursor`: Cursor for fetching next page (null if no more results)
- `has_more`: Boolean indicating if more results are available
- `has_output`: Boolean indicating if run has output data
- `has_error`: Boolean indicating if run has error

**Status Codes:**

- `200`: Success
- `400`: Invalid status filter value
- `401`: Missing or invalid API key

---

### PATCH /processors/{name}

Update processor configuration.

**Path Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | Processor name |

**Request Body:**

```json
{
  "config": {
    "max_retries": 5,
    "timeout_seconds": 300,
    "custom_setting": "value"
  }
}
```

**Response:** `200 OK`

```json
{
  "processor": "demo",
  "config": {
    "max_retries": 5,
    "timeout_seconds": 300,
    "custom_setting": "value"
  },
  "updated_at": "2025-10-19T10:30:00Z"
}
```

---

## Legacy Extraction API

Original API endpoints (backward compatible).

### POST /extract/upload

Upload PDF files for extraction.

**Request:**

```bash
curl -X POST https://api.algorythmos.fr/api/extract/upload \
  -H "X-Api-Key: your-key" \
  -F "files=@invoice.pdf" \
  -F "provider_hint=orange_france"
```

**Response:** `200 OK`

```json
{
  "records": [
    {
      "date": "2024-09-01",
      "usage_mb": 1024.5,
      "provider": "Orange France",
      "source_file": "invoice.pdf"
    }
  ]
}
```

---

### POST /extract/path

Extract from pre-uploaded files.

**Request:**

```bash
curl -X POST https://api.algorythmos.fr/api/extract/path \
  -H "X-Api-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "/path/to/files/",
    "provider_hint": "orange_france"
  }'
```

**Response:** Same as `/extract/upload`

---

## Background Jobs API

Asynchronous job processing endpoints.

### POST /jobs

Create a background extraction job.

**Request:**

```bash
curl -X POST https://api.algorythmos.fr/api/jobs \
  -H "X-Api-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "input_path": "/path/to/files/",
    "provider_hint": "orange_france",
    "callback_url": "https://your-api.com/webhook"
  }'
```

**Response:** `201 Created`

```json
{
  "job_id": "job_abc123",
  "status": "pending",
  "created_at": "2025-10-19T10:30:00Z"
}
```

---

### GET /jobs/{job_id}

Get job status.

**Response:** `200 OK`

```json
{
  "job_id": "job_abc123",
  "status": "completed",
  "created_at": "2025-10-19T10:30:00Z",
  "completed_at": "2025-10-19T10:32:15Z",
  "result": {
    "records": [...]
  },
  "error": null
}
```

**Status Values:**

- `pending`: Job queued
- `processing`: Job in progress
- `completed`: Job finished successfully
- `failed`: Job failed

---

## Webhooks

### POST /webhooks/vendor

Receive callbacks from upstream vendor service.

**Authentication:** HMAC-SHA256 signature validation

**Headers:**

- `X-Webhook-Signature`: HMAC signature of request body
- `X-Event-ID`: Unique event identifier (for replay protection)
- `X-Timestamp`: Event timestamp (ISO 8601)

**Signature Calculation:**

```python
import hmac
import hashlib

secret = "your-webhook-secret"
payload = request.body  # Raw bytes
signature = hmac.new(
    secret.encode(),
    payload,
    hashlib.sha256
).hexdigest()

headers = {
    "X-Webhook-Signature": f"sha256={signature}",
    "X-Event-ID": "evt_unique_123",
    "X-Timestamp": "2025-10-19T10:30:00Z"
}
```

**Request Body:**

```json
{
  "event": "job.completed",
  "job_id": "vendor_xyz789",
  "status": "succeeded",
  "output": {
    "records": [...]
  },
  "error": null
}
```

**Response:** `204 No Content`

**Status Codes:**

- `204`: Webhook processed successfully
- `400`: Invalid request (missing headers, invalid signature)
- `401`: Signature validation failed
- `409`: Duplicate event (replay detected)

---

## Error Handling

All error responses follow a consistent format:

```json
{
  "detail": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message"
  }
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `MISSING_API_KEY` | 401 | X-Api-Key header not provided |
| `INVALID_API_KEY` | 401 | API key is invalid or expired |
| `MISSING_TENANT_ID` | 400 | X-Tenant-Id header not provided |
| `NO_FILES` | 400 | No files provided in request |
| `TOO_MANY_FILES` | 400 | Exceeded maximum file count |
| `FILE_TOO_LARGE` | 400 | File exceeds size limit |
| `INVALID_CONTENT_TYPE` | 400 | Unsupported Content-Type header |
| `INVALID_STATUS_FILTER` | 400 | Invalid status filter value |
| `RUN_NOT_FOUND` | 404 | Requested run does not exist |
| `PROCESSOR_NOT_FOUND` | 404 | Processor does not exist |
| `IDEMPOTENCY_CONFLICT` | 409 | Idempotency key used with different parameters |
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `VENDOR_ERROR` | 502 | Upstream vendor service error |
| `INTERNAL_ERROR` | 500 | Unexpected internal error |

### Example Error Response

```json
{
  "detail": {
    "code": "FILE_TOO_LARGE",
    "message": "File 'invoice.pdf' (12.5 MB) exceeds maximum size of 10.0 MB"
  }
}
```

---

## Rate Limiting

Currently not enforced at the API level. Configure rate limiting at the infrastructure level (API Gateway, reverse proxy).

---

## Idempotency

### Using Idempotency Keys

Include an `Idempotency-Key` header to make requests idempotent:

```bash
curl -X POST https://api.algorythmos.fr/api/processors/demo/runs \
  -H "X-Api-Key: your-key" \
  -H "X-Tenant-Id: tenant-123" \
  -H "Idempotency-Key: order-456-attempt-1" \
  -F "files=@invoice.pdf"
```

### Guarantees

1. **Same Key, Same Result**: Multiple requests with the same idempotency key return the same run
2. **Conflict Detection**: Using the same key with different files returns 409 Conflict
3. **Race Protection**: Concurrent requests with the same key are handled safely
4. **Key Expiration**: Keys expire after 24 hours

### Best Practices

- Use unique, deterministic keys: `{order_id}-{attempt_number}`
- Include retry attempt number in key if retrying failed requests
- Store keys with your orders/transactions for replay
- Don't reuse keys for different operations

---

## Pagination

All list endpoints use **cursor-based pagination** for efficiency.

### Pattern

1. Make initial request with `limit` parameter
2. Check `has_more` in response
3. Use `next_cursor` for subsequent requests

### Example Flow

```bash
# Page 1
curl "https://api.algorythmos.fr/api/processors/demo/runs?limit=10"
# Response: {"runs": [...], "next_cursor": "abc123", "has_more": true}

# Page 2
curl "https://api.algorythmos.fr/api/processors/demo/runs?limit=10&cursor=abc123"
# Response: {"runs": [...], "next_cursor": "def456", "has_more": true}

# Page 3
curl "https://api.algorythmos.fr/api/processors/demo/runs?limit=10&cursor=def456"
# Response: {"runs": [...], "next_cursor": null, "has_more": false}
```

### Notes

- Cursors are opaque strings (base64-encoded timestamps + IDs)
- Results are ordered by creation time (newest first)
- Cursors expire after 24 hours
- Maximum `limit` is 100

---

## OpenAPI / Swagger

Interactive API documentation available at:

```
https://api.algorythmos.fr/api/docs
```

Features:
- Try-it-out functionality
- Request/response examples
- Schema definitions
- Authentication configuration

---

## SDK Examples

### Python

```python
import httpx

API_BASE = "https://api.algorythmos.fr/api"
API_KEY = "your-api-key"
TENANT_ID = "tenant-123"

headers = {
    "X-Api-Key": API_KEY,
    "X-Tenant-Id": TENANT_ID,
}

# Create a run
with open("invoice.pdf", "rb") as f:
    files = {"files": f}
    response = httpx.post(
        f"{API_BASE}/processors/demo/runs",
        headers=headers,
        files=files,
    )
    run = response.json()
    run_id = run["run_id"]

# Poll for completion
while True:
    response = httpx.get(
        f"{API_BASE}/processors/demo/runs/{run_id}",
        headers=headers,
    )
    run = response.json()
    if run["status"] in ["succeeded", "failed"]:
        break
    time.sleep(2)

# Get output
if run["status"] == "succeeded":
    print(run["output"])
```

### JavaScript/TypeScript

```typescript
const API_BASE = "https://api.algorythmos.fr/api";
const API_KEY = "your-api-key";
const TENANT_ID = "tenant-123";

const headers = {
  "X-Api-Key": API_KEY,
  "X-Tenant-Id": TENANT_ID,
};

// Create a run
const formData = new FormData();
formData.append("files", fileBlob, "invoice.pdf");

const createResponse = await fetch(
  `${API_BASE}/processors/demo/runs`,
  {
    method: "POST",
    headers,
    body: formData,
  }
);
const run = await createResponse.json();

// Poll for completion
let status = run.status;
while (status !== "succeeded" && status !== "failed") {
  await new Promise(resolve => setTimeout(resolve, 2000));
  const statusResponse = await fetch(
    `${API_BASE}/processors/demo/runs/${run.run_id}`,
    { headers }
  );
  const updated = await statusResponse.json();
  status = updated.status;
}
```

### cURL

```bash
#!/bin/bash

API_BASE="https://api.algorythmos.fr/api"
API_KEY="your-api-key"
TENANT_ID="tenant-123"

# Create run
RUN=$(curl -X POST "$API_BASE/processors/demo/runs" \
  -H "X-Api-Key: $API_KEY" \
  -H "X-Tenant-Id: $TENANT_ID" \
  -H "Idempotency-Key: $(uuidgen)" \
  -F "files=@invoice.pdf")

RUN_ID=$(echo "$RUN" | jq -r '.run_id')

# Poll for completion
while true; do
  STATUS_RESPONSE=$(curl -s "$API_BASE/processors/demo/runs/$RUN_ID" \
    -H "X-Api-Key: $API_KEY" \
    -H "X-Tenant-Id: $TENANT_ID")
  
  STATUS=$(echo "$STATUS_RESPONSE" | jq -r '.status')
  
  if [ "$STATUS" = "succeeded" ] || [ "$STATUS" = "failed" ]; then
    echo "$STATUS_RESPONSE" | jq .
    break
  fi
  
  sleep 2
done
```

---

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for version history and migration guides.

---

## Support

- **Documentation**: [README.md](./README.md)
- **Deployment**: [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
- **Issues**: GitHub Issues
- **Email**: support@algorythmos.fr
