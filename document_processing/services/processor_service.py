"""
Processor service for managing custom processing plugins.

Processors are reusable processing units that can be chained in workflows.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import ProcessorDB


async def create_processor(
    session: AsyncSession,
    tenant_id: str,
    name: str,
    processor_type: str,
    implementation: dict,
    description: Optional[str] = None,
    input_schema: Optional[dict] = None,
    output_schema: Optional[dict] = None,
    enabled: bool = True,
    metadata: Optional[dict] = None
) -> ProcessorDB:
    """
    Create a new processor.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        name: Processor name
        processor_type: Type of processor (extractor, transformer, validator, custom)
        implementation: Implementation details (code, config, or reference)
        description: Optional description
        input_schema: Expected input format schema
        output_schema: Expected output format schema
        enabled: Whether processor is enabled
        metadata: Additional metadata
    
    Returns:
        Created processor
    """
    # Check for duplicate name (among non-deleted processors)
    existing = await session.execute(
        select(ProcessorDB).where(
            and_(
                ProcessorDB.tenant_id == tenant_id,
                ProcessorDB.name == name,
                ProcessorDB.is_deleted == False
            )
        )
    )
    if existing.scalars().first():
        raise ValueError(f"Processor with name '{name}' already exists")
    
    processor = ProcessorDB(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        description=description or "",
        processor_type=processor_type,
        implementation=implementation,
        input_schema=input_schema,
        output_schema=output_schema,
        enabled=enabled,
        version=1,
        processor_metadata=metadata,
        is_deleted=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    session.add(processor)
    await session.commit()
    await session.refresh(processor)
    
    return processor


async def get_processor(
    session: AsyncSession,
    tenant_id: str,
    processor_id: str
) -> Optional[ProcessorDB]:
    """
    Get processor by ID.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        processor_id: Processor ID
    
    Returns:
        Processor or None if not found
    """
    result = await session.execute(
        select(ProcessorDB).where(
            and_(
                ProcessorDB.id == processor_id,
                ProcessorDB.tenant_id == tenant_id,
                ProcessorDB.is_deleted == False
            )
        )
    )
    return result.scalars().first()


async def list_processors(
    session: AsyncSession,
    tenant_id: str,
    limit: int = 50,
    offset: int = 0,
    processor_type: Optional[str] = None,
    enabled: Optional[bool] = None
) -> Tuple[List[ProcessorDB], int]:
    """
    List processors with pagination and filtering.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of results
        offset: Number of results to skip
        processor_type: Filter by processor type
        enabled: Filter by enabled status
    
    Returns:
        Tuple of (processors list, total count)
    """
    # Build query with filters
    conditions = [
        ProcessorDB.tenant_id == tenant_id,
        ProcessorDB.is_deleted == False
    ]
    
    if processor_type:
        conditions.append(ProcessorDB.processor_type == processor_type)
    
    if enabled is not None:
        conditions.append(ProcessorDB.enabled == enabled)
    
    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(ProcessorDB).where(and_(*conditions))
    )
    total = count_result.scalar() or 0
    
    # Get items
    result = await session.execute(
        select(ProcessorDB)
        .where(and_(*conditions))
        .order_by(ProcessorDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    items = list(result.scalars().all())
    return items, total


async def update_processor(
    session: AsyncSession,
    tenant_id: str,
    processor_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    processor_type: Optional[str] = None,
    implementation: Optional[dict] = None,
    input_schema: Optional[dict] = None,
    output_schema: Optional[dict] = None,
    enabled: Optional[bool] = None,
    metadata: Optional[dict] = None
) -> Optional[ProcessorDB]:
    """
    Update processor.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        processor_id: Processor ID
        name: Optional new name
        description: Optional new description
        processor_type: Optional new processor type
        implementation: Optional new implementation
        input_schema: Optional new input schema
        output_schema: Optional new output schema
        enabled: Optional new enabled status
        metadata: Optional new metadata
    
    Returns:
        Updated processor or None if not found
    """
    processor = await get_processor(session, tenant_id, processor_id)
    if not processor:
        return None
    
    # Check name uniqueness if changing
    if name and name != processor.name:
        existing = await session.execute(
            select(ProcessorDB).where(
                and_(
                    ProcessorDB.tenant_id == tenant_id,
                    ProcessorDB.name == name,
                    ProcessorDB.is_deleted == False,
                    ProcessorDB.id != processor_id
                )
            )
        )
        if existing.scalars().first():
            raise ValueError(f"Processor with name '{name}' already exists")
        processor.name = name
    
    # Update fields
    if description is not None:
        processor.description = description
    if processor_type:
        processor.processor_type = processor_type
    if implementation:
        processor.implementation = implementation
        processor.version += 1  # Increment version on implementation change
    if input_schema is not None:
        processor.input_schema = input_schema
    if output_schema is not None:
        processor.output_schema = output_schema
    if enabled is not None:
        processor.enabled = enabled
    if metadata is not None:
        processor.processor_metadata = metadata
    
    processor.updated_at = datetime.utcnow()
    
    await session.commit()
    await session.refresh(processor)
    
    return processor


async def delete_processor(
    session: AsyncSession,
    tenant_id: str,
    processor_id: str
) -> bool:
    """
    Soft delete processor.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        processor_id: Processor ID
    
    Returns:
        True if deleted, False if not found
    """
    processor = await get_processor(session, tenant_id, processor_id)
    if not processor:
        return False
    
    processor.is_deleted = True
    processor.updated_at = datetime.utcnow()
    
    await session.commit()
    return True
