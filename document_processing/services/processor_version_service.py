"""
Processor version service (Sprint 4 - P3.1-P3.2).

Handles processor versioning with create, publish, get, and list operations.
Supports version lifecycle management (draft → published → deprecated).
"""

import uuid
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import ProcessorDB, ProcessorVersionDB


async def create_processor_version(
    session: AsyncSession,
    tenant_id: str,
    processor_id: str,
    change_notes: Optional[str] = None,
    created_by: Optional[str] = None,
    name_override: Optional[str] = None,
    description_override: Optional[str] = None,
    implementation_override: Optional[dict] = None,
    input_schema_override: Optional[dict] = None,
    output_schema_override: Optional[dict] = None
) -> ProcessorVersionDB:
    """
    Create a new version from an existing processor.
    
    Creates a snapshot of the processor configuration as a new version.
    The version starts in 'draft' status and can be edited before publishing.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        processor_id: ID of processor to version
        change_notes: Notes about what changed in this version
        created_by: User who created the version
        name_override: Optional name override
        description_override: Optional description override
        implementation_override: Optional implementation override
        input_schema_override: Optional input schema override
        output_schema_override: Optional output schema override
    
    Returns:
        Created processor version
        
    Raises:
        ValueError: If processor not found
    """
    # Get source processor
    result = await session.execute(
        select(ProcessorDB).where(
            and_(
                ProcessorDB.id == processor_id,
                ProcessorDB.tenant_id == tenant_id,
                ProcessorDB.is_deleted == False
            )
        )
    )
    processor = result.scalars().first()
    
    if not processor:
        raise ValueError(f"Processor {processor_id} not found")
    
    # Get next version number
    max_version_result = await session.execute(
        select(func.max(ProcessorVersionDB.version_number)).where(
            and_(
                ProcessorVersionDB.processor_id == processor_id,
                ProcessorVersionDB.is_deleted == False
            )
        )
    )
    max_version = max_version_result.scalar() or 0
    next_version = max_version + 1
    
    # Create version snapshot (with overrides if provided)
    version = ProcessorVersionDB(
        id=f"pver_{uuid.uuid4().hex[:12]}",
        processor_id=processor_id,
        tenant_id=tenant_id,
        version_number=next_version,
        name=name_override or processor.name,
        description=description_override if description_override is not None else processor.description,
        processor_type=processor.processor_type,
        implementation=implementation_override or processor.implementation,
        input_schema=input_schema_override if input_schema_override is not None else processor.input_schema,
        output_schema=output_schema_override if output_schema_override is not None else processor.output_schema,
        status='draft',
        is_default=False,
        published_at=None,
        deprecated_at=None,
        change_notes=change_notes,
        created_by=created_by,
        version_metadata=None,
        is_deleted=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    session.add(version)
    await session.commit()
    await session.refresh(version)
    
    return version


async def publish_processor_version(
    session: AsyncSession,
    tenant_id: str,
    version_id: str,
    make_default: bool = False
) -> ProcessorVersionDB:
    """
    Publish a processor version.
    
    Publishing makes the version immutable and available for production use.
    Optionally sets it as the default version for the processor.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        version_id: Version ID to publish
        make_default: Whether to make this the default version
    
    Returns:
        Published version
        
    Raises:
        ValueError: If version not found or already published
    """
    # Get version
    result = await session.execute(
        select(ProcessorVersionDB).where(
            and_(
                ProcessorVersionDB.id == version_id,
                ProcessorVersionDB.tenant_id == tenant_id,
                ProcessorVersionDB.is_deleted == False
            )
        )
    )
    version = result.scalars().first()
    
    if not version:
        raise ValueError(f"Version {version_id} not found")
    
    if version.status == 'published':
        raise ValueError(f"Version {version_id} is already published")
    
    if version.status == 'deprecated':
        raise ValueError(f"Cannot publish deprecated version {version_id}")
    
    # Publish version
    version.status = 'published'
    version.published_at = datetime.utcnow()
    version.updated_at = datetime.utcnow()
    
    # If making default, unset other defaults for this processor
    if make_default:
        await session.execute(
            select(ProcessorVersionDB).where(
                and_(
                    ProcessorVersionDB.processor_id == version.processor_id,
                    ProcessorVersionDB.tenant_id == tenant_id,
                    ProcessorVersionDB.is_default == True,
                    ProcessorVersionDB.is_deleted == False
                )
            )
        )
        # Unset all other defaults
        existing_defaults = await session.execute(
            select(ProcessorVersionDB).where(
                and_(
                    ProcessorVersionDB.processor_id == version.processor_id,
                    ProcessorVersionDB.tenant_id == tenant_id,
                    ProcessorVersionDB.is_default == True,
                    ProcessorVersionDB.id != version_id,
                    ProcessorVersionDB.is_deleted == False
                )
            )
        )
        for default_version in existing_defaults.scalars().all():
            default_version.is_default = False
        
        version.is_default = True
    
    await session.commit()
    await session.refresh(version)
    
    return version


async def get_processor_version(
    session: AsyncSession,
    tenant_id: str,
    version_id: str
) -> Optional[ProcessorVersionDB]:
    """
    Get processor version by ID.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        version_id: Version ID
    
    Returns:
        Processor version or None if not found
    """
    result = await session.execute(
        select(ProcessorVersionDB).where(
            and_(
                ProcessorVersionDB.id == version_id,
                ProcessorVersionDB.tenant_id == tenant_id,
                ProcessorVersionDB.is_deleted == False
            )
        )
    )
    return result.scalars().first()


async def list_processor_versions(
    session: AsyncSession,
    tenant_id: str,
    processor_id: str,
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
) -> Tuple[List[ProcessorVersionDB], int]:
    """
    List versions for a specific processor.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        processor_id: Processor ID
        limit: Maximum number of results
        offset: Number of results to skip
        status: Filter by status (draft, published, deprecated)
    
    Returns:
        Tuple of (versions list, total count)
    """
    # Build query with filters
    conditions = [
        ProcessorVersionDB.processor_id == processor_id,
        ProcessorVersionDB.tenant_id == tenant_id,
        ProcessorVersionDB.is_deleted == False
    ]
    
    if status:
        conditions.append(ProcessorVersionDB.status == status)
    
    # Get total count
    count_result = await session.execute(
        select(func.count()).select_from(ProcessorVersionDB).where(and_(*conditions))
    )
    total = count_result.scalar() or 0
    
    # Get items (ordered by version_number descending - newest first)
    result = await session.execute(
        select(ProcessorVersionDB)
        .where(and_(*conditions))
        .order_by(desc(ProcessorVersionDB.version_number))
        .limit(limit)
        .offset(offset)
    )
    
    items = list(result.scalars().all())
    return items, total


async def get_default_processor_version(
    session: AsyncSession,
    tenant_id: str,
    processor_id: str
) -> Optional[ProcessorVersionDB]:
    """
    Get the default version for a processor.
    
    Returns the version marked as default, or the latest published version
    if no default is set.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        processor_id: Processor ID
    
    Returns:
        Default processor version or None if no versions exist
    """
    # Try to get explicitly marked default
    result = await session.execute(
        select(ProcessorVersionDB).where(
            and_(
                ProcessorVersionDB.processor_id == processor_id,
                ProcessorVersionDB.tenant_id == tenant_id,
                ProcessorVersionDB.is_default == True,
                ProcessorVersionDB.status == 'published',
                ProcessorVersionDB.is_deleted == False
            )
        )
    )
    default = result.scalars().first()
    
    if default:
        return default
    
    # Fall back to latest published version
    result = await session.execute(
        select(ProcessorVersionDB)
        .where(
            and_(
                ProcessorVersionDB.processor_id == processor_id,
                ProcessorVersionDB.tenant_id == tenant_id,
                ProcessorVersionDB.status == 'published',
                ProcessorVersionDB.is_deleted == False
            )
        )
        .order_by(desc(ProcessorVersionDB.version_number))
        .limit(1)
    )
    return result.scalars().first()


async def deprecate_processor_version(
    session: AsyncSession,
    tenant_id: str,
    version_id: str
) -> ProcessorVersionDB:
    """
    Deprecate a processor version.
    
    Deprecated versions can no longer be used for new runs but existing
    runs continue to work.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        version_id: Version ID to deprecate
    
    Returns:
        Deprecated version
        
    Raises:
        ValueError: If version not found or not published
    """
    version = await get_processor_version(session, tenant_id, version_id)
    
    if not version:
        raise ValueError(f"Version {version_id} not found")
    
    if version.status != 'published':
        raise ValueError(f"Can only deprecate published versions")
    
    if version.is_default:
        raise ValueError(f"Cannot deprecate default version. Set a new default first.")
    
    version.status = 'deprecated'
    version.deprecated_at = datetime.utcnow()
    version.updated_at = datetime.utcnow()
    
    await session.commit()
    await session.refresh(version)
    
    return version
