"""Durable async parser worker.

Processes parser run jobs persisted in `parser_run_jobs`.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Optional
from uuid import uuid4

from config import settings
from database import async_session_factory
from document_processing.services import parser_service
from pdf_usage_extractor.logging_utils import get_logger


logger = get_logger()


async def process_next_parser_job(*, worker_id: str) -> bool:
    """Claim and process one parser job. Returns True if a job was processed."""
    async with async_session_factory() as session:
        job = await parser_service.claim_next_parser_run_job(
            session,
            worker_id=worker_id,
            lock_timeout_seconds=settings.PARSE_WORKER_LOCK_TIMEOUT_S,
        )

    if job is None:
        return False

    try:
        async with async_session_factory() as session:
            result = await parser_service.execute_parser_run(session, job.tenant_id, job.run_id)
    except asyncio.CancelledError:
        async with async_session_factory() as session:
            await parser_service.mark_parser_run_job_failed(
                session,
                job_id=job.id,
                error_message="Parser worker cancelled",
                base_delay_seconds=settings.PARSE_WORKER_BASE_DELAY_S,
                max_delay_seconds=settings.PARSE_WORKER_MAX_DELAY_S,
                jitter_seconds=settings.PARSE_WORKER_JITTER_S,
            )
        raise
    except Exception as exc:  # pragma: no cover - defensive path
        async with async_session_factory() as session:
            await parser_service.mark_parser_run_job_failed(
                session,
                job_id=job.id,
                error_message=str(exc),
                base_delay_seconds=settings.PARSE_WORKER_BASE_DELAY_S,
                max_delay_seconds=settings.PARSE_WORKER_MAX_DELAY_S,
                jitter_seconds=settings.PARSE_WORKER_JITTER_S,
            )
        logger.warning(
            "Parser async job failed",
            extra={"context": {"job_id": job.id, "run_id": job.run_id, "error": type(exc).__name__}},
        )
        return True

    if result.status == "completed":
        async with async_session_factory() as session:
            await parser_service.mark_parser_run_job_succeeded(session, job_id=job.id)
        logger.info(
            "Parser async job succeeded",
            extra={"context": {"job_id": job.id, "run_id": job.run_id}},
        )
        return True

    async with async_session_factory() as session:
        await parser_service.mark_parser_run_job_failed(
            session,
            job_id=job.id,
            error_message=result.error or "Parser run failed",
            base_delay_seconds=settings.PARSE_WORKER_BASE_DELAY_S,
            max_delay_seconds=settings.PARSE_WORKER_MAX_DELAY_S,
            jitter_seconds=settings.PARSE_WORKER_JITTER_S,
        )
    logger.warning(
        "Parser async job marked for retry/dead-letter",
        extra={"context": {"job_id": job.id, "run_id": job.run_id}},
    )
    return True


async def run_worker_forever(*, worker_id: Optional[str] = None) -> None:
    """Continuously process parser jobs until interrupted."""
    worker_id = worker_id or f"parse-worker-{uuid4().hex[:12]}"
    poll_interval = max(0.1, float(settings.PARSE_WORKER_POLL_INTERVAL_S))

    logger.info(
        "Parser worker started",
        extra={
            "context": {
                "worker_id": worker_id,
                "poll_interval_s": poll_interval,
                "max_attempts": settings.PARSE_WORKER_MAX_ATTEMPTS,
            }
        },
    )

    while True:
        processed = await process_next_parser_job(worker_id=worker_id)
        if not processed:
            await asyncio.sleep(poll_interval)


async def run_worker_once(*, worker_id: Optional[str] = None) -> int:
    """Process a single job and return process exit code semantics (0=job,1=none)."""
    worker_id = worker_id or f"parse-worker-once-{uuid4().hex[:10]}"
    processed = await process_next_parser_job(worker_id=worker_id)
    return 0 if processed else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Durable parser async worker")
    parser.add_argument("--once", action="store_true", help="Process a single queued job and exit")
    parser.add_argument("--worker-id", default=None, help="Optional worker instance identifier")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.once:
        return asyncio.run(run_worker_once(worker_id=args.worker_id))
    asyncio.run(run_worker_forever(worker_id=args.worker_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
