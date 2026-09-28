# Runbook: production mode

Production must run with `ENV=prod`. That switches on the fail-fast checks in
`config.py` (required secrets, a distributed state store, explicit CORS origins,
tenant rules) and the production behaviour in `app.py`. Without it the service
runs its development defaults, whatever else is configured.

`scripts/vercel_build.py` enforces this at build time: a production build fails
unless `ENV` is `prod` or `production` **and** the settings pass the production
validator. A failed build is never promoted, so the previous deployment keeps
serving. The build log names the problem and never prints values. The validator
stops at the first problem, so set every variable below in one pass.

## 1. Variables (Vercel → Project → Settings → Environment Variables → Production)

| Group | Variables | Notes |
|---|---|---|
| Core | `ENV=prod`, `ALG_API_KEY` (or its alias `API_KEY`), `GOOGLE_CLIENT_ID` | |
| State | `REDIS_URL`, `STATE_BACKEND=redis` | Upstash Redis through the Vercel Marketplace, same region as the functions (`vercel.json` `regions`). `KV_URL` and `UPSTASH_REDIS_URL` are accepted as aliases, so remove stale ones. |
| Browser access | `CORS_ORIGINS` | Explicit origins only. `*` and local origins (`localhost`, `127.0.0.1`) are refused. An empty value passes the validator but blocks every browser client. |
| Sign-in | `GOOGLE_ALLOWED_EMAILS` and/or `GOOGLE_ALLOWED_DOMAINS` | Without an allow-list any Google account can sign in. Set them in **Preview** too. |
| Tenancy | `ALG_TENANT_ID`, `ALG_STATIC_KEY_ALLOWED_TENANTS`, `GOOGLE_TENANT_MAP` (optional) | The allow-list must not contain `*`. See `tenant-binding.md`. |
| Secrets | `WEBHOOK_SECRET`, `CRON_SECRET`, `VENDOR_WEBHOOK_SECRET` | `WEBHOOK_SECRET` must not be the development default. `VENDOR_WEBHOOK_SECRET` is not validated, but without it every vendor webhook is rejected with 401. |
| Leave unset | `WEBHOOK_ALLOW_LEGACY_SIGNATURES`, `LOCAL_EXTRACT_BASE_DIR`, `RETENTION_ALLOW_NON_PROD` | Production turns legacy vendor signatures off unless this is set explicitly. Set it to `true` only if the vendor still signs with `sha256=`, then check `/capabilities`. |

## 2. Switching on

1. Provision Upstash Redis first, because validation requires `REDIS_URL`.
2. Set every variable in section 1, then redeploy production **straight away**
   (merge the next change, or **Redeploy** the current production deployment).
   Variables only take effect on the next build.
   Nothing else should deploy in between.
3. If the build fails, read `[vercel_build]` in the build log, fix the named
   variable, and redeploy. Production keeps serving the previous deployment
   meanwhile.
4. Run the smoke tests (section 3).

## 3. Smoke tests

Read the key into a variable instead of typing it on the command line:
`read -rs ALG_KEY`. Both `/x` and `/api/x` resolve.

| Check | Expected |
|---|---|
| `GET https://api.algorythmos.fr/alg/healthz` | 200 |
| `GET /version` | `"env":"prod"` |
| Preflight (`OPTIONS /files`) from the dashboard origin | `access-control-allow-origin` echoes it |
| Preflight from `https://evil.example` | no `access-control-allow-origin` |
| `GET /metrics` without credentials | 401 |
| `GET /openapi.json` | `components.securitySchemes` lists `ApiKeyAuth` and `BearerAuth` |
| Static key, allowed or absent `X-Tenant-Id` | 200 |
| Static key, unlisted `X-Tenant-Id` | 403 `TENANT_MISMATCH` |
| Dashboard | sign-in and one data call work in the browser |

## 4. Rollback caveats

- **Never roll back past the first production-mode deployment.** Older
  deployments were built without `ENV=prod` and run with development defaults.
- After an **Instant Rollback**, Vercel stops auto-assigning production to new
  deployments. The next merge does not go live until you promote it or undo the
  rollback.
- Some plans can only roll back to the immediately previous deployment.
- Rolling back code does not undo data written meanwhile (for example tenants
  bound to users, see `tenant-binding.md`). Migrations are expand-only, so the
  previous code runs against the newer schema.
