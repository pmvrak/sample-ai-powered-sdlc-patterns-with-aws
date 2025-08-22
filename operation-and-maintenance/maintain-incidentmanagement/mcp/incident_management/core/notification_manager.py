"""
Multi-channel notification manager for incident management.

This module provides comprehensive notification capabilities with support for
multiple channels, fallback mechanisms, and templated messages.
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional, Set, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json

from models.incident import Incident, IncidentSeverity, IncidentStatus
from interfaces.base import BaseNotificationManager
from utils.formatters import format_incident_message, format_timestamp

logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Available notification channels"""
    SLACK = "slack"
    TEAMS = "teams"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    CONSOLE = "console"  # Fallback console logging


class NotificationPriority(Enum):
    """Notification priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationStatus(Enum):
    """Notification delivery status"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class NotificationTemplate:
    """Template for notification messages"""
    name: str
    title_template: str
    body_template: str
    channel_specific: Dict[str, Dict[str, str]] = field(default_factory=dict)
    required_fields: List[str] = field(default_factory=list)
    priority: NotificationPriority = NotificationPriority.NORMAL
    
    def render(self, context: Dict[str, Any], channel: NotificationChannel) -> Dict[str, str]:
        """Render template with context data"""
        # Use channel-specific template if available
        if channel.value in self.channel_specific:
            channel_template = self.channel_specific[channel.value]
            title = channel_template.get("title", self.title_template)
            body = channel_template.get("body", self.body_template)
        else:
            title = self.title_template
            body = self.body_template
        
        # Simple template rendering (replace {key} with values)
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            title = title.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))
        
        return {"title": title, "body": body}


@dataclass
class NotificationConfig:
    """Configuration for notification channels"""
    channel: NotificationChannel
    enabled: bool = True
    priority_threshold: NotificationPriority = NotificationPriority.LOW
    retry_attempts: int = 3
    retry_delay: timedelta = field(default_factory=lambda: timedelta(seconds=30))
    timeout: timedelta = field(default_factory=lambda: timedelta(seconds=30))
    rate_limit: Optional[int] = None  # Max notifications per minute
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationRequest:
    """Request to send a notification"""
    id: str
    incident: Incident
    channels: List[NotificationChannel]
    template_name: str
    context: Dict[str, Any] = field(default_factory=dict)
    priority: NotificationPriority = NotificationPriority.NORMAL
    created_at: datetime = field(default_factory=datetime.utcnow)
    attempts: int = 0
    status: NotificationStatus = NotificationStatus.PENDING
    error_message: Optional[str] = None
    delivered_channels: Set[NotificationChannel] = field(default_factory=set)
    failed_channels: Set[NotificationChannel] = field(default_factory=set)


class NotificationManager(BaseNotificationManager):
    """
    Multi-channel notification manager with fallback support.
    
    Features:
    - Multiple notification channels (Slack, Teams, Email, SMS, Webhook)
    - Template-based message formatting
    - Automatic fallback when primary channels fail
    - Rate limiting and retry mechanisms
    - Priority-based routing
    - Delivery tracking and reporting
    """
    
    def __init__(self):
        self.templates: Dict[str, NotificationTemplate] = {}
        self.channel_configs: Dict[NotificationChannel, NotificationConfig] = {}
        self.channel_handlers: Dict[NotificationChannel, Callable] = {}
        self.pending_notifications: Dict[str, NotificationRequest] = {}
        self.rate_limiters: Dict[NotificationChannel, List[datetime]] = {}
        
        # Initialize default templates and configurations
        self._initialize_default_templates()
        self._initialize_default_configs()
        self._initialize_channel_handlers()
    
    def _initialize_default_templates(self) -> None:
        """Initialize default notification templates"""
        
        # Incident created template
        self.templates["incident_created"] = NotificationTemplate(
            name="incident_created",
            title_template="🚨 New Incident: {incident_title}",
            body_template="A new {severity} severity incident has been detected.\n\n"
                         "**Title:** {incident_title}\n"
                         "**ID:** {incident_id}\n"
                         "**Severity:** {severity}\n"
                         "**Affected Systems:** {affected_systems}\n"
                         "**Created:** {created_at}\n\n"
                         "Please investigate and respond accordingly.",
            channel_specific={
                "slack": {
                    "title": "🚨 New Incident Detected",
                    "body": "<!channel> A new *{severity}* severity incident requires attention:\n\n"
                           "*{incident_title}*\n"
                           "• ID: `{incident_id}`\n"
                           "• Severity: {severity_emoji} {severity}\n"
                           "• Systems: {affected_systems}\n"
                           "• Created: {created_at}\n\n"
                           "React with ✋ to take ownership or use `/incident assign {incident_id}` to assign."
                },
                "teams": {
                    "title": "🚨 New Incident: {incident_title}",
                    "body": "**New {severity} severity incident detected**\n\n"
                           "**{incident_title}**\n\n"
                           "- **ID:** {incident_id}\n"
                           "- **Severity:** {severity}\n"
                           "- **Affected Systems:** {affected_systems}\n"
                           "- **Created:** {created_at}\n\n"
                           "Please investigate and respond accordingly."
                }
            },
            priority=NotificationPriority.HIGH
        )
        
        # Incident assigned template
        self.templates["incident_assigned"] = NotificationTemplate(
            name="incident_assigned",
            title_template="👤 Incident Assigned: {incident_title}",
            body_template="Incident {incident_id} has been assigned.\n\n"
                         "**Assigned to:** {assigned_team}"
                         "{assigned_user_info}\n"
                         "**Title:** {incident_title}\n"
                         "**Severity:** {severity}\n"
                         "**Status:** {status}\n\n"
                         "Please begin investigation and provide updates.",
            channel_specific={
                "slack": {
                    "body": "👤 Incident assignment update:\n\n"
                           "*{incident_title}*\n"
                           "• Assigned to: *{assigned_team}*{assigned_user_info}\n"
                           "• Severity: {severity_emoji} {severity}\n"
                           "• Status: {status}\n"
                           "• ID: `{incident_id}`\n\n"
                           "Use `/incident status {incident_id}` for details."
                }
            },
            priority=NotificationPriority.NORMAL
        )
        
        # Incident escalated template
        self.templates["incident_escalated"] = NotificationTemplate(
            name="incident_escalated",
            title_template="⚠️ Incident Escalated: {incident_title}",
            body_template="Incident {incident_id} has been escalated.\n\n"
                         "**Reason:** {escalation_reason}\n"
                         "**From:** {original_team}\n"
                         "**To:** {escalated_team}\n"
                         "**Title:** {incident_title}\n"
                         "**Severity:** {severity}\n"
                         "**Duration:** {incident_duration}\n\n"
                         "Immediate attention required.",
            priority=NotificationPriority.URGENT
        )
        
        # Incident resolved template
        self.templates["incident_resolved"] = NotificationTemplate(
            name="incident_resolved",
            title_template="✅ Incident Resolved: {incident_title}",
            body_template="Incident {incident_id} has been resolved.\n\n"
                         "**Resolved by:** {resolved_by}\n"
                         "**Resolution:** {resolution_summary}\n"
                         "**Duration:** {incident_duration}\n"
                         "**Title:** {incident_title}\n\n"
                         "Thank you for your response.",
            priority=NotificationPriority.LOW
        )
        
        # Team overload warning template
        self.templates["team_overload"] = NotificationTemplate(
            name="team_overload",
            title_template="⚠️ Team Capacity Warning: {team_name}",
            body_template="Team {team_name} is approaching capacity limits.\n\n"
                         "**Current Load:** {current_incidents}/{max_capacity}\n"
                         "**Available Members:** {available_members}\n"
                         "**Load Percentage:** {load_percentage}%\n\n"
                         "Consider load balancing or escalation for new incidents.",
            priority=NotificationPriority.HIGH
        )
    
    def _initialize_default_configs(self) -> None:
        """Initialize default channel configurations"""
        
        # Slack configuration
        self.channel_configs[NotificationChannel.SLACK] = NotificationConfig(
            channel=NotificationChannel.SLACK,
            enabled=True,
            priority_threshold=NotificationPriority.LOW,
            retry_attempts=3,
            retry_delay=timedelta(seconds=30),
            timeout=timedelta(seconds=15),
            rate_limit=60,  # 60 messages per minute
            config={
                "webhook_url": None,  # To be configured
                "default_channel": "#incidents",
                "mention_channel": True,
                "thread_replies": True
            }
        )
        
        # Teams configuration
        self.channel_configs[NotificationChannel.TEAMS] = NotificationConfig(
            channel=NotificationChannel.TEAMS,
            enabled=True,
            priority_threshold=NotificationPriority.LOW,
            retry_attempts=3,
            retry_delay=timedelta(seconds=30),
            timeout=timedelta(seconds=15),
            rate_limit=60,
            config={
                "webhook_url": None,  # To be configured
                "default_channel": "Incidents",
                "mention_channel": True
            }
        )
        
        # Email configuration
        self.channel_configs[NotificationChannel.EMAIL] = NotificationConfig(
            channel=NotificationChannel.EMAIL,
            enabled=False,  # Disabled by default
            priority_threshold=NotificationPriority.HIGH,
            retry_attempts=2,
            retry_delay=timedelta(minutes=1),
            timeout=timedelta(seconds=30),
            rate_limit=30,
            config={
                "smtp_server": None,
                "smtp_port": 587,
                "username": None,
                "password": None,
                "from_address": "incidents@company.com",
                "default_recipients": []
            }
        )
        
        # Console fallback (always enabled)
        self.channel_configs[NotificationChannel.CONSOLE] = NotificationConfig(
            channel=NotificationChannel.CONSOLE,
            enabled=True,
            priority_threshold=NotificationPriority.LOW,
            retry_attempts=1,
            retry_delay=timedelta(seconds=1),
            timeout=timedelta(seconds=1),
            config={}
        )
    
    def _initialize_channel_handlers(self) -> None:
        """Initialize channel-specific handlers"""
        self.channel_handlers = {
            NotificationChannel.SLACK: self._send_slack_notification,
            NotificationChannel.TEAMS: self._send_teams_notification,
            NotificationChannel.EMAIL: self._send_email_notification,
            NotificationChannel.SMS: self._send_sms_notification,
            NotificationChannel.WEBHOOK: self._send_webhook_notification,
            NotificationChannel.CONSOLE: self._send_console_notification
        }
    
    async def send_notification(self, incident: Incident, channels: List[str], 
                              message_type: str = "incident_created") -> bool:
        """
        Send notification about incident to specified channels.
        
        Args:
            incident: The incident to notify about
            channels: List of channel names to send to
            message_type: Type of notification template to use
        
        Returns:
            True if at least one notification was sent successfully
        """
        try:
            # Convert string channels to enum
            notification_channels = []
            for channel_str in channels:
                try:
                    channel = NotificationChannel(channel_str.lower())
                    notification_channels.append(channel)
                except ValueError:
                    logger.warning(f"Unknown notification channel: {channel_str}")
            
            if not notification_channels:
                logger.error("No valid notification channels specified")
                return False
            
            # Create notification request
            request_id = f"notif_{incident.id}_{int(datetime.utcnow().timestamp())}"
            context = self._build_notification_context(incident)
            
            # Determine priority based on incident severity
            priority = self._get_priority_for_incident(incident)
            
            notification_request = NotificationRequest(
                id=request_id,
                incident=incident,
                channels=notification_channels,
                template_name=message_type,
                context=context,
                priority=priority
            )
            
            # Store request for tracking
            self.pending_notifications[request_id] = notification_request
            
            # Send notifications
            success = await self._process_notification_request(notification_request)
            
            # Clean up completed request
            if request_id in self.pending_notifications:
                del self.pending_notifications[request_id]
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending notification for incident {incident.id}: {str(e)}")
            return False
    
    async def send_custom_message(self, channel: str, message: str, 
                                metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Send custom message to a specific channel.
        
        Args:
            channel: Channel name to send to
            message: Message content
            metadata: Optional metadata for the message
        
        Returns:
            True if message was sent successfully
        """
        try:
            channel_enum = NotificationChannel(channel.lower())
            
            if not self._is_channel_enabled(channel_enum):
                logger.warning(f"Channel {channel} is not enabled")
                return False
            
            handler = self.channel_handlers.get(channel_enum)
            if not handler:
                logger.error(f"No handler found for channel {channel}")
                return False
            
            # Create simple message context
            context = {
                "title": "Custom Message",
                "body": message,
                "timestamp": format_timestamp(datetime.utcnow())
            }
            
            if metadata:
                context.update(metadata)
            
            return await handler(context, channel_enum)
            
        except Exception as e:
            logger.error(f"Error sending custom message to {channel}: {str(e)}")
            return False
    
    async def handle_user_response(self, user_id: str, channel: str, 
                                 response: str) -> Dict[str, Any]:
        """
        Handle user response from notification.
        
        Args:
            user_id: ID of the responding user
            channel: Channel where response was received
            response: User's response content
        
        Returns:
            Dictionary with response handling results
        """
        try:
            # Parse response for commands or actions
            response_lower = response.lower().strip()
            
            result = {
                "user_id": user_id,
                "channel": channel,
                "response": response,
                "timestamp": datetime.utcnow().isoformat(),
                "action_taken": None,
                "success": False
            }
            
            # Handle common response patterns
            if "take" in response_lower or "assign me" in response_lower:
                result["action_taken"] = "assignment_request"
                result["success"] = True
                logger.info(f"User {user_id} requested assignment via {channel}")
            
            elif "escalate" in response_lower:
                result["action_taken"] = "escalation_request"
                result["success"] = True
                logger.info(f"User {user_id} requested escalation via {channel}")
            
            elif "resolve" in response_lower or "fixed" in response_lower:
                result["action_taken"] = "resolution_report"
                result["success"] = True
                logger.info(f"User {user_id} reported resolution via {channel}")
            
            else:
                result["action_taken"] = "general_response"
                result["success"] = True
                logger.info(f"General response from user {user_id} via {channel}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error handling user response: {str(e)}")
            return {
                "user_id": user_id,
                "channel": channel,
                "response": response,
                "error": str(e),
                "success": False
            }
    
    async def get_available_channels(self) -> List[str]:
        """
        Get list of available and enabled notification channels.
        
        Returns:
            List of available channel names
        """
        available = []
        for channel, config in self.channel_configs.items():
            if config.enabled:
                available.append(channel.value)
        return available    

    def add_template(self, template: NotificationTemplate) -> None:
        """Add or update a notification template"""
        self.templates[template.name] = template
        logger.info(f"Added notification template: {template.name}")
    
    def configure_channel(self, channel: NotificationChannel, config: NotificationConfig) -> None:
        """Configure a notification channel"""
        self.channel_configs[channel] = config
        logger.info(f"Configured notification channel: {channel.value}")
    
    def enable_channel(self, channel: NotificationChannel) -> None:
        """Enable a notification channel"""
        if channel in self.channel_configs:
            self.channel_configs[channel].enabled = True
            logger.info(f"Enabled notification channel: {channel.value}")
    
    def disable_channel(self, channel: NotificationChannel) -> None:
        """Disable a notification channel"""
        if channel in self.channel_configs:
            self.channel_configs[channel].enabled = False
            logger.info(f"Disabled notification channel: {channel.value}")
    
    def get_notification_stats(self) -> Dict[str, Any]:
        """Get notification delivery statistics"""
        return {
            "total_templates": len(self.templates),
            "enabled_channels": len([c for c in self.channel_configs.values() if c.enabled]),
            "pending_notifications": len(self.pending_notifications),
            "channel_configs": {
                channel.value: {
                    "enabled": config.enabled,
                    "retry_attempts": config.retry_attempts,
                    "rate_limit": config.rate_limit
                }
                for channel, config in self.channel_configs.items()
            }
        }
    
    # Private helper methods
    
    def _build_notification_context(self, incident: Incident) -> Dict[str, Any]:
        """Build context dictionary for template rendering"""
        severity_emojis = {
            IncidentSeverity.CRITICAL: "🔴",
            IncidentSeverity.HIGH: "🟠",
            IncidentSeverity.MEDIUM: "🟡",
            IncidentSeverity.LOW: "🟢"
        }
        
        context = {
            "incident_id": incident.id,
            "incident_title": incident.title,
            "incident_description": incident.description,
            "severity": incident.severity.value.title(),
            "severity_emoji": severity_emojis.get(incident.severity, "⚪"),
            "status": incident.status.value.title(),
            "affected_systems": ", ".join(incident.affected_systems) if incident.affected_systems else "None",
            "tags": ", ".join(incident.tags) if incident.tags else "None",
            "created_at": format_timestamp(incident.created_at),
            "assigned_team": incident.assigned_team or "Unassigned",
            "assigned_user": incident.assigned_user or "",
            "assigned_user_info": f" ({incident.assigned_user})" if incident.assigned_user else ""
        }
        
        # Add duration if incident is resolved
        if incident.resolved_at:
            duration = incident.resolved_at - incident.created_at
            context["incident_duration"] = self._format_duration(duration)
        
        return context
    
    def _get_priority_for_incident(self, incident: Incident) -> NotificationPriority:
        """Determine notification priority based on incident severity"""
        priority_map = {
            IncidentSeverity.CRITICAL: NotificationPriority.URGENT,
            IncidentSeverity.HIGH: NotificationPriority.HIGH,
            IncidentSeverity.MEDIUM: NotificationPriority.NORMAL,
            IncidentSeverity.LOW: NotificationPriority.LOW
        }
        return priority_map.get(incident.severity, NotificationPriority.NORMAL)
    
    def _is_channel_enabled(self, channel: NotificationChannel) -> bool:
        """Check if a channel is enabled and configured"""
        config = self.channel_configs.get(channel)
        return config is not None and config.enabled
    
    def _should_send_to_channel(self, channel: NotificationChannel, priority: NotificationPriority) -> bool:
        """Check if notification should be sent to channel based on priority"""
        config = self.channel_configs.get(channel)
        if not config or not config.enabled:
            return False
        
        priority_levels = [NotificationPriority.LOW, NotificationPriority.NORMAL, 
                          NotificationPriority.HIGH, NotificationPriority.URGENT]
        
        channel_threshold = priority_levels.index(config.priority_threshold)
        notification_priority = priority_levels.index(priority)
        
        return notification_priority >= channel_threshold
    
    def _check_rate_limit(self, channel: NotificationChannel) -> bool:
        """Check if channel is within rate limits"""
        config = self.channel_configs.get(channel)
        if not config or not config.rate_limit:
            return True
        
        now = datetime.utcnow()
        minute_ago = now - timedelta(minutes=1)
        
        # Initialize rate limiter for channel if not exists
        if channel not in self.rate_limiters:
            self.rate_limiters[channel] = []
        
        # Clean old entries
        self.rate_limiters[channel] = [
            timestamp for timestamp in self.rate_limiters[channel]
            if timestamp > minute_ago
        ]
        
        # Check if under limit
        if len(self.rate_limiters[channel]) < config.rate_limit:
            self.rate_limiters[channel].append(now)
            return True
        
        return False
    
    async def _process_notification_request(self, request: NotificationRequest) -> bool:
        """Process a notification request across all channels"""
        template = self.templates.get(request.template_name)
        if not template:
            logger.error(f"Template not found: {request.template_name}")
            return False
        
        success_count = 0
        total_channels = len(request.channels)
        
        # Try each channel
        for channel in request.channels:
            try:
                if not self._should_send_to_channel(channel, request.priority):
                    logger.debug(f"Skipping channel {channel.value} due to priority threshold")
                    continue
                
                if not self._check_rate_limit(channel):
                    logger.warning(f"Rate limit exceeded for channel {channel.value}")
                    request.failed_channels.add(channel)
                    continue
                
                # Render template for this channel
                rendered = template.render(request.context, channel)
                
                # Send notification
                handler = self.channel_handlers.get(channel)
                if handler:
                    success = await handler(rendered, channel)
                    if success:
                        request.delivered_channels.add(channel)
                        success_count += 1
                        logger.info(f"Notification sent successfully via {channel.value}")
                    else:
                        request.failed_channels.add(channel)
                        logger.warning(f"Failed to send notification via {channel.value}")
                else:
                    logger.error(f"No handler found for channel {channel.value}")
                    request.failed_channels.add(channel)
                
            except Exception as e:
                logger.error(f"Error sending notification via {channel.value}: {str(e)}")
                request.failed_channels.add(channel)
        
        # Update request status
        if success_count > 0:
            request.status = NotificationStatus.DELIVERED
        elif request.failed_channels:
            request.status = NotificationStatus.FAILED
            # Try fallback if all primary channels failed
            if success_count == 0:
                await self._try_fallback_notification(request, template)
        
        return success_count > 0
    
    async def _try_fallback_notification(self, request: NotificationRequest, 
                                       template: NotificationTemplate) -> bool:
        """Try fallback notification methods when primary channels fail"""
        logger.info(f"Attempting fallback notification for request {request.id}")
        
        # Always try console as last resort
        if NotificationChannel.CONSOLE not in request.failed_channels:
            try:
                rendered = template.render(request.context, NotificationChannel.CONSOLE)
                success = await self._send_console_notification(rendered, NotificationChannel.CONSOLE)
                if success:
                    request.delivered_channels.add(NotificationChannel.CONSOLE)
                    logger.info("Fallback console notification sent successfully")
                    return True
            except Exception as e:
                logger.error(f"Fallback console notification failed: {str(e)}")
        
        return False
    
    def _format_duration(self, duration: timedelta) -> str:
        """Format duration for display"""
        total_seconds = int(duration.total_seconds())
        
        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes}m"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
        else:
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            return f"{days}d {hours}h" if hours > 0 else f"{days}d"
    
    # Channel-specific handlers
    
    async def _send_slack_notification(self, message: Dict[str, str], 
                                     channel: NotificationChannel) -> bool:
        """Send notification via Slack"""
        try:
            config = self.channel_configs[channel].config
            webhook_url = config.get("webhook_url")
            
            if not webhook_url:
                logger.error("Slack webhook URL not configured")
                return False
            
            # For now, just log the message (actual Slack integration would go here)
            logger.info(f"[SLACK] {message['title']}")
            logger.info(f"[SLACK] {message['body']}")
            
            # TODO: Implement actual Slack webhook call
            # payload = {
            #     "text": message['title'],
            #     "attachments": [{
            #         "text": message['body'],
            #         "color": "warning"
            #     }]
            # }
            # async with aiohttp.ClientSession() as session:
            #     async with session.post(webhook_url, json=payload) as response:
            #         return response.status == 200
            
            return True  # Simulate success for now
            
        except Exception as e:
            logger.error(f"Slack notification error: {str(e)}")
            return False
    
    async def _send_teams_notification(self, message: Dict[str, str], 
                                     channel: NotificationChannel) -> bool:
        """Send notification via Microsoft Teams"""
        try:
            config = self.channel_configs[channel].config
            webhook_url = config.get("webhook_url")
            
            if not webhook_url:
                logger.error("Teams webhook URL not configured")
                return False
            
            # For now, just log the message (actual Teams integration would go here)
            logger.info(f"[TEAMS] {message['title']}")
            logger.info(f"[TEAMS] {message['body']}")
            
            # TODO: Implement actual Teams webhook call
            return True  # Simulate success for now
            
        except Exception as e:
            logger.error(f"Teams notification error: {str(e)}")
            return False
    
    async def _send_email_notification(self, message: Dict[str, str], 
                                     channel: NotificationChannel) -> bool:
        """Send notification via Email"""
        try:
            config = self.channel_configs[channel].config
            
            # For now, just log the message (actual email integration would go here)
            logger.info(f"[EMAIL] Subject: {message['title']}")
            logger.info(f"[EMAIL] Body: {message['body']}")
            
            # TODO: Implement actual SMTP email sending
            return True  # Simulate success for now
            
        except Exception as e:
            logger.error(f"Email notification error: {str(e)}")
            return False
    
    async def _send_sms_notification(self, message: Dict[str, str], 
                                   channel: NotificationChannel) -> bool:
        """Send notification via SMS"""
        try:
            # For now, just log the message (actual SMS integration would go here)
            logger.info(f"[SMS] {message['title']}: {message['body'][:100]}...")
            
            # TODO: Implement actual SMS sending (Twilio, AWS SNS, etc.)
            return True  # Simulate success for now
            
        except Exception as e:
            logger.error(f"SMS notification error: {str(e)}")
            return False
    
    async def _send_webhook_notification(self, message: Dict[str, str], 
                                       channel: NotificationChannel) -> bool:
        """Send notification via generic webhook"""
        try:
            # For now, just log the message (actual webhook integration would go here)
            logger.info(f"[WEBHOOK] {message['title']}")
            logger.info(f"[WEBHOOK] {message['body']}")
            
            # TODO: Implement actual webhook call
            return True  # Simulate success for now
            
        except Exception as e:
            logger.error(f"Webhook notification error: {str(e)}")
            return False
    
    async def _send_console_notification(self, message: Dict[str, str], 
                                       channel: NotificationChannel) -> bool:
        """Send notification to console (fallback method)"""
        try:
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"[CONSOLE NOTIFICATION] {timestamp}")
            logger.info(f"Title: {message['title']}")
            logger.info(f"Body: {message['body']}")
            logger.info("-" * 50)
            return True
            
        except Exception as e:
            logger.error(f"Console notification error: {str(e)}")
            return False


# Utility functions for notification management

def create_incident_notification_context(incident: Incident, 
                                        additional_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create notification context for an incident"""
    manager = NotificationManager()
    context = manager._build_notification_context(incident)
    
    if additional_context:
        context.update(additional_context)
    
    return context


def get_default_channels_for_severity(severity: IncidentSeverity) -> List[str]:
    """Get default notification channels based on incident severity"""
    if severity == IncidentSeverity.CRITICAL:
        return ["slack", "teams", "email", "sms"]
    elif severity == IncidentSeverity.HIGH:
        return ["slack", "teams", "email"]
    elif severity == IncidentSeverity.MEDIUM:
        return ["slack", "teams"]
    else:
        return ["slack"]