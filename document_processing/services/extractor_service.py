"""Service layer for extractor management."""

from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import ExtractorDB, ExtractionSchemaDB
from document_processing.schemas import (
    ExtractorConfig,
    CreateExtractorRequest,
    UpdateExtractorRequest
)


async def create_extractor(
    db: AsyncSession,
    tenant_id: str,
    request: CreateExtractorRequest
) -> ExtractorConfig:
    """Create a new extractor configuration.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        request: Extractor creation request
    
    Returns:
        Created extractor configuration
    
    Raises:
        ValueError: If schema_id doesn't exist or name already exists
    """
    # Verify schema exists and belongs to this tenant
    schema_result = await db.execute(
        select(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.id == request.schema_id,
                ExtractionSchemaDB.tenant_id == tenant_id
            )
        )
    )
    schema = schema_result.scalar_one_or_none()
    if not schema:
        raise ValueError(f"Schema '{request.schema_id}' not found for this tenant")
    
    # Check for duplicate name
    existing_result = await db.execute(
        select(ExtractorDB).where(
            and_(
                ExtractorDB.tenant_id == tenant_id,
                ExtractorDB.name == request.name
            )
        )
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"Extractor with name '{request.name}' already exists for this tenant")
    
    # Generate extractor_id: {tenant_id}_{name_slug}_{timestamp}
    name_slug = request.name.lower().replace(" ", "_").replace("-", "_")
    timestamp = int(datetime.utcnow().timestamp())
    extractor_id = f"{tenant_id}_{name_slug}_{timestamp}"
    
    # Create extractor
    now = datetime.utcnow()
    db_extractor = ExtractorDB(
        id=extractor_id,
        tenant_id=tenant_id,
        name=request.name,
        type=request.type,
        schema_id=request.schema_id,
        enabled=request.enabled,
        priority=request.priority,
        rules=request.rules,
        created_at=now,
        updated_at=now
    )
    
    db.add(db_extractor)
    await db.commit()
    await db.refresh(db_extractor)
    
    return _db_to_pydantic(db_extractor)


async def get_extractor(
    db: AsyncSession,
    tenant_id: str,
    extractor_id: str
) -> Optional[ExtractorConfig]:
    """Get an extractor by ID.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        extractor_id: Extractor identifier
    
    Returns:
        Extractor configuration or None if not found
    """
    result = await db.execute(
        select(ExtractorDB).where(
            and_(
                ExtractorDB.id == extractor_id,
                ExtractorDB.tenant_id == tenant_id
            )
        )
    )
    db_extractor = result.scalar_one_or_none()
    
    if not db_extractor:
        return None
    
    return _db_to_pydantic(db_extractor)


async def list_extractors(
    db: AsyncSession,
    tenant_id: str,
    limit: int = 20,
    cursor: Optional[str] = None,
    schema_id: Optional[str] = None,
    enabled: Optional[bool] = None
) -> Tuple[List[ExtractorConfig], int, Optional[str], bool]:
    """List extractors with pagination and filters.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of items to return
        cursor: Pagination cursor (created_at timestamp)
        schema_id: Filter by schema ID
        enabled: Filter by enabled status
    
    Returns:
        Tuple of (extractors, total_count, next_cursor, has_more)
    """
    # Build query
    query = select(ExtractorDB).where(ExtractorDB.tenant_id == tenant_id)
    
    if schema_id:
        query = query.where(ExtractorDB.schema_id == schema_id)
    
    if enabled is not None:
        query = query.where(ExtractorDB.enabled == enabled)
    
    if cursor:
        query = query.where(ExtractorDB.created_at < datetime.fromisoformat(cursor))
    
    # Order by created_at descending (newest first)
    query = query.order_by(ExtractorDB.created_at.desc()).limit(limit + 1)
    
    # Execute query
    result = await db.execute(query)
    extractors = result.scalars().all()
    
    # Check if there are more results
    has_more = len(extractors) > limit
    if has_more:
        extractors = extractors[:limit]
    
    # Calculate next cursor
    next_cursor = None
    if has_more and extractors:
        next_cursor = extractors[-1].created_at.isoformat()
    
    # Get total count
    count_query = select(ExtractorDB).where(ExtractorDB.tenant_id == tenant_id)
    if schema_id:
        count_query = count_query.where(ExtractorDB.schema_id == schema_id)
    if enabled is not None:
        count_query = count_query.where(ExtractorDB.enabled == enabled)
    
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return (
        [_db_to_pydantic(e) for e in extractors],
        total,
        next_cursor,
        has_more
    )


async def update_extractor(
    db: AsyncSession,
    tenant_id: str,
    extractor_id: str,
    request: UpdateExtractorRequest
) -> Optional[ExtractorConfig]:
    """Update an extractor configuration.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        extractor_id: Extractor identifier
        request: Update request
    
    Returns:
        Updated extractor or None if not found
    """
    result = await db.execute(
        select(ExtractorDB).where(
            and_(
                ExtractorDB.id == extractor_id,
                ExtractorDB.tenant_id == tenant_id
            )
        )
    )
    db_extractor = result.scalar_one_or_none()
    
    if not db_extractor:
        return None
    
    # Update fields
    if request.name is not None:
        db_extractor.name = request.name
    if request.enabled is not None:
        db_extractor.enabled = request.enabled
    if request.priority is not None:
        db_extractor.priority = request.priority
    if request.rules is not None:
        db_extractor.rules = request.rules
    
    db_extractor.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(db_extractor)
    
    return _db_to_pydantic(db_extractor)


async def delete_extractor(
    db: AsyncSession,
    tenant_id: str,
    extractor_id: str
) -> bool:
    """Delete an extractor.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        extractor_id: Extractor identifier
    
    Returns:
        True if deleted, False if not found
    """
    result = await db.execute(
        select(ExtractorDB).where(
            and_(
                ExtractorDB.id == extractor_id,
                ExtractorDB.tenant_id == tenant_id
            )
        )
    )
    db_extractor = result.scalar_one_or_none()
    
    if not db_extractor:
        return False
    
    await db.delete(db_extractor)
    await db.commit()
    
    return True


def _db_to_pydantic(db_extractor: ExtractorDB) -> ExtractorConfig:
    """Convert database model to Pydantic model."""
    return ExtractorConfig(
        extractor_id=db_extractor.id,
        name=db_extractor.name,
        type=db_extractor.type,
        schema_id=db_extractor.schema_id,
        tenant_id=db_extractor.tenant_id,
        enabled=db_extractor.enabled,
        priority=db_extractor.priority,
        rules=db_extractor.rules,
        created_at=db_extractor.created_at,
        updated_at=db_extractor.updated_at
    )
