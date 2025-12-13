# Agent Knowledge Base for api-algorythmos

## Project Overview
- FastAPI application deployed as Vercel Serverless Functions.
- Entry point: `api/index.py` (exposed directly via root rewrite).
- All routes must be defined in or imported into `api/index.py`.
- Critical: Keep bundle size < 250 MB (Vercel limit).

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

## AI Agent Instructions
- Always test changes on Python 3.12.12 before PR.
- Never add runtime specification.
- Prioritize small, focused PRs.
- Update tests for any route/logic changes.
- Keep this agent.md up to date.

Last updated: December 13, 2025
