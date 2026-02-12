"""Service for orchestrating document parsing operations."""

import random
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import FileDB, ParserRunDB, ParserRunJobDB
from document_processing.schemas import ParserRunStatus, ParseResult
from document_processing.services import file_service
from document_processing.services.classification_service import classify_document
from document_processing.services.splitting_service import split_document
from document_processing.services.regex_extractor_service import extract_with_schema
from document_processing.services.format_handlers import format_detector
from document_processing.services.llm_service import llm_service


async def create_parser_run(
    session: AsyncSession,
    tenant_id: str,
    file_id: str,
    schema_id: Optional[str] = None,
    extractor_id: Optional[str] = None,
    classifier_id: Optional[str] = None,
    splitter_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> ParserRunStatus:
    """
    Create a new parser run record.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        file_id: File to parse
        schema_id: Optional schema for extraction
        extractor_id: Optional extractor to use
        classifier_id: Optional classifier to use
        splitter_id: Optional splitter to use
        metadata: Additional run metadata
        
    Returns:
        ParserRunStatus with run information
    """
    # Verify file exists and belongs to tenant
    file_db = await file_service.get_file(session, tenant_id, file_id)
    if not file_db:
        raise ValueError(f"File not found: {file_id}")
    
    # Create run ID
    run_id = f"run_{uuid.uuid4().hex}"
    
    # Create database record
    run_db = ParserRunDB(
        id=run_id,
        tenant_id=tenant_id,
        file_id=file_id,
        status="pending",
        schema_id=schema_id,
        extractor_id=extractor_id,
        classifier_id=classifier_id,
        splitter_id=splitter_id,
        run_metadata=metadata or {},
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    session.add(run_db)
    await session.commit()
    await session.refresh(run_db)
    
    return _run_db_to_status(run_db)


async def execute_parser_run(
    session: AsyncSession,
    tenant_id: str,
    run_id: str
) -> ParseResult:
    """
    Execute a parser run synchronously.
    
    Orchestrates classification, splitting, and extraction steps.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        run_id: Parser run identifier
        
    Returns:
        ParseResult with execution results
        
    Raises:
        ValueError: If run not found or invalid state
    """
    # Get run
    result = await session.execute(
        select(ParserRunDB).where(
            ParserRunDB.id == run_id,
            ParserRunDB.tenant_id == tenant_id
        )
    )
    
    run_db = result.scalar_one_or_none()
    
    if not run_db:
        raise ValueError(f"Parser run not found: {run_id}")

    if run_db.status == "completed":
        return ParseResult(
            run_id=run_db.id,
            file_id=run_db.file_id,
            status="completed",
            classification=run_db.classification_result,
            chunks=run_db.split_chunks,
            extracted=run_db.extracted_data,
            confidence=(run_db.confidence_score / 100.0) if run_db.confidence_score is not None else None,
            processing_time_ms=run_db.processing_time_ms or 0,
            completed_at=run_db.completed_at or datetime.utcnow(),
            error=None,
        )

    if run_db.status not in ("pending", "running", "failed"):
        raise ValueError(f"Parser run already {run_db.status}")
    
    # Update status to running
    run_db.status = "running"
    run_db.started_at = datetime.utcnow()
    run_db.updated_at = datetime.utcnow()
    await session.commit()
    
    start_time = time.time()
    
    try:
        # Get file content
        file_db = await file_service.get_file(session, tenant_id, run_db.file_id)
        if not file_db:
            raise ValueError(f"File not found: {run_db.file_id}")
        
        file_content = await file_service.get_file_content(file_db)
        
        # PHASE 5: Use format handlers for multi-format support
        try:
            text = format_detector.extract_text(
                file_content,
                file_db.content_type,
                file_db.filename
            )
            
            # Extract format-specific metadata
            format_metadata = format_detector.extract_metadata(
                file_content,
                file_db.content_type,
                file_db.filename
            )
            
            # Add to run metadata
            if not run_db.run_metadata:
                run_db.run_metadata = {}
            run_db.run_metadata["format_metadata"] = format_metadata
            
        except Exception as e:
            # Fallback to simple text decoding
            text = file_content.decode("utf-8", errors="ignore")
        
        # Step 1: Classification (if classifier specified)
        classification_result = None
        if run_db.classifier_id:
            classification_result = await classify_document(
                session,
                tenant_id,
                text,
                run_db.classifier_id,
            )
            run_db.classification_result = classification_result
        
        # Step 2: Splitting (if splitter specified)
        split_chunks = None
        if run_db.splitter_id:
            split_chunks = await split_document(
                session,
                tenant_id,
                text,
                run_db.splitter_id,
            )
            run_db.split_chunks = split_chunks.get("chunks") if isinstance(split_chunks, dict) else split_chunks
        
        # Step 3: Extraction (if schema specified)
        extracted_data = None
        confidence_score = None
        if run_db.schema_id:
            extraction_result = await extract_with_schema(
                session,
                tenant_id,
                run_db.schema_id,
                text,
                run_db.extractor_id,
            )
            extracted_fields = extraction_result.get("fields")
            if extracted_fields is None:
                extracted_fields = extraction_result.get("extracted_fields", [])
            extracted_data = {
                "fields": extracted_fields,
                "citations": extraction_result.get("citations", [])
            }
            raw_confidence = extraction_result.get("confidence")
            if raw_confidence is None:
                total_fields = extraction_result.get("total_fields") or len(extracted_fields)
                extracted_count = extraction_result.get("extracted_count", len(extracted_fields))
                raw_confidence = (float(extracted_count) / float(total_fields)) if total_fields else 0.0
            confidence_score = int(max(0.0, min(1.0, float(raw_confidence))) * 100)
            
            # PHASE 5: Optional LLM post-processing
            use_llm = run_db.run_metadata.get("use_llm_post_processing", False)
            if use_llm:
                # Get schema for LLM context
                from document_processing.services.schema_service import SchemaService
                schema_service = SchemaService(session)
                schema = await schema_service.get_schema(tenant_id, run_db.schema_id)
                
                if schema:
                    llm_result = await llm_service.post_process_extraction(
                        extraction_result,
                        text,
                        schema.model_dump()
                    )
                    
                    # Merge LLM enhancements
                    extracted_data["llm_enhanced"] = True
                    extracted_data["validated_fields"] = llm_result.get("validated_fields", {})
                    extracted_data["inferred_fields"] = llm_result.get("inferred_fields", {})
                    extracted_data["entities"] = llm_result.get("entities", [])
                    
                    # Update confidence if LLM provided better score
                    if llm_result.get("overall_confidence"):
                        confidence_score = int(llm_result["overall_confidence"] * 100)
            
            run_db.extracted_data = extracted_data
            run_db.confidence_score = confidence_score
        
        # Calculate processing time
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Update run as completed
        run_db.status = "completed"
        run_db.completed_at = datetime.utcnow()
        run_db.processing_time_ms = processing_time_ms
        run_db.updated_at = datetime.utcnow()
        
        await session.commit()
        await session.refresh(run_db)
        
        return ParseResult(
            run_id=run_db.id,
            file_id=run_db.file_id,
            status="completed",
            classification=classification_result,
            chunks=(split_chunks.get("chunks") if isinstance(split_chunks, dict) else split_chunks),
            extracted=extracted_data,
            confidence=confidence_score / 100.0 if confidence_score else None,
            processing_time_ms=processing_time_ms,
            completed_at=run_db.completed_at
        )
        
    except Exception as e:
        # Mark as failed
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        run_db.status = "failed"
        run_db.error_message = str(e)
        run_db.completed_at = datetime.utcnow()
        run_db.processing_time_ms = processing_time_ms
        run_db.updated_at = datetime.utcnow()
        
        await session.commit()
        await session.refresh(run_db)
        
        return ParseResult(
            run_id=run_db.id,
            file_id=run_db.file_id,
            status="failed",
            processing_time_ms=processing_time_ms,
            completed_at=run_db.completed_at,
            error=str(e)
        )


async def enqueue_parser_run_job(
    session: AsyncSession,
    tenant_id: str,
    run_id: str,
    *,
    max_attempts: int = 5,
) -> ParserRunJobDB:
    """Enqueue a durable async execution job for a parser run."""
    existing_result = await session.execute(
        select(ParserRunJobDB).where(
            ParserRunJobDB.run_id == run_id,
            ParserRunJobDB.tenant_id == tenant_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return existing

    now = datetime.utcnow()
    job = ParserRunJobDB(
        id=f"pjob_{uuid.uuid4().hex}",
        run_id=run_id,
        tenant_id=tenant_id,
        status="queued",
        attempt_count=0,
        max_attempts=max(1, int(max_attempts)),
        last_error=None,
        next_attempt_at=now,
        lock_owner=None,
        locked_at=None,
        dead_lettered_at=None,
        created_at=now,
        updated_at=now,
        started_at=None,
        completed_at=None,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def claim_next_parser_run_job(
    session: AsyncSession,
    *,
    worker_id: str,
    lock_timeout_seconds: int = 300,
) -> Optional[ParserRunJobDB]:
    """Claim the next due parser run job with optimistic concurrency semantics."""
    now = datetime.utcnow()
    stale_before = now - timedelta(seconds=max(1, int(lock_timeout_seconds)))

    due_result = await session.execute(
        select(ParserRunJobDB).where(
            and_(
                ParserRunJobDB.status.in_(["queued", "failed"]),
                ParserRunJobDB.next_attempt_at <= now,
            )
        ).order_by(ParserRunJobDB.next_attempt_at.asc(), ParserRunJobDB.created_at.asc()).limit(1)
    )
    job = due_result.scalar_one_or_none()

    if job is None:
        stale_result = await session.execute(
            select(ParserRunJobDB).where(
                and_(
                    ParserRunJobDB.status == "running",
                    ParserRunJobDB.locked_at.is_not(None),
                    ParserRunJobDB.locked_at <= stale_before,
                )
            ).order_by(ParserRunJobDB.locked_at.asc()).limit(1)
        )
        job = stale_result.scalar_one_or_none()

    if job is None:
        return None

    previous_status = job.status
    claim_result = await session.execute(
        update(ParserRunJobDB)
        .where(
            and_(
                ParserRunJobDB.id == job.id,
                ParserRunJobDB.status == previous_status,
            )
        )
        .values(
            status="running",
            attempt_count=job.attempt_count + 1,
            lock_owner=worker_id,
            locked_at=now,
            started_at=job.started_at or now,
            updated_at=now,
        )
    )
    if claim_result.rowcount != 1:
        await session.rollback()
        return None

    run_result = await session.execute(
        select(ParserRunDB).where(
            ParserRunDB.id == job.run_id,
            ParserRunDB.tenant_id == job.tenant_id,
        )
    )
    run_db = run_result.scalar_one_or_none()
    if run_db and run_db.status in ("pending", "failed", "dead_letter"):
        run_db.status = "running"
        run_db.started_at = run_db.started_at or now
        run_db.updated_at = now

    await session.commit()
    await session.refresh(job)
    return job


async def mark_parser_run_job_succeeded(
    session: AsyncSession,
    *,
    job_id: str,
) -> Optional[ParserRunJobDB]:
    """Mark a parser run job as succeeded."""
    now = datetime.utcnow()
    result = await session.execute(
        select(ParserRunJobDB).where(ParserRunJobDB.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    if job.status == "succeeded":
        return job

    job.status = "succeeded"
    job.lock_owner = None
    job.locked_at = None
    job.completed_at = now
    job.updated_at = now
    await session.commit()
    await session.refresh(job)
    return job


def _calculate_retry_delay_seconds(
    attempt_count: int,
    *,
    base_delay_seconds: float,
    max_delay_seconds: float,
    jitter_seconds: float,
) -> float:
    exp_delay = base_delay_seconds * (2 ** max(0, attempt_count - 1))
    bounded = min(max_delay_seconds, exp_delay)
    jitter = random.uniform(0.0, max(0.0, jitter_seconds))
    return bounded + jitter


async def mark_parser_run_job_failed(
    session: AsyncSession,
    *,
    job_id: str,
    error_message: str,
    base_delay_seconds: float = 2.0,
    max_delay_seconds: float = 120.0,
    jitter_seconds: float = 1.0,
) -> Optional[ParserRunJobDB]:
    """Handle parser run job failure with bounded retry and dead-lettering."""
    now = datetime.utcnow()
    result = await session.execute(
        select(ParserRunJobDB).where(ParserRunJobDB.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    run_result = await session.execute(
        select(ParserRunDB).where(
            ParserRunDB.id == job.run_id,
            ParserRunDB.tenant_id == job.tenant_id,
        )
    )
    run_db = run_result.scalar_one_or_none()

    job.last_error = (error_message or "Unknown parser execution error")[:4000]
    job.lock_owner = None
    job.locked_at = None
    job.updated_at = now

    if job.attempt_count >= job.max_attempts:
        job.status = "dead_letter"
        job.dead_lettered_at = now
        job.completed_at = now
        if run_db:
            run_db.status = "dead_letter"
            run_db.error_message = f"Dead-lettered after {job.attempt_count} attempts: {job.last_error}"
            run_db.completed_at = now
            run_db.updated_at = now
    else:
        delay_seconds = _calculate_retry_delay_seconds(
            job.attempt_count,
            base_delay_seconds=base_delay_seconds,
            max_delay_seconds=max_delay_seconds,
            jitter_seconds=jitter_seconds,
        )
        job.status = "failed"
        job.next_attempt_at = now + timedelta(seconds=delay_seconds)
        if run_db:
            run_db.status = "failed"
            run_db.error_message = job.last_error
            run_db.updated_at = now

    await session.commit()
    await session.refresh(job)
    return job


async def replay_dead_letter_parser_run_job(
    session: AsyncSession,
    *,
    tenant_id: str,
    run_id: str,
) -> bool:
    """Replay a dead-lettered parser run job in an idempotent way."""
    result = await session.execute(
        select(ParserRunJobDB).where(
            ParserRunJobDB.tenant_id == tenant_id,
            ParserRunJobDB.run_id == run_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        return False

    if job.status != "dead_letter":
        return True

    now = datetime.utcnow()
    job.status = "queued"
    job.attempt_count = 0
    job.last_error = None
    job.next_attempt_at = now
    job.lock_owner = None
    job.locked_at = None
    job.dead_lettered_at = None
    job.updated_at = now

    run_result = await session.execute(
        select(ParserRunDB).where(
            ParserRunDB.id == run_id,
            ParserRunDB.tenant_id == tenant_id,
        )
    )
    run_db = run_result.scalar_one_or_none()
    if run_db:
        run_db.status = "pending"
        run_db.error_message = None
        run_db.updated_at = now

    await session.commit()
    return True


async def list_dead_letter_parser_run_jobs(
    session: AsyncSession,
    *,
    tenant_id: Optional[str] = None,
    limit: int = 100,
) -> list[ParserRunJobDB]:
    """List dead-letter parser jobs for operational replay tooling."""
    query = select(ParserRunJobDB).where(ParserRunJobDB.status == "dead_letter")
    if tenant_id:
        query = query.where(ParserRunJobDB.tenant_id == tenant_id)

    result = await session.execute(
        query.order_by(ParserRunJobDB.dead_lettered_at.desc(), ParserRunJobDB.updated_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_parser_run(
    session: AsyncSession,
    tenant_id: str,
    run_id: str
) -> Optional[ParserRunStatus]:
    """
    Get parser run status.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        run_id: Run identifier
        
    Returns:
        ParserRunStatus if found, None otherwise
    """
    result = await session.execute(
        select(ParserRunDB).where(
            ParserRunDB.id == run_id,
            ParserRunDB.tenant_id == tenant_id
        )
    )
    
    run_db = result.scalar_one_or_none()
    
    if not run_db:
        return None
    
    return _run_db_to_status(run_db)


async def list_parser_runs(
    session: AsyncSession,
    tenant_id: str,
    file_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Tuple[list[ParserRunStatus], int]:
    """
    List parser runs with optional filtering.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        file_id: Optional file filter
        status: Optional status filter
        limit: Maximum number of results
        offset: Number of results to skip
        
    Returns:
        Tuple of (list of ParserRunStatus, total count)
    """
    # Build base query
    query = select(ParserRunDB).where(
        ParserRunDB.tenant_id == tenant_id
    )
    
    count_query = select(func.count(ParserRunDB.id)).where(
        ParserRunDB.tenant_id == tenant_id
    )
    
    # Apply filters
    if file_id:
        query = query.where(ParserRunDB.file_id == file_id)
        count_query = count_query.where(ParserRunDB.file_id == file_id)
    
    if status:
        query = query.where(ParserRunDB.status == status)
        count_query = count_query.where(ParserRunDB.status == status)
    
    # Get total count
    count_result = await session.execute(count_query)
    total = count_result.scalar_one()
    
    # Get runs
    result = await session.execute(
        query
        .order_by(ParserRunDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    runs = result.scalars().all()
    
    run_statuses = [_run_db_to_status(run) for run in runs]
    
    return run_statuses, total


def _run_db_to_status(run_db: ParserRunDB) -> ParserRunStatus:
    """Convert ParserRunDB to ParserRunStatus."""
    return ParserRunStatus(
        run_id=run_db.id,
        file_id=run_db.file_id,
        status=run_db.status,
        tenant_id=run_db.tenant_id,
        schema_id=run_db.schema_id,
        extractor_id=run_db.extractor_id,
        classifier_id=run_db.classifier_id,
        splitter_id=run_db.splitter_id,
        classification_result=run_db.classification_result,
        split_chunks=run_db.split_chunks,
        extracted_data=run_db.extracted_data,
        confidence_score=run_db.confidence_score,
        started_at=run_db.started_at,
        completed_at=run_db.completed_at,
        processing_time_ms=run_db.processing_time_ms,
        error_message=run_db.error_message,
        created_at=run_db.created_at,
        updated_at=run_db.updated_at,
        metadata=run_db.run_metadata
    )
