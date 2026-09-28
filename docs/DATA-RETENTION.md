# Data retention

How long this API keeps customer data, and how it is removed.
Implementation: `document_processing/services/retention_service.py`.

## Policy

| Data | Kept for | Rule |
|---|---|---|
| Uploaded documents and everything derived from them: `files`, `parser_runs`, `parser_run_jobs`, `extraction_results`, `document_chunks`, `runs`, `background_jobs`, `workflow_runs`, `webhook_deliveries` | **30 days** from creation (`RETENTION_DAYS`) | removed by age (`created_at`) |
| Anything the user deleted (soft delete, `is_deleted`), including configuration objects: schemas, extractors, classifiers, splitters, processors and versions, workflows, webhooks, evaluation sets and items | **7 days** after deletion (`SOFT_DELETE_PURGE_DAYS`) | removed by `updated_at` of the deleted row |
| Idempotency cache (stored responses) and webhook replay guard | until their own `expires_at` (24 hours / replay window) | removed once expired |
| Accounts (`users`) and API keys (`api_keys`) | while the account exists | not touched by this job |

Configuration objects that are not deleted do not expire. Uploaded file bytes on
Vercel live in per-instance temporary storage and do not persist beyond the
instance.

## How it runs

- Vercel Cron calls `GET /api/internal/cron/retention` daily at 03:00 UTC
  (`vercel.json`). On the Hobby plan Vercel may run it any time within that hour.
- The endpoint requires `Authorization: Bearer <CRON_SECRET>` (Vercel sends it
  when `CRON_SECRET` is set), refuses (`401`) when `CRON_SECRET` is not set, and
  refuses (`403`) outside the production deployment, because preview deployments
  share the production database.
- One run at a time: a Postgres transaction advisory lock; a concurrent run is
  skipped. Runs are idempotent, so a missed or repeated run is harmless.

## Modes

- `RETENTION_MODE=report` (default): counts what would be removed, per table,
  and logs it. **Nothing is deleted.**
- `RETENTION_MODE=enforce`: deletes. Switch only after reviewing a report run's
  counts and creating a database restore point (Neon branch).

## Changing the policy

Change `RETENTION_DAYS` / `SOFT_DELETE_PURGE_DAYS` in the production environment
and redeploy. Shortening a period removes more on the next enforced run.

## Residency

Functions run in `iad1` (US East) and the database is in the same region
(`vercel.json` `regions`). Moving to the EU is described in
`docs/runbooks/eu-region-migration.md`.
