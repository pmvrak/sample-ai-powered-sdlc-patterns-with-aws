"""
Slack bot integration for incident management.

This module provides comprehensive Slack integration including:
- Rich incident notifications with action buttons
- Real-time status updates
- Interactive components for incident management
- Slash command support
"""

import logging
import asyncio
import json
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from dataclasses import dataclass
import os

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.signature import SignatureVerifier

from models.incident import Incident, IncidentSeverity, IncidentStatus
from utils.formatters import format_timestamp, format_incident_message
from utils.validators import validate_user_permissions

logger = logging.getLogger(__name__)


@dataclass
class SlackMessage:
    """Represents a Slack message with rich formatting"""
    channel: str
    text: str
    blocks: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    thread_ts: Optional[str] = None
    user: Optional[str] = None


@dataclass
class SlackInteraction:
    """Represents a Slack interaction (button click, modal submission, etc.)"""
    type: str
    user_id: str
    channel_id: str
    trigger_id: Optional[str] = None
    action_id: Optional[str] = None
    value: Optional[str] = None
    response_url: Optional[str] = None


class SlackBot:
    """
    Slack bot for incident management with rich interactive features.
    
    Features:
    - Rich incident notifications with action buttons
    - Real-time incident status updates
    - Interactive modals for complex operations
    - Slash command processing
    - Thread-based conversations
    - User permission validation
    """
    
    def __init__(self, bot_token: str, signing_secret: str):
        """
        Initialize Slack bot.
        
        Args:
            bot_token: Slack bot token (starts with xoxb-)
            signing_secret: Slack signing secret for request verification
        """
        self.client = AsyncWebClient(token=bot_token)
        self.signing_secret = signing_secret
        self.signature_verifier = SignatureVerifier(signing_secret)
        
        # Callback handlers for different events
        self.incident_handlers: Dict[str, Callable] = {}
        self.command_handlers: Dict[str, Callable] = {}
        self.interaction_handlers: Dict[str, Callable] = {}
        
        # Message tracking for updates
        self.incident_messages: Dict[str, Dict[str, str]] = {}  # incident_id -> {channel: ts}
        
        # Initialize default handlers
        self._initialize_handlers()
    
    def _initialize_handlers(self) -> None:
        """Initialize default event handlers"""
        # Default interaction handlers
        self.interaction_handlers = {
            "assign_incident": self._handle_assign_incident,
            "escalate_incident": self._handle_escalate_incident,
            "resolve_incident": self._handle_resolve_incident,
            "view_incident_details": self._handle_view_incident_details,
            "add_incident_note": self._handle_add_incident_note,
            # Quick action handlers
            "quick_assign_self": self._handle_quick_assign_self,
            "quick_add_note": self._handle_quick_add_note,
            "quick_escalate": self._handle_escalate_incident,
            "quick_resolve": self._handle_resolve_incident,
            "refresh_incident": self._handle_refresh_incident,
            # Additional interactive handlers
            "refresh_timeline": self._handle_refresh_timeline,
            "generate_report": self._handle_generate_report,
            "view_detailed_metrics": self._handle_view_detailed_metrics,
            "export_metrics": self._handle_export_metrics
        }
    
    # Additional interaction handlers
    
    async def _handle_refresh_timeline(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                     user_id: str) -> Dict[str, Any]:
        """Handle timeline refresh request"""
        incident_id = action.get("value")
        logger.info(f"Timeline refresh request: incident={incident_id}, user={user_id}")
        
        return {
            "response_action": "update",
            "text": f"🔄 Timeline refreshed for incident `{incident_id}`"
        }
    
    async def _handle_generate_report(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                    user_id: str) -> Dict[str, Any]:
        """Handle report generation request"""
        incident_id = action.get("value")
        logger.info(f"Report generation request: incident={incident_id}, user={user_id}")
        
        return {
            "response_action": "update",
            "text": f"📊 Generating report for incident `{incident_id}`..."
        }
    
    async def _handle_view_detailed_metrics(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                          user_id: str) -> Dict[str, Any]:
        """Handle detailed metrics view request"""
        timeframe = action.get("selected_option", {}).get("value", "24h")
        logger.info(f"Detailed metrics request: timeframe={timeframe}, user={user_id}")
        
        return {
            "response_action": "update",
            "text": f"📈 Loading detailed metrics for {timeframe}..."
        }
    
    async def _handle_export_metrics(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                   user_id: str) -> Dict[str, Any]:
        """Handle metrics export request"""
        export_type = action.get("value", "current")
        logger.info(f"Metrics export request: type={export_type}, user={user_id}")
        
        return {
            "response_action": "update",
            "text": f"📤 Exporting metrics report..."
        }
    
    async def send_incident_notification(self, incident: Incident, 
                                       channels: List[str]) -> Dict[str, bool]:
        """
        Send rich incident notification to Slack channels.
        
        Args:
            incident: Incident to notify about
            channels: List of channel names/IDs to send to
        
        Returns:
            Dictionary mapping channel to success status
        """
        results = {}
        
        for channel in channels:
            try:
                # Build rich message blocks
                blocks = self._build_incident_blocks(incident)
                
                # Send message
                response = await self.client.chat_postMessage(
                    channel=channel,
                    text=f"🚨 New Incident: {incident.title}",
                    blocks=blocks,
                    unfurl_links=False,
                    unfurl_media=False
                )
                
                if response["ok"]:
                    # Store message info for future updates
                    if incident.id not in self.incident_messages:
                        self.incident_messages[incident.id] = {}
                    self.incident_messages[incident.id][channel] = response["ts"]
                    
                    results[channel] = True
                    logger.info(f"Incident notification sent to {channel} for {incident.id}")
                else:
                    results[channel] = False
                    logger.error(f"Failed to send notification to {channel}: {response.get('error')}")
                
            except SlackApiError as e:
                results[channel] = False
                logger.error(f"Slack API error sending to {channel}: {e.response['error']}")
            except Exception as e:
                results[channel] = False
                logger.error(f"Unexpected error sending to {channel}: {str(e)}")
        
        return results
    
    async def update_incident_message(self, incident: Incident) -> Dict[str, bool]:
        """
        Update existing incident messages with current status.
        
        Args:
            incident: Updated incident
        
        Returns:
            Dictionary mapping channel to update success status
        """
        results = {}
        
        if incident.id not in self.incident_messages:
            logger.warning(f"No tracked messages found for incident {incident.id}")
            return results
        
        for channel, ts in self.incident_messages[incident.id].items():
            try:
                # Build updated message blocks
                blocks = self._build_incident_blocks(incident, is_update=True)
                
                # Update message
                response = await self.client.chat_update(
                    channel=channel,
                    ts=ts,
                    text=f"📋 Incident Update: {incident.title}",
                    blocks=blocks
                )
                
                if response["ok"]:
                    results[channel] = True
                    logger.info(f"Updated incident message in {channel} for {incident.id}")
                else:
                    results[channel] = False
                    logger.error(f"Failed to update message in {channel}: {response.get('error')}")
                
            except SlackApiError as e:
                results[channel] = False
                logger.error(f"Slack API error updating {channel}: {e.response['error']}")
            except Exception as e:
                results[channel] = False
                logger.error(f"Unexpected error updating {channel}: {str(e)}")
        
        return results
    
    async def send_thread_update(self, incident: Incident, message: str, 
                               channel: Optional[str] = None) -> bool:
        """
        Send update message in incident thread.
        
        Args:
            incident: Incident to update
            message: Update message
            channel: Specific channel (if None, updates all channels)
        
        Returns:
            True if at least one update was sent successfully
        """
        if incident.id not in self.incident_messages:
            logger.warning(f"No tracked messages found for incident {incident.id}")
            return False
        
        success_count = 0
        channels_to_update = [channel] if channel else list(self.incident_messages[incident.id].keys())
        
        for ch in channels_to_update:
            if ch not in self.incident_messages[incident.id]:
                continue
                
            try:
                ts = self.incident_messages[incident.id][ch]
                
                response = await self.client.chat_postMessage(
                    channel=ch,
                    thread_ts=ts,
                    text=message,
                    unfurl_links=False
                )
                
                if response["ok"]:
                    success_count += 1
                    logger.info(f"Thread update sent to {ch} for {incident.id}")
                
            except Exception as e:
                logger.error(f"Error sending thread update to {ch}: {str(e)}")
        
        return success_count > 0
    
    async def handle_slash_command(self, command: str, text: str, user_id: str, 
                                 channel_id: str, response_url: str) -> Dict[str, Any]:
        """
        Handle Slack slash commands.
        
        Args:
            command: The slash command (e.g., "/incident")
            text: Command arguments
            user_id: User who executed the command
            channel_id: Channel where command was executed
            response_url: URL for delayed responses
        
        Returns:
            Response dictionary for Slack
        """
        try:
            # Parse command and arguments
            args = text.strip().split() if text else []
            
            if not args:
                return self._build_help_response()
            
            subcommand = args[0].lower()
            
            # Route to appropriate handler
            if subcommand == "status":
                return await self._handle_status_command(args[1:], user_id, channel_id)
            elif subcommand == "assign":
                return await self._handle_assign_command(args[1:], user_id, channel_id)
            elif subcommand == "resolve":
                return await self._handle_resolve_command(args[1:], user_id, channel_id)
            elif subcommand == "list":
                return await self._handle_list_command(args[1:], user_id, channel_id)
            elif subcommand == "help":
                return self._build_help_response()
            else:
                return {
                    "response_type": "ephemeral",
                    "text": f"Unknown command: {subcommand}. Use `/incident help` for available commands."
                }
                
        except Exception as e:
            logger.error(f"Error handling slash command: {str(e)}")
            return {
                "response_type": "ephemeral",
                "text": "An error occurred processing your command. Please try again."
            }
    
    async def handle_interaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Slack interactive components (buttons, modals, etc.).
        
        Args:
            payload: Slack interaction payload
        
        Returns:
            Response dictionary for Slack
        """
        try:
            interaction_type = payload.get("type")
            user_id = payload.get("user", {}).get("id")
            
            if interaction_type == "block_actions":
                return await self._handle_block_actions(payload)
            elif interaction_type == "view_submission":
                return await self._handle_modal_submission(payload)
            elif interaction_type == "view_closed":
                return await self._handle_modal_closed(payload)
            else:
                logger.warning(f"Unhandled interaction type: {interaction_type}")
                return {"response_action": "clear"}
                
        except Exception as e:
            logger.error(f"Error handling interaction: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "An error occurred processing your request."}
            }
    
    def register_incident_handler(self, event_type: str, handler: Callable) -> None:
        """Register handler for incident events"""
        self.incident_handlers[event_type] = handler
    
    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register handler for slash commands"""
        self.command_handlers[command] = handler
    
    def register_interaction_handler(self, action_id: str, handler: Callable) -> None:
        """Register handler for interactive components"""
        self.interaction_handlers[action_id] = handler
    
    # Private helper methods
    
    def _build_incident_blocks(self, incident: Incident, is_update: bool = False) -> List[Dict[str, Any]]:
        """Build Slack blocks for incident notification"""
        severity_colors = {
            IncidentSeverity.CRITICAL: "#FF0000",
            IncidentSeverity.HIGH: "#FF8C00",
            IncidentSeverity.MEDIUM: "#FFD700",
            IncidentSeverity.LOW: "#32CD32"
        }
        
        severity_emojis = {
            IncidentSeverity.CRITICAL: "🔴",
            IncidentSeverity.HIGH: "🟠",
            IncidentSeverity.MEDIUM: "🟡",
            IncidentSeverity.LOW: "🟢"
        }
        
        status_emojis = {
            IncidentStatus.DETECTED: "🆕",
            IncidentStatus.ASSIGNED: "👤",
            IncidentStatus.IN_PROGRESS: "⚙️",
            IncidentStatus.RESOLVED: "✅",
            IncidentStatus.CLOSED: "🔒"
        }
        
        # Header block
        header_text = "📋 Incident Update" if is_update else "🚨 New Incident Detected"
        if not is_update and incident.severity in [IncidentSeverity.CRITICAL, IncidentSeverity.HIGH]:
            header_text += " <!channel>"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": header_text
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{incident.title}*\n{incident.description[:200]}{'...' if len(incident.description) > 200 else ''}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*ID:*\n`{incident.id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity_emojis.get(incident.severity, '⚪')} {incident.severity.value.title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:*\n{status_emojis.get(incident.status, '❓')} {incident.status.value.replace('_', ' ').title()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Created:*\n{format_timestamp(incident.created_at)}"
                    }
                ]
            }
        ]
        
        # Assignment info
        if incident.assigned_team or incident.assigned_user:
            assignment_text = f"*Team:* {incident.assigned_team or 'Unassigned'}"
            if incident.assigned_user:
                assignment_text += f"\n*User:* <@{incident.assigned_user}>"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": assignment_text
                }
            })
        
        # Affected systems
        if incident.affected_systems:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Affected Systems:*\n{', '.join(incident.affected_systems)}"
                }
            })
        
        # Action buttons (only for active incidents)
        if incident.status not in [IncidentStatus.RESOLVED, IncidentStatus.CLOSED]:
            action_elements = []
            
            if incident.status == IncidentStatus.DETECTED:
                action_elements.extend([
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🙋 Take Ownership"
                        },
                        "style": "primary",
                        "action_id": "assign_incident",
                        "value": incident.id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📋 View Details"
                        },
                        "action_id": "view_incident_details",
                        "value": incident.id
                    }
                ])
            
            if incident.status in [IncidentStatus.ASSIGNED, IncidentStatus.IN_PROGRESS]:
                action_elements.extend([
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Mark Resolved"
                        },
                        "style": "primary",
                        "action_id": "resolve_incident",
                        "value": incident.id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "⚠️ Escalate"
                        },
                        "style": "danger",
                        "action_id": "escalate_incident",
                        "value": incident.id
                    }
                ])
            
            # Add note button (always available)
            action_elements.append({
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "📝 Add Note"
                },
                "action_id": "add_incident_note",
                "value": incident.id
            })
            
            if action_elements:
                blocks.append({
                    "type": "actions",
                    "elements": action_elements
                })
        
        # Divider
        blocks.append({"type": "divider"})
        
        return blocks
    
    def _build_help_response(self) -> Dict[str, Any]:
        """Build help response for slash commands"""
        help_text = """
*Incident Management Commands:*

• `/incident status <incident_id>` - Show incident details
• `/incident assign <incident_id> [team] [user]` - Assign incident
• `/incident resolve <incident_id> [resolution]` - Mark incident as resolved
• `/incident list [status] [team]` - List incidents
• `/incident help` - Show this help message

*Examples:*
• `/incident status INC-20240123-ABC123`
• `/incident assign INC-20240123-ABC123 devops @john`
• `/incident resolve INC-20240123-ABC123 Fixed database connection`
• `/incident list open devops`
        """
        
        return {
            "response_type": "ephemeral",
            "text": help_text.strip()
        }
    
    async def _handle_status_command(self, args: List[str], user_id: str, 
                                   channel_id: str) -> Dict[str, Any]:
        """Handle incident status command"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please provide an incident ID. Usage: `/incident status <incident_id>`"
            }
        
        incident_id = args[0]
        
        # This would typically call the incident management system
        # For now, return a placeholder response
        return {
            "response_type": "ephemeral",
            "text": f"Fetching status for incident `{incident_id}`...\n_This feature requires integration with the incident management system._"
        }
    
    async def _handle_assign_command(self, args: List[str], user_id: str, 
                                   channel_id: str) -> Dict[str, Any]:
        """Handle incident assignment command"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please provide an incident ID. Usage: `/incident assign <incident_id> [team] [user]`"
            }
        
        incident_id = args[0]
        team = args[1] if len(args) > 1 else None
        user = args[2] if len(args) > 2 else None
        
        # This would typically call the incident management system
        assignment_text = f"Assigning incident `{incident_id}`"
        if team:
            assignment_text += f" to team `{team}`"
        if user:
            assignment_text += f" and user `{user}`"
        
        return {
            "response_type": "ephemeral",
            "text": f"{assignment_text}...\n_This feature requires integration with the incident management system._"
        }
    
    async def _handle_resolve_command(self, args: List[str], user_id: str, 
                                    channel_id: str) -> Dict[str, Any]:
        """Handle incident resolution command"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please provide an incident ID. Usage: `/incident resolve <incident_id> [resolution]`"
            }
        
        incident_id = args[0]
        resolution = " ".join(args[1:]) if len(args) > 1 else "Resolved via Slack command"
        
        return {
            "response_type": "ephemeral",
            "text": f"Resolving incident `{incident_id}` with resolution: '{resolution}'...\n_This feature requires integration with the incident management system._"
        }
    
    async def _handle_list_command(self, args: List[str], user_id: str, 
                                 channel_id: str) -> Dict[str, Any]:
        """Handle incident list command"""
        status_filter = args[0] if args else "open"
        team_filter = args[1] if len(args) > 1 else None
        
        filter_text = f"status: `{status_filter}`"
        if team_filter:
            filter_text += f", team: `{team_filter}`"
        
        return {
            "response_type": "ephemeral",
            "text": f"Listing incidents with {filter_text}...\n_This feature requires integration with the incident management system._"
        }
    
    async def _handle_block_actions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle block action interactions (button clicks)"""
        actions = payload.get("actions", [])
        if not actions:
            return {"response_action": "clear"}
        
        action = actions[0]
        action_id = action.get("action_id")
        value = action.get("value")
        user_id = payload.get("user", {}).get("id")
        
        # Route to appropriate handler
        handler = self.interaction_handlers.get(action_id)
        if handler:
            return await handler(payload, action, user_id)
        else:
            logger.warning(f"No handler found for action: {action_id}")
            return {"response_action": "clear"}
    
    async def _handle_modal_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle modal form submissions"""
        view = payload.get("view", {})
        callback_id = view.get("callback_id")
        
        # Extract form values
        values = view.get("state", {}).get("values", {})
        
        # Route based on callback_id
        if callback_id == "incident_resolution_modal":
            return await self._handle_resolution_modal(payload, values)
        elif callback_id == "incident_assignment_modal":
            return await self._handle_assignment_modal(payload, values)
        elif callback_id == "incident_note_modal":
            return await self._handle_note_modal(payload, values)
        elif callback_id == "incident_escalation_modal":
            return await self._handle_escalation_modal(payload, values)
        elif callback_id == "quick_note_modal":
            return await self._handle_quick_note_modal(payload, values)
        elif callback_id.startswith("confirm_"):
            return await self._handle_confirmation_modal(payload, values, callback_id)
        else:
            logger.warning(f"Unknown modal callback_id: {callback_id}")
            return {"response_action": "clear"}
    
    async def _handle_quick_note_modal(self, payload: Dict[str, Any], 
                                     values: Dict[str, Any]) -> Dict[str, Any]:
        """Handle quick note modal submission"""
        try:
            incident_id = values.get("incident_id", {}).get("incident_id_input", {}).get("value", "")
            update_type = values.get("update_type", {}).get("type_select", {}).get("selected_option", {}).get("value", "")
            update_text = values.get("update_text", {}).get("text_input", {}).get("value", "")
            
            # This would typically call the incident management system
            logger.info(f"Quick note request: incident={incident_id}, type={update_type}, text={update_text}")
            
            return {"response_action": "clear"}
            
        except Exception as e:
            logger.error(f"Error processing quick note modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to add update."}
            }
    
    async def _handle_confirmation_modal(self, payload: Dict[str, Any], 
                                       values: Dict[str, Any], callback_id: str) -> Dict[str, Any]:
        """Handle confirmation modal submissions"""
        try:
            action = callback_id.replace("confirm_", "")
            incident_id = values.get("incident_id", {}).get("incident_id_input", {}).get("value", "")
            
            # This would typically call the incident management system
            logger.info(f"Confirmed action: {action} for incident={incident_id}")
            
            return {"response_action": "clear"}
            
        except Exception as e:
            logger.error(f"Error processing confirmation modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to process confirmation."}
            }
    
    async def _handle_modal_closed(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle modal close events"""
        return {"response_action": "clear"}
    
    # Default interaction handlers
    
    async def _handle_assign_incident(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                    user_id: str) -> Dict[str, Any]:
        """Handle incident assignment button click"""
        incident_id = action.get("value")
        
        # Enhanced assignment modal with team selection and priority options
        modal = {
            "type": "modal",
            "callback_id": "incident_assignment_modal",
            "title": {
                "type": "plain_text",
                "text": "Assign Incident"
            },
            "submit": {
                "type": "plain_text",
                "text": "Assign"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Assigning Incident:* `{incident_id}`"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "input",
                    "block_id": "incident_id",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "incident_id_input",
                        "initial_value": incident_id
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Incident ID"
                    }
                },
                {
                    "type": "input",
                    "block_id": "team",
                    "element": {
                        "type": "static_select",
                        "action_id": "team_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select team"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "DevOps"
                                },
                                "value": "devops"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Platform Engineering"
                                },
                                "value": "platform"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Security"
                                },
                                "value": "security"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Database Team"
                                },
                                "value": "database"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Network Team"
                                },
                                "value": "network"
                            }
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Team"
                    }
                },
                {
                    "type": "input",
                    "block_id": "assignee",
                    "element": {
                        "type": "users_select",
                        "action_id": "assignee_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select specific user (optional)"
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Specific Assignee"
                    },
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "priority",
                    "element": {
                        "type": "static_select",
                        "action_id": "priority_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Set priority (optional)"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "🔴 Critical"
                                },
                                "value": "critical"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "🟠 High"
                                },
                                "value": "high"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "🟡 Medium"
                                },
                                "value": "medium"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "🟢 Low"
                                },
                                "value": "low"
                            }
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Update Priority"
                    },
                    "optional": True
                },
                {
                    "type": "input",
                    "block_id": "notes",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Add assignment notes (optional)"
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Assignment Notes"
                    },
                    "optional": True
                }
            ]
        }
        
        try:
            trigger_id = payload.get("trigger_id")
            await self.client.views_open(trigger_id=trigger_id, view=modal)
            return {"response_action": "clear"}
        except Exception as e:
            logger.error(f"Error opening assignment modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to open assignment form."}
            }
    
    async def _handle_escalate_incident(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                      user_id: str) -> Dict[str, Any]:
        """Handle incident escalation button click"""
        incident_id = action.get("value")
        
        # Enhanced escalation modal with confirmation and reason selection
        modal = {
            "type": "modal",
            "callback_id": "incident_escalation_modal",
            "title": {
                "type": "plain_text",
                "text": "Escalate Incident"
            },
            "submit": {
                "type": "plain_text",
                "text": "Escalate"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚠️ *Escalating Incident:* `{incident_id}`\n\nThis will notify senior staff and escalate the incident priority."
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "input",
                    "block_id": "incident_id",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "incident_id_input",
                        "initial_value": incident_id
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Incident ID"
                    }
                },
                {
                    "type": "input",
                    "block_id": "escalation_reason",
                    "element": {
                        "type": "static_select",
                        "action_id": "reason_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select escalation reason"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "No response from assigned team"
                                },
                                "value": "no_response"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Incident severity increased"
                                },
                                "value": "severity_increase"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Customer impact detected"
                                },
                                "value": "customer_impact"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "SLA breach imminent"
                                },
                                "value": "sla_breach"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Requires additional expertise"
                                },
                                "value": "need_expertise"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Other (specify in notes)"
                                },
                                "value": "other"
                            }
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Escalation Reason"
                    }
                },
                {
                    "type": "input",
                    "block_id": "escalation_target",
                    "element": {
                        "type": "static_select",
                        "action_id": "target_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select escalation target"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Team Lead"
                                },
                                "value": "team_lead"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Engineering Manager"
                                },
                                "value": "eng_manager"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "On-Call Manager"
                                },
                                "value": "oncall_manager"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Incident Commander"
                                },
                                "value": "incident_commander"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "Executive Team"
                                },
                                "value": "executive"
                            }
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Escalate To"
                    }
                },
                {
                    "type": "input",
                    "block_id": "escalation_notes",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Provide additional context for the escalation..."
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Escalation Notes"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚠️ *Warning:* This action will immediately notify the selected escalation target and may trigger additional alerting."
                    }
                }
            ]
        }
        
        try:
            trigger_id = payload.get("trigger_id")
            await self.client.views_open(trigger_id=trigger_id, view=modal)
            return {"response_action": "clear"}
        except Exception as e:
            logger.error(f"Error opening escalation modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to open escalation form."}
            }
    
    async def _handle_resolve_incident(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                     user_id: str) -> Dict[str, Any]:
        """Handle incident resolution button click"""
        incident_id = action.get("value")
        
        # Open resolution modal
        modal = {
            "type": "modal",
            "callback_id": "incident_resolution_modal",
            "title": {
                "type": "plain_text",
                "text": "Resolve Incident"
            },
            "submit": {
                "type": "plain_text",
                "text": "Resolve"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "input",
                    "block_id": "incident_id",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "incident_id_input",
                        "initial_value": incident_id
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Incident ID"
                    }
                },
                {
                    "type": "input",
                    "block_id": "resolution",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "resolution_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Describe how the incident was resolved..."
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Resolution Details"
                    }
                }
            ]
        }
        
        try:
            trigger_id = payload.get("trigger_id")
            await self.client.views_open(trigger_id=trigger_id, view=modal)
            return {"response_action": "clear"}
        except Exception as e:
            logger.error(f"Error opening resolution modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to open resolution form."}
            }
    
    async def _handle_view_incident_details(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                          user_id: str) -> Dict[str, Any]:
        """Handle view incident details button click"""
        incident_id = action.get("value")
        
        # This would typically fetch incident details from the management system
        modal = {
            "type": "modal",
            "title": {
                "type": "plain_text",
                "text": "Incident Details"
            },
            "close": {
                "type": "plain_text",
                "text": "Close"
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Incident ID:* `{incident_id}`\n\n_Detailed incident information would be displayed here._\n\n_This feature requires integration with the incident management system._"
                    }
                }
            ]
        }
        
        try:
            trigger_id = payload.get("trigger_id")
            await self.client.views_open(trigger_id=trigger_id, view=modal)
            return {"response_action": "clear"}
        except Exception as e:
            logger.error(f"Error opening details modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to open incident details."}
            }
    
    async def _handle_add_incident_note(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                      user_id: str) -> Dict[str, Any]:
        """Handle add incident note button click"""
        incident_id = action.get("value")
        
        # Open note modal
        modal = {
            "type": "modal",
            "callback_id": "incident_note_modal",
            "title": {
                "type": "plain_text",
                "text": "Add Note"
            },
            "submit": {
                "type": "plain_text",
                "text": "Add Note"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "input",
                    "block_id": "incident_id",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "incident_id_input",
                        "initial_value": incident_id
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Incident ID"
                    }
                },
                {
                    "type": "input",
                    "block_id": "note",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "note_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Add your note or update here..."
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Note"
                    }
                }
            ]
        }
        
        try:
            trigger_id = payload.get("trigger_id")
            await self.client.views_open(trigger_id=trigger_id, view=modal)
            return {"response_action": "clear"}
        except Exception as e:
            logger.error(f"Error opening note modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to open note form."}
            }
    
    # Modal submission handlers
    
    async def _handle_assignment_modal(self, payload: Dict[str, Any], 
                                     values: Dict[str, Any]) -> Dict[str, Any]:
        """Handle assignment modal submission"""
        try:
            incident_id = values.get("incident_id", {}).get("incident_id_input", {}).get("value", "")
            team = values.get("team", {}).get("team_input", {}).get("value", "")
            assignee = values.get("assignee", {}).get("assignee_select", {}).get("selected_user", "")
            
            # This would typically call the incident management system
            logger.info(f"Assignment request: incident={incident_id}, team={team}, assignee={assignee}")
            
            return {"response_action": "clear"}
            
        except Exception as e:
            logger.error(f"Error processing assignment modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to process assignment."}
            }
    
    async def _handle_resolution_modal(self, payload: Dict[str, Any], 
                                     values: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resolution modal submission"""
        try:
            incident_id = values.get("incident_id", {}).get("incident_id_input", {}).get("value", "")
            resolution = values.get("resolution", {}).get("resolution_input", {}).get("value", "")
            
            # This would typically call the incident management system
            logger.info(f"Resolution request: incident={incident_id}, resolution={resolution}")
            
            return {"response_action": "clear"}
            
        except Exception as e:
            logger.error(f"Error processing resolution modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to process resolution."}
            }
    
    async def _handle_note_modal(self, payload: Dict[str, Any], 
                               values: Dict[str, Any]) -> Dict[str, Any]:
        """Handle note modal submission"""
        try:
            incident_id = values.get("incident_id", {}).get("incident_id_input", {}).get("value", "")
            note = values.get("note", {}).get("note_input", {}).get("value", "")
            
            # This would typically call the incident management system
            logger.info(f"Note request: incident={incident_id}, note={note}")
            
            return {"response_action": "clear"}
            
        except Exception as e:
            logger.error(f"Error processing note modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to add note."}
            }
    
    async def _handle_escalation_modal(self, payload: Dict[str, Any], 
                                     values: Dict[str, Any]) -> Dict[str, Any]:
        """Handle escalation modal submission"""
        try:
            incident_id = values.get("incident_id", {}).get("incident_id_input", {}).get("value", "")
            reason = values.get("escalation_reason", {}).get("reason_select", {}).get("selected_option", {}).get("value", "")
            target = values.get("escalation_target", {}).get("target_select", {}).get("selected_option", {}).get("value", "")
            notes = values.get("escalation_notes", {}).get("notes_input", {}).get("value", "")
            
            # This would typically call the incident management system
            logger.info(f"Escalation request: incident={incident_id}, reason={reason}, target={target}, notes={notes}")
            
            return {"response_action": "clear"}
            
        except Exception as e:
            logger.error(f"Error processing escalation modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to process escalation."}
            }
    
    # Additional interactive components
    
    async def send_confirmation_dialog(self, trigger_id: str, action: str, 
                                     incident_id: str, details: str = "") -> bool:
        """Send confirmation dialog for destructive actions"""
        try:
            modal = {
                "type": "modal",
                "callback_id": f"confirm_{action}",
                "title": {
                    "type": "plain_text",
                    "text": "Confirm Action"
                },
                "submit": {
                    "type": "plain_text",
                    "text": "Confirm"
                },
                "close": {
                    "type": "plain_text",
                    "text": "Cancel"
                },
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"⚠️ *Confirm {action.title()}*\n\nAre you sure you want to {action} incident `{incident_id}`?"
                        }
                    }
                ]
            }
            
            if details:
                modal["blocks"].append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Details:* {details}"
                    }
                })
            
            modal["blocks"].extend([
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "This action cannot be undone."
                    }
                },
                {
                    "type": "input",
                    "block_id": "incident_id",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "incident_id_input",
                        "initial_value": incident_id
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Incident ID"
                    }
                }
            ])
            
            response = await self.client.views_open(trigger_id=trigger_id, view=modal)
            return response["ok"]
            
        except Exception as e:
            logger.error(f"Error sending confirmation dialog: {str(e)}")
            return False
    
    async def send_quick_action_buttons(self, channel: str, incident_id: str, 
                                      thread_ts: Optional[str] = None) -> bool:
        """Send quick action buttons for common incident operations"""
        try:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Quick Actions for `{incident_id}`*"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🙋 Take Ownership"
                            },
                            "style": "primary",
                            "action_id": "quick_assign_self",
                            "value": incident_id
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📝 Add Update"
                            },
                            "action_id": "quick_add_note",
                            "value": incident_id
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "⚠️ Escalate"
                            },
                            "style": "danger",
                            "action_id": "quick_escalate",
                            "value": incident_id
                        }
                    ]
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Mark Resolved"
                            },
                            "style": "primary",
                            "action_id": "quick_resolve",
                            "value": incident_id
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📋 View Details"
                            },
                            "action_id": "view_incident_details",
                            "value": incident_id
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🔄 Refresh Status"
                            },
                            "action_id": "refresh_incident",
                            "value": incident_id
                        }
                    ]
                }
            ]
            
            response = await self.client.chat_postMessage(
                channel=channel,
                text=f"Quick actions for {incident_id}",
                blocks=blocks,
                thread_ts=thread_ts
            )
            
            return response["ok"]
            
        except Exception as e:
            logger.error(f"Error sending quick action buttons: {str(e)}")
            return False
    
    async def send_incident_timeline(self, channel: str, incident_id: str, 
                                   timeline_events: List[Dict[str, Any]]) -> bool:
        """Send interactive incident timeline"""
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"📅 Timeline: {incident_id}"
                    }
                }
            ]
            
            for event in timeline_events:
                timestamp = event.get("timestamp", "")
                action = event.get("action", "")
                user = event.get("user", "")
                details = event.get("details", "")
                
                event_text = f"*{timestamp}* - {action}"
                if user:
                    event_text += f" by <@{user}>"
                if details:
                    event_text += f"\n{details}"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": event_text
                    }
                })
            
            # Add action buttons
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔄 Refresh Timeline"
                        },
                        "action_id": "refresh_timeline",
                        "value": incident_id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📊 Generate Report"
                        },
                        "action_id": "generate_report",
                        "value": incident_id
                    }
                ]
            })
            
            response = await self.client.chat_postMessage(
                channel=channel,
                text=f"Timeline for {incident_id}",
                blocks=blocks
            )
            
            return response["ok"]
            
        except Exception as e:
            logger.error(f"Error sending incident timeline: {str(e)}")
            return False
    
    async def send_incident_metrics(self, channel: str, metrics: Dict[str, Any]) -> bool:
        """Send interactive incident metrics dashboard"""
        try:
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 Incident Metrics Dashboard"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Active Incidents:*\n{metrics.get('active_incidents', 0)}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Resolved Today:*\n{metrics.get('resolved_today', 0)}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Avg Resolution Time:*\n{metrics.get('avg_resolution_time', 'N/A')}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Critical Incidents:*\n{metrics.get('critical_incidents', 0)}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Team Performance:*"
                    }
                }
            ]
            
            # Add team performance data
            for team, data in metrics.get('team_performance', {}).items():
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• *{team}:* {data.get('active', 0)} active, {data.get('avg_time', 'N/A')} avg time"
                    }
                })
            
            # Add interactive elements
            blocks.extend([
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "static_select",
                            "placeholder": {
                                "type": "plain_text",
                                "text": "View detailed metrics"
                            },
                            "action_id": "view_detailed_metrics",
                            "options": [
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Last 24 Hours"
                                    },
                                    "value": "24h"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Last Week"
                                    },
                                    "value": "7d"
                                },
                                {
                                    "text": {
                                        "type": "plain_text",
                                        "text": "Last Month"
                                    },
                                    "value": "30d"
                                }
                            ]
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📈 Export Report"
                            },
                            "action_id": "export_metrics",
                            "value": "current"
                        }
                    ]
                }
            ])
            
            response = await self.client.chat_postMessage(
                channel=channel,
                text="Incident metrics dashboard",
                blocks=blocks
            )
            
            return response["ok"]
            
        except Exception as e:
            logger.error(f"Error sending incident metrics: {str(e)}")
            return False
    
    # Quick action handlers
    
    async def _handle_quick_assign_self(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                      user_id: str) -> Dict[str, Any]:
        """Handle quick self-assignment"""
        incident_id = action.get("value")
        
        # This would typically call the incident management system
        logger.info(f"Quick self-assignment: incident={incident_id}, user={user_id}")
        
        return {
            "response_action": "update",
            "text": f"✅ You have taken ownership of incident `{incident_id}`"
        }
    
    async def _handle_quick_add_note(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                   user_id: str) -> Dict[str, Any]:
        """Handle quick note addition"""
        incident_id = action.get("value")
        
        # Open simplified note modal
        modal = {
            "type": "modal",
            "callback_id": "quick_note_modal",
            "title": {
                "type": "plain_text",
                "text": "Quick Update"
            },
            "submit": {
                "type": "plain_text",
                "text": "Add Update"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "blocks": [
                {
                    "type": "input",
                    "block_id": "incident_id",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "incident_id_input",
                        "initial_value": incident_id
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Incident ID"
                    }
                },
                {
                    "type": "input",
                    "block_id": "update_type",
                    "element": {
                        "type": "static_select",
                        "action_id": "type_select",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select update type"
                        },
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "🔍 Investigation Update"
                                },
                                "value": "investigation"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "🔧 Mitigation Applied"
                                },
                                "value": "mitigation"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "📞 Customer Communication"
                                },
                                "value": "customer_comm"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "⏰ Status Update"
                                },
                                "value": "status"
                            },
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": "📝 General Note"
                                },
                                "value": "general"
                            }
                        ]
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Update Type"
                    }
                },
                {
                    "type": "input",
                    "block_id": "update_text",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "text_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter your update..."
                        }
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Update Details"
                    }
                }
            ]
        }
        
        try:
            trigger_id = payload.get("trigger_id")
            await self.client.views_open(trigger_id=trigger_id, view=modal)
            return {"response_action": "clear"}
        except Exception as e:
            logger.error(f"Error opening quick note modal: {str(e)}")
            return {
                "response_action": "errors",
                "errors": {"base": "Failed to open update form."}
            }
    
    async def _handle_refresh_incident(self, payload: Dict[str, Any], action: Dict[str, Any], 
                                     user_id: str) -> Dict[str, Any]:
        """Handle incident refresh request"""
        incident_id = action.get("value")
        
        # This would typically refresh incident data from the management system
        logger.info(f"Refresh request: incident={incident_id}, user={user_id}")
        
        return {
            "response_action": "update",
            "text": f"🔄 Refreshed status for incident `{incident_id}`"
        }