"""Replay dead-lettered parser async jobs.

This is an operational/internal script. Use with care and audit output.
"""

from __future__ import annotations

import argparse
import asyncio

from database import async_session_factory
from document_processing.services import parser_service


async def _replay_single(tenant_id: str, run_id: str) -> int:
    async with async_session_factory() as session:
        changed = await parser_service.replay_dead_letter_parser_run_job(
            session,
            tenant_id=tenant_id,
            run_id=run_id,
        )
    if changed:
        print(f"requeued run_id={run_id} tenant_id={tenant_id}")
        return 0
    print(f"not-found run_id={run_id} tenant_id={tenant_id}")
    return 1


async def _replay_batch(tenant_id: str, limit: int) -> int:
    async with async_session_factory() as session:
        jobs = await parser_service.list_dead_letter_parser_run_jobs(
            session,
            tenant_id=tenant_id,
            limit=limit,
        )

    if not jobs:
        print("no dead-letter parser jobs found")
        return 0

    requeued = 0
    for job in jobs:
        async with async_session_factory() as session:
            changed = await parser_service.replay_dead_letter_parser_run_job(
                session,
                tenant_id=job.tenant_id,
                run_id=job.run_id,
            )
        if changed:
            requeued += 1
            print(f"requeued run_id={job.run_id} tenant_id={job.tenant_id}")

    print(f"requeued={requeued} scanned={len(jobs)}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replay dead-letter parser jobs")
    parser.add_argument("--tenant-id", required=True, help="Tenant scope for replay")
    parser.add_argument("--run-id", default=None, help="Specific parser run ID to replay")
    parser.add_argument("--limit", type=int, default=100, help="Batch replay limit when --run-id is omitted")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.run_id:
        return asyncio.run(_replay_single(args.tenant_id, args.run_id))
    return asyncio.run(_replay_batch(args.tenant_id, max(1, args.limit)))


if __name__ == "__main__":
    raise SystemExit(main())
