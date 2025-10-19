"""Service layer for splitter management."""

from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import SplitterDB
from document_processing.schemas import (
    SplitterConfig,
    CreateSplitterRequest,
    UpdateSplitterRequest
)


async def create_splitter(
    db: AsyncSession,
    tenant_id: str,
    request: CreateSplitterRequest
) -> SplitterConfig:
    """Create a new splitter configuration.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        request: Splitter creation request
    
    Returns:
        Created splitter configuration
    
    Raises:
        ValueError: If name already exists
    """
    # Check for duplicate name
    existing_result = await db.execute(
        select(SplitterDB).where(
            and_(
                SplitterDB.tenant_id == tenant_id,
                SplitterDB.name == request.name
            )
        )
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"Splitter with name '{request.name}' already exists for this tenant")
    
    # Generate splitter_id: {tenant_id}_{name_slug}_{timestamp}
    name_slug = request.name.lower().replace(" ", "_").replace("-", "_")
    timestamp = int(datetime.utcnow().timestamp())
    splitter_id = f"{tenant_id}_{name_slug}_{timestamp}"
    
    # Create splitter
    now = datetime.utcnow()
    db_splitter = SplitterDB(
        id=splitter_id,
        tenant_id=tenant_id,
        name=request.name,
        type=request.type,
        enabled=request.enabled,
        rules=request.rules,
        created_at=now,
        updated_at=now
    )
    
    db.add(db_splitter)
    await db.commit()
    await db.refresh(db_splitter)
    
    return _db_to_pydantic(db_splitter)


async def get_splitter(
    db: AsyncSession,
    tenant_id: str,
    splitter_id: str
) -> Optional[SplitterConfig]:
    """Get a splitter by ID.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        splitter_id: Splitter identifier
    
    Returns:
        Splitter configuration or None if not found
    """
    result = await db.execute(
        select(SplitterDB).where(
            and_(
                SplitterDB.id == splitter_id,
                SplitterDB.tenant_id == tenant_id
            )
        )
    )
    db_splitter = result.scalar_one_or_none()
    
    if not db_splitter:
        return None
    
    return _db_to_pydantic(db_splitter)


async def list_splitters(
    db: AsyncSession,
    tenant_id: str,
    limit: int = 20,
    cursor: Optional[str] = None,
    enabled: Optional[bool] = None
) -> Tuple[List[SplitterConfig], int, Optional[str], bool]:
    """List splitters with pagination and filters.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of items to return
        cursor: Pagination cursor (created_at timestamp)
        enabled: Filter by enabled status
    
    Returns:
        Tuple of (splitters, total_count, next_cursor, has_more)
    """
    # Build query
    query = select(SplitterDB).where(SplitterDB.tenant_id == tenant_id)
    
    if enabled is not None:
        query = query.where(SplitterDB.enabled == enabled)
    
    if cursor:
        query = query.where(SplitterDB.created_at < datetime.fromisoformat(cursor))
    
    # Order by created_at descending (newest first)
    query = query.order_by(SplitterDB.created_at.desc()).limit(limit + 1)
    
    # Execute query
    result = await db.execute(query)
    splitters = result.scalars().all()
    
    # Check if there are more results
    has_more = len(splitters) > limit
    if has_more:
        splitters = splitters[:limit]
    
    # Calculate next cursor
    next_cursor = None
    if has_more and splitters:
        next_cursor = splitters[-1].created_at.isoformat()
    
    # Get total count
    count_query = select(SplitterDB).where(SplitterDB.tenant_id == tenant_id)
    if enabled is not None:
        count_query = count_query.where(SplitterDB.enabled == enabled)
    
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return (
        [_db_to_pydantic(s) for s in splitters],
        total,
        next_cursor,
        has_more
    )


async def update_splitter(
    db: AsyncSession,
    tenant_id: str,
    splitter_id: str,
    request: UpdateSplitterRequest
) -> Optional[SplitterConfig]:
    """Update a splitter configuration.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        splitter_id: Splitter identifier
        request: Update request
    
    Returns:
        Updated splitter or None if not found
    """
    result = await db.execute(
        select(SplitterDB).where(
            and_(
                SplitterDB.id == splitter_id,
                SplitterDB.tenant_id == tenant_id
            )
        )
    )
    db_splitter = result.scalar_one_or_none()
    
    if not db_splitter:
        return None
    
    # Update fields
    if request.name is not None:
        db_splitter.name = request.name
    if request.enabled is not None:
        db_splitter.enabled = request.enabled
    if request.rules is not None:
        db_splitter.rules = request.rules
    
    db_splitter.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(db_splitter)
    
    return _db_to_pydantic(db_splitter)


async def delete_splitter(
    db: AsyncSession,
    tenant_id: str,
    splitter_id: str
) -> bool:
    """Delete a splitter.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        splitter_id: Splitter identifier
    
    Returns:
        True if deleted, False if not found
    """
    result = await db.execute(
        select(SplitterDB).where(
            and_(
                SplitterDB.id == splitter_id,
                SplitterDB.tenant_id == tenant_id
            )
        )
    )
    db_splitter = result.scalar_one_or_none()
    
    if not db_splitter:
        return False
    
    await db.delete(db_splitter)
    await db.commit()
    
    return True


def _db_to_pydantic(db_splitter: SplitterDB) -> SplitterConfig:
    """Convert database model to Pydantic model."""
    return SplitterConfig(
        splitter_id=db_splitter.id,
        name=db_splitter.name,
        type=db_splitter.type,
        tenant_id=db_splitter.tenant_id,
        enabled=db_splitter.enabled,
        rules=db_splitter.rules,
        created_at=db_splitter.created_at,
        updated_at=db_splitter.updated_at
    )
