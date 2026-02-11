# Async Operations Runbook

This runbook covers runtime operations for durable parser async jobs.

## Scope

- Endpoint: `POST /api/parse/async`
- Worker: `python scripts/parse_worker.py`
- Durable state tables: `parser_run_jobs`, `parser_runs`, `idempotency_keys`, `webhook_replay_events`

## Required Runtime Configuration

- `DATABASE_URL` must be reachable and migrated to `head`.
- `REDIS_URL` must be configured in production.
- `STATE_BACKEND` must not be `memory` in production.

## Job Lifecycle

- Queue status: `queued -> running -> succeeded|failed|dead_letter`
- Parser run status: `pending -> running -> completed|failed|dead_letter`

Retries are bounded by `PARSE_WORKER_MAX_ATTEMPTS` with exponential backoff and jitter.

## Common Failures

1. Worker not running:
   - Symptom: parser jobs remain `queued`.
   - Action: start/restart `scripts/parse_worker.py`.
2. Repeated transient failures:
   - Symptom: jobs oscillate between `running` and `failed`.
   - Action: inspect `last_error`, upstream service dependencies, and file access.
3. Dead-letter growth:
   - Symptom: increasing `dead_letter` jobs.
   - Action: fix root cause first, then replay selected jobs.

## Queue Backlog Triage

1. Check queue depth:
   - Count jobs by status in `parser_run_jobs`.
2. Check oldest queued jobs:
   - Order by `next_attempt_at` ascending.
3. Scale workers:
   - Increase worker replicas or CPU allocation.
4. Confirm lock health:
   - Inspect stale `running` jobs with old `locked_at` values.

## Dead-letter Replay Procedure

Replay one run:

```bash
python scripts/replay_dead_letter_parser_runs.py --tenant-id <tenant> --run-id <run_id>
```

Replay batch for a tenant:

```bash
python scripts/replay_dead_letter_parser_runs.py --tenant-id <tenant> --limit 100
```

Audit notes:
- Replay is idempotent: non-dead-letter jobs are left unchanged.
- Record replay commands and affected run IDs in incident timeline.

## Rollback Notes

1. Stop worker processes if regression is active.
2. Roll back application image to previous stable release.
3. Keep DB schema at current head unless a migration rollback is explicitly approved.
4. Resume workers after verification with `--once` smoke checks.
