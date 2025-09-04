#!/usr/bin/env python3
"""
Enhanced Slack Integration
==========================

Comprehensive Slack integration that combines:
- Interactive incident investigation
- Real-time MCP server queries
- Collaborative incident resolution
- Rich interactive components
"""

import asyncio
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import hmac
import hashlib
import time
import aiohttp

from integrations.interactive_slack_investigator import InteractiveSlackInvestigator
from integrations.slack_bot import SlackBot
from integrations.real_splunk_mcp_client import SplunkIncidentClient
from integrations.pagerduty_client import PagerDutyIncidentClient

logger = logging.getLogger(__name__)


class EnhancedSlackIntegration:
    """
    Enhanced Slack integration with interactive investigation capabilities.
    
    Features:
    - Interactive incident investigation
    - Real-time Splunk queries from Slack
    - PagerDuty incident management
    - Collaborative workflows
    - Rich notifications
    """
    
    def __init__(self, bot_token: str, signing_secret: str, 
                 splunk_client: Optional[SplunkIncidentClient] = None, 
                 pagerduty_client: Optional[PagerDutyIncidentClient] = None):
        """
        Initialize enhanced Slack integration.
        
        Args:
            bot_token: Slack bot token
            signing_secret: Slack signing secret
            splunk_client: Connected Splunk MCP client (optional)
            pagerduty_client: Connected PagerDuty MCP client (optional)
        """
        self.bot_token = bot_token
        self.signing_secret = signing_secret
        self.splunk_client = splunk_client
        self.pagerduty_client = pagerduty_client
        
        # Initialize components
        self.slack_bot = SlackBot(bot_token, signing_secret)
        self.investigator = InteractiveSlackInvestigator(
            bot_token, splunk_client, pagerduty_client
        )
        
        # Command routing
        self.command_routes = {
            "/investigate": self.investigator.handle_slash_command,
            "/query": self.investigator.handle_slash_command,
            "/pagerduty": self.investigator.handle_slash_command,
            "/resolve": self.investigator.handle_slash_command,
            "/incident": self.slack_bot.handle_slash_command
        }
    
    def setup_fastapi_routes(self, app: FastAPI):
        """Setup FastAPI routes for Slack integration"""
        
        @app.post("/slack/commands")
        async def handle_slack_commands(request: Request):
            """Handle Slack slash commands"""
            try:
                # Verify Slack signature
                if not await self._verify_slack_signature(request):
                    raise HTTPException(status_code=401, detail="Invalid signature")
                
                # Parse form data
                form_data = await request.form()
                
                command = form_data.get("command")
                text = form_data.get("text", "")
                user_id = form_data.get("user_id")
                channel_id = form_data.get("channel_id")
                trigger_id = form_data.get("trigger_id")
                response_url = form_data.get("response_url")
                
                logger.info(f"Slack command: {command} from {user_id} in {channel_id}")
                
                # Route to appropriate handler
                handler = self.command_routes.get(command)
                if handler:
                    if command in ["/investigate", "/query", "/pagerduty", "/resolve"]:
                        # Interactive investigator commands
                        subcommand = text.split()[0] if text else command.replace("/", "")
                        return await handler(subcommand, text, user_id, channel_id, trigger_id)
                    else:
                        # Standard bot commands
                        return await handler(command, text, user_id, channel_id, response_url)
                else:
                    return JSONResponse({
                        "response_type": "ephemeral",
                        "text": f"Unknown command: {command}"
                    })
                    
            except Exception as e:
                logger.error(f"Error handling Slack command: {e}")
                return JSONResponse({
                    "response_type": "ephemeral",
                    "text": "An error occurred processing your command."
                })
        
        @app.post("/slack/interactions")
        async def handle_slack_interactions(request: Request):
            """Handle Slack interactive components"""
            try:
                # Verify Slack signature
                if not await self._verify_slack_signature(request):
                    raise HTTPException(status_code=401, detail="Invalid signature")
                
                # Parse payload
                form_data = await request.form()
                payload = json.loads(form_data.get("payload", "{}"))
                
                logger.info(f"Slack interaction: {payload.get('type')} from {payload.get('user', {}).get('id')}")
                
                # Check if this is an AI investigation action that needs special handling
                action_id = None
                if payload.get("type") == "block_actions" and payload.get("actions"):
                    action_id = payload["actions"][0].get("action_id")
                
                # Handle AI investigation actions asynchronously to avoid 3-second timeout
                if action_id and action_id.startswith("ai_investigate_"):
                    logger.info(f"🤖 Handling AI investigation action asynchronously: {action_id}")
                    
                    # Return immediate acknowledgment
                    incident_id = payload["actions"][0].get("value")
                    investigation_type = action_id.replace("ai_investigate_", "")
                    user_id = payload.get("user", {}).get("id")
                    channel_id = payload.get("channel", {}).get("id")
                    
                    # Get thread_ts from the message
                    thread_ts = payload.get("message", {}).get("ts")
                    
                    # Send immediate acknowledgment via response_url
                    response_url = payload.get("response_url")
                    if response_url:
                        immediate_response = {
                            "response_type": "ephemeral",
                            "replace_original": False,
                            "text": f"🤖 AI {investigation_type.replace('_', ' ').title()} Investigation started for `{incident_id}`",
                            "blocks": [
                                {
                                    "type": "header",
                                    "text": {
                                        "type": "plain_text",
                                        "text": f"🤖 AI {investigation_type.replace('_', ' ').title()} Investigation Started"
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
                        
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.post(response_url, json=immediate_response) as resp:
                                    if resp.status == 200:
                                        logger.info("✅ Sent immediate AI investigation acknowledgment")
                                    else:
                                        logger.error(f"❌ Failed to send immediate acknowledgment: {resp.status}")
                        except Exception as e:
                            logger.error(f"❌ Error sending immediate acknowledgment: {e}")
                    
                    # Start AI investigation in background (don't await)
                    logger.info(f"🤖 Running background AI investigation for {incident_id}")
                    asyncio.create_task(self._run_ai_investigation_background(
                        incident_id, investigation_type, user_id, channel_id, thread_ts
                    ))
                    
                    # Return immediate HTTP 200 OK acknowledgment
                    return JSONResponse(content={})
                
                # For non-AI actions, handle normally
                response = await self.investigator.handle_interaction(payload)
                logger.info(f"🔧 Slack interaction response: {json.dumps(response, indent=2)}")
                
                # According to Slack documentation, we should use response_url for message updates
                response_url = payload.get("response_url")
                logger.info(f"🔧 Response URL present: {response_url is not None}")
                
                if response_url and (response.get("text") or response.get("blocks")):
                    try:
                        # ALL actions now send ephemeral responses to preserve original message
                        # This includes "Start Investigation" which will add content beneath
                        update_payload = {
                            "response_type": "ephemeral",
                            "replace_original": False
                        }
                        
                        if "text" in response:
                            update_payload["text"] = response["text"]
                        if "blocks" in response:
                            update_payload["blocks"] = response["blocks"]
                        else:
                            update_payload["text"] = "Action completed"
                        
                        logger.info(f"🔧 Updating message via response_url (ephemeral response to preserve original)")
                        
                        async with aiohttp.ClientSession() as session:
                            async with session.post(response_url, json=update_payload) as resp:
                                response_text = await resp.text()
                                if resp.status == 200:
                                    logger.info("✅ Successfully updated message via response_url")
                                    # Return acknowledgment response (empty 200 OK)
                                    return JSONResponse(content={})
                                else:
                                    logger.error(f"❌ Failed to update message via response_url: {resp.status} - {response_text}")
                                    # Fall back to using Slack Web API
                                    return await self._fallback_to_web_api(payload, response)
                        
                    except Exception as e:
                        logger.error(f"❌ Error using response_url: {e}")
                        # Fall back to using Slack Web API
                        return await self._fallback_to_web_api(payload, response)
                else:
                    # No response_url or no content to update - return acknowledgment
                    logger.info("🔧 No response_url or content, returning acknowledgment")
                    return JSONResponse(content={})
                
            except Exception as e:
                logger.error(f"Error handling Slack interaction: {e}")
                return JSONResponse({"response_action": "clear"})
        
        @app.post("/slack/events")
        async def handle_slack_events(request: Request):
            """Handle Slack events (mentions, messages, etc.)"""
            try:
                # Parse event data first to check for URL verification
                event_data = await request.json()
                
                # Handle URL verification challenge BEFORE signature verification
                # This is needed during Slack app setup
                if event_data.get("type") == "url_verification":
                    logger.info("Handling Slack URL verification challenge")
                    return JSONResponse({"challenge": event_data.get("challenge")})
                
                # For all other events, verify Slack signature
                if not await self._verify_slack_signature(request):
                    raise HTTPException(status_code=401, detail="Invalid signature")
                
                # Handle app mentions and direct messages
                event = event_data.get("event", {})
                if event.get("type") == "app_mention":
                    await self._handle_app_mention(event)
                elif event.get("type") == "message" and event.get("channel_type") == "im":
                    await self._handle_direct_message(event)
                
                return JSONResponse({"status": "ok"})
                
            except Exception as e:
                logger.error(f"Error handling Slack event: {e}")
                return JSONResponse({"status": "error"})
    
    async def send_incident_notification(self, incident_data: Dict[str, Any], 
                                       channels: List[str]) -> Dict[str, bool]:
        """
        Send enhanced incident notification with investigation capabilities.
        
        Args:
            incident_data: Incident information
            channels: List of Slack channels to notify
            
        Returns:
            Dictionary mapping channel to success status
        """
        try:
            # Build enhanced notification blocks
            blocks = self._build_enhanced_incident_blocks(incident_data)
            
            results = {}
            for channel in channels:
                try:
                    response = await self.slack_bot.client.chat_postMessage(
                        channel=channel,
                        text=f"🚨 New Incident: {incident_data.get('title', 'Unknown')}",
                        blocks=blocks,
                        unfurl_links=False,
                        unfurl_media=False
                    )
                    
                    results[channel] = response["ok"]
                    if response["ok"]:
                        logger.info(f"Enhanced incident notification sent to {channel}")
                    
                except Exception as e:
                    logger.error(f"Error sending notification to {channel}: {e}")
                    results[channel] = False
            
            return results
            
        except Exception as e:
            logger.error(f"Error sending incident notifications: {e}")
            return {channel: False for channel in channels}
    
    async def _run_ai_investigation_background(self, incident_id: str, investigation_type: str, 
                                             user_id: str, channel_id: str, thread_ts: str = None):
        """Run AI investigation in background and post results when ready"""
        try:
            logger.info(f"🤖 Starting background AI investigation for {incident_id}")
            
            # Start AI investigation using the MCP AI investigator
            if hasattr(self.investigator, 'ai_investigator') and self.investigator.ai_investigator:
                result = await self.investigator.ai_investigator.start_ai_investigation(
                    incident_id=incident_id,
                    investigation_type=investigation_type,
                    user_id=user_id,
                    channel_id=channel_id,
                    thread_ts=thread_ts
                )
                
                if result.get("success"):
                    logger.info(f"✅ Background AI investigation completed for {incident_id}")
                else:
                    logger.error(f"❌ Background AI investigation failed for {incident_id}: {result.get('error')}")
                    
                    # Send error message to Slack
                    try:
                        await self.slack_bot.client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=thread_ts,
                            text=f"❌ AI Investigation failed for `{incident_id}`: {result.get('error', 'Unknown error')}"
                        )
                    except Exception as slack_error:
                        logger.error(f"❌ Failed to send error message to Slack: {slack_error}")
            else:
                logger.error("❌ AI investigator not available")
                
                # Send error message to Slack
                try:
                    await self.slack_bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=f"❌ AI Investigation is not available. Please check system configuration."
                    )
                except Exception as slack_error:
                    logger.error(f"❌ Failed to send error message to Slack: {slack_error}")
                    
        except Exception as e:
            logger.error(f"❌ Error in background AI investigation: {e}")
            
            # Send error message to Slack
            try:
                await self.slack_bot.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"❌ AI Investigation encountered an error: {str(e)}"
                )
            except Exception as slack_error:
                logger.error(f"❌ Failed to send error message to Slack: {slack_error}")
    
    async def _fallback_to_web_api(self, payload: Dict[str, Any], response: Dict[str, Any]) -> JSONResponse:
        """Fallback to using Slack Web API when response_url fails"""
        try:
            message = payload.get("message", {})
            channel_id = payload.get("channel", {}).get("id")
            message_ts = message.get("ts")
            
            if channel_id and message_ts:
                # Update the message using Slack Web API
                update_payload = {
                    "channel": channel_id,
                    "ts": message_ts
                }
                
                if "blocks" in response:
                    update_payload["blocks"] = response["blocks"]
                if "text" in response:
                    update_payload["text"] = response["text"]
                else:
                    # Add fallback text to avoid Slack warning
                    update_payload["text"] = "Message updated"
                
                logger.info(f"🔧 Fallback: Updating message via Web API: {channel_id}:{message_ts}")
                await self.slack_bot.client.chat_update(**update_payload)
                logger.info("✅ Successfully updated message via Web API fallback")
                
                # Return empty response to acknowledge the interaction
                return JSONResponse(content={})
            else:
                logger.warning("⚠️ Missing channel_id or message_ts for Web API fallback")
                # Return the response content directly as last resort
                slack_response = {}
                if "text" in response:
                    slack_response["text"] = response["text"]
                if "blocks" in response:
                    slack_response["blocks"] = response["blocks"]
                return JSONResponse(content=slack_response)
                
        except Exception as e:
            logger.error(f"❌ Error in Web API fallback: {e}")
            # Return the response content directly as last resort
            slack_response = {}
            if "text" in response:
                slack_response["text"] = response["text"]
            if "blocks" in response:
                slack_response["blocks"] = response["blocks"]
            return JSONResponse(content=slack_response)

    async def _verify_slack_signature(self, request: Request) -> bool:
        """Verify Slack request signature"""
        try:
            timestamp = request.headers.get("X-Slack-Request-Timestamp")
            signature = request.headers.get("X-Slack-Signature")
            
            if not timestamp or not signature:
                return False
            
            # Check timestamp (prevent replay attacks)
            if abs(time.time() - int(timestamp)) > 60 * 5:  # 5 minutes
                return False
            
            # Get request body
            body = await request.body()
            
            # Create signature
            sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
            expected_signature = "v0=" + hmac.new(
                self.signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            logger.error(f"Error verifying Slack signature: {e}")
            return False
    
    async def _handle_app_mention(self, event: Dict[str, Any]):
        """Handle app mentions in channels"""
        try:
            text = event.get("text", "")
            user = event.get("user")
            channel = event.get("channel")
            
            # Extract command from mention
            # Format: @bot_name command args
            parts = text.split()
            if len(parts) > 1:
                command = parts[1].lower()
                args = " ".join(parts[2:])
                
                if command == "investigate":
                    # Start investigation
                    if args:
                        await self.investigator.handle_slash_command(
                            "investigate", args, user, channel, None
                        )
                    else:
                        await self.slack_bot.client.chat_postMessage(
                            channel=channel,
                            text="Please provide an incident ID to investigate. Example: `@bot investigate INC-123`"
                        )
                
                elif command == "query":
                    # Run Splunk query
                    if args:
                        await self.investigator.handle_slash_command(
                            "query", args, user, channel, None
                        )
                    else:
                        await self.slack_bot.client.chat_postMessage(
                            channel=channel,
                            text="Please provide a Splunk query. Example: `@bot query search index=main error`"
                        )
                
                elif command == "help":
                    # Show help
                    await self.investigator.handle_slash_command(
                        "help", "", user, channel, None
                    )
                
                elif command == "status":
                    # Show system status
                    await self._handle_status_command(user, channel, thread_ts)
                
                else:
                    # Check if this is an AI chat request (not a recognized command)
                    # Treat as natural language conversation with AI
                    thread_ts = event.get("thread_ts")  # Check if in a thread
                    
                    # Use AI investigator for natural language processing
                    await self._handle_ai_mention(text, user, channel, thread_ts)
            else:
                # No specific command - treat as AI chat
                thread_ts = event.get("thread_ts")
                await self._handle_ai_mention(text, user, channel, thread_ts)
                
        except Exception as e:
            logger.error(f"Error handling app mention: {e}")
    
    async def _handle_ai_mention(self, text: str, user_id: str, channel_id: str, thread_ts: str = None):
        """Handle AI chat mentions"""
        try:
            logger.info(f"🤖 Handling AI mention from {user_id} in {channel_id}")
            
            # Ensure AI investigator is connected with retry logic
            if not self.investigator.ai_investigator.connected:
                logger.info("🔄 AI investigator not connected, attempting connection...")
                connected = await self.investigator.ai_investigator.connect()
                if not connected:
                    # Try one more time after a brief delay
                    logger.warning("⚠️ First connection attempt failed, retrying...")
                    await asyncio.sleep(2)
                    connected = await self.investigator.ai_investigator.connect()
                    
                if not connected:
                    await self.slack_bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text="❌ AI investigation is currently unavailable. The system may still be initializing. Please try running `/rca` first or try again in a few moments."
                    )
                    return
                else:
                    logger.info("✅ AI investigator connected successfully on retry")
            
            # Send immediate acknowledgment
            await self.slack_bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="🤖 Processing your request...",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🤖 *AI Assistant*\n\n⏳ Processing your request with Claude 3.7...\n*This may take a few seconds*"
                        }
                    }
                ]
            )
            
            # Handle AI chat in background
            asyncio.create_task(self._process_ai_chat_background(
                text, user_id, channel_id, thread_ts
            ))
            
        except Exception as e:
            logger.error(f"Error handling AI mention: {e}")
            await self.slack_bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"❌ Error processing AI request: {str(e)}"
            )
    
    async def _handle_status_command(self, user_id: str, channel_id: str, thread_ts: str = None):
        """Handle status command to show system initialization status"""
        try:
            # Check AI investigator connection status
            ai_connected = self.investigator.ai_investigator.connected if hasattr(self.investigator, 'ai_investigator') else False
            
            # Check MCP client connections
            splunk_connected = self.splunk_client is not None
            pagerduty_connected = self.pagerduty_client is not None
            
            # Build status message
            status_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🔍 *System Status*\n\n"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*AI Investigator:*\n{'✅ Connected' if ai_connected else '❌ Not Connected'}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Splunk MCP:*\n{'✅ Available' if splunk_connected else '❌ Not Available'}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*PagerDuty MCP:*\n{'✅ Available' if pagerduty_connected else '❌ Not Available'}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Slack Bot:*\n✅ Connected"
                        }
                    ]
                }
            ]
            
            # Add recommendations if not fully connected
            if not ai_connected:
                status_blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "💡 *Recommendation:* Run `/rca` command first to initialize all components, then try bot mentions."
                    }
                })
            
            await self.slack_bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=status_blocks
            )
            
        except Exception as e:
            logger.error(f"Error handling status command: {e}")
            await self.slack_bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"❌ Error checking system status: {str(e)}"
            )
    
    async def _process_ai_chat_background(self, text: str, user_id: str, channel_id: str, thread_ts: str = None):
        """Process AI chat in background"""
        try:
            # First try to handle as existing chat session
            result = await self.investigator.ai_investigator.handle_ai_chat(
                message=text,
                user_id=user_id,
                channel_id=channel_id,
                thread_ts=thread_ts
            )
            
            if not result.get("success"):
                # Check if no active session exists
                if "No active MCP AI investigation session found" in result.get('error', ''):
                    # Try to extract incident ID from the message or find recent incident
                    incident_id = await self._extract_or_find_incident_id(text, channel_id, thread_ts)
                    
                    if incident_id:
                        # Start a new investigation session
                        logger.info(f"🤖 Starting new AI investigation session for {incident_id} from direct mention")
                        
                        # Start AI investigation with general analysis
                        investigation_result = await self.investigator.ai_investigator.start_ai_investigation(
                            incident_id=incident_id,
                            investigation_type="root_cause",  # Default to root cause analysis
                            user_id=user_id,
                            channel_id=channel_id,
                            thread_ts=thread_ts
                        )
                        
                        if investigation_result.get("success"):
                            # Now try the chat again with the active session
                            chat_result = await self.investigator.ai_investigator.handle_ai_chat(
                                message=text,
                                user_id=user_id,
                                channel_id=channel_id,
                                thread_ts=thread_ts
                            )
                            
                            if not chat_result.get("success"):
                                await self.slack_bot.client.chat_postMessage(
                                    channel=channel_id,
                                    thread_ts=thread_ts,
                                    text=f"❌ AI chat failed after starting investigation: {chat_result.get('error', 'Unknown error')}"
                                )
                        else:
                            await self.slack_bot.client.chat_postMessage(
                                channel=channel_id,
                                thread_ts=thread_ts,
                                text=f"❌ Failed to start AI investigation: {investigation_result.get('error', 'Unknown error')}"
                            )
                    else:
                        # No incident found - provide helpful guidance
                        await self.slack_bot.client.chat_postMessage(
                            channel=channel_id,
                            thread_ts=thread_ts,
                            text="🤖 Hi! I'm your AI incident investigation assistant.",
                            blocks=[
                                {
                                    "type": "section",
                                    "text": {
                                        "type": "mrkdwn",
                                        "text": "🤖 *AI Incident Investigation Assistant*\n\nI can help you:\n• Investigate incidents with AI-powered analysis\n• Run Splunk queries and analyze results\n• Manage PagerDuty incidents\n• Provide root cause analysis\n\n*To get started:*\n• Mention an incident ID in your message (e.g., `INC-12345`)\n• Use `/investigate <incident-id>` to start an investigation\n• Or ask me about a specific incident in a thread"
                                    }
                                }
                            ]
                        )
                else:
                    # Other error
                    await self.slack_bot.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=f"❌ AI chat failed: {result.get('error', 'Unknown error')}",
                        blocks=[
                            {
                                "type": "section",
                                "text": {
                                    "type": "mrkdwn",
                                    "text": f"❌ *AI Chat Failed*\n\n{result.get('error', 'Unknown error')}\n\nTry starting an investigation with `/investigate <incident-id>` first."
                                }
                            }
                        ]
                    )
            
        except Exception as e:
            logger.error(f"Error in AI chat background processing: {e}")
            await self.slack_bot.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"❌ AI processing error: {str(e)}"
            )
    
    async def _extract_or_find_incident_id(self, text: str, channel_id: str, thread_ts: str = None) -> Optional[str]:
        """Extract incident ID from text or find most recent incident in channel"""
        import re
        
        # Try to extract incident ID from the message
        # Look for patterns like INC-12345, INC-PD-12345, etc.
        incident_patterns = [
            r'INC-[A-Z0-9-]+',
            r'incident[:\s]+([A-Z0-9-]+)',
            r'#([A-Z0-9-]+)',
        ]
        
        for pattern in incident_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                incident_id = matches[0] if isinstance(matches[0], str) else matches[0]
                if incident_id.startswith('INC-'):
                    return incident_id
                else:
                    return f"INC-{incident_id}"
        
        # If no incident ID found in text, try to find the most recent incident
        # This could be from the incident cache or recent notifications in the channel
        try:
            # Import here to avoid circular imports
            from ..run_api import incident_cache
            
            if incident_cache:
                # Get the most recent incident
                recent_incidents = sorted(incident_cache.values(), 
                                        key=lambda x: x.get('created_at', ''), 
                                        reverse=True)
                if recent_incidents:
                    return recent_incidents[0].get('id')
        except Exception as e:
            logger.warning(f"Could not access incident cache: {e}")
        
        return None

    async def _handle_direct_message(self, event: Dict[str, Any]):
        """Handle direct messages to the bot"""
        try:
            text = event.get("text", "")
            user = event.get("user")
            channel = event.get("channel")
            
            # Parse as command
            parts = text.split()
            if parts:
                command = parts[0].lower()
                args = " ".join(parts[1:])
                
                if command in ["investigate", "query", "pagerduty", "resolve", "help"]:
                    await self.investigator.handle_slash_command(
                        command, args, user, channel, None
                    )
                else:
                    await self.slack_bot.client.chat_postMessage(
                        channel=channel,
                        text=f"Unknown command: `{command}`. Try `help` for available commands."
                    )
            else:
                await self.slack_bot.client.chat_postMessage(
                    channel=channel,
                    text="Hi! I can help you investigate incidents. Try `help` for available commands."
                )
                
        except Exception as e:
            logger.error(f"Error handling direct message: {e}")
    
    def _build_enhanced_incident_blocks(self, incident_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build enhanced incident notification blocks with investigation capabilities"""
        incident_id = incident_data.get('id', 'Unknown')
        title = incident_data.get('title', 'Unknown Incident')
        description = incident_data.get('description', 'No description available')
        severity = incident_data.get('severity', 'MEDIUM')
        
        # Severity emoji mapping
        severity_emojis = {
            'CRITICAL': '🔴',
            'HIGH': '🟠',
            'MEDIUM': '🟡',
            'LOW': '🟢'
        }
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 New Incident Detected"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{title}*\n{description[:200]}{'...' if len(description) > 200 else ''}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*ID:*\n`{incident_id}`"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:*\n{severity_emojis.get(severity, '⚪')} {severity}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Source:*\n{incident_data.get('source', 'Unknown')}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🔍 Investigation Actions:*"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🔍 Start Investigation"
                        },
                        "style": "primary",
                        "action_id": "start_investigation",
                        "value": incident_id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "📊 Quick Queries"
                        },
                        "action_id": "show_quick_queries",
                        "value": incident_id
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🚨 Create PD Incident"
                        },
                        "action_id": "create_pagerduty_incident",
                        "value": incident_id
                    }
                ]
            }
        ]
        
        # Add remediation suggestions if available
        remediation_suggestions = incident_data.get('remediation_suggestions', [])
        if remediation_suggestions:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*🔧 Suggested Remediation Steps:*"
                }
            })
            
            # Add up to 3 top remediation suggestions
            for i, suggestion in enumerate(remediation_suggestions[:3]):
                risk_emoji = {
                    'LOW': '🟢',
                    'MEDIUM': '🟡', 
                    'HIGH': '🟠',
                    'NONE': '⚪'
                }.get(suggestion.get('risk_level', 'MEDIUM'), '🟡')
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{risk_emoji} *{suggestion.get('title', 'Remediation Step')}*\n" +
                               f"_{suggestion.get('description', 'No description available')}_\n" +
                               f"*Risk:* {suggestion.get('risk_level', 'MEDIUM')} | " +
                               f"*Time:* {suggestion.get('estimated_time', 'Unknown')}"
                    }
                })
                
                # Add detailed instructions if available
                instructions = suggestion.get('detailed_instructions', [])
                if instructions:
                    instruction_text = "\n".join([f"• {inst}" for inst in instructions[:3]])
                    if len(instructions) > 3:
                        instruction_text += f"\n• ... and {len(instructions) - 3} more steps"
                    
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Steps:*\n{instruction_text}"
                        }
                    })
            
            if len(remediation_suggestions) > 3:
                blocks.append({
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"💡 {len(remediation_suggestions) - 3} additional remediation suggestions available. Click 'Start Investigation' for full details."
                        }
                    ]
                })
        
        # Add quick commands section
        blocks.extend([
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*💡 Quick Commands:*\n" +
                           f"• `/investigate {incident_id}` - Start investigation session\n" +
                           f"• `/query search index=main error` - Run Splunk query\n" +
                           f"• `/pagerduty create \"{title}\"` - Create PagerDuty incident"
                }
            }
        ])
        
        return blocks


# Test function
async def test_enhanced_slack_integration():
    """Test the enhanced Slack integration"""
    print("🧪 Testing Enhanced Slack Integration")
    print("=" * 50)
    
    print("✅ Enhanced Slack integration module loaded successfully")
    print("💡 Features available:")
    print("   - Interactive incident investigation")
    print("   - Real-time Splunk queries from Slack")
    print("   - PagerDuty incident management")
    print("   - Collaborative workflows")
    print("   - Rich interactive components")
    
    return True

if __name__ == "__main__":
    asyncio.run(test_enhanced_slack_integration())