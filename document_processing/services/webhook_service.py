"""
Webhook service for event notifications.

Provides webhook subscription management and delivery with:
- Event-based subscriptions
- Retry logic with exponential backoff
- Signature verification
- Idempotency tracking
"""

import hashlib
import hmac
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from document_processing.models import WebhookDB, WebhookDeliveryDB


# Supported webhook events
WEBHOOK_EVENTS = [
    "parser_run.started",
    "parser_run.completed",
    "parser_run.failed",
    "file.uploaded",
    "file.deleted",
    "schema.created",
    "schema.updated",
    "schema.deleted",
]


async def create_webhook(
    session: AsyncSession,
    tenant_id: str,
    name: str,
    url: str,
    events: List[str],
    secret: Optional[str] = None,
    max_retries: int = 3,
    timeout_seconds: int = 30,
    metadata: Optional[Dict[str, Any]] = None
) -> WebhookDB:
    """
    Create a new webhook subscription.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        name: Webhook name
        url: Webhook endpoint URL
        events: List of event types to subscribe to
        secret: Optional secret for signature verification
        max_retries: Maximum delivery retry attempts
        timeout_seconds: Request timeout
        metadata: Additional metadata
        
    Returns:
        Created webhook
        
    Raises:
        ValueError: If invalid events specified
    """
    # Validate events
    invalid_events = [e for e in events if e not in WEBHOOK_EVENTS]
    if invalid_events:
        raise ValueError(f"Invalid events: {invalid_events}")
    
    # Generate webhook ID
    webhook_id = f"webhook_{uuid.uuid4().hex}"
    
    # Generate secret if not provided
    if not secret:
        secret = f"whsec_{uuid.uuid4().hex}"
    
    # Create webhook
    webhook = WebhookDB(
        id=webhook_id,
        tenant_id=tenant_id,
        name=name,
        url=url,
        events=events,
        enabled=True,
        secret=secret,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        webhook_metadata=metadata or {},
        is_deleted=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    session.add(webhook)
    await session.commit()
    await session.refresh(webhook)
    
    return webhook


async def get_webhook(
    session: AsyncSession,
    tenant_id: str,
    webhook_id: str
) -> Optional[WebhookDB]:
    """Get webhook by ID."""
    result = await session.execute(
        select(WebhookDB).where(
            WebhookDB.id == webhook_id,
            WebhookDB.tenant_id == tenant_id,
            WebhookDB.is_deleted == False
        )
    )
    
    return result.scalar_one_or_none()


async def list_webhooks(
    session: AsyncSession,
    tenant_id: str,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[WebhookDB], int]:
    """List webhooks for tenant with pagination."""
    # Get total count
    count_result = await session.execute(
        select(func.count(WebhookDB.id)).where(
            WebhookDB.tenant_id == tenant_id,
            WebhookDB.is_deleted == False
        )
    )
    total = count_result.scalar_one()
    
    # Get webhooks
    result = await session.execute(
        select(WebhookDB)
        .where(
            WebhookDB.tenant_id == tenant_id,
            WebhookDB.is_deleted == False
        )
        .order_by(WebhookDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    webhooks = result.scalars().all()
    
    return list(webhooks), total


async def update_webhook(
    session: AsyncSession,
    tenant_id: str,
    webhook_id: str,
    name: Optional[str] = None,
    url: Optional[str] = None,
    events: Optional[List[str]] = None,
    enabled: Optional[bool] = None,
    max_retries: Optional[int] = None,
    timeout_seconds: Optional[int] = None
) -> Optional[WebhookDB]:
    """Update webhook settings."""
    webhook = await get_webhook(session, tenant_id, webhook_id)
    
    if not webhook:
        return None
    
    if name is not None:
        webhook.name = name
    if url is not None:
        webhook.url = url
    if events is not None:
        # Validate events
        invalid_events = [e for e in events if e not in WEBHOOK_EVENTS]
        if invalid_events:
            raise ValueError(f"Invalid events: {invalid_events}")
        webhook.events = events
    if enabled is not None:
        webhook.enabled = enabled
    if max_retries is not None:
        webhook.max_retries = max_retries
    if timeout_seconds is not None:
        webhook.timeout_seconds = timeout_seconds
    
    webhook.updated_at = datetime.utcnow()
    
    await session.commit()
    await session.refresh(webhook)
    
    return webhook


async def delete_webhook(
    session: AsyncSession,
    tenant_id: str,
    webhook_id: str
) -> bool:
    """Soft delete webhook."""
    webhook = await get_webhook(session, tenant_id, webhook_id)
    
    if not webhook:
        return False
    
    webhook.is_deleted = True
    webhook.updated_at = datetime.utcnow()
    
    await session.commit()
    
    return True


def generate_signature(payload: bytes, secret: str) -> str:
    """Generate HMAC signature for webhook payload."""
    return hmac.new(
        secret.encode('utf-8'),
        payload,
        hashlib.sha256
    ).hexdigest()


async def trigger_webhook(
    session: AsyncSession,
    tenant_id: str,
    event_type: str,
    payload: Dict[str, Any]
) -> List[str]:
    """
    Trigger webhooks for an event.
    
    Creates delivery records for all subscribed webhooks.
    Actual delivery happens asynchronously.
    
    Args:
        session: Database session
        tenant_id: Tenant identifier
        event_type: Event type (e.g., 'parser_run.completed')
        payload: Event payload
        
    Returns:
        List of delivery IDs created
    """
    # Find subscribed webhooks
    result = await session.execute(
        select(WebhookDB).where(
            WebhookDB.tenant_id == tenant_id,
            WebhookDB.enabled == True,
            WebhookDB.is_deleted == False
        )
    )
    
    webhooks = result.scalars().all()
    
    # Filter webhooks subscribed to this event
    subscribed = [w for w in webhooks if event_type in w.events]
    
    delivery_ids = []
    
    for webhook in subscribed:
        # Create delivery record
        delivery_id = f"delivery_{uuid.uuid4().hex}"
        
        delivery = WebhookDeliveryDB(
            id=delivery_id,
            webhook_id=webhook.id,
            event_type=event_type,
            payload=payload,
            status="pending",
            attempt_count=0,
            scheduled_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        session.add(delivery)
        delivery_ids.append(delivery_id)
    
    await session.commit()
    
    return delivery_ids


async def deliver_webhook(
    session: AsyncSession,
    delivery_id: str,
    api_version: Optional[str] = None
) -> bool:
    """
    Attempt to deliver a webhook.
    
    Args:
        session: Database session
        delivery_id: Delivery record ID
        api_version: API version from request context (optional, for echo)
        
    Returns:
        True if delivered successfully, False otherwise
    """
    # Get delivery record
    delivery_result = await session.execute(
        select(WebhookDeliveryDB).where(
            WebhookDeliveryDB.id == delivery_id
        )
    )
    
    delivery = delivery_result.scalar_one_or_none()
    
    if not delivery:
        return False
    
    # Get webhook
    webhook_result = await session.execute(
        select(WebhookDB).where(
            WebhookDB.id == delivery.webhook_id
        )
    )
    
    webhook = webhook_result.scalar_one_or_none()
    
    if not webhook or not webhook.enabled:
        delivery.status = "failed"
        delivery.error_message = "Webhook not found or disabled"
        delivery.completed_at = datetime.utcnow()
        await session.commit()
        return False
    
    # Prepare payload
    import json
    payload_json = json.dumps(delivery.payload)
    payload_bytes = payload_json.encode('utf-8')
    
    # Generate signature
    signature = generate_signature(payload_bytes, webhook.secret)
    
    # Update attempt count
    delivery.attempt_count += 1
    delivery.attempted_at = datetime.utcnow()
    delivery.status = "retrying" if delivery.attempt_count < webhook.max_retries else "pending"
    
    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Event": delivery.event_type,
        "X-Webhook-Delivery": delivery.id,
        "X-Webhook-Timestamp": str(int(time.time()))
    }
    
    # Echo API version if provided (Extend parity)
    if api_version:
        headers["x-extend-api-version"] = api_version
    
    try:
        # Send webhook
        async with httpx.AsyncClient(timeout=webhook.timeout_seconds) as client:
            response = await client.post(
                webhook.url,
                content=payload_bytes,
                headers=headers
            )
            
            delivery.response_status_code = response.status_code
            delivery.response_body = response.text[:1000]  # Limit stored response
            
            if 200 <= response.status_code < 300:
                # Success
                delivery.status = "success"
                delivery.completed_at = datetime.utcnow()
                
                # Update webhook statistics
                webhook.last_triggered_at = datetime.utcnow()
                webhook.total_deliveries += 1
                webhook.successful_deliveries += 1
                
                await session.commit()
                return True
            else:
                # HTTP error
                delivery.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                
                if delivery.attempt_count >= webhook.max_retries:
                    delivery.status = "failed"
                    delivery.completed_at = datetime.utcnow()
                    webhook.failed_deliveries += 1
                else:
                    # Schedule retry with exponential backoff
                    delay_seconds = 2 ** delivery.attempt_count  # 2, 4, 8, 16...
                    delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
                    delivery.status = "retrying"
                
                await session.commit()
                return False
    
    except Exception as e:
        # Network or other error
        delivery.error_message = str(e)
        
        if delivery.attempt_count >= webhook.max_retries:
            delivery.status = "failed"
            delivery.completed_at = datetime.utcnow()
            webhook.total_deliveries += 1
            webhook.failed_deliveries += 1
        else:
            # Schedule retry
            delay_seconds = 2 ** delivery.attempt_count
            delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
            delivery.status = "retrying"
        
        await session.commit()
        return False


async def get_webhook_deliveries(
    session: AsyncSession,
    webhook_id: str,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[WebhookDeliveryDB], int]:
    """Get delivery history for a webhook."""
    # Get total count
    count_result = await session.execute(
        select(func.count(WebhookDeliveryDB.id)).where(
            WebhookDeliveryDB.webhook_id == webhook_id
        )
    )
    total = count_result.scalar_one()
    
    # Get deliveries
    result = await session.execute(
        select(WebhookDeliveryDB)
        .where(WebhookDeliveryDB.webhook_id == webhook_id)
        .order_by(WebhookDeliveryDB.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    
    deliveries = result.scalars().all()
    
    return list(deliveries), total
