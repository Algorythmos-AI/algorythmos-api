# Agent Knowledge Base for api-algorythmos

## Project Overview
- FastAPI application deployed as Vercel Serverless Functions.
- Entry point: `api/index.py` (exposed directly via root rewrite).
- All routes must be defined in or imported into `api/index.py`.
- Critical: Keep bundle size < 250 MB (Vercel limit).

## 🚨 CRITICAL: FastAPI + SQLAlchemy OpenAPI Safety Rule

**THIS IS A HARD CONSTRAINT — VIOLATING IT BREAKS PRODUCTION**

### The Rule
**Route handler parameters using `Depends(get_session)` MUST NOT have type annotations for SQLAlchemy session types.**

### ❌ NEVER DO THIS
```python
async def handler(db: AsyncSession = Depends(get_session)):  # ❌ BREAKS OPENAPI
async def handler(session: AsyncSession = Depends(get_session)):  # ❌ BREAKS OPENAPI
async def handler(db: Optional[AsyncSession] = Depends(get_session)):  # ❌ BREAKS OPENAPI
```

### ✅ ALWAYS DO THIS
```python
async def handler(db = Depends(get_session)):  # ✅ CORRECT
async def handler(session = Depends(get_session)):  # ✅ CORRECT
```

### Why This Matters
- Pydantic v2 introspects type annotations during OpenAPI schema generation
- SQLAlchemy's `AsyncSession` has internal types (`_AsyncSessionBind`) that Pydantic cannot resolve
- This causes `/openapi.json` to return 500 and `/docs` to fail
- **This only fails on Vercel** (not locally) due to different introspection behavior
- December 2025: Production outage occurred due to this exact issue

### Enforcement
- A regression test (`tests/test_no_asyncsession_in_routes.py`) will fail if this rule is violated
- Pre-commit hook blocks commits containing the forbidden pattern
- Runtime behavior is identical with or without the annotation

---

## Runtime & Deployment Rules (MUST FOLLOW)
- Vercel uses **Python 3.12** exclusively for serverless functions.
- **NEVER** specify `"runtime": "python3.11"` or any Python version in vercel.json or elsewhere — it causes build failure: "Function Runtimes must have a valid version".
- Vercel auto-detects Python from files in `/api/`.

## Required vercel.json (use exactly this)
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "installCommand": "pip install -r requirements.txt",
  "rewrites": [
    { "source": "/(.*)", "destination": "/api/index.py" }
  ],
  "functions": {
    "api/**/*.py": {
      "excludeFiles": "{tests/**,__tests__/**,**/*.test.py,**/test_*.py,fixtures/**,__fixtures__/**,testdata/**,sample-data/**,static/**,assets/**,vendor_libs/**}"
    }
  }
}
```

## Health Check
- Always include a lightweight root endpoint in `api/index.py`:
```python
@app.get("/")
def health(): return {"status": "ok"}
```

## Testing Requirements (ENFORCED BEFORE ANY PR)
All PRs must confirm these pass locally using Python 3.12.12:
- `pytest` → all tests green
- `ruff check` → no lint errors
- `ruff format --check` → code formatted correctly
- Manual: `uvicorn api.index:app --reload` → health check returns 200 + JSON

Include test output summary in PR description.

## Dependencies
- All runtime deps pinned in `requirements.txt`.
- Use `pip install -r requirements.txt` only (no uv in build).
- Dev dependencies (pytest, pytest-asyncio, ruff, mypy) should be installed separately for local testing.

## Common Issues
- 500 FUNCTION_INVOCATION_FAILED → usually import or missing dep.
- Bundle too large → use excludeFiles above.
- Proxy blocking pip → pin exact versions in requirements.txt.
- **OpenAPI 500 on Vercel** → Check for AsyncSession type annotations (see critical rule above).

---

## Google Authentication (Identity Persistence)

### Endpoint
`POST /api/auth/google` - Verifies Google ID tokens and persists user identity.

### Architecture
```
├── models_user.py           # UserDB model (at root to avoid app package load issues)
└── app/
    └── auth/
        ├── __init__.py      # Auth package exports
        └── google_auth.py   # Google token verification service
```

### Key Files
- **`app/auth/google_auth.py`**: Uses `google-auth` library to verify tokens against Google's public keys
- **`app/models_user.py`**: Contains `UserDB` model with email as unique identifier
- **`alembic/versions/20251214_create_users.py`**: Migration for users table

### Configuration
- `GOOGLE_CLIENT_ID` (optional in dev, recommended in prod): Validates token audience

### Important Notes
- This is **identity persistence only** — NOT sessions, NOT JWTs, NOT RBAC
- Uses **Google Identity Services (GIS)** with ID tokens — NOT OAuth redirect flow
- Uses upsert logic: creates user on first login, updates `last_login_at` on subsequent logins
- Returns `{"status": "ok"}` on success — no sensitive data in response
- The `provider` field supports future SSO (SAML/OIDC)
- **Production safety**: App fails to start if `GOOGLE_CLIENT_ID` is not set when `ENV=prod`

### Modifying Auth
When adding new authentication providers:
1. Add new verification service in `app/auth/`
2. Export in `app/auth/__init__.py`
3. Add endpoint in `app.py` (under AUTHENTICATION ENDPOINTS section)
4. Use `provider` field to differentiate (e.g., "saml", "oidc")

---

## AI Agent Instructions
- Always test changes on Python 3.12.12 before PR.
- Never add runtime specification.
- Prioritize small, focused PRs.
- Update tests for any route/logic changes.
- **NEVER add AsyncSession type annotations to route handlers** (see critical rule above).
- Keep this agent.md up to date.

Last updated: December 25, 2025
