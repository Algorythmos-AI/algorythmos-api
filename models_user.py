"""User model for identity persistence.

This module defines the User model for storing human user identities
authenticated via Google OAuth. This is identity persistence only -
not sessions, not RBAC, not API key handling.

Future compatibility notes:
- API keys can be owned by users via a separate api_keys table
- Workspaces can be linked via junction table
- Enterprise SSO (SAML/OIDC) can use the provider field
- RBAC can be added as separate tables referencing users
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.sql import func

from database import Base


class UserDB(Base):
    """Database model for human users (identity persistence only).
    
    Schema follows the minimal safe design:
    - email as unique identifier
    - provider for auth source (currently "google")
    - provider_account_id for provider-specific unique ID
    - is_active for soft-disable capability
    - timestamps for audit trail
    
    Does NOT include:
    - Roles or permissions (future RBAC)
    - Organization/workspace relationships
    - Session data or tokens
    """
    
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)  # UUID
    email = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    provider = Column(String(50), nullable=False, default="google")  # Auth provider
    provider_account_id = Column(String(255), nullable=True, index=True)  # Google 'sub' claim
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    # Tenant this user acts for; assigned on first sign-in (core/tenancy.py).
    tenant_id = Column(String(255), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, provider={self.provider})>"
