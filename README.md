# Algorythmos Platform

Algorythmos is a split-stack document intelligence platform:
- Backend API (FastAPI) from repository root.
- Frontend app (Next.js) from `/frontend`.

Canonical production domains:
- Marketing: `https://algorythmos.com`
- Frontend app: `https://app.algorythmos.com`
- API: `https://api.algorythmos.com`
- WWW redirect: `https://www.algorythmos.com` -> `https://algorythmos.com`

## 1) What this project is
This repo contains the API and app used to upload/process documents, manage extraction schemas, and operate enterprise document workflows.

## 2) Monorepo layout
```text
api-algorythmos/
├── api/                         # Vercel serverless entrypoint for backend
│   └── index.py
├── app.py                       # FastAPI application entrypoint
├── app/                         # Backend modules
├── document_processing/         # Processing runtime/workers
├── tests/                       # Backend tests
├── scripts/                     # Verification and utility scripts
├── docs/                        # Architecture/deployment docs
├── vercel.json                  # Backend Vercel config (root project)
├── .env.example                 # Backend env template
└── frontend/                    # Frontend Next.js project
    ├── app/
    ├── components/
    ├── lib/
    ├── package.json
    ├── .env.example
    └── next.config.ts
```

## 3) Local development quickstart
### Backend
```bash
cp .env.example .env
python3 -m pip install -r requirements.txt
python3 -m uvicorn app:app --reload
```

Backend will be available at `http://localhost:8000`.

### Frontend
```bash
cp frontend/.env.example frontend/.env.local
npm --prefix frontend ci
npm --prefix frontend run dev
```

Frontend will be available at `http://localhost:3000`.

## 4) Testing commands
### Backend
```bash
python3 -m pytest -q
```

### Frontend
```bash
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### Verification helpers
```bash
./scripts/verify_env_contract.sh
./scripts/verify_local_stack.sh
./scripts/verify_domains.sh
```

## 5) Deployment model
This is deployed as two Vercel projects from one repository:
- Backend project:
  Root directory: `/`
  Uses `vercel.json` at repo root
  Serves `api.algorythmos.com`
- Frontend project:
  Root directory: `/frontend`
  Standard Next.js build (`npm run build`)
  Serves `app.algorythmos.com`

A separate marketing project (outside this repo) serves `algorythmos.com`.

## 6) Custom domain model
- `algorythmos.com`: canonical brand/marketing domain.
- `www.algorythmos.com`: permanent redirect to apex.
- `app.algorythmos.com`: user-facing application.
- `api.algorythmos.com`: API domain.
- Optional later: `status.algorythmos.com`, `docs.algorythmos.com`.

Legacy domain compatibility:
- Keep legacy domains active during migration.
- Configure permanent redirects where safe.
- For API clients that do not follow redirects reliably, keep legacy API domain live until client migration is complete.

## 7) Environment variables
| Scope | Variable | Required | Example | Notes |
|---|---|---|---|---|
| Backend | `ALG_API_KEY` | Yes | `replace-with-secure-api-key` | Required for API auth.
| Backend | `ALG_TENANT_ID` | Yes | `default` | Default tenant.
| Backend | `ENV` | Yes | `dev` or `prod` | Runtime mode.
| Backend | `API_BASE` | No | `https://api.algorythmos.com` | Canonical API hostname.
| Backend | `CORS_ORIGINS` | Yes in prod | `https://app.algorythmos.com,http://localhost:3000` | Use explicit origins in prod.
| Backend | `REDIS_URL` | Yes in prod | `redis://...` | Required for production distributed state.
| Backend | `GOOGLE_CLIENT_ID` | Recommended, required in prod by policy | `<client-id>` | Audience validation.
| Frontend | `NEXT_PUBLIC_API_BASE_URL` | Yes | `https://api.algorythmos.com/api` | Canonical frontend API base.
| Frontend | `NEXT_PUBLIC_API_URL` | Legacy fallback | `https://api.algorythmos.com/api` | Backward-compatible alias.
| Frontend | `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Optional | `<client-id>` | Google OAuth in UI.

## 8) Troubleshooting
- Frontend cannot reach API:
  Verify `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`.
  Confirm backend health: `curl http://localhost:8000/alg/healthz`.
- CORS errors in browser:
  Set explicit `CORS_ORIGINS` including `http://localhost:3000` and `https://app.algorythmos.com`.
- Backend fails to start:
  Run `./scripts/verify_env_contract.sh` and fill missing variables.
- Deployment health checks fail:
  Run `./scripts/verify_domains.sh` to see redirect and endpoint diagnostics.

## 9) Manual Vercel steps
These steps require Vercel UI and are not automated by repository code.

1. Create or verify backend Vercel project.
2. Set backend project Root Directory to repository root (`/`).
3. Confirm backend environment variables from `.env.example` are set in Vercel.
4. Add production domain `api.algorythmos.com` to backend project.
5. Create or verify frontend Vercel project.
6. Set frontend project Root Directory to `frontend`.
7. Confirm frontend environment variables from `frontend/.env.example` are set in Vercel.
8. Add production domain `app.algorythmos.com` to frontend project.
9. In marketing project/domain settings, configure `www.algorythmos.com` -> `algorythmos.com` as permanent redirect (301).
10. If legacy domains are still in use, configure redirect or alias behavior and rollout plan before decommissioning.

## 10) Go-live DNS checklist
Record intent only (provider-specific values omitted):
- Apex `algorythmos.com`: ALIAS/ANAME/A to marketing host.
- `www`: CNAME to marketing host with 301 redirect to apex.
- `app`: CNAME/ALIAS to frontend Vercel target.
- `api`: CNAME/ALIAS to backend Vercel target.
- Optional `status`: reserved CNAME/ALIAS for future status provider.
- Optional `docs`: reserved CNAME/ALIAS for future docs host.

## Additional docs
- Baseline snapshot: `docs/PROJECT_BASELINE.md`
- Deployment architecture: `docs/DEPLOYMENT_ARCHITECTURE.md`
- Deployment matrix: `docs/DEPLOYMENT_MATRIX.md`
