<div align="center">

# 📄 Algorythmos API

### Extract internet usage data from telecom PDF invoices

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.117+-00a393.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Live](https://img.shields.io/badge/live-api.algorythmos.fr-6366f1.svg)](https://api.algorythmos.fr)

**[🌐 Live Demo](https://api.algorythmos.fr/api/)** · **[📚 API Docs](https://api.algorythmos.fr/api/docs)** · **[💚 Health Check](https://api.algorythmos.fr/api/alg/healthz)**

</div>

---

## What is this?

**Algorythmos API** is a REST API that takes telecom PDF invoices (like your Orange or SFR bill) and automatically extracts the internet usage data from them — how much data you used, when, from which line, etc.

Instead of opening each PDF manually and copying numbers into a spreadsheet, you upload the PDF to this API and it gives you back clean, structured data (JSON) that you can use in dashboards, reports, or any other tool.

### Why does this exist?

Telecom companies send you PDF invoices every month. If you manage multiple lines (for a business, a family, or a fleet of devices), extracting the usage data from each PDF by hand is:

- **Slow** — each invoice can be 5–20 pages
- **Error-prone** — copy-paste mistakes add up
- **Not scalable** — imagine doing this for 100+ lines every month

This API automates the entire process: upload → extract → get clean data.

---

## Quick Start (5 minutes)

> **Who is this for?** Anyone who wants to run this project on their own computer. You don't need to be a developer — just follow the steps below.

### What you need first

| Tool | Why you need it | How to check if you have it |
|------|-----------------|---------------------------|
| **Python 3.11** | The programming language this API is written in | Run `python3 --version` in your terminal |
| **Git** | To download the project code | Run `git --version` |
| **A terminal** | To type commands | On Mac: open "Terminal" app. On Windows: use "PowerShell" |

### Step 1: Download the project

```bash
# This copies the entire project to your computer
git clone https://github.com/skalaliya/api-algorythmos.git

# Move into the project folder
cd api-algorythmos
```

> **What just happened?** Git downloaded all the source code from GitHub to a folder called `api-algorythmos` on your machine.

### Step 2: Install the package manager

```bash
# Install "uv" — a fast tool that manages Python packages for you
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> **Why uv?** Python projects use many external libraries (FastAPI, SQLAlchemy, etc.). `uv` downloads and manages all of them automatically, so you don't have to install each one manually.

### Step 3: Install dependencies

```bash
# This reads the project file (pyproject.toml) and installs everything needed
uv sync
```

> **What just happened?** `uv` looked at the list of libraries this project needs (FastAPI for the web server, SQLAlchemy for the database, etc.) and installed all of them in an isolated environment so they don't interfere with other Python projects on your computer.

### Step 4: Set up the database

```bash
# Create the database tables
uv run alembic upgrade head
```

> **What just happened?** The API needs a database to store things like processing runs, user records, and API keys. This command creates a local SQLite database file (`dev.db`) and sets up all the tables inside it. Think of it like creating an empty spreadsheet with the right column headers.
>
> **What is Alembic?** Alembic is a "migration tool" — it keeps track of database changes over time. When we update the code and add new features that need new database columns, Alembic knows exactly what to add without losing your existing data.

### Step 5: Start the server

```bash
# Start the API server in development mode
uv run uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

> **What just happened?**
> - `uvicorn` is the web server that runs the API
> - `app:app` tells it to load the application from `app.py`
> - `--reload` makes it automatically restart when you change code (useful for development)
> - `--host 0.0.0.0` makes it accessible from any network interface
> - `--port 8000` means it listens on port 8000

### Step 6: Open in your browser

Open these links in your browser:

| URL | What it shows |
|-----|--------------|
| [http://localhost:8000/api/](http://localhost:8000/api/) | 🏠 **Landing page** — a visual overview of the API |
| [http://localhost:8000/api/docs](http://localhost:8000/api/docs) | 📚 **Interactive docs** — try every endpoint directly in your browser |
| [http://localhost:8000/api/alg/healthz](http://localhost:8000/api/alg/healthz) | 💚 **Health check** — confirms the server is running |

Or test from the command line:

```bash
# Quick health check
curl http://localhost:8000/api/alg/healthz
# Expected: {"status": "ok"}
```

### 🎉 That's it! Your API is running locally.

---

## How to set environment variables

The API uses environment variables to configure its behaviour. You can set them in two ways:

### Option A: Use a `.env` file (recommended)

Create a file called `.env` in the project root:

```bash
cat > .env << EOF
# === Required ===
ALG_API_KEY=your-api-key-min-32-chars-here

# === Database ===
# For local development, SQLite is used automatically (no setup needed)
# For production, use PostgreSQL:
# DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# === Optional ===
ENVIRONMENT=development
STATE_BACKEND=memory
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
EOF
```

### Option B: Set them directly in your terminal

```bash
export ALG_API_KEY="your-api-key-min-32-chars"
export ENVIRONMENT="development"
```

### All environment variables explained

| Variable | Required? | Default | What it does |
|----------|:---------:|---------|-------------|
| `ALG_API_KEY` | ✅ | — | The secret key that protects your API from unauthorized access. Must be 32+ characters. |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///./dev.db` | Where to store data. SQLite for local dev, PostgreSQL for production. |
| `ENVIRONMENT` | No | `development` | Tells the app if it's running locally or in production. Affects security checks. |
| `STATE_BACKEND` | No | `auto` | How to store temporary processing state. `memory` for local, `redis` for production. |
| `REDIS_URL` | No | — | Only needed if `STATE_BACKEND=redis`. Connection URL for Redis. |
| `GOOGLE_CLIENT_ID` | No | — | For Google Sign-In. Required in production. |
| `CORS_ORIGINS` | No | `https://app.algorythmos.fr` | Which websites can call your API from a browser. |
| `LOG_LEVEL` | No | `INFO` | How much detail to show in logs. `DEBUG` shows everything, `ERROR` shows only errors. |
| `RUN_MAX_FILES` | No | `50` | Maximum number of files allowed in one processing run. |
| `RUN_MAX_FILE_BYTES` | No | `10485760` | Maximum file size (default: 10MB). |

> **Why environment variables?** They let you change how the app behaves without modifying the code. This is especially important for secrets (like API keys) — you never want those committed to Git where anyone could see them.

---

## How the API works (under the hood)

Here's what happens when you send a PDF to the API:

```
You upload a PDF
       │
       ▼
┌──────────────────┐
│  1. AUTHENTICATE │  Your API key is checked. No key = rejected.
│                  │  WHY: Prevents unauthorized access
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  2. RATE LIMIT   │  Checks if you've sent too many requests (60/min)
│                  │  WHY: Prevents one user from overwhelming the server
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  3. VALIDATE     │  Checks the file type, size, and format
│                  │  WHY: Rejects invalid files early, saving resources
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  4. PROCESS      │  Extracts text, tables, and data from the PDF
│                  │  WHY: This is the core value — turning PDF → data
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  5. STORE        │  Saves the result to the database
│                  │  WHY: So you can retrieve the result later
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  6. RESPOND      │  Returns the extracted data as JSON
│                  │  WHY: JSON is easy to use in any programming language
└────────┬─────────┘
         │
         ▼
    Clean, structured data ✅
```

### Key concepts explained

| Concept | What it means | Why it matters |
|---------|--------------|---------------|
| **REST API** | A standard way for computers to talk to each other over the internet (like a waiter taking orders between you and the kitchen) | Any programming language or tool can use this API — Python, JavaScript, Postman, curl, etc. |
| **FastAPI** | The Python framework this API is built with. It's fast, modern, and automatically generates interactive documentation | You get beautiful, interactive API docs for free at `/docs` |
| **SQLAlchemy** | The library that talks to the database. It lets us write Python code instead of raw SQL queries | Makes database operations safer and works with both SQLite (local) and PostgreSQL (production) |
| **Async** | Requests are processed concurrently — the server doesn't wait for one to finish before starting the next | The server can handle many users at the same time without slowing down |
| **Alembic** | Tracks database changes (migrations) so the schema evolves safely over time | You can add new features without manually re-creating the database or losing data |
| **Multi-tenant** | Each user's data is isolated from other users' data | Company A can't see Company B's invoices, even though they use the same API |
| **Idempotency** | Sending the same request twice produces the same result (no duplicates) | Safe to retry if your network drops — you won't accidentally process the same invoice twice |

---

## Using the API

### Authentication

Most endpoints require an API key. Include it in the request header:

```bash
# Using API key
curl -X GET "http://localhost:8000/api/version" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: your-company"
```

> **What is X-Tenant-ID?** It's your organization identifier. It ensures your data is separated from other users' data. Think of it like a folder with your company name on it.

### Public endpoints (no auth needed)

These work without any API key — useful for monitoring:

```bash
# Is the server alive?
curl http://localhost:8000/api/alg/healthz
# → {"status": "ok"}

# What version is running?
curl http://localhost:8000/api/version
# → {"app": "api-algorythmos", "service": "0.1.0", ...}

# Interactive documentation
open http://localhost:8000/api/docs
```

### Upload & parse a PDF

```bash
# Upload a PDF file for processing
curl -X POST "http://localhost:8000/api/files" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -F "file=@your-invoice.pdf"

# Parse the uploaded file
curl -X POST "http://localhost:8000/api/parse" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -H "Content-Type: application/json" \
  -d '{"file_id": "file-abc123"}'
```

### Safe retries with idempotency

If your network is unreliable, add an `Idempotency-Key` header:

```bash
curl -X POST "http://localhost:8000/api/parse" \
  -H "X-API-Key: your-api-key" \
  -H "X-Tenant-ID: acme-corp" \
  -H "Idempotency-Key: invoice-jan-2026" \
  -H "Content-Type: application/json" \
  -d '{"file_id": "file-abc123"}'
```

> **Why?** If you send this exact request twice (maybe your internet dropped and you weren't sure if the first one went through), the API recognizes the same key and returns the original result instead of processing the file again. No duplicates, no wasted resources.

---

## Project structure (what each file does)

```
api-algorythmos/
│
├── app.py                  ← The main application (all API endpoints live here)
├── database.py             ← Database connection setup
├── config.py               ← Application settings
│
├── app/                    ← Core application modules
│   ├── database.py         ← Re-exports from root (for backward compatibility)
│   └── models.py           ← Database table definitions (what columns exist)
│
├── document_processing/    ← The PDF processing engine
│   ├── services/           ← Business logic (parsing, extraction, validation)
│   └── routers/            ← API endpoint definitions, grouped by feature
│
├── alembic/                ← Database migration files
│   └── versions/           ← Each file = one database change (add table, add column, etc.)
│
├── tests/                  ← Automated tests (150+)
├── scripts/                ← Helper scripts (smoke tests, workers, etc.)
│
├── api/
│   └── index.py            ← Vercel serverless entry point
│
├── vercel.json             ← Vercel hosting configuration
├── pyproject.toml          ← Project metadata & dependency list
├── requirements.txt        ← Production dependencies (for Vercel)
├── Makefile                ← Shortcut commands (make test, make dev, etc.)
└── README.md               ← You are here!
```

> **Why is `app.py` so large?** All API endpoints are in a single file for a specific reason: Vercel's serverless platform works best when the entire application can be loaded from one entry point. Splitting into many files introduces import issues in serverless environments (we learned this the hard way!). The code is organized with clear section headers and comments internally.

> **Why are there two `database.py` files?** The root-level `database.py` is the "real" one. The one inside `app/` just re-exports everything from the root level. This exists because Vercel's module system gets confused when `app.py` (a file) and `app/` (a folder) have the same name. By keeping the database config at the root level, we avoid circular import issues.

---

## Database

### Local development (SQLite)

By default, the API uses **SQLite** — a simple file-based database that requires zero setup. When you run `alembic upgrade head`, it creates a `dev.db` file in the project root.

> **Why SQLite for development?** It's the simplest option — no separate database server to install or manage. The file is created automatically and works out of the box.

### Production (PostgreSQL)

For production, use **PostgreSQL** — a full database server that handles concurrent users, large datasets, and data integrity much better than SQLite.

```bash
# Set the production database URL
export DATABASE_URL="postgresql+asyncpg://user:password@host:5432/dbname"

# Run migrations
alembic upgrade head
```

> **Why PostgreSQL for production?** SQLite can only handle one write at a time (it locks the entire file). PostgreSQL handles thousands of concurrent connections, supports advanced queries, and is the industry standard for web applications.

### Managing database changes

```bash
# Check what migration version you're at
alembic current

# Apply all pending migrations
alembic upgrade head

# Check if there are multiple migration branches (should show single head)
alembic heads

# If you see multiple heads, merge them:
alembic merge <head1> <head2> -m "merge branches"
```

> **What are migrations?** Imagine your database is a spreadsheet. Over time, you need to add new columns (like a "created_at" timestamp). Instead of manually editing the database, you write a "migration" file that describes the change. Alembic then applies it automatically. This way, everyone on the team (and the production server) gets the exact same database structure.

---

## Deploying to Vercel (production)

The API is deployed to [Vercel](https://vercel.com) — a cloud platform that hosts your code and makes it available on the internet.

### How it works

1. You push code to GitHub
2. Vercel automatically detects the push
3. It installs dependencies and deploys the new version
4. Your API is live at `https://api.algorythmos.fr`

> **Why Vercel?** It's free for small projects, deploys automatically from Git, and handles scaling (handling more users) for you. No server management required.

### Setup

1. Go to [vercel.com](https://vercel.com) and sign in with GitHub
2. Import the `api-algorythmos` repository
3. Add these environment variables in Vercel's dashboard:

| Variable | Value |
|----------|-------|
| `ALG_API_KEY` | Your 32+ character API key |
| `DATABASE_URL` | Your PostgreSQL connection string |
| `ENVIRONMENT` | `production` |
| `STATE_BACKEND` | `redis` (or `memory` if no Redis available) |
| `GOOGLE_CLIENT_ID` | Your Google OAuth client ID |

4. Deploy! Every push to `main` will automatically update production.

### Important Vercel notes

> **⚠️ Don't annotate route functions with `AsyncSession` types.**
> Vercel's runtime triggers a Pydantic bug when SQLAlchemy's `AsyncSession` type is used in route function signatures. Always use untyped `Depends()`:
> ```python
> # ❌ Breaks on Vercel
> async def handler(db: AsyncSession = Depends(get_session)):
>
> # ✅ Works everywhere
> async def handler(db = Depends(get_session)):
> ```

---

## Running tests

Tests verify that everything works correctly. Even if you're not a developer, running tests is a good way to confirm the project is set up properly.

```bash
# Run all tests (takes ~30 seconds)
uv run pytest

# Run all tests with a coverage report (shows how much code is tested)
make test

# Run only the quick "smoke" tests
make test-smoke

# Run a specific test file
uv run pytest tests/test_smoke.py -v
```

> **What does "passing" mean?** Each test checks one specific thing (e.g., "does the health endpoint return 200?"). If all tests pass, it means the project is working correctly on your machine.

---

## Development commands

If you're a developer working on this project:

```bash
make help           # Show all available commands
make dev            # Start development server with auto-reload
make test           # Run tests with coverage report
make fmt            # Auto-format code (Black + isort + Ruff)
make lint           # Check code style
make clean          # Clean build artifacts
make deploy-check   # Verify deployment readiness
```

### Code quality standards

| Tool | What it does | Why |
|------|-------------|-----|
| **Black** | Auto-formats Python code | Consistent style across the whole codebase |
| **isort** | Sorts import statements | Clean, organized imports |
| **Ruff** | Fast linter (catches bugs) | Catches common mistakes before they reach production |
| **pytest** | Runs automated tests | Confirms everything works after changes |
| **pre-commit** | Runs checks before each Git commit | Prevents broken code from being committed |

---

## Monitoring & observability

### Health checks

```bash
# API health (is the server running?)
curl http://localhost:8000/api/alg/healthz
# → {"status": "ok"}

# Vendor health (can we reach external services?)
curl http://localhost:8000/api/vendor/healthz
```

### Prometheus metrics

The API exposes real-time metrics at `/api/metrics` in Prometheus format:

```bash
curl http://localhost:8000/api/metrics
```

Available metrics include:
- `http_requests_total` — how many requests the API has received
- `http_request_duration_seconds` — how long requests take
- `runs_started_total` / `runs_succeeded_total` / `runs_failed_total` — processing stats

> **Why metrics?** They help you understand how your API is performing — is it getting slow? Are errors increasing? Are users hitting rate limits? You can connect these to dashboards (Grafana, Datadog) for visual monitoring.

### Logging

Logs are written in JSON format for easy parsing:

```json
{
  "ts": "2026-02-12T10:00:00Z",
  "level": "INFO",
  "message": "Processor run queued",
  "run_id": "550e8400-...",
  "tenant_id": "acme"
}
```

Set `LOG_LEVEL=DEBUG` for verbose output when troubleshooting.

---

## Troubleshooting

### "Module not found" errors

```bash
# Make sure you've installed dependencies
uv sync

# Make sure you're in the project directory
cd api-algorythmos
```

### "Database is locked" (SQLite)

This happens when too many requests hit the database simultaneously. SQLite isn't designed for high concurrency.

```bash
# Solution: switch to PostgreSQL for production
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost/dbname"
```

### Server won't start

```bash
# Check if another process is using port 8000
lsof -i :8000

# Try a different port
uv run uvicorn app:app --reload --port 8001
```

### "Alembic shows multiple heads"

This means database migrations diverged (usually after merging branches):

```bash
# See the current heads
alembic heads

# Merge them
alembic merge <head1> <head2> -m "merge migration heads"

# Apply
alembic upgrade head
```

### Enable debug mode

```bash
export LOG_LEVEL=DEBUG
uv run uvicorn app:app --reload
```

This shows detailed SQL queries, request payloads, and internal processing steps.

---

## Security

| Feature | How it works | Why it matters |
|---------|-------------|---------------|
| **API keys** | Every protected request needs an `X-API-Key` header | Only authorized users can access the API |
| **Key hashing** | API keys are stored as SHA-256 hashes (not plain text) | Even if the database is compromised, keys can't be reversed |
| **Tenant isolation** | Each request includes an `X-Tenant-ID` header; data is filtered by tenant | Company A cannot see Company B's data |
| **Rate limiting** | 60 requests per minute per tenant | Prevents abuse and ensures fair usage |
| **HMAC webhooks** | Webhook payloads are signed with HMAC-SHA256 | Receivers can verify the webhook actually came from this API |
| **Idempotency** | Duplicate requests with the same key return the same result | Prevents accidental double-processing |
| **CORS** | Only whitelisted origins can call the API from a browser | Prevents unauthorized websites from using your API |

---

## Architecture diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Your Application                      │
│              (Website, Mobile App, Script)                │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTPS + API Key
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   Algorythmos API                        │
│                                                          │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │  Auth   │→ │   Rate   │→ │  Route   │→ │ Process │ │
│  │Middleware│  │ Limiter  │  │ Handler  │  │  Logic  │ │
│  └─────────┘  └──────────┘  └──────────┘  └────┬────┘ │
│                                                  │      │
│                                    ┌─────────────┼───┐  │
│                                    ▼             ▼   │  │
│                              ┌──────────┐  ┌────────┐│  │
│                              │ Database │  │  PDF   ││  │
│                              │(Postgres)│  │ Parser ││  │
│                              └──────────┘  └────────┘│  │
│                                    └─────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
              Hosted on Vercel (serverless)
              Live at api.algorythmos.fr
```

---

## Contributing

1. **Fork** the repository
2. **Create a branch**: `git checkout -b feature/your-feature`
3. **Install dev tools**: `uv sync --group dev && make pre-commit-install`
4. **Make your changes** and write tests
5. **Run checks**: `make fmt && make lint && make test`
6. **Submit a PR** with a clear description

### Commit message format

```
type(scope): brief description

feat: add new PDF parser
fix: correct rate limiting for batch requests
docs: update README with setup instructions
test: add webhook signature tests
```

---

## License

This project is proprietary software. All rights reserved.

---

<div align="center">
  <br/>
  Built with ❤️ using <a href="https://fastapi.tiangolo.com">FastAPI</a> & <a href="https://www.python.org">Python</a>
  <br/><br/>
  <a href="https://api.algorythmos.fr/api/">🌐 Live Demo</a> · <a href="https://api.algorythmos.fr/api/docs">📚 API Docs</a> · <a href="https://github.com/skalaliya/api-algorythmos/issues">🐛 Report Bug</a>
</div>
