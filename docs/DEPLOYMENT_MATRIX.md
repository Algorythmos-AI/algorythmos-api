# Deployment Matrix

This repository is structured for split Vercel projects with monorepo-friendly root directory mapping.

| Project | Root Directory | Build Command | Output / Runtime | Production Domain | Required Environment Variables |
|---|---|---|---|---|---|
| Marketing (external/canonical site) | Not in this repo | N/A in this repo | Static/site runtime managed by marketing project | `https://algorythmos.com` | Managed in marketing repo/project |
| Marketing WWW Redirect (external) | Not in this repo | N/A in this repo | 301 redirect | `https://www.algorythmos.com` -> `https://algorythmos.com` | None |
| Frontend App | `frontend` | `npm run build` | Next.js standalone output | `https://app.algorythmos.com` | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_GOOGLE_CLIENT_ID` (optional), legacy fallback `NEXT_PUBLIC_API_URL` (temporary compatibility) |
| Backend API | `.` (repo root) | Vercel install: `pip install -r requirements.txt` | Python serverless function (`api/index.py` -> FastAPI `app`) | `https://api.algorythmos.com` | `ALG_API_KEY`, `ALG_TENANT_ID`, `ENV`, `CORS_ORIGINS`, `GOOGLE_CLIENT_ID` (recommended in prod), `REDIS_URL` (required in prod), `STATE_BACKEND` |
| Optional Status Site (future) | External | N/A in this repo | Status page provider runtime | `https://status.algorythmos.com` | Provider-specific |
| Optional Docs Site (future) | External or dedicated docs project | N/A in this repo | Static/site runtime | `https://docs.algorythmos.com` | Provider-specific |

## Notes
- Backend compatibility: existing clients should continue to work when they target legacy domains, provided redirect rules remain in place at DNS/platform level.
- Frontend compatibility: `NEXT_PUBLIC_API_URL` remains supported in code as a fallback to avoid breaking old deployments during migration.
