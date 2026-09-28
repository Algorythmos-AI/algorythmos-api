"""API Key model for programmatic authentication.

This module defines the ApiKey model for storing hashed API keys
that can be used for programmatic access to the API.

Security notes:
- Raw keys are NEVER stored - only SHA-256 hashes
- Keys are shown to users exactly once (on creation)
- Prefix is stored for display purposes only (first 8 chars)
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Index
from sqlalchemy.sql import func

from database import Base


class ApiKeyDB(Base):
    """Database model for API keys.
    
    Schema:
    - id: UUID primary key
    - user_id: Foreign key to users table
    - name: User-defined name for the key ("Production", "Development")
    - key_hash: SHA-256 hash of the full key
    - prefix: First 8 chars after 'alg_' for display (e.g., "dGhpc19p")
    - created_at: When the key was created
    - last_used_at: Last time the key was used (nullable)
    - is_active: Soft delete flag
    """
    
    __tablename__ = "api_keys"
    
    id = Column(String, primary_key=True)  # UUID
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True, index=True)  # SHA-256 = 64 hex chars
    prefix = Column(String(12), nullable=False)  # "alg_" + first 8 chars
    # Tenant this key acts for, copied from its user when the key is created.
    tenant_id = Column(String(255), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    
    # Soft delete
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Composite index for efficient lookups
    __table_args__ = (
        Index("ix_api_keys_user_active", "user_id", "is_active"),
    )
    
    def __repr__(self) -> str:
        return f"<ApiKey(id={self.id}, user_id={self.user_id}, name={self.name}, prefix={self.prefix})>"
