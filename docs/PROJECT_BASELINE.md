# Project Baseline

Snapshot date: 2026-02-13 (captured at 2026-02-13 04:57:00 UTC)

## Environment
- Python: `3.9.6`
- Node.js: `v24.13.0`
- npm: `11.6.2`
- Git branch at capture: `main`
- Git status at capture: clean (`main...origin/main`)

## Repository Layout (Baseline)
- Backend code lives at repository root (FastAPI app and supporting modules)
- Frontend code lives in `/frontend` (Next.js + TypeScript)
- Vercel entrypoint for backend: `/api/index.py`
- Existing backend Vercel config: `/vercel.json`

## Backend Entrypoint and Runtime Shape
- Canonical FastAPI app object is defined in `/app.py` (`app`)
- Vercel serverless entrypoint `/api/index.py` re-exports `app` from root `app.py`
- Local backend startup (as documented/observed): `uvicorn app:app`
- Existing health endpoint: `GET /alg/healthz`
- Existing capabilities endpoint: `GET /capabilities`

## Frontend Build and Runtime Scripts
`/frontend/package.json` scripts at baseline:
- `dev`: `next dev`
- `build`: `next build`
- `start`: `next start`
- `lint`: `next lint`

## Current Domain/Env Baseline
- Frontend currently reads `NEXT_PUBLIC_API_URL`
- Frontend fallback API URL currently references legacy domain (`api.algorythmos.fr`)
- Backend config default `API_BASE` currently references legacy domain (`api.algorythmos.fr`)

## Risks Identified at Baseline
- Domain naming in docs/config is mixed between legacy and target canonical domains.
- Frontend env contract currently uses `NEXT_PUBLIC_API_URL`; target model requires `NEXT_PUBLIC_API_BASE_URL` while preserving backward compatibility.
- CORS is configurable, but production-safe explicit origin examples are not centrally documented.
