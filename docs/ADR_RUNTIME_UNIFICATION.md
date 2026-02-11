# ADR: Runtime Unification and Migration Discipline

## Status
Accepted (Phase 1)

## Decision
Use exactly one canonical ASGI runtime: `app.py` exported `app`.

## Context / Problem
The repository had multiple deployable runtime entrypoints with overlapping request/auth logic, which increased drift risk. Schema lifecycle expectations were also ambiguous, allowing startup-time schema mutation and split Alembic heads.

## Chosen Approach
- Canonicalize runtime to `app.py:app`.
- Keep `service.py` as a compatibility shim that only re-exports canonical `app`.
- Keep serverless entrypoint (`api/index.py`) as a re-export of the same canonical app object.
- Remove startup schema mutation (`Base.metadata.create_all`).
- Enforce Alembic-first schema lifecycle (`alembic upgrade head` before start/release).
- Enforce single Alembic head in CI.

## Deprecations
- `service.py` is no longer an independent runtime and must not contain routes, auth, middleware, or business logic.
- Startup-driven schema creation is deprecated and removed.

## Rollback Notes
If runtime issues occur:
1. Roll back to the previous release artifact.
2. Keep database schema at the currently applied Alembic revision (do not hot-edit tables manually).
3. Re-run smoke tests against canonical `app.py:app` before re-promoting.
