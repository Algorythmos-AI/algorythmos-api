"""Service for managing file uploads and storage."""

import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import UploadFile, HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import FileDB
from document_processing.schemas import FileUpload
from document_processing.services.format_validator import format_validator, FormatValidationError


# Storage configuration
# Use /tmp in serverless environments (Vercel, Lambda), otherwise local 'files' dir
def _get_upload_dir() -> Path:
    """Get upload directory, using /tmp in serverless environments."""
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return Path("/tmp/files")
    return Path("files")


UPLOAD_DIR = _get_upload_dir()


def _ensure_upload_dir() -> None:
    """Lazily create upload directory when needed (avoid read-only fs errors at import time)."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def _calculate_checksum(content: bytes) -> str:
    """Calculate SHA-256 checksum of file content."""
    return hashlib.sha256(content).hexdigest()


async def _save_file_to_disk(file_id: str, content: bytes, filename: str) -> str:
    """
    Save file content to disk.
    
    Returns:
        Storage path relative to UPLOAD_DIR
    """
    # Ensure upload directory exists (lazy creation for serverless compatibility)
    _ensure_upload_dir()
    
    # Create subdirectory based on first 2 chars of file_id for better distribution
    subdir = UPLOAD_DIR / file_id[:2]
    subdir.mkdir(parents=True, exist_ok=True)
    
    # Store with file_id as name, preserving extension
    ext = Path(filename).suffix
    storage_filename = f"{file_id}{ext}"
    storage_path = subdir / storage_filename
    
    # Write file
    with open(storage_path, "wb") as f:
        f.write(content)
    
    # Return relative path
    return str(storage_path.relative_to(UPLOAD_DIR))


async def upload_file(
    session: AsyncSession,
    tenant_id: str,
    file: UploadFile,
    metadata: Optional[Dict[str, Any]] = None
) -> FileUpload:
    """
    Upload a file and store metadata in database.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        file: Uploaded file
        metadata: Additional metadata
        
    Returns:
        FileUpload with file information
        
    Raises:
        HTTPException: If file format is unsupported or invalid
    """
    # Read file content
    content = await file.read()
    size_bytes = len(content)
    
    # Validate and normalize format (Sprint 2 - P1.1)
    try:
        normalized_type, mime_type, format_metadata = format_validator.validate_and_normalize(
            content=content,
            filename=file.filename or "unknown",
            declared_content_type=file.content_type
        )
    except FormatValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "UNSUPPORTED_FORMAT",
                "message": str(e),
                "supported_formats": format_validator.get_supported_formats()
            }
        )
    
    # Calculate checksum
    checksum = await _calculate_checksum(content)
    
    # Generate file ID
    file_id = f"file_{uuid.uuid4().hex}"
    
    # Save to disk
    storage_path = await _save_file_to_disk(file_id, content, file.filename or "unknown")
    
    # Merge format metadata with user metadata
    combined_metadata = {
        **(metadata or {}),
        "format_info": format_metadata,
        "normalized_type": normalized_type
    }
    
    # Create database record with normalized MIME type
    file_db = FileDB(
        id=file_id,
        tenant_id=tenant_id,
        filename=file.filename or "unknown",
        content_type=mime_type,  # Use normalized MIME type
        size_bytes=size_bytes,
        storage_path=storage_path,
        checksum=checksum,
        file_metadata=combined_metadata,
        is_deleted=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    session.add(file_db)
    await session.commit()
    await session.refresh(file_db)
    
    return FileUpload(
        file_id=file_db.id,
        filename=file_db.filename,
        content_type=file_db.content_type,
        size_bytes=file_db.size_bytes,
        checksum=file_db.checksum,
        tenant_id=file_db.tenant_id,
        created_at=file_db.created_at,
        metadata=file_db.file_metadata
    )


async def get_file(
    session: AsyncSession,
    tenant_id: str,
    file_id: str
) -> Optional[FileDB]:
    """
    Retrieve file metadata by ID.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        file_id: File identifier
        
    Returns:
        FileDB if found, None otherwise
    """
    result = await session.execute(
        select(FileDB).where(
            FileDB.id == file_id,
            FileDB.tenant_id == tenant_id,
            FileDB.is_deleted == False
        )
    )
    
    return result.scalar_one_or_none()


async def get_file_content(file_db: FileDB) -> bytes:
    """
    Read file content from disk.
    
    Args:
        file_db: File database record
        
    Returns:
        File content as bytes
        
    Raises:
        FileNotFoundError: If file doesn't exist on disk
    """
    file_path = UPLOAD_DIR / file_db.storage_path
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found on disk: {file_path}")
    
    with open(file_path, "rb") as f:
        return f.read()


async def list_files(
    session: AsyncSession,
    tenant_id: str,
    limit: int = 50,
    offset: int = 0
) -> Tuple[list[FileUpload], int]:
    """
    List files for a tenant with pagination.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        limit: Maximum number of results
        offset: Number of results to skip
        
    Returns:
        Tuple of (list of FileUpload, total count)
    """
    # Get total count
    count_result = await session.execute(
        select(func.count(FileDB.id)).where(
            FileDB.tenant_id == tenant_id,
            FileDB.is_deleted == False
        )
    )
    total = count_result.scalar_one()
    
    # Get files
    result = await session.execute(
        select(FileDB)
        .where(
            FileDB.tenant_id == tenant_id,
            FileDB.is_deleted == False
        )
        .order_by(FileDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    files = result.scalars().all()
    
    file_uploads = [
        FileUpload(
            file_id=f.id,
            filename=f.filename,
            content_type=f.content_type,
            size_bytes=f.size_bytes,
            checksum=f.checksum,
            tenant_id=f.tenant_id,
            created_at=f.created_at,
            metadata=f.file_metadata
        )
        for f in files
    ]
    
    return file_uploads, total


async def delete_file(
    session: AsyncSession,
    tenant_id: str,
    file_id: str
) -> bool:
    """
    Soft delete a file.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        file_id: File identifier
        
    Returns:
        True if deleted, False if not found
    """
    result = await session.execute(
        select(FileDB).where(
            FileDB.id == file_id,
            FileDB.tenant_id == tenant_id,
            FileDB.is_deleted == False
        )
    )
    
    file_db = result.scalar_one_or_none()
    
    if not file_db:
        return False
    
    file_db.is_deleted = True
    file_db.updated_at = datetime.utcnow()
    
    await session.commit()
    
    return True
