"""
Webhook system for real-time notifications

This module provides a comprehensive webhook delivery system with retry logic,
subscription management, payload validation, and security features.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
import aiohttp
from pydantic import BaseModel, HttpUrl, validator
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

class WebhookEvent(str, Enum):
    """Webhook event types"""
    INCIDENT_CREATED = "incident.created"
    INCIDENT_UPDATED = "incident.updated"
    INCIDENT_ASSIGNED = "incident.assigned"
    INCIDENT_RESOLVED = "incident.resolved"
    INCIDENT_CLOSED = "incident.closed"
    ANALYSIS_COMPLETED = "analysis.completed"
    AUTOMATION_STARTED = "automation.started"
    AUTOMATION_COMPLETED = "automation.completed"
    AUTOMATION_FAILED = "automation.failed"

class WebhookStatus(str, Enum):
    """Webhook delivery status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    DISABLED = "disabled"

class WebhookSubscription(BaseModel):
    """Webhook subscription model"""
    id: str
    name: str
    url: HttpUrl
    events: List[WebhookEvent]
    secret: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    headers: Dict[str, str] = {}
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_backoff_seconds: int = 60
    
    @validator('events')
    def validate_events(cls, v):
        if not v:
            raise ValueError('At least one event must be specified')
        return v
    
    @validator('timeout_seconds')
    def validate_timeout(cls, v):
        if v < 1 or v > 300:
            raise ValueError('Timeout must be between 1 and 300 seconds')
        return v

class WebhookDelivery(BaseModel):
    """Webhook delivery record"""
    id: str
    subscription_id: str
    event_type: WebhookEvent
    payload: Dict[str, Any]
    status: WebhookStatus
    attempts: int = 0
    last_attempt_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

class WebhookPayload(BaseModel):
    """Standard webhook payload structure"""
    event: WebhookEvent
    timestamp: datetime
    data: Dict[str, Any]
    subscription_id: str
    delivery_id: str

@dataclass
class WebhookDeliveryResult:
    """Result of webhook delivery attempt"""
    success: bool
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: int = 0

class WebhookManager:
    """Webhook management system"""
    
    def __init__(self):
        self.subscriptions: Dict[str, WebhookSubscription] = {}
        self.deliveries: Dict[str, WebhookDelivery] = {}
        self.delivery_queue: asyncio.Queue = asyncio.Queue()
        self.retry_queue: asyncio.Queue = asyncio.Queue()
        self._delivery_task: Optional[asyncio.Task] = None
        self._retry_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start webhook delivery workers"""
        if self._running:
            return
        
        self._running = True
        self._delivery_task = asyncio.create_task(self._delivery_worker())
        self._retry_task = asyncio.create_task(self._retry_worker())
        logger.info("Webhook manager started")
    
    async def stop(self):
        """Stop webhook delivery workers"""
        if not self._running:
            return
        
        self._running = False
        
        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass
        
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Webhook manager stopped")
    
    def create_subscription(
        self,
        name: str,
        url: str,
        events: List[WebhookEvent],
        headers: Dict[str, str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3
    ) -> WebhookSubscription:
        """Create new webhook subscription"""
        subscription_id = secrets.token_urlsafe(16)
        secret = secrets.token_urlsafe(32)
        
        subscription = WebhookSubscription(
            id=subscription_id,
            name=name,
            url=url,
            events=events,
            secret=secret,
            headers=headers or {},
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        self.subscriptions[subscription_id] = subscription
        logger.info(f"Created webhook subscription: {name} ({subscription_id})")
        
        return subscription
    
    def get_subscription(self, subscription_id: str) -> Optional[WebhookSubscription]:
        """Get webhook subscription by ID"""
        return self.subscriptions.get(subscription_id)
    
    def list_subscriptions(self) -> List[WebhookSubscription]:
        """List all webhook subscriptions"""
        return list(self.subscriptions.values())
    
    def update_subscription(
        self,
        subscription_id: str,
        updates: Dict[str, Any]
    ) -> Optional[WebhookSubscription]:
        """Update webhook subscription"""
        subscription = self.subscriptions.get(subscription_id)
        if not subscription:
            return None
        
        # Update allowed fields
        allowed_fields = {
            'name', 'url', 'events', 'is_active', 'headers',
            'timeout_seconds', 'max_retries', 'retry_backoff_seconds'
        }
        
        for field, value in updates.items():
            if field in allowed_fields and hasattr(subscription, field):
                setattr(subscription, field, value)
        
        subscription.updated_at = datetime.utcnow()
        logger.info(f"Updated webhook subscription: {subscription_id}")
        
        return subscription
    
    def delete_subscription(self, subscription_id: str) -> bool:
        """Delete webhook subscription"""
        if subscription_id in self.subscriptions:
            del self.subscriptions[subscription_id]
            logger.info(f"Deleted webhook subscription: {subscription_id}")
            return True
        return False
    
    async def send_webhook(
        self,
        event: WebhookEvent,
        data: Dict[str, Any],
        subscription_ids: Optional[List[str]] = None
    ) -> List[str]:
        """Send webhook to subscribed endpoints"""
        delivery_ids = []
        
        # Get relevant subscriptions
        if subscription_ids:
            subscriptions = [
                sub for sub in self.subscriptions.values()
                if sub.id in subscription_ids and sub.is_active and event in sub.events
            ]
        else:
            subscriptions = [
                sub for sub in self.subscriptions.values()
                if sub.is_active and event in sub.events
            ]
        
        # Create deliveries
        for subscription in subscriptions:
            delivery_id = secrets.token_urlsafe(16)
            
            delivery = WebhookDelivery(
                id=delivery_id,
                subscription_id=subscription.id,
                event_type=event,
                payload=data,
                status=WebhookStatus.PENDING,
                created_at=datetime.utcnow()
            )
            
            self.deliveries[delivery_id] = delivery
            await self.delivery_queue.put(delivery_id)
            delivery_ids.append(delivery_id)
        
        logger.info(f"Queued {len(delivery_ids)} webhook deliveries for event: {event}")
        return delivery_ids
    
    async def _delivery_worker(self):
        """Worker to process webhook deliveries"""
        while self._running:
            try:
                # Wait for delivery with timeout
                delivery_id = await asyncio.wait_for(
                    self.delivery_queue.get(),
                    timeout=1.0
                )
                
                delivery = self.deliveries.get(delivery_id)
                if not delivery:
                    continue
                
                subscription = self.subscriptions.get(delivery.subscription_id)
                if not subscription or not subscription.is_active:
                    delivery.status = WebhookStatus.DISABLED
                    continue
                
                # Attempt delivery
                result = await self._deliver_webhook(subscription, delivery)
                
                # Update delivery record
                delivery.attempts += 1
                delivery.last_attempt_at = datetime.utcnow()
                delivery.response_status = result.status_code
                delivery.response_body = result.response_body
                delivery.error_message = result.error_message
                
                if result.success:
                    delivery.status = WebhookStatus.DELIVERED
                    logger.info(f"Webhook delivered successfully: {delivery_id}")
                else:
                    # Schedule retry if attempts remaining
                    if delivery.attempts < subscription.max_retries:
                        retry_delay = subscription.retry_backoff_seconds * (2 ** (delivery.attempts - 1))
                        delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=retry_delay)
                        await self.retry_queue.put(delivery_id)
                        logger.warning(f"Webhook delivery failed, scheduled retry: {delivery_id}")
                    else:
                        delivery.status = WebhookStatus.FAILED
                        logger.error(f"Webhook delivery failed permanently: {delivery_id}")
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in webhook delivery worker: {str(e)}")
    
    async def _retry_worker(self):
        """Worker to process webhook retries"""
        while self._running:
            try:
                # Wait for retry with timeout
                delivery_id = await asyncio.wait_for(
                    self.retry_queue.get(),
                    timeout=5.0
                )
                
                delivery = self.deliveries.get(delivery_id)
                if not delivery or not delivery.next_retry_at:
                    continue
                
                # Check if it's time to retry
                if datetime.utcnow() < delivery.next_retry_at:
                    # Put back in queue for later
                    await asyncio.sleep(1)
                    await self.retry_queue.put(delivery_id)
                    continue
                
                # Add back to delivery queue
                await self.delivery_queue.put(delivery_id)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in webhook retry worker: {str(e)}")
    
    async def _deliver_webhook(
        self,
        subscription: WebhookSubscription,
        delivery: WebhookDelivery
    ) -> WebhookDeliveryResult:
        """Deliver webhook to endpoint"""
        start_time = datetime.utcnow()
        
        try:
            # Create payload
            payload = WebhookPayload(
                event=delivery.event_type,
                timestamp=delivery.created_at,
                data=delivery.payload,
                subscription_id=subscription.id,
                delivery_id=delivery.id
            )
            
            payload_json = json.dumps(payload.dict(), default=str)
            
            # Create signature
            signature = self._create_signature(payload_json, subscription.secret)
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
                "X-Webhook-Event": delivery.event_type,
                "X-Webhook-Delivery": delivery.id,
                "User-Agent": "IncidentManagement-Webhook/1.0"
            }
            headers.update(subscription.headers)
            
            # Make HTTP request
            timeout = aiohttp.ClientTimeout(total=subscription.timeout_seconds)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    str(subscription.url),
                    data=payload_json,
                    headers=headers
                ) as response:
                    response_body = await response.text()
                    
                    duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                    
                    if 200 <= response.status < 300:
                        return WebhookDeliveryResult(
                            success=True,
                            status_code=response.status,
                            response_body=response_body[:1000],  # Limit response body size
                            duration_ms=int(duration)
                        )
                    else:
                        return WebhookDeliveryResult(
                            success=False,
                            status_code=response.status,
                            response_body=response_body[:1000],
                            error_message=f"HTTP {response.status}",
                            duration_ms=int(duration)
                        )
        
        except asyncio.TimeoutError:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            return WebhookDeliveryResult(
                success=False,
                error_message="Request timeout",
                duration_ms=int(duration)
            )
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds() * 1000
            return WebhookDeliveryResult(
                success=False,
                error_message=str(e),
                duration_ms=int(duration)
            )
    
    def _create_signature(self, payload: str, secret: str) -> str:
        """Create HMAC signature for webhook payload"""
        signature = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def verify_signature(self, payload: str, signature: str, secret: str) -> bool:
        """Verify webhook signature"""
        expected_signature = self._create_signature(payload, secret)
        return hmac.compare_digest(signature, expected_signature)
    
    def get_delivery(self, delivery_id: str) -> Optional[WebhookDelivery]:
        """Get webhook delivery by ID"""
        return self.deliveries.get(delivery_id)
    
    def list_deliveries(
        self,
        subscription_id: Optional[str] = None,
        status: Optional[WebhookStatus] = None,
        limit: int = 100
    ) -> List[WebhookDelivery]:
        """List webhook deliveries with filtering"""
        deliveries = list(self.deliveries.values())
        
        if subscription_id:
            deliveries = [d for d in deliveries if d.subscription_id == subscription_id]
        
        if status:
            deliveries = [d for d in deliveries if d.status == status]
        
        # Sort by creation time (newest first)
        deliveries.sort(key=lambda d: d.created_at, reverse=True)
        
        return deliveries[:limit]
    
    def get_delivery_stats(self, subscription_id: Optional[str] = None) -> Dict[str, Any]:
        """Get webhook delivery statistics"""
        deliveries = list(self.deliveries.values())
        
        if subscription_id:
            deliveries = [d for d in deliveries if d.subscription_id == subscription_id]
        
        total = len(deliveries)
        if total == 0:
            return {
                "total": 0,
                "delivered": 0,
                "failed": 0,
                "pending": 0,
                "success_rate": 0.0
            }
        
        delivered = len([d for d in deliveries if d.status == WebhookStatus.DELIVERED])
        failed = len([d for d in deliveries if d.status == WebhookStatus.FAILED])
        pending = len([d for d in deliveries if d.status == WebhookStatus.PENDING])
        
        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "pending": pending,
            "success_rate": (delivered / total) * 100 if total > 0 else 0.0
        }

# Global webhook manager instance
webhook_manager = WebhookManager()