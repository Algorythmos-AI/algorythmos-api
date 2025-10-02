# PDF Usage Extraction Service

Production-ready FastAPI microservice that extracts structured internet usage data from telecom PDF invoices. Features provider-specific extractors (Orange France + generic fallback), async processing, and robust error handling. Deployed on Vercel at https://api.algorythmos.fr.

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

All protected endpoints require authentication via the `x-api-key` header and tenant identification via `x-tenant-id`.

### Health Check (Public)
```bash
curl http://localhost:8000/api/alg/healthz
```

### Upload PDFs
```bash
curl -X POST "http://localhost:8000/api/extract/upload" \
     -H "x-api-key: $API_KEY" \
     -H "x-tenant-id: acme" \
     -F "files=@/path/facture.pdf"
```

### Process File Path
```bash
curl -X POST "http://localhost:8000/api/extract/path" \
     -H "Content-Type: application/json" \
     -H "x-api-key: $API_KEY" \
     -H "x-tenant-id: acme" \
     -d '{"input_path": "/path/to/pdfs", "debug": true}'
```

### Async Jobs
```bash
# Create background job
curl -X POST "http://localhost:8000/api/jobs" \
     -H "x-api-key: $API_KEY" \
     -H "x-tenant-id: acme" \
     -H "Content-Type: application/json" \
     -d '{"input_path": "/data/batch", "webhook_url": "https://webhooks.site/acme"}'

# Check job status
curl -X GET "http://localhost:8000/api/jobs/<job_id>" \
     -H "x-api-key: $API_KEY" \
     -H "x-tenant-id: acme"
```

### Response Format

All endpoints return structured JSON with proper error codes:

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

### Vercel (Production)

1. **Connect GitHub repository** to Vercel
2. **Set environment variables** in Vercel dashboard:
   ```bash
   API_KEY=your_secure_api_key_here
   CORS_ORIGINS=https://app.algorythmos.fr
   LOG_LEVEL=INFO
   RATE_PER_MIN=120
   MAX_FILE_MB=25
   ```

3. **Deploy**:
   ```bash
   # Test locally with Vercel
   vercel dev
   
   # Deploy to production
   vercel --prod
   ```

4. **Custom domain**: Add CNAME record pointing to your Vercel deployment

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

## 🔒 Security & Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | *required* | API authentication key |
| `CORS_ORIGINS` | `https://app.algorythmos.fr` | Allowed CORS origins |
| `LOG_LEVEL` | `INFO` | Logging level |
| `RATE_PER_MIN` | `120` | Rate limit per tenant per minute |
| `MAX_FILE_MB` | `25` | Maximum file size in MB |
| `S3_*` | *(optional)* | S3 configuration for file storage |

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
├── test_smoke.py      # Health checks, basic functionality
├── test_uploads.py    # Upload scenarios and edge cases
├── data/
│   ├── valid_test.pdf    # Minimal valid PDF
│   └── corrupt_test.pdf  # Invalid PDF for error testing
```

### Test Coverage
- ✅ Health endpoint accessibility
- ✅ Authentication (valid/invalid/missing API keys)
- ✅ File validation (empty, wrong type, oversized)
- ✅ Error handling with structured responses
- ✅ Rate limiting behavior
- ✅ Request context (IDs, headers)

### Running Tests
```bash
# All tests with coverage report
pytest --cov=. --cov-report=html

# Specific test categories
pytest -m "not slow"           # Skip slow tests
pytest tests/test_smoke.py     # Just smoke tests
pytest -v --tb=short          # Verbose with short tracebacks
```

## 🏗 Architecture

### Project Structure
```
.
├── app.py                 # Main FastAPI application factory
├── config.py              # Configuration management
├── service.py             # Legacy service (kept for reference)
├── api/
│   └── index.py          # Vercel serverless adapter
├── pdf_usage_extractor/   # Core extraction logic
│   ├── extractors/       # Provider-specific extractors
│   └── schemas.py        # Pydantic models
├── tests/                # Test suite
└── vercel.json           # Vercel deployment config
```

### Key Components

- **FastAPI App** (`app.py`): Centralized application factory with middleware
- **Configuration** (`config.py`): Pydantic settings management
- **Extractors**: Modular, confidence-scored PDF processing
- **Vercel Adapter** (`api/index.py`): Serverless function wrapper
- **Test Suite**: Comprehensive edge case coverage

### Middleware Stack
1. CORS (configured origins)
2. File size validation
3. Request context (ID injection)
4. API key authentication (selective)

## 🤝 Contributing

1. **Setup development environment**:
   ```bash
   make setup-dev
   ```

2. **Make changes** with tests
3. **Run quality checks**:
   ```bash
   make fmt lint test
   ```

4. **Submit PR** with clear description

### Code Style
- **Formatter**: Black (120 char line length)
- **Import sorting**: isort with Black profile  
- **Linting**: Ruff with strict settings
- **Type hints**: Encouraged for public APIs

## 📜 License

This project is proprietary software. All rights reserved.
