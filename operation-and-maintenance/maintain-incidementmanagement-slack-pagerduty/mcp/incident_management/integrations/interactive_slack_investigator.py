#!/usr/bin/env python3
"""
Interactive Slack Incident Investigator
=======================================

Enhanced Slack bot that allows users to investigate incidents directly in Slack
using both Splunk and PagerDuty MCP servers for real-time data analysis.

Features:
- Interactive Splunk queries from Slack
- PagerDuty incident management
- Real-time investigation workflows
- Collaborative incident resolution
- Rich interactive components
"""

import asyncio
import logging
import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from integrations.real_splunk_mcp_client import SplunkIncidentClient
from integrations.pagerduty_client import PagerDutyIncidentClient
from integrations.mcp_ai_investigator import MCPAIInvestigator

logger = logging.getLogger(__name__)


@dataclass
class InvestigationSession:
    """Represents an active investigation session"""
    incident_id: str
    channel_id: str
    thread_ts: str
    user_id: str
    created_at: datetime
    splunk_client: Optional[SplunkIncidentClient] = None
    pagerduty_client: Optional[PagerDutyIncidentClient] = None
    context: Dict[str, Any] = None


class InteractiveSlackInvestigator:
    """
    Interactive Slack bot for incident investigation using MCP servers.
    
    Provides real-time investigation capabilities:
    - Run Splunk queries from Slack
    - Manage PagerDuty incidents
    - Collaborative investigation workflows
    - Rich interactive components
    """
    
    def __init__(self, bot_token: str, 
                 splunk_client: Optional[SplunkIncidentClient] = None, 
                 pagerduty_client: Optional[PagerDutyIncidentClient] = None):
        """
        Initialize the interactive investigator.
        
        Args:
            bot_token: Slack bot token
            splunk_client: Connected Splunk MCP client (optional)
            pagerduty_client: Connected PagerDuty MCP client (optional)
        """
        self.slack_client = AsyncWebClient(token=bot_token)
        self.splunk_client = splunk_client
        self.pagerduty_client = pagerduty_client
        
        # Initialize MCP AI investigator with existing clients
        self.ai_investigator = MCPAIInvestigator(
            slack_client=self.slack_client,
            splunk_client=self.splunk_client,
            pagerduty_client=self.pagerduty_client
        )
        
        # Active investigation sessions
        self.active_sessions: Dict[str, InvestigationSession] = {}
        
        # Command handlers
        self.command_handlers = {
            "query": self._handle_query_command,
            "pagerduty": self._handle_pagerduty_command,
            "resolve": self._handle_resolve_command,
            "help": self._handle_help_command
        }
        
        # Interactive handlers
        self.interaction_handlers = {
            "start_investigation": self._handle_start_investigation,
            "run_splunk_query": self._handle_run_splunk_query,


            "create_pagerduty_incident": self._handle_create_pagerduty_incident,
            "escalate_incident": self._handle_escalate_incident,
            "acknowledge_incident": self._handle_acknowledge_incident,
            "resolve_incident": self._handle_resolve_incident,
            "open_pagerduty_incident": self._handle_open_pagerduty_incident,
            "show_pagerduty_status": self._handle_show_pagerduty_status,

            "add_investigation_note": self._handle_add_investigation_note,
            # AI Investigation handlers
            "ai_investigate_root_cause": self._handle_ai_investigate,
            "ai_investigate_performance": self._handle_ai_investigate,
            "ai_investigate_errors": self._handle_ai_investigate,
            "ai_investigate_security": self._handle_ai_investigate,
            "ai_run_query": self._handle_ai_run_query,
            "ai_get_data": self._handle_ai_get_data,
            "ai_get_more_data": self._handle_ai_get_more_data,
            "ai_continue_chat": self._handle_ai_continue_chat,
        }
    
    def _get_pagerduty_app_host(self) -> str:
        """
        Get PagerDuty app host from environment variable.
        
        Environment Variable:
            PAGERDUTY_APP_HOST: The base URL for PagerDuty app links (default: https://app.pagerduty.com)
                               Used for generating incident links in Slack messages.
                               Examples: 
                               - https://app.pagerduty.com (default)
                               - https://mycompany.pagerduty.com (custom domain)
        """
        return os.getenv('PAGERDUTY_APP_HOST', 'https://app.pagerduty.com')
    
    def _get_pagerduty_incident_id(self, internal_incident_id: str) -> Optional[str]:
        """
        Get the PagerDuty incident ID from our internal incident ID.
        
        This method looks up the detected incidents to find the corresponding
        PagerDuty incident ID that was created when the incident was auto-created,
        or extracts it from PagerDuty-imported incidents.
        
        Args:
            internal_incident_id: Our internal incident ID (e.g., INC-20250730130828-AWSCloudTrailErrors)
            
        Returns:
            PagerDuty incident ID if found, otherwise None
        """
        logger.info(f"🔧 Looking up PagerDuty ID for internal incident: {internal_incident_id}")
        
        # First, check if this is a PagerDuty-imported incident with ID in the format
        # INC-PD-20250730133015-Q33HR89D (last part is PagerDuty ID)
        if internal_incident_id.startswith('INC-PD-'):
            parts = internal_incident_id.split('-')
            if len(parts) >= 4:
                # The PagerDuty ID is the last part after the timestamp
                pd_id = parts[-1]
                logger.info(f"🔧 Extracted PagerDuty ID from internal ID: {pd_id}")
                return pd_id
        
        # Import here to avoid circular imports
        try:
            from run_api import detected_incidents
            
            for incident in detected_incidents:
                if incident.get('id') == internal_incident_id:
                    # Check if we have a stored PagerDuty incident ID (from auto-creation)
                    pd_id = incident.get('pagerduty_incident_id')
                    if pd_id:
                        logger.info(f"🔧 Found stored PagerDuty ID: {pd_id}")
                        return pd_id
            
            # If not found in detected incidents, check if this is already a PagerDuty ID
            # PagerDuty IDs are typically short alphanumeric strings (8-12 chars)
            if len(internal_incident_id) < 15 and internal_incident_id.replace('_', '').isalnum():
                logger.info(f"🔧 Internal ID appears to be a PagerDuty ID: {internal_incident_id}")
                return internal_incident_id
                
            logger.warning(f"🔧 Could not find PagerDuty ID for internal incident: {internal_incident_id}")
            return None
        except ImportError:
            logger.warning("Could not import detected_incidents for PagerDuty ID lookup")
            return None
    
    def _get_available_sources(self) -> List[str]:
        """Get list of available data sources"""
        sources = []
        if self.splunk_client:
            sources.append("Splunk")
        if self.pagerduty_client:
            sources.append("PagerDuty")
        return sources
    
    def _build_unavailable_source_message(self, requested_source: str) -> str:
        """Build message when requested source is unavailable"""
        available = self._get_available_sources()
        if not available:
            return f"❌ {requested_source} is not available. No data sources are currently connected. The system is running in basic mode."
        else:
            return f"❌ {requested_source} is not available. Available sources: {', '.join(available)}"
    
    async def handle_slash_command(self, command: str, text: str, user_id: str, 
                                 channel_id: str, trigger_id: str) -> Dict[str, Any]:
        """
        Handle slash commands for incident investigation.
        
        Commands:
        - /investigate <incident_id> - Start investigation session
        - /query <splunk_query> - Run Splunk query
        - /pagerduty <action> [args] - PagerDuty operations
        - /resolve <incident_id> - Resolve incident
        """
        try:
            args = text.strip().split() if text else []
            
            if not args:
                return await self._handle_help_command([], user_id, channel_id, trigger_id)
            
            subcommand = args[0].lower()
            command_args = args[1:]
            
            # Route to appropriate handler
            handler = self.command_handlers.get(subcommand)
            if handler:
                return await handler(command_args, user_id, channel_id, trigger_id)
            else:
                # If no subcommand matches, treat the first argument as an incident ID for investigation
                if command == "/investigate":
                    return await self._handle_investigate_command(args, user_id, channel_id, trigger_id)
                else:
                    return {
                        "response_type": "ephemeral",
                        "text": f"Unknown command: {subcommand}. Use `/{command.lstrip('/')} help` for available commands."
                    }
                
        except Exception as e:
            logger.error(f"Error handling slash command: {e}")
            return {
                "response_type": "ephemeral",
                "text": "An error occurred processing your command. Please try again."
            }
    
    async def handle_interaction(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle interactive component interactions"""
        try:
            interaction_type = payload.get("type")
            
            if interaction_type == "block_actions":
                return await self._handle_block_actions(payload)
            elif interaction_type == "view_submission":
                return await self._handle_modal_submission(payload)
            else:
                return {}
                
        except Exception as e:
            logger.error(f"Error handling interaction: {e}")
            return {}
    
    # Command Handlers
    
    async def _handle_investigate_command(self, args: List[str], user_id: str, 
                                        channel_id: str, trigger_id: str) -> Dict[str, Any]:
        """Start an investigation session"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please provide an incident ID. Usage: `/investigate <incident_id>`"
            }
        
        incident_id = args[0]
        
        try:
            # Create investigation session
            session_id = f"{incident_id}_{channel_id}_{user_id}"
            
            # Send initial investigation message
            response = await self.slack_client.chat_postMessage(
                channel=channel_id,
                text=f"🔍 Starting investigation for incident `{incident_id}`",
                blocks=self._build_investigation_start_blocks(incident_id, user_id)
            )
            
            if response["ok"]:
                # Try to find and store the original incident data for later use
                original_incident_data = None
                try:
                    from run_api import detected_incidents, incident_cache, load_incident_cache
                    
                    # Reload cache from file in case it was updated by another process
                    load_incident_cache()
                    
                    # First try detected_incidents (most recent)
                    for incident in detected_incidents:
                        if incident.get('id') == incident_id:
                            original_incident_data = incident.copy()  # Make a copy to avoid mutations
                            logger.info(f"✅ Found incident {incident_id} in detected_incidents with {len(incident.get('remediation_suggestions', []))} remediation suggestions")
                            break
                    
                    # If not found in detected_incidents, try the persistent cache
                    if not original_incident_data and incident_id in incident_cache:
                        original_incident_data = incident_cache[incident_id].copy()
                        logger.info(f"✅ Found incident {incident_id} in persistent cache with {len(original_incident_data.get('remediation_suggestions', []))} remediation suggestions")
                    
                    if original_incident_data:
                        logger.info(f"✅ Stored original incident data for {incident_id} in investigation session")
                    else:
                        logger.warning(f"⚠️ Could not find incident {incident_id} in detected_incidents or persistent cache")
                        
                except ImportError:
                    logger.warning("Could not import detected_incidents/incident_cache for session storage")
                
                # Create investigation session
                session = InvestigationSession(
                    incident_id=incident_id,
                    channel_id=channel_id,
                    thread_ts=response["ts"],
                    user_id=user_id,
                    created_at=datetime.now(),
                    splunk_client=self.splunk_client,
                    pagerduty_client=self.pagerduty_client,
                    context={
                        'original_incident_data': original_incident_data  # Store for later PagerDuty creation
                    }
                )
                
                self.active_sessions[session_id] = session
                
                # Get initial incident data from PagerDuty
                await self._fetch_initial_incident_data(session)
                
                return {
                    "response_type": "ephemeral",
                    "text": f"✅ Investigation session started for `{incident_id}` in this channel."
                }
            else:
                return {
                    "response_type": "ephemeral",
                    "text": "Failed to start investigation session. Please try again."
                }
                
        except Exception as e:
            logger.error(f"Error starting investigation: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"Error starting investigation: {str(e)}"
            }
    
    async def _handle_query_command(self, args: List[str], user_id: str, 
                                  channel_id: str, trigger_id: str) -> Dict[str, Any]:
        """Run a Splunk query"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please provide a Splunk query. Usage: `/query <splunk_search>`"
            }
        
        query = " ".join(args)
        
        try:
            # Execute Splunk query
            results = await self.splunk_client.execute_detection_query(query)
            
            # Format results for Slack
            blocks = self._build_query_results_blocks(query, results, user_id)
            
            return {
                "response_type": "in_channel",
                "blocks": blocks
            }
            
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"Error executing query: {str(e)}"
            }
    
    async def _handle_pagerduty_command(self, args: List[str], user_id: str, 
                                      channel_id: str, trigger_id: str) -> Dict[str, Any]:
        """Handle PagerDuty operations"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please specify a PagerDuty action. Usage: `/pagerduty <action> [args]`\nActions: list, create, update, resolve"
            }
        
        action = args[0].lower()
        action_args = args[1:]
        
        try:
            if action == "list":
                incidents = await self.pagerduty_client.get_active_incidents()
                blocks = self._build_pagerduty_list_blocks(incidents)
                
                return {
                    "response_type": "ephemeral",
                    "blocks": blocks
                }
                
            elif action == "create":
                if len(action_args) < 1:
                    return {
                        "response_type": "ephemeral",
                        "text": "Please provide incident title. Usage: `/pagerduty create <title> [description]`"
                    }
                
                title = action_args[0]
                description = " ".join(action_args[1:]) if len(action_args) > 1 else f"Created from Slack by <@{user_id}>"
                
                # Create incident data
                incident_data = {
                    "id": f"slack-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "title": title,
                    "description": description,
                    "severity": "MEDIUM",
                    "source": "slack"
                }
                
                result = await self.pagerduty_client.create_incident_from_detection(incident_data, [])
                
                if result.get('success'):
                    return {
                        "response_type": "in_channel",
                        "text": f"✅ PagerDuty incident created: {result.get('incident_id')}\n*Title:* {title}\n*Created by:* <@{user_id}>"
                    }
                else:
                    return {
                        "response_type": "ephemeral",
                        "text": f"Failed to create PagerDuty incident: {result.get('error')}"
                    }
                    
            else:
                return {
                    "response_type": "ephemeral",
                    "text": f"Unknown PagerDuty action: {action}. Available: list, create, update, resolve"
                }
                
        except Exception as e:
            logger.error(f"Error handling PagerDuty command: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"Error executing PagerDuty command: {str(e)}"
            }
    
    async def _handle_resolve_command(self, args: List[str], user_id: str, 
                                    channel_id: str, trigger_id: str) -> Dict[str, Any]:
        """Resolve an incident"""
        if not args:
            return {
                "response_type": "ephemeral",
                "text": "Please provide an incident ID. Usage: `/resolve <incident_id> [resolution_notes]`"
            }
        
        incident_id = args[0]
        resolution = " ".join(args[1:]) if len(args) > 1 else "Resolved via Slack investigation"
        
        try:
            # Close investigation session if exists
            session_key = None
            for key, session in self.active_sessions.items():
                if session.incident_id == incident_id and session.channel_id == channel_id:
                    session_key = key
                    break
            
            if session_key:
                del self.active_sessions[session_key]
            
            return {
                "response_type": "in_channel",
                "text": f"✅ Incident `{incident_id}` resolved by <@{user_id}>\n*Resolution:* {resolution}\n🔍 Investigation session closed."
            }
            
        except Exception as e:
            logger.error(f"Error resolving incident: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"Error resolving incident: {str(e)}"
            }
    
    async def _handle_help_command(self, args: List[str], user_id: str, 
                                 channel_id: str, trigger_id: str) -> Dict[str, Any]:
        """Show help information"""
        help_blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔍 Interactive Incident Investigation"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Use these commands to investigate incidents with real-time Splunk and PagerDuty data:"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Available Commands:*\n" +
                           "• `/investigate <incident_id>` - Start investigation session\n" +
                           "• `/query <splunk_search>` - Run Splunk query\n" +
                           "• `/pagerduty <action> [args]` - PagerDuty operations\n" +
                           "• `/resolve <incident_id> [notes]` - Resolve incident"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Examples:*\n" +
                           "• `/investigate INC-20240123-ABC123`\n" +
                           "• `/query search index=main error | head 10`\n" +
                           "• `/pagerduty list`\n" +
                           "• `/pagerduty create \"Database Error\" \"Connection timeout\"`"
                }
            }
        ]
        
        return {
            "response_type": "ephemeral",
            "blocks": help_blocks
        }
    
    # Interactive Handlers
    
    async def _handle_block_actions(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle block action interactions"""
        actions = payload.get("actions", [])
        if not actions:
            return {}
        
        action = actions[0]
        action_id = action.get("action_id")
        
        handler = self.interaction_handlers.get(action_id)
        if handler:
            return await handler(payload, action)
        else:
            return {}
    
    async def _handle_run_splunk_query(self, payload: Dict[str, Any], 
                                     action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Splunk query execution from button"""
        query = action.get("value")
        user_id = payload.get("user", {}).get("id")
        
        try:
            results = await self.splunk_client.execute_detection_query(query)
            
            # Update message with results
            blocks = self._build_query_results_blocks(query, results, user_id)
            
            return {
                "blocks": blocks
            }
            
        except Exception as e:
            return {
                "text": f"❌ Query failed: {str(e)}"
            }
    
    async def _handle_modal_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle modal form submissions"""
        view = payload.get("view", {})
        callback_id = view.get("callback_id")
        
        if callback_id == "investigation_query_modal":
            return await self._handle_investigation_query_modal(payload)
        elif callback_id == "pagerduty_incident_modal":
            return await self._handle_pagerduty_incident_modal(payload)
        elif callback_id == "add_investigation_note_modal":
            return await self._handle_add_note_modal_submission(payload)
        else:
            return {}
    
    async def _handle_add_note_modal_submission(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle the submission of the add note modal"""
        view = payload.get("view", {})
        user_id = payload.get("user", {}).get("id")
        incident_id = view.get("private_metadata")  # Get incident ID from modal metadata
        
        # Extract the note text from the modal
        values = view.get("state", {}).get("values", {})
        note_input = values.get("note_input", {})
        note_text = note_input.get("note_text", {}).get("value", "").strip()
        
        if not note_text:
            return {
                "response_action": "errors",
                "errors": {
                    "note_input": "Please enter a note before submitting."
                }
            }
        
        if not incident_id:
            return {
                "response_action": "errors",
                "errors": {
                    "note_input": "Incident ID not found. Please try again."
                }
            }
        
        # Get the PagerDuty incident ID
        pagerduty_incident_id = self._get_pagerduty_incident_id(incident_id)
        
        if not pagerduty_incident_id:
            # If no PagerDuty incident exists, show error
            return {
                "response_action": "errors",
                "errors": {
                    "note_input": f"No PagerDuty incident found for {incident_id}. Create a PagerDuty incident first."
                }
            }
        
        try:
            # Format the note with user information
            formatted_note = f"📝 **Investigation Note by <@{user_id}>**\n\n{note_text}\n\n*Added via Slack at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC*"
            
            # Add the note to PagerDuty
            success = await self.pagerduty_client.client.add_note_to_incident(
                pagerduty_incident_id, 
                formatted_note
            )
            
            if success:
                # Send a success message as ephemeral response (since we don't have channel context in modal)
                # The modal submission doesn't provide channel context, so we'll just close successfully
                logger.info(f"✅ Successfully added note to PagerDuty incident {pagerduty_incident_id} by user {user_id}")
                
                # For now, we'll rely on the modal closing to indicate success
                # In a future enhancement, we could store the channel ID when opening the modal
                try:
                    # Optional: Try to send a message if we can determine the channel
                    # This is a placeholder for future enhancement
                    pass
                except Exception as e:
                    logger.warning(f"Could not send success message to channel: {e}")
                
                # Close the modal successfully
                return {}
            else:
                return {
                    "response_action": "errors",
                    "errors": {
                        "note_input": "Failed to add note to PagerDuty. Please try again."
                    }
                }
                
        except Exception as e:
            logger.error(f"Error adding note to PagerDuty: {e}")
            return {
                "response_action": "errors",
                "errors": {
                    "note_input": f"Error adding note: {str(e)}"
                }
            }
    
    # PagerDuty Integration Handlers
    
    async def _handle_escalate_incident(self, payload: Dict[str, Any], 
                                      action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incident escalation in PagerDuty"""
        internal_incident_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        
        if not self.pagerduty_client:
            return {
                "text": "❌ PagerDuty is not available"
            }
        
        # Get the actual PagerDuty incident ID
        pagerduty_incident_id = self._get_pagerduty_incident_id(internal_incident_id)
        if not pagerduty_incident_id:
            return {
                "text": f"❌ No PagerDuty incident found for `{internal_incident_id}`",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *Cannot escalate incident*\n\nNo PagerDuty incident found for `{internal_incident_id}`. You need to create a PagerDuty incident first before you can escalate it."
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🚨 Create PagerDuty Incident"
                                },
                                "style": "primary",
                                "action_id": "create_pagerduty_incident",
                                "value": internal_incident_id
                            }
                        ]
                    }
                ]
            }
        
        try:
            # Escalate incident in PagerDuty
            result = await self.pagerduty_client.escalate_incident(pagerduty_incident_id, user_id)
            
            if result.get("success"):
                actions_taken = result.get("actions_taken", [])
                actions_text = "\n".join([f"• {action}" for action in actions_taken])
                
                return {
                    "text": f"🚨 Incident `{internal_incident_id}` has been escalated in PagerDuty",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"🚨 *Incident Escalated Successfully*\n\nIncident `{internal_incident_id}` (PagerDuty ID: `{pagerduty_incident_id}`) has been escalated in PagerDuty by <@{user_id}>\n\n*Actions Completed:*\n{actions_text}\n\n*Next Steps:*\n• Higher-level responders have been notified\n• Continue monitoring for updates"
                            }
                        }
                    ]
                }
            else:
                return {
                    "text": f"❌ Failed to escalate incident: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error escalating incident: {e}")
            return {
                "text": f"❌ Error escalating incident: {str(e)}"
            }
    
    async def _handle_acknowledge_incident(self, payload: Dict[str, Any], 
                                         action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incident acknowledgment in PagerDuty"""
        internal_incident_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        
        if not self.pagerduty_client:
            return {
                "text": "❌ PagerDuty is not available"
            }
        
        # Get the actual PagerDuty incident ID
        pagerduty_incident_id = self._get_pagerduty_incident_id(internal_incident_id)
        if not pagerduty_incident_id:
            return {
                "text": f"❌ No PagerDuty incident found for `{internal_incident_id}`",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *Cannot acknowledge incident*\n\nNo PagerDuty incident found for `{internal_incident_id}`. You need to create a PagerDuty incident first before you can acknowledge it."
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🚨 Create PagerDuty Incident"
                                },
                                "style": "primary",
                                "action_id": "create_pagerduty_incident",
                                "value": internal_incident_id
                            }
                        ]
                    }
                ]
            }
        
        try:
            # Acknowledge incident in PagerDuty
            result = await self.pagerduty_client.acknowledge_incident(pagerduty_incident_id, user_id)
            
            if result.get("success"):
                actions_taken = result.get("actions_taken", [])
                actions_text = "\n".join([f"• {action}" for action in actions_taken])
                
                return {
                    "text": f"✅ Incident `{internal_incident_id}` has been acknowledged",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"✅ *Incident Acknowledged Successfully*\n\nIncident `{internal_incident_id}` (PagerDuty ID: `{pagerduty_incident_id}`) has been acknowledged in PagerDuty by <@{user_id}>\n\n*Actions Completed:*\n{actions_text}\n\n*Next Steps:*\n• Continue investigation\n• Update incident with findings\n• Resolve when issue is fixed"
                            }
                        }
                    ]
                }
            else:
                return {
                    "text": f"❌ Failed to acknowledge incident: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error acknowledging incident: {e}")
            return {
                "text": f"❌ Error acknowledging incident: {str(e)}"
            }
    
    async def _handle_resolve_incident(self, payload: Dict[str, Any], 
                                     action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incident resolution in PagerDuty"""
        internal_incident_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        
        if not self.pagerduty_client:
            return {
                "text": "❌ PagerDuty is not available"
            }
        
        # Get the actual PagerDuty incident ID
        pagerduty_incident_id = self._get_pagerduty_incident_id(internal_incident_id)
        if not pagerduty_incident_id:
            return {
                "text": f"❌ No PagerDuty incident found for `{internal_incident_id}`",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *Cannot resolve incident*\n\nNo PagerDuty incident found for `{internal_incident_id}`. You need to create a PagerDuty incident first before you can resolve it."
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🚨 Create PagerDuty Incident"
                                },
                                "style": "primary",
                                "action_id": "create_pagerduty_incident",
                                "value": internal_incident_id
                            }
                        ]
                    }
                ]
            }
        
        try:
            # Resolve incident in PagerDuty
            result = await self.pagerduty_client.resolve_incident(pagerduty_incident_id, user_id)
            
            if result.get("success"):
                actions_taken = result.get("actions_taken", [])
                actions_text = "\n".join([f"• {action}" for action in actions_taken])
                
                return {
                    "text": f"✅ Incident `{internal_incident_id}` has been resolved",
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"✅ *Incident Resolved Successfully*\n\nIncident `{internal_incident_id}` (PagerDuty ID: `{pagerduty_incident_id}`) has been resolved in PagerDuty by <@{user_id}>\n\n*Actions Completed:*\n{actions_text}\n\n*Status:* Incident is now closed and all notifications have stopped."
                            }
                        }
                    ]
                }
            else:
                return {
                    "text": f"❌ Failed to resolve incident: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error resolving incident: {e}")
            return {
                "text": f"❌ Error resolving incident: {str(e)}"
            }
    
    async def _handle_open_pagerduty_incident(self, payload: Dict[str, Any], 
                                            action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle opening PagerDuty incident page"""
        incident_id = action.get("value")
        
        # This will be handled by the URL in the button, but we can provide feedback
        return {
            
            "text": f"🔗 Opening PagerDuty incident `{incident_id}` in your browser..."
        }
    
    async def _handle_show_pagerduty_status(self, payload: Dict[str, Any], 
                                          action: Dict[str, Any]) -> Dict[str, Any]:
        """Show PagerDuty incident status"""
        internal_incident_id = action.get("value")
        
        if not self.pagerduty_client:
            return {
                "text": "❌ PagerDuty is not available"
            }
        
        # Get the actual PagerDuty incident ID
        pagerduty_incident_id = self._get_pagerduty_incident_id(internal_incident_id)
        if not pagerduty_incident_id:
            return {
                "text": f"❌ No PagerDuty incident found for `{internal_incident_id}`",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *Cannot show PagerDuty status*\n\nNo PagerDuty incident found for `{internal_incident_id}`. You need to create a PagerDuty incident first."
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🚨 Create PagerDuty Incident"
                                },
                                "style": "primary",
                                "action_id": "create_pagerduty_incident",
                                "value": internal_incident_id
                            }
                        ]
                    }
                ]
            }
        
        try:
            # Get incident details from PagerDuty
            incident_details = await self.pagerduty_client.get_incident_details(pagerduty_incident_id)
            
            if incident_details:
                status_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"📊 *PagerDuty Status for `{internal_incident_id}`*\n\n*PagerDuty ID:* `{pagerduty_incident_id}`\n*Status:* {incident_details.get('status', 'Unknown')}\n*Priority:* {incident_details.get('priority', 'Unknown')}\n*Assigned:* {incident_details.get('assigned_to', 'Unassigned')}\n*Created:* {incident_details.get('created_at', 'Unknown')}"
                        }
                    }
                ]
                
                return {
                    "blocks": status_blocks
                }
            else:
                return {
                    "text": f"❌ Could not find incident `{pagerduty_incident_id}` in PagerDuty"
                }
                
        except Exception as e:
            logger.error(f"Error getting PagerDuty status: {e}")
            return {
                "text": f"❌ Error getting PagerDuty status: {str(e)}"
            }
    

    
    async def _handle_add_investigation_note(self, payload: Dict[str, Any], 
                                           action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle adding investigation notes - opens a modal for note input"""
        incident_id = action.get("value")
        trigger_id = payload.get("trigger_id")
        
        if not trigger_id:
            return {
                "text": "❌ Unable to open note dialog. Please try again."
            }
        
        # Create modal for note input
        modal_view = {
            "type": "modal",
            "callback_id": "add_investigation_note_modal",
            "title": {
                "type": "plain_text",
                "text": "Add Investigation Note"
            },
            "submit": {
                "type": "plain_text",
                "text": "Add Note"
            },
            "close": {
                "type": "plain_text",
                "text": "Cancel"
            },
            "private_metadata": incident_id,  # Store incident ID for submission
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Add a note to incident:* `{incident_id}`\n\nThis note will be added to the PagerDuty incident and visible to all responders."
                    }
                },
                {
                    "type": "input",
                    "block_id": "note_input",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "note_text",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter your investigation note here..."
                        },
                        "multiline": True,
                        "max_length": 3000
                    },
                    "label": {
                        "type": "plain_text",
                        "text": "Investigation Note"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "💡 *Tip:* Include findings, actions taken, or next steps for other responders."
                        }
                    ]
                }
            ]
        }
        
        try:
            # Open the modal using Slack Web API
            if hasattr(self, 'slack_client') and self.slack_client:
                logger.info(f"🔧 Opening note modal for incident {incident_id}")
                response = await self.slack_client.views_open(
                    trigger_id=trigger_id,
                    view=modal_view
                )
                
                if response.get("ok"):
                    logger.info(f"✅ Successfully opened note modal for incident {incident_id}")
                    # Return empty response since modal is opened
                    return {}
                else:
                    logger.error(f"❌ Failed to open note modal: {response.get('error', 'Unknown error')}")
                    return {
                        "text": f"❌ Failed to open note dialog: {response.get('error', 'Unknown error')}"
                    }
            else:
                logger.error("❌ Slack client not available for modal")
                return {
                    "text": "❌ Slack client not available. Cannot open note dialog."
                }
                
        except Exception as e:
            logger.error(f"Error opening note modal: {e}")
            return {
                "text": f"❌ Error opening note dialog: {str(e)}"
            }
    
    async def _handle_start_investigation(self, payload: Dict[str, Any], 
                                         action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle starting an investigation session"""
        incident_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        channel_id = payload.get("channel", {}).get("id")
        
        logger.info(f"🔍 Starting investigation for incident {incident_id} by user {user_id}")
        
        try:
            # Create investigation session
            session_id = f"{incident_id}_{channel_id}_{user_id}"
            
            # Build investigation blocks with all the interactive buttons
            blocks = self._build_investigation_start_blocks(incident_id, user_id)
            logger.info(f"✅ Built {len(blocks)} investigation blocks for incident {incident_id}")
            
            # Try to find and store the original incident data for later use
            original_incident_data = None
            try:
                from run_api import detected_incidents, incident_cache, load_incident_cache
                
                # Reload cache from file in case it was updated by another process
                load_incident_cache()
                
                # First try detected_incidents (most recent)
                for incident in detected_incidents:
                    if incident.get('id') == incident_id:
                        original_incident_data = incident.copy()  # Make a copy to avoid mutations
                        logger.info(f"✅ Found incident {incident_id} in detected_incidents with {len(incident.get('remediation_suggestions', []))} remediation suggestions")
                        break
                
                # If not found in detected_incidents, try the persistent cache
                if not original_incident_data and incident_id in incident_cache:
                    original_incident_data = incident_cache[incident_id].copy()
                    logger.info(f"✅ Found incident {incident_id} in persistent cache with {len(original_incident_data.get('remediation_suggestions', []))} remediation suggestions")
                
                if original_incident_data:
                    logger.info(f"✅ Stored original incident data for {incident_id} in investigation session")
                else:
                    logger.warning(f"⚠️ Could not find incident {incident_id} in detected_incidents or persistent cache")
                    
            except ImportError:
                logger.warning("Could not import detected_incidents/incident_cache for session storage")
            
            # Create investigation session
            session = InvestigationSession(
                incident_id=incident_id,
                channel_id=channel_id,
                thread_ts="",  # Will be updated when message is posted
                user_id=user_id,
                created_at=datetime.now(),
                splunk_client=self.splunk_client,
                pagerduty_client=self.pagerduty_client,
                context={
                    'original_incident_data': original_incident_data  # Store for later PagerDuty creation
                }
            )
            
            self.active_sessions[session_id] = session
            logger.info(f"✅ Created investigation session {session_id}")
            
            response = {
                "blocks": blocks
            }
            logger.info(f"✅ Returning investigation response with {len(blocks)} blocks")
            return response
            
        except Exception as e:
            logger.error(f"❌ Error starting investigation: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "text": f"❌ Error starting investigation: {str(e)}"
            }

    async def _handle_create_pagerduty_incident(self, payload: Dict[str, Any], 
                                              action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle creating a PagerDuty incident with full incident details"""
        incident_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        channel_id = payload.get("channel", {}).get("id")
        
        if not self.pagerduty_client:
            return {
                "text": "❌ PagerDuty is not available"
            }
        
        try:
            # Debug incident data availability
            debug_info = self._debug_incident_data_availability(incident_id)
            
            # Find the incident data from multiple sources
            incident_data = None
            
            # First, try to find in detected_incidents
            try:
                from run_api import detected_incidents, incident_cache, load_incident_cache
                
                # Reload cache from file in case it was updated by another process
                load_incident_cache()
                
                # Try detected_incidents first (most recent)
                for incident in detected_incidents:
                    if incident.get('id') == incident_id:
                        incident_data = incident
                        logger.info(f"✅ Found incident {incident_id} in detected_incidents with {len(incident.get('remediation_suggestions', []))} remediation suggestions")
                        break
                
                # If not found in detected_incidents, try the persistent cache
                if not incident_data and incident_id in incident_cache:
                    incident_data = incident_cache[incident_id]
                    logger.info(f"✅ Found incident {incident_id} in persistent cache with {len(incident_data.get('remediation_suggestions', []))} remediation suggestions")
                    
            except ImportError:
                logger.warning("Could not import detected_incidents/incident_cache")
            
            # If not found in detected_incidents, try to find in active investigation sessions
            if not incident_data:
                logger.info(f"🔍 Incident {incident_id} not found in detected_incidents, checking investigation sessions...")
                for session_id, session in self.active_sessions.items():
                    if session.incident_id == incident_id:
                        # Check if the session has stored incident data
                        stored_incident = session.context.get('original_incident_data')
                        if stored_incident:
                            incident_data = stored_incident
                            logger.info(f"✅ Found incident {incident_id} in investigation session {session_id} with {len(incident_data.get('remediation_suggestions', []))} remediation suggestions")
                            break
            
            # If we can't find the incident, create a basic one without remediation suggestions
            if not incident_data:
                logger.warning(f"⚠️ Incident {incident_id} not found in detected_incidents or investigation sessions")
                logger.warning(f"⚠️ Available sessions: {list(self.active_sessions.keys())}")
                
                # Try to infer incident type from the incident ID for better remediation suggestions
                affected_systems = ['manual-creation']
                description = f"Incident {incident_id} created manually via Slack integration. Requires investigation and resolution."
                
                # Enhance description and affected systems based on incident ID patterns
                incident_id_lower = incident_id.lower()
                if 'error' in incident_id_lower or 'exception' in incident_id_lower:
                    affected_systems = ['application-services', 'error-handling']
                    description = f"Error-related incident {incident_id} detected. Investigation required for application errors and exceptions."
                elif 'aws' in incident_id_lower or 'cloudtrail' in incident_id_lower:
                    affected_systems = ['aws-infrastructure', 'cloudtrail', 'security']
                    description = f"AWS infrastructure incident {incident_id} detected. Investigation required for AWS service issues."
                elif 'performance' in incident_id_lower or 'cpu' in incident_id_lower or 'memory' in incident_id_lower:
                    affected_systems = ['system-performance', 'infrastructure']
                    description = f"Performance-related incident {incident_id} detected. Investigation required for system performance issues."
                elif 'security' in incident_id_lower or 'auth' in incident_id_lower:
                    affected_systems = ['security-systems', 'authentication']
                    description = f"Security-related incident {incident_id} detected. Investigation required for security and authentication issues."
                
                incident_data = {
                    'id': incident_id,
                    'title': f"Manual Incident Creation: {incident_id}",
                    'description': description,
                    'severity': 'HIGH',
                    'status': 'DETECTED',
                    'affected_systems': affected_systems,
                    'created_at': datetime.now().isoformat(),
                    'event_count': 1,
                    'source_query': f"Manual creation for {incident_id}",
                    'remediation_suggestions': []
                }
                
                # For manual incidents that can't be found, don't generate new remediation suggestions
                # They should be created only once when the incident is first detected
                logger.warning(f"⚠️ Created fallback incident data for {incident_id} without remediation suggestions")
                logger.warning(f"⚠️ This indicates the original incident data was lost - remediation instructions will be missing from PagerDuty")
            else:
                # If we found existing incident data, use the existing remediation suggestions
                # Don't generate new ones - they should have been created when the incident was first detected
                remediation_count = len(incident_data.get('remediation_suggestions', []))
                logger.info(f"✅ Using existing incident data for {incident_id} with {remediation_count} existing remediation suggestions")
                if remediation_count > 0:
                    logger.info(f"✅ Remediation instructions will be included in PagerDuty incident")
                else:
                    logger.warning(f"⚠️ No remediation suggestions found for incident {incident_id}")
            
            # Use the same method as auto-creation for consistency
            result = await self.pagerduty_client.create_incident_from_detection(
                incident_data, 
                incident_data.get('remediation_suggestions', [])
            )
            
            if result.get("success"):
                pd_incident_id = result.get("incident_id", "Unknown")
                
                # Update the incident data with the PagerDuty incident ID
                try:
                    from run_api import detected_incidents
                    for incident in detected_incidents:
                        if incident.get('id') == incident_id:
                            incident['pagerduty_incident_id'] = pd_incident_id
                            incident['pagerduty_created'] = True
                            logger.info(f"✅ Updated incident {incident_id} with PagerDuty ID {pd_incident_id}")
                            break
                    else:
                        # If incident not found in detected_incidents, add it
                        if incident_data:
                            incident_data['pagerduty_incident_id'] = pd_incident_id
                            incident_data['pagerduty_created'] = True
                            detected_incidents.append(incident_data)
                            logger.info(f"✅ Added new incident {incident_id} to detected_incidents with PagerDuty ID {pd_incident_id}")
                except ImportError:
                    logger.warning("Could not update detected_incidents with PagerDuty ID")
                
                return {
                    "text": f"✅ PagerDuty incident created successfully!\n\n*Incident ID:* `{pd_incident_id}`\n*Created by:* <@{user_id}>\n*Original Incident:* `{incident_id}`",
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ PagerDuty Incident Created Successfully!"
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"🎉 *Incident successfully created in PagerDuty*\n\n*PagerDuty ID:* `{pd_incident_id}`\n*Original Incident:* `{incident_id}`\n*Created by:* <@{user_id}>\n*Status:* Active and assigned to on-call team"
                            },
                            "accessory": {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "🔗 Open in PagerDuty"
                                },
                                "url": f"{self._get_pagerduty_app_host()}/incidents/{pd_incident_id}",
                                "action_id": "open_pagerduty"
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*✅ Next Steps Completed:*\n• PagerDuty responders have been automatically notified\n• Incident is now tracked and monitored in PagerDuty\n• On-call team has been paged for immediate response"
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "*🚨 PagerDuty Incident Management:*"
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🚨 Escalate"
                                    },
                                    "style": "danger",
                                    "action_id": "escalate_incident",
                                    "value": incident_id,
                                    "confirm": {
                                        "title": {
                                            "type": "plain_text",
                                            "text": "Escalate Incident"
                                        },
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f"Are you sure you want to escalate incident `{incident_id}` in PagerDuty?"
                                        },
                                        "confirm": {
                                            "type": "plain_text",
                                            "text": "Escalate"
                                        },
                                        "deny": {
                                            "type": "plain_text",
                                            "text": "Cancel"
                                        }
                                    }
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "✅ Acknowledge"
                                    },
                                    "style": "primary",
                                    "action_id": "acknowledge_incident",
                                    "value": incident_id
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "✅ Resolve"
                                    },
                                    "style": "primary",
                                    "action_id": "resolve_incident",
                                    "value": incident_id,
                                    "confirm": {
                                        "title": {
                                            "type": "plain_text",
                                            "text": "Resolve Incident"
                                        },
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f"Are you sure you want to resolve incident `{incident_id}` in PagerDuty? This will close the incident."
                                        },
                                        "confirm": {
                                            "type": "plain_text",
                                            "text": "Resolve"
                                        },
                                        "deny": {
                                            "type": "plain_text",
                                            "text": "Cancel"
                                        }
                                    }
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
                                        "text": "📊 PagerDuty Status"
                                    },
                                    "action_id": "show_pagerduty_status",
                                    "value": incident_id
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "📝 Add Note"
                                    },
                                    "action_id": "add_investigation_note",
                                    "value": incident_id
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🔍 Start Investigation"
                                    },
                                    "action_id": "start_investigation",
                                    "value": incident_id,
                                    "style": "primary"
                                }
                            ]
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"✅ Created at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | PagerDuty incident tracking active"
                                }
                            ]
                        }
                    ]
                }
            else:
                return {
                    "text": f"❌ Failed to create PagerDuty incident: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            logger.error(f"Error creating PagerDuty incident: {e}")
            return {
                "text": f"❌ Error creating PagerDuty incident: {str(e)}"
            }
    
    # Helper Methods
    
    def _build_investigation_start_blocks(self, incident_id: str, user_id: str) -> List[Dict[str, Any]]:
        """Build blocks for investigation start message with PagerDuty integration"""
        logger.info(f"🔧 Building investigation blocks for incident {incident_id}")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔍 Investigation: {incident_id}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Investigation started by <@{user_id}> at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            }
        ]
        logger.info(f"✅ Added header and basic info blocks")
        
        # Add PagerDuty incident management buttons if PagerDuty is available
        if self.pagerduty_client:
            # Check if incident already has a PagerDuty incident
            pd_incident_id = self._get_pagerduty_incident_id(incident_id)
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🚨 PagerDuty Incident Management:*"
                }
            })
            
            if pd_incident_id:
                # If PagerDuty incident exists, show management buttons
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🚨 Escalate"
                            },
                            "style": "danger",
                            "action_id": "escalate_incident",
                            "value": incident_id,
                            "confirm": {
                                "title": {
                                    "type": "plain_text",
                                    "text": "Escalate Incident"
                                },
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"Are you sure you want to escalate incident `{incident_id}` in PagerDuty?"
                                },
                                "confirm": {
                                    "type": "plain_text",
                                    "text": "Escalate"
                                },
                                "deny": {
                                    "type": "plain_text",
                                    "text": "Cancel"
                                }
                            }
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Acknowledge"
                            },
                            "style": "primary",
                            "action_id": "acknowledge_incident",
                            "value": incident_id
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "✅ Resolve"
                            },
                            "style": "primary",
                            "action_id": "resolve_incident",
                            "value": incident_id,
                            "confirm": {
                                "title": {
                                    "type": "plain_text",
                                    "text": "Resolve Incident"
                                },
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"Are you sure you want to resolve incident `{incident_id}` in PagerDuty? This will close the incident."
                                },
                                "confirm": {
                                    "type": "plain_text",
                                    "text": "Resolve"
                                },
                                "deny": {
                                    "type": "plain_text",
                                    "text": "Cancel"
                                }
                            }
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📋 More Info"
                            },
                            "action_id": "open_pagerduty_incident",
                            "value": incident_id,
                            "url": f"{self._get_pagerduty_app_host()}/incidents/{pd_incident_id}"
                        }
                    ]
                })
            else:
                # If no PagerDuty incident exists, show create button
                blocks.append({
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🚨 Create PagerDuty Incident"
                            },
                            "style": "primary",
                            "action_id": "create_pagerduty_incident",
                            "value": incident_id,
                            "confirm": {
                                "title": {
                                    "type": "plain_text",
                                    "text": "Create PagerDuty Incident"
                                },
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"Create a PagerDuty incident for `{incident_id}`? This will notify the on-call team."
                                },
                                "confirm": {
                                    "type": "plain_text",
                                    "text": "Create"
                                },
                                "deny": {
                                    "type": "plain_text",
                                    "text": "Cancel"
                                }
                            }
                        }
                    ]
                })
        
        # Add investigation tools
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🔍 Investigation Tools:*"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📊 PagerDuty Status"
                        },
                        "action_id": "show_pagerduty_status",
                        "value": incident_id
                    },

                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📝 Add Note"
                        },
                        "action_id": "add_investigation_note",
                        "value": incident_id
                    }
                ]
            }
        ])
        
        # Add AI Investigation section
        blocks.extend([
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🤖 AI-Powered Investigation:*"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🎯 Root Cause Analysis"
                        },
                        "style": "primary",
                        "action_id": "ai_investigate_root_cause",
                        "value": incident_id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "⚡ Performance Analysis"
                        },
                        "action_id": "ai_investigate_performance",
                        "value": incident_id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔍 Error Analysis"
                        },
                        "action_id": "ai_investigate_errors",
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
                            "text": "🛡️ Security Analysis"
                        },
                        "action_id": "ai_investigate_security",
                        "value": incident_id
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 *Tip: @mention me in this thread to chat with AI about this incident*"
                    }
                ]
            }
        ])
        

        
        logger.info(f"✅ Completed building {len(blocks)} investigation blocks for incident {incident_id}")
        logger.info(f"🔧 PagerDuty client available: {self.pagerduty_client is not None}")
        logger.info(f"🔧 Splunk client available: {self.splunk_client is not None}")
        
        return blocks
    
    def _build_query_results_blocks(self, query: str, results: List[Dict], 
                                  user_id: str) -> List[Dict[str, Any]]:
        """Build blocks for query results"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🔍 Splunk Query Results"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Query:* `{query}`\n*Executed by:* <@{user_id}>\n*Results:* {len(results)} records"
                }
            }
        ]
        
        if results:
            # Show first few results
            results_text = ""
            for i, result in enumerate(results[:5], 1):
                result_str = ", ".join([f"{k}: {v}" for k, v in result.items()])
                results_text += f"{i}. {result_str}\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Sample Results:*\n```{results_text}```"
                }
            })
            
            if len(results) > 5:
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"... and {len(results) - 5} more results"
                        }
                    ]
                })
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No results found for this query."
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
                        "text": "🔄 Run Again"
                    },
                    "action_id": "run_splunk_query",
                    "value": query
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 Create PD Incident"
                    },
                    "action_id": "create_pagerduty_incident",
                    "value": f"Query results: {len(results)} records found"
                }
            ]
        })
        
        return blocks
    
    def _build_pagerduty_list_blocks(self, incidents: List[Dict]) -> List[Dict[str, Any]]:
        """Build blocks for PagerDuty incident list"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📊 Active PagerDuty Incidents"
                }
            }
        ]
        
        if incidents:
            for incident in incidents[:10]:  # Show first 10
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{incident.get('title', 'Unknown')}*\n" +
                               f"ID: `{incident.get('id', 'N/A')}`\n" +
                               f"Status: {incident.get('status', 'Unknown')}\n" +
                               f"Urgency: {incident.get('urgency', 'Unknown')}"
                    },
                    "accessory": {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔍 Investigate"
                        },
                        "action_id": "investigate_pagerduty_incident",
                        "value": incident.get('id', '')
                    }
                })
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No active incidents found."
                }
            })
        
        return blocks
    
    async def _fetch_initial_incident_data(self, session: InvestigationSession):
        """Fetch initial incident data for investigation"""
        try:
            # Get PagerDuty incidents
            incidents = await self.pagerduty_client.get_active_incidents()
            
            # Find matching incident
            matching_incident = None
            for incident in incidents:
                if session.incident_id in incident.get('title', '') or incident.get('id') == session.incident_id:
                    matching_incident = incident
                    break
            
            if matching_incident:
                session.context['pagerduty_incident'] = matching_incident
                
                # Send update to thread
                await self.slack_client.chat_postMessage(
                    channel=session.channel_id,
                    thread_ts=session.thread_ts,
                    text=f"📊 Found PagerDuty incident: {matching_incident.get('title')}\n" +
                         f"Status: {matching_incident.get('status')}, Urgency: {matching_incident.get('urgency')}"
                )
            
        except Exception as e:
            logger.error(f"Error fetching initial incident data: {e}")
    
    def _debug_incident_data_availability(self, incident_id: str) -> Dict[str, Any]:
        """Debug helper to check incident data availability"""
        debug_info = {
            'incident_id': incident_id,
            'found_in_detected_incidents': False,
            'found_in_sessions': False,
            'session_count': len(self.active_sessions),
            'sessions_with_incident_data': 0,
            'remediation_suggestions_count': 0
        }
        
        # Check detected_incidents and persistent cache
        try:
            from run_api import detected_incidents, incident_cache, load_incident_cache
            
            # Reload cache from file in case it was updated by another process
            load_incident_cache()
            
            # Debug: Log all available incident IDs
            detected_ids = [inc.get('id') for inc in detected_incidents]
            cache_ids = list(incident_cache.keys())
            logger.info(f"🔍 Available incident IDs in detected_incidents: {detected_ids}")
            logger.info(f"🔍 Available incident IDs in incident_cache: {cache_ids}")
            
            # Check detected_incidents
            for incident in detected_incidents:
                if incident.get('id') == incident_id:
                    debug_info['found_in_detected_incidents'] = True
                    debug_info['remediation_suggestions_count'] = len(incident.get('remediation_suggestions', []))
                    break
            
            # Check persistent cache
            if incident_id in incident_cache:
                debug_info['found_in_persistent_cache'] = True
                if not debug_info['found_in_detected_incidents']:
                    debug_info['remediation_suggestions_count'] = len(incident_cache[incident_id].get('remediation_suggestions', []))
            else:
                debug_info['found_in_persistent_cache'] = False
                
        except ImportError:
            debug_info['detected_incidents_import_error'] = True
        
        # Check investigation sessions
        for session_id, session in self.active_sessions.items():
            if session.incident_id == incident_id:
                debug_info['found_in_sessions'] = True
                stored_incident = session.context.get('original_incident_data')
                if stored_incident:
                    debug_info['sessions_with_incident_data'] += 1
                    if not debug_info['found_in_detected_incidents']:
                        debug_info['remediation_suggestions_count'] = len(stored_incident.get('remediation_suggestions', []))
        
        logger.info(f"🔍 Debug info for incident {incident_id}: {debug_info}")
        return debug_info
    
    # AI Investigation Handlers
    
    async def _handle_ai_investigate(self, payload: Dict[str, Any], 
                                   action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AI investigation button clicks with immediate response"""
        incident_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        channel_id = payload.get("channel", {}).get("id")
        thread_ts = payload.get("message", {}).get("ts")
        
        # Extract investigation type from action_id
        action_id = action.get("action_id", "")
        investigation_type = action_id.replace("ai_investigate_", "")
        
        logger.info(f"🤖 Starting AI investigation: {investigation_type} for incident {incident_id}")
        
        # Immediate response to avoid Slack timeout (following successful PagerDuty pattern)
        investigation_type_display = investigation_type.replace('_', ' ').title()
        immediate_response = {
            "text": f"🤖 AI {investigation_type_display} Investigation started for `{incident_id}`",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🤖 AI {investigation_type_display} Investigation Started"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🔍 *Analyzing incident `{incident_id}` with Claude 3.7*\n\n⏳ Gathering data from Splunk and PagerDuty...\n*Started by:* <@{user_id}>\n*Status:* Investigation in progress"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "⏱️ This may take a couple of minutes • Results will appear below"
                        }
                    ]
                }
            ]
        }
        
        # Start background AI investigation (don't await to avoid timeout)
        asyncio.create_task(self._run_ai_investigation_background(
            incident_id=incident_id,
            investigation_type=investigation_type,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts
        ))
        
        return immediate_response
    
    async def _run_ai_investigation_background(self, incident_id: str, investigation_type: str,
                                             user_id: str, channel_id: str, thread_ts: str = None):
        """Run AI investigation in background and post results"""
        try:
            logger.info(f"🤖 Running background AI investigation for {incident_id}")
            
            # Start AI investigation
            result = await self.ai_investigator.start_ai_investigation(
                incident_id=incident_id,
                investigation_type=investigation_type,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts
            )
            
            if not result.get("success"):
                # Post error message
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"❌ AI Investigation Failed: {result.get('error', 'Unknown error')}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *AI Investigation Failed*\n\n{result.get('error', 'Unknown error')}\n\nPlease try again or check the logs for more details."
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🔄 Retry Investigation"
                                    },
                                    "action_id": f"ai_investigate_{investigation_type}",
                                    "value": incident_id,
                                    "style": "primary"
                                }
                            ]
                        }
                    ]
                )
                
        except Exception as e:
            logger.error(f"Error in background AI investigation: {e}")
            import traceback
            traceback.print_exc()
            
            # Post error message
            try:
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"❌ AI Investigation Error: {str(e)}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *AI Investigation Error*\n\n```{str(e)}```\n\nThis appears to be a system error. Please try again or contact support."
                            }
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🔄 Retry Investigation"
                                    },
                                    "action_id": f"ai_investigate_{investigation_type}",
                                    "value": incident_id,
                                    "style": "primary"
                                }
                            ]
                        }
                    ]
                )
            except Exception as slack_error:
                logger.error(f"Failed to post error message to Slack: {slack_error}")
    
    async def _handle_ai_run_query(self, payload: Dict[str, Any], 
                                 action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AI query execution requests"""
        session_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        
        # Get the AI investigation session
        session = self.ai_investigator.get_investigation_session(session_id)
        if not session:
            return {
                "text": "❌ Investigation session not found. Please start a new AI investigation."
            }
        
        return {
            "text": "🤖 Please specify what query you'd like me to run by @mentioning me in this thread."
        }
    
    async def _handle_ai_get_data(self, payload: Dict[str, Any], 
                                action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AI data gathering requests"""
        session_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        channel_id = payload.get("channel", {}).get("id")
        
        # Get the AI investigation session
        session = self.ai_investigator.get_investigation_session(session_id)
        if not session:
            return {
                "text": "❌ Investigation session not found. Please start a new AI investigation."
            }
        
        # Ask AI to gather more data
        message = "Please gather more data about this incident. What additional information would be helpful?"
        
        result = await self.ai_investigator.handle_ai_chat(
            message=message,
            user_id=user_id,
            channel_id=channel_id,
            incident_id=session.get('incident_id')
        )
        
        if result.get("success"):
            return {
                "text": "🤖 AI is gathering more data about the incident..."
            }
        else:
            return {
                "text": f"❌ Error getting more data: {result.get('error', 'Unknown error')}"
            }
    
    def _get_pagerduty_incident_id(self, internal_incident_id: str) -> Optional[str]:
        """
        Get the PagerDuty incident ID for an internal incident ID.
        
        Args:
            internal_incident_id: Our internal incident ID (e.g., INC-20250811121551-AWSCloudTrailErrors)
            
        Returns:
            The actual PagerDuty incident ID (e.g., Q06NQPEVC6328E) or None if not found
        """
        try:
            # Try to find the mapping in the detected_incidents global list
            from run_api import detected_incidents, incident_cache
            
            # First check detected_incidents
            for incident in detected_incidents:
                if incident.get('id') == internal_incident_id:
                    pagerduty_id = incident.get('pagerduty_incident_id')
                    if pagerduty_id:
                        logger.info(f"Found PagerDuty incident {pagerduty_id} for internal ID {internal_incident_id}")
                        return pagerduty_id
                    break
            
            # Also check the incident_cache
            incident_data = incident_cache.get(internal_incident_id)
            if incident_data:
                pagerduty_id = incident_data.get('pagerduty_incident_id')
                if pagerduty_id:
                    logger.info(f"Found cached PagerDuty incident {pagerduty_id} for internal ID {internal_incident_id}")
                    return pagerduty_id
            
            logger.warning(f"No PagerDuty incident ID found for internal ID {internal_incident_id}")
            return None
            
        except ImportError:
            logger.warning("Could not import run_api to check detected_incidents")
            return None
        except Exception as e:
            logger.error(f"Error getting PagerDuty incident ID: {e}")
            return None
    
    def _get_pagerduty_app_host(self) -> str:
        """Get the PagerDuty app host URL"""
        return os.getenv('PAGERDUTY_APP_HOST', 'https://dakozlov.pagerduty.com')

    async def _handle_ai_focus_incident(self, payload: Dict[str, Any], 
                                      action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AI focus on specific incident"""
        value = action.get("value", "")
        if "|" in value:
            session_id, incident_id = value.split("|", 1)
        else:
            return {
                "text": "❌ Invalid focus request format"
            }
        
        user_id = payload.get("user", {}).get("id")
        channel_id = payload.get("channel", {}).get("id")
        
        # Ask AI to focus on the specific incident
        message = f"Please focus our investigation on incident {incident_id}. What should we investigate first?"
        
        result = await self.ai_investigator.handle_ai_chat(
            message=message,
            user_id=user_id,
            channel_id=channel_id,
            incident_id=incident_id
        )
        
        if result.get("success"):
            return {
                "text": f"🤖 AI is now focusing on incident `{incident_id}`"
            }
        else:
            return {
                "text": f"❌ Error focusing on incident: {result.get('error', 'Unknown error')}"
            }
    
    async def _handle_ai_continue_chat(self, payload: Dict[str, Any], 
                                     action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AI continue chat requests"""
        session_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        
        # Get the AI investigation session
        session = self.ai_investigator.get_investigation_session(session_id)
        if not session:
            return {
                "text": "❌ Investigation session not found. Please start a new AI investigation."
            }
        
        return {
            "text": f"💬 @mention me in this thread to continue our investigation conversation, <@{user_id}>!\n\nFor example:\n• `@incident-bot What should we check next?`\n• `@incident-bot Can you run a query to find related errors?`\n• `@incident-bot What's the root cause of this issue?`"
        }
    
    async def _handle_ai_get_more_data(self, payload: Dict[str, Any], 
                                     action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle AI get more data requests - allows appending to the investigation"""
        session_id = action.get("value")
        user_id = payload.get("user", {}).get("id")
        channel_id = payload.get("channel", {}).get("id")
        thread_ts = payload.get("message", {}).get("ts")
        
        # Get the AI investigation session
        session = self.ai_investigator.get_investigation_session(session_id)
        if not session:
            return {
                "text": "❌ Investigation session not found. Please start a new AI investigation."
            }
        
        # Ask AI to gather more data with a specific prompt
        message = "Please gather more data about this incident. What additional MCP tools should we use to get deeper insights? Focus on areas we haven't explored yet."
        
        # Start background task to handle the follow-up
        asyncio.create_task(self._run_ai_followup_background(
            session_id=session_id,
            message=message,
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts
        ))
        
        return {
            "text": "📊 Gathering more data about the incident...",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "📊 *Gathering More Data*\n\n🔍 Asking AI to identify additional data sources and run more MCP tools...\n⏳ This may take a couple of minutes"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Requested by <@{user_id}> • Results will appear below"
                        }
                    ]
                }
            ]
        }
    
    async def _run_ai_followup_background(self, session_id: str, message: str,
                                        user_id: str, channel_id: str, thread_ts: str = None):
        """Run AI follow-up in background and post results"""
        try:
            logger.info(f"🤖 Running AI follow-up for session {session_id}")
            
            # Use the MCP AI investigator's chat handler
            result = await self.ai_investigator.handle_ai_chat(
                message=message,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                session_id=session_id
            )
            
            if not result.get("success"):
                # Post error message
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"❌ AI follow-up failed: {result.get('error', 'Unknown error')}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *AI Follow-up Failed*\n\n{result.get('error', 'Unknown error')}\n\nPlease try again or @mention me directly."
                            }
                        }
                    ]
                )
                
        except Exception as e:
            logger.error(f"Error in AI follow-up: {e}")
            # Post error message
            try:
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"❌ AI follow-up error: {str(e)}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *AI Follow-up Error*\n\n```{str(e)}```\n\nPlease try @mentioning me directly."
                            }
                        }
                    ]
                )
            except Exception as slack_error:
                logger.error(f"Failed to post follow-up error message to Slack: {slack_error}")


# Test function
async def test_interactive_investigator():
    """Test the interactive investigator"""
    print("🧪 Testing Interactive Slack Investigator")
    print("=" * 50)
    
    # This would require actual Slack bot token and MCP clients
    print("✅ Interactive investigator module loaded successfully")
    print("💡 To use: Initialize with bot token and connected MCP clients")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_interactive_investigator())