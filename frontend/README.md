# Algorythmos Frontend

Next.js frontend for `https://app.algorythmos.com`.

## Quick Start
```bash
npm ci
cp .env.example .env.local
npm run dev
```

## Environment Variables
| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Canonical API base URL (local example: `http://localhost:8000`, production example: `https://api.algorythmos.com/api`). |
| `NEXT_PUBLIC_API_URL` | Legacy | Backward-compatible alias for older deployments. |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Optional | Google OAuth client ID for frontend auth flow. |

## Scripts
| Command | Description |
|---|---|
| `npm run dev` | Start local development server. |
| `npm run lint` | Lint with warnings treated as failures. |
| `npm run typecheck` | Run TypeScript checks (`tsc --noEmit`). |
| `npm run build` | Build production bundle. |
| `npm run start` | Start production server. |
