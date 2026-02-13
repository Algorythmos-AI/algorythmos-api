# Deployment Architecture

## Canonical Domain Map
- `https://algorythmos.com`: Global canonical marketing domain.
- `https://www.algorythmos.com`: Permanent redirect target -> `https://algorythmos.com` (301).
- `https://app.algorythmos.com`: Frontend application (Next.js project from `/frontend`).
- `https://api.algorythmos.com`: Backend API (FastAPI project from repository root).
- Optional future domains:
  `https://status.algorythmos.com`
  `https://docs.algorythmos.com`

## Request Flow
1. Browser loads frontend from `app.algorythmos.com`.
2. Frontend calls backend using `NEXT_PUBLIC_API_BASE_URL` (production: `https://api.algorythmos.com/api`).
3. Backend processes requests in FastAPI (`app.py`) via Vercel entrypoint (`api/index.py`).
4. Responses return directly to the frontend/browser.

## Preview vs Production Model
- Preview deployments:
  Frontend and backend each get project-specific preview URLs from Vercel.
  Preview frontend should point to preview backend using environment overrides in Vercel.
- Production deployments:
  Frontend project serves `app.algorythmos.com`.
  Backend project serves `api.algorythmos.com`.
  Marketing site project serves `algorythmos.com` and handles `www` redirect.

## DNS Checklist (Go-Live Intent)
- Apex (`algorythmos.com`) points to marketing project/provider.
- `www` CNAME/Alias points to marketing project and has redirect rule to apex.
- `app` CNAME/Alias points to frontend Vercel project.
- `api` CNAME/Alias points to backend Vercel project.
- Optional `status` and `docs` records reserved/created when services are ready.

## CORS Checklist
- Configure backend `CORS_ORIGINS` explicitly in production.
- Include `https://app.algorythmos.com`.
- Include local dev origins as needed (for example `http://localhost:3000`).
- If legacy frontend domain is still active temporarily, include it until cutover is complete.
- Do not use wildcard `*` in production.

## Redirect Policy
- Required:
  `https://www.algorythmos.com` -> `https://algorythmos.com` (301).

- Legacy compatibility (recommended while clients migrate):
  Legacy frontend domains should 301 redirect to `https://app.algorythmos.com`.
  Legacy API domains should 301/308 redirect to `https://api.algorythmos.com` where safe.
  For API clients sensitive to redirect handling, keep legacy API domain active until clients are confirmed migrated.

## Backward Compatibility Note
- This repository keeps API surface/paths unchanged.
- Frontend env contract supports both `NEXT_PUBLIC_API_BASE_URL` (new canonical) and `NEXT_PUBLIC_API_URL` (legacy alias).
- Domain redirects are documented and require Vercel/DNS manual configuration.
