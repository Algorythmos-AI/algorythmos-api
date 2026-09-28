# Runbook: tenant binding

Since tenant binding, the tenant a request acts for comes from its credential
(`core/tenancy.py`). `X-Tenant-Id` is optional and must match when sent.

## Before and after deploying

1. **Check `ALG_TENANT_ID` is set in production.** It is the tenant the service
   API key acts for, and production refuses to start without it once `ENV=prod`.
2. **Inventory the tenants already holding data.** Data written before binding
   is keyed by whatever `X-Tenant-Id` callers sent. Run this read-only query
   against the production database (Neon console, SQL editor):

   ```sql
   SELECT 'files' AS table_name, tenant_id, count(*) AS rows FROM files GROUP BY tenant_id
   UNION ALL SELECT 'parser_runs', tenant_id, count(*) FROM parser_runs GROUP BY tenant_id
   UNION ALL SELECT 'extraction_schemas', tenant_id, count(*) FROM extraction_schemas GROUP BY tenant_id
   UNION ALL SELECT 'extractors', tenant_id, count(*) FROM extractors GROUP BY tenant_id
   UNION ALL SELECT 'classifiers', tenant_id, count(*) FROM classifiers GROUP BY tenant_id
   UNION ALL SELECT 'splitters', tenant_id, count(*) FROM splitters GROUP BY tenant_id
   UNION ALL SELECT 'processors', tenant_id, count(*) FROM processors GROUP BY tenant_id
   UNION ALL SELECT 'workflows', tenant_id, count(*) FROM workflows GROUP BY tenant_id
   UNION ALL SELECT 'runs', tenant_id, count(*) FROM runs GROUP BY tenant_id
   UNION ALL SELECT 'background_jobs', tenant_id, count(*) FROM background_jobs GROUP BY tenant_id
   ORDER BY 1, 3 DESC;
   ```

3. **Decide per tenant:** keep it reachable through the service key by adding it
   to `ALG_STATIC_KEY_ALLOWED_TENANTS` (deprecated, temporary), or leave it
   unreachable until the retention job removes it.

## Callers to update

- **Dashboard (`algorythmos-ui`):** stop sending `X-Tenant-ID`. It currently
  sends the first label of the email domain, which will not match the user's
  tenant and returns `403 TENANT_MISMATCH`.
- **Console (`algorythmos-console`):** send no tenant, or only the service
  tenant; lock down its `/api/alg/[...path]` proxy before it is ever deployed.
- **Docs (`algorythmos-docs`):** describe the optional header and the tenant rules.

## Rollback

The migration is expand-only (nullable `tenant_id` on `users` and `api_keys`).
Rolling back the deployment restores header-based tenancy; the columns can stay.
