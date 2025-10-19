"""Service layer for classifier management."""

from datetime import datetime
from typing import Optional, List, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import ClassifierDB
from document_processing.schemas import (
    ClassifierConfig,
    CreateClassifierRequest,
    UpdateClassifierRequest
)


async def create_classifier(
    db: AsyncSession,
    tenant_id: str,
    request: CreateClassifierRequest
) -> ClassifierConfig:
    """Create a new classifier configuration.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        request: Classifier creation request
    
    Returns:
        Created classifier configuration
    
    Raises:
        ValueError: If name already exists
    """
    # Check for duplicate name
    existing_result = await db.execute(
        select(ClassifierDB).where(
            and_(
                ClassifierDB.tenant_id == tenant_id,
                ClassifierDB.name == request.name,
                ClassifierDB.is_deleted == False
            )
        )
    )
    if existing_result.scalar_one_or_none():
        raise ValueError(f"Classifier with name '{request.name}' already exists for this tenant")
    
    # Generate classifier_id: {tenant_id}_{name_slug}_{timestamp}
    name_slug = request.name.lower().replace(" ", "_").replace("-", "_")
    timestamp = int(datetime.utcnow().timestamp())
    classifier_id = f"{tenant_id}_{name_slug}_{timestamp}"
    
    # Create classifier
    now = datetime.utcnow()
    db_classifier = ClassifierDB(
        id=classifier_id,
        tenant_id=tenant_id,
        name=request.name,
        type=request.type,
        enabled=request.enabled,
        categories=request.categories,
        rules=request.rules,
        created_at=now,
        updated_at=now
    )
    
    db.add(db_classifier)
    await db.commit()
    await db.refresh(db_classifier)
    
    return _db_to_pydantic(db_classifier)


async def get_classifier(
    db: AsyncSession,
    tenant_id: str,
    classifier_id: str
) -> Optional[ClassifierConfig]:
    """Get a classifier by ID.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        classifier_id: Classifier identifier
    
    Returns:
        Classifier configuration or None if not found
    """
    result = await db.execute(
        select(ClassifierDB).where(
            and_(
                ClassifierDB.id == classifier_id,
                ClassifierDB.tenant_id == tenant_id,
                ClassifierDB.is_deleted == False
            )
        )
    )
    db_classifier = result.scalar_one_or_none()
    
    if not db_classifier:
        return None
    
    return _db_to_pydantic(db_classifier)


async def list_classifiers(
    db: AsyncSession,
    tenant_id: str,
    limit: int = 20,
    offset: int = 0,
    enabled: Optional[bool] = None
) -> Tuple[List[ClassifierConfig], int]:
    """List classifiers with pagination and filters.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of items to return
        offset: Number of items to skip
        enabled: Filter by enabled status
    
    Returns:
        Tuple of (classifiers, total_count)
    """
    # Build query
    query = select(ClassifierDB).where(
        and_(
            ClassifierDB.tenant_id == tenant_id,
            ClassifierDB.is_deleted == False
        )
    )
    
    if enabled is not None:
        query = query.where(ClassifierDB.enabled == enabled)
    
    # Order by created_at descending (newest first) and apply pagination
    query = query.order_by(ClassifierDB.created_at.desc()).offset(offset).limit(limit)
    
    # Execute query
    result = await db.execute(query)
    classifiers = result.scalars().all()
    
    # Get total count
    count_query = select(ClassifierDB).where(
        and_(
            ClassifierDB.tenant_id == tenant_id,
            ClassifierDB.is_deleted == False
        )
    )
    if enabled is not None:
        count_query = count_query.where(ClassifierDB.enabled == enabled)
    
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())
    
    return (
        [_db_to_pydantic(c) for c in classifiers],
        total
    )


async def update_classifier(
    db: AsyncSession,
    tenant_id: str,
    classifier_id: str,
    request: UpdateClassifierRequest
) -> Optional[ClassifierConfig]:
    """Update a classifier configuration.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        classifier_id: Classifier identifier
        request: Update request
    
    Returns:
        Updated classifier or None if not found
    """
    result = await db.execute(
        select(ClassifierDB).where(
            and_(
                ClassifierDB.id == classifier_id,
                ClassifierDB.tenant_id == tenant_id,
                ClassifierDB.is_deleted == False
            )
        )
    )
    db_classifier = result.scalar_one_or_none()
    
    if not db_classifier:
        return None
    
    # Check for duplicate name if name is being changed
    if request.name is not None and request.name != db_classifier.name:
        existing_result = await db.execute(
            select(ClassifierDB).where(
                and_(
                    ClassifierDB.tenant_id == tenant_id,
                    ClassifierDB.name == request.name,
                    ClassifierDB.is_deleted == False
                )
            )
        )
        if existing_result.scalar_one_or_none():
            raise ValueError(f"Classifier with name '{request.name}' already exists for this tenant")
    
    # Update fields
    if request.name is not None:
        db_classifier.name = request.name
    if request.enabled is not None:
        db_classifier.enabled = request.enabled
    if request.categories is not None:
        db_classifier.categories = request.categories
    if request.rules is not None:
        db_classifier.rules = request.rules
    
    db_classifier.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(db_classifier)
    
    return _db_to_pydantic(db_classifier)


async def delete_classifier(
    db: AsyncSession,
    tenant_id: str,
    classifier_id: str
) -> bool:
    """Soft delete a classifier.
    
    Args:
        db: Database session
        tenant_id: Tenant identifier
        classifier_id: Classifier identifier
    
    Returns:
        True if deleted, False if not found
    """
    result = await db.execute(
        select(ClassifierDB).where(
            and_(
                ClassifierDB.id == classifier_id,
                ClassifierDB.tenant_id == tenant_id,
                ClassifierDB.is_deleted == False
            )
        )
    )
    db_classifier = result.scalar_one_or_none()
    
    if not db_classifier:
        return False
    
    # Soft delete: set is_deleted flag
    db_classifier.is_deleted = True
    db_classifier.updated_at = datetime.utcnow()
    
    await db.commit()
    
    return True


def _db_to_pydantic(db_classifier: ClassifierDB) -> ClassifierConfig:
    """Convert database model to Pydantic model."""
    return ClassifierConfig(
        classifier_id=db_classifier.id,
        name=db_classifier.name,
        type=db_classifier.type,
        tenant_id=db_classifier.tenant_id,
        enabled=db_classifier.enabled,
        categories=db_classifier.categories,
        rules=db_classifier.rules,
        created_at=db_classifier.created_at,
        updated_at=db_classifier.updated_at
    )
