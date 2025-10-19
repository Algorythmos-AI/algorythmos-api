"""Schema service for managing extraction schemas."""

from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ExtractionSchemaDB
from ..schemas import (
    CreateSchemaRequest,
    ExtractionSchema,
    FieldDefinition,
    SchemaListResponse,
    UpdateSchemaRequest,
)


class SchemaService:
    """Service for managing extraction schemas."""
    
    @staticmethod
    async def create_schema(
        session: AsyncSession,
        tenant_id: str,
        request: CreateSchemaRequest,
    ) -> ExtractionSchema:
        """Create a new extraction schema."""
        
        # Generate unique schema ID
        schema_id = f"{tenant_id}_{request.name.lower().replace(' ', '_')}_{int(time.time())}"
        
        # Check for duplicate name within tenant (excluding soft-deleted)
        stmt = select(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.tenant_id == tenant_id,
                ExtractionSchemaDB.name == request.name,
                ExtractionSchemaDB.is_deleted == False
            )
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"Schema with name '{request.name}' already exists for this tenant")
        
        # Convert FieldDefinition objects to dicts for JSON storage
        fields_data = [field.model_dump() for field in request.fields]
        
        # Create database record
        db_schema = ExtractionSchemaDB(
            id=schema_id,
            tenant_id=tenant_id,
            name=request.name,
            description=request.description,
            fields=fields_data,
            version=1,
            schema_metadata=request.metadata or {},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        session.add(db_schema)
        await session.commit()
        await session.refresh(db_schema)
        
        # Convert back to Pydantic model
        return SchemaService._db_to_pydantic(db_schema)
    
    @staticmethod
    async def get_schema(
        session: AsyncSession,
        tenant_id: str,
        schema_id: str,
    ) -> Optional[ExtractionSchema]:
        """Get a schema by ID (excluding soft-deleted)."""
        
        stmt = select(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.id == schema_id,
                ExtractionSchemaDB.tenant_id == tenant_id,
                ExtractionSchemaDB.is_deleted == False
            )
        )
        result = await session.execute(stmt)
        db_schema = result.scalar_one_or_none()
        
        if not db_schema:
            return None
        
        return SchemaService._db_to_pydantic(db_schema)
    
    @staticmethod
    async def list_schemas(
        session: AsyncSession,
        tenant_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> Tuple[List[ExtractionSchema], int]:
        """List schemas for a tenant with offset-based pagination."""
        
        # Build base query (excluding soft-deleted)
        stmt = select(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.tenant_id == tenant_id,
                ExtractionSchemaDB.is_deleted == False
            )
        )
        
        # Order by created_at descending (newest first)
        stmt = stmt.order_by(ExtractionSchemaDB.created_at.desc()).limit(limit).offset(offset)
        
        result = await session.execute(stmt)
        db_schemas = result.scalars().all()
        
        # Get total count (excluding soft-deleted)
        count_stmt = select(func.count()).select_from(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.tenant_id == tenant_id,
                ExtractionSchemaDB.is_deleted == False
            )
        )
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()
        
        # Convert to Pydantic models
        items = [SchemaService._db_to_pydantic(db_schema) for db_schema in db_schemas]
        
        return items, total
    
    @staticmethod
    async def update_schema(
        session: AsyncSession,
        tenant_id: str,
        schema_id: str,
        request: UpdateSchemaRequest,
    ) -> Optional[ExtractionSchema]:
        """Update an existing schema."""
        
        # Get existing schema (excluding soft-deleted)
        stmt = select(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.id == schema_id,
                ExtractionSchemaDB.tenant_id == tenant_id,
                ExtractionSchemaDB.is_deleted == False
            )
        )
        result = await session.execute(stmt)
        db_schema = result.scalar_one_or_none()
        
        if not db_schema:
            return None
        
        # Update fields
        if request.name is not None:
            # Check for duplicate name (excluding soft-deleted and current schema)
            stmt = select(ExtractionSchemaDB).where(
                and_(
                    ExtractionSchemaDB.tenant_id == tenant_id,
                    ExtractionSchemaDB.name == request.name,
                    ExtractionSchemaDB.id != schema_id,
                    ExtractionSchemaDB.is_deleted == False
                )
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                raise ValueError(f"Schema with name '{request.name}' already exists for this tenant")
            db_schema.name = request.name
        
        if request.description is not None:
            db_schema.description = request.description
        
        if request.fields is not None:
            db_schema.fields = [field.model_dump() for field in request.fields]
            # Increment version when fields change
            db_schema.version += 1
        
        if request.metadata is not None:
            db_schema.schema_metadata = request.metadata
        
        db_schema.updated_at = datetime.utcnow()
        
        await session.commit()
        await session.refresh(db_schema)
        
        return SchemaService._db_to_pydantic(db_schema)
    
    @staticmethod
    async def delete_schema(
        session: AsyncSession,
        tenant_id: str,
        schema_id: str,
    ) -> bool:
        """Soft-delete a schema."""
        
        stmt = select(ExtractionSchemaDB).where(
            and_(
                ExtractionSchemaDB.id == schema_id,
                ExtractionSchemaDB.tenant_id == tenant_id,
                ExtractionSchemaDB.is_deleted == False
            )
        )
        result = await session.execute(stmt)
        db_schema = result.scalar_one_or_none()
        
        if not db_schema:
            return False
        
        # Soft delete
        db_schema.is_deleted = True
        db_schema.updated_at = datetime.utcnow()
        
        await session.commit()
        
        return True
    
    @staticmethod
    def _db_to_pydantic(db_schema: ExtractionSchemaDB) -> ExtractionSchema:
        """Convert database model to Pydantic model."""
        
        # Convert field dicts back to FieldDefinition objects
        fields = [FieldDefinition(**field_data) for field_data in db_schema.fields]
        
        return ExtractionSchema(
            schema_id=db_schema.id,
            name=db_schema.name,
            description=db_schema.description,
            fields=fields,
            version=db_schema.version,
            tenant_id=db_schema.tenant_id,
            created_at=db_schema.created_at,
            updated_at=db_schema.updated_at,
            metadata=db_schema.schema_metadata,
        )
