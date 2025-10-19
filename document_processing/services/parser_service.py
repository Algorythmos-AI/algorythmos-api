"""Service for orchestrating document parsing operations."""

import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import ParserRunDB, FileDB
from document_processing.schemas import ParserRunStatus, ParseResult
from document_processing.services import file_service
from document_processing.services.classification_service import classify_document
from document_processing.services.splitting_service import split_document
from document_processing.services.regex_extractor_service import extract_with_regex


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
    
    if run_db.status not in ("pending", "running"):
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
        
        # Detect content type - for now assume text
        # In production, would use file type detection
        if file_db.content_type == "application/pdf":
            # Would extract text from PDF here
            # For now, just use placeholder
            text = "[PDF content extraction not yet implemented]"
        else:
            # Assume text file
            text = file_content.decode("utf-8", errors="ignore")
        
        # Step 1: Classification (if classifier specified)
        classification_result = None
        if run_db.classifier_id:
            classification_result = await classify_document(
                session, tenant_id, run_db.classifier_id, text
            )
            run_db.classification_result = classification_result
        
        # Step 2: Splitting (if splitter specified)
        split_chunks = None
        if run_db.splitter_id:
            split_chunks = await split_document(
                session, tenant_id, run_db.splitter_id, text, run_db.run_metadata
            )
            run_db.split_chunks = split_chunks
        
        # Step 3: Extraction (if schema specified)
        extracted_data = None
        confidence_score = None
        if run_db.schema_id:
            extraction_result = await extract_with_regex(
                session, tenant_id, run_db.schema_id, text, {}
            )
            extracted_data = {
                "fields": extraction_result["fields"],
                "citations": extraction_result.get("citations", [])
            }
            confidence_score = int(extraction_result.get("confidence", 0) * 100)
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
            chunks=split_chunks,
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
