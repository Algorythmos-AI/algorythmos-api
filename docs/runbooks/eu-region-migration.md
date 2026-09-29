# Runbook: move the API and its database to the EU

**Status:** planned, not scheduled. Today functions run in `iad1` (US East) and the
Neon database is in the same region. Customer documents processed here include
EU/French data, so an EU region is the target.

## Target

- Neon project in `aws-eu-central-1` (Frankfurt).
- Vercel functions in `fra1` (`vercel.json` `"regions": ["fra1"]`).
- Keep functions and database in the same region: a cross-region pair adds a
  round trip to every query.

## Steps

1. **Prepare.** Create the EU Neon project through the Vercel Marketplace
   integration, connected to Production only. Keep the current database.
2. **Rehearse.** Restore a copy of the current database into an EU branch
   (`pg_dump --no-owner --format=custom` then `pg_restore`), run
   `alembic upgrade head`, and compare row counts per table.
3. **Freeze writes.** Announce a short window. With the retention job in
   `report` mode, pause writes (maintenance response or disable the upload routes).
4. **Copy.** Final `pg_dump` / `pg_restore` into the EU database; verify row
   counts and `alembic current`.
5. **Switch.** Point the production `DATABASE_URL*` variables at the EU
   database, set `"regions": ["fra1"]`, deploy, and check `/alg/healthz`,
   `/version` and an authenticated read.
6. **Hold.** Keep the US database read-only for 7 days as the rollback target,
   then delete it and record the deletion.

## Rollback

Restore the previous `DATABASE_URL*` values and `"regions": ["iad1"]`, redeploy.
Writes made in the EU database since the switch must be copied back first.

## Record

Update `docs/DATA-RETENTION.md` (Residency), the privacy policy's data-location
statement, and the org decision log.
