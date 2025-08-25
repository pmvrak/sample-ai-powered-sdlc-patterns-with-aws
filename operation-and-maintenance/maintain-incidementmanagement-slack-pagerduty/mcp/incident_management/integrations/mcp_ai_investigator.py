#!/usr/bin/env python3
"""
MCP-Based AI Incident Investigator
==================================

A proper MCP client implementation for AI-powered incident investigation
following best practices from the MCP TypeScript SDK.

Features:
- Proper MCP client lifecycle management
- Tool discovery and validation
- Structured tool calls with error handling
- Resource management and cleanup
- Streaming responses for real-time updates
"""

import asyncio
import logging
import json
from typing import Dict, List, Any, Optional, AsyncGenerator
from datetime import datetime
from contextlib import AsyncExitStack
import boto3
import os

from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from mcp.types import (
    CallToolRequest, 
    CallToolResult, 
    ListToolsRequest,
    Tool,
    TextContent,
    ImageContent
)

logger = logging.getLogger(__name__)


class MCPAIInvestigator:
    """
    MCP-based AI Incident Investigator following MCP best practices.
    
    This class acts as a proper MCP client that:
    1. Manages connections to multiple MCP servers (Splunk, PagerDuty)
    2. Discovers available tools dynamically
    3. Makes structured tool calls
    4. Handles errors gracefully
    5. Provides streaming responses
    
    ARCHITECTURAL NOTE:
    The current implementation has too many wrapper layers:
    Claude -> MCPAIInvestigator -> PagerDutyIncidentClient -> PagerDutyMCPClient -> MCP Server
    
    This should be simplified to:
    Claude -> MCPAIInvestigator -> MCP Server (direct connection)
    
    The wrapper classes (PagerDutyIncidentClient) add complexity without much value
    and make error handling and method discovery more difficult.
    """
    
    def __init__(self, slack_client=None, splunk_client=None, pagerduty_client=None):
        """
        Initialize the MCP AI Investigator.
        
        Args:
            slack_client: Slack bot client for messaging
            splunk_client: Existing Splunk MCP client (optional)
            pagerduty_client: Existing PagerDuty MCP client (optional)
        """
        self.slack_client = slack_client
        self.existing_splunk_client = splunk_client  # Use existing clients if provided
        self.existing_pagerduty_client = pagerduty_client
        
        # MCP client sessions
        self.splunk_session: Optional[ClientSession] = None
        self.pagerduty_session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None
        
        # Tool discovery cache
        self.available_tools: Dict[str, List[Tool]] = {}
        self.tool_capabilities: Dict[str, Dict[str, Any]] = {}
        
        # Connection state
        self.connected = False
        self._connection_lock = asyncio.Lock()
        
        # Active investigation sessions
        self.active_investigations: Dict[str, Dict[str, Any]] = {}
        
        # AWS Bedrock configuration
        self.bedrock_model_id = os.getenv('BEDROCK_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0')
        self.bedrock_region = os.getenv('AWS_REGION', 'us-east-1')
        self.ai_investigation_enabled = os.getenv('ENABLE_AI_INVESTIGATION', 'true').lower() == 'true'
        
        # Initialize Bedrock client
        try:
            self.bedrock_client = boto3.client(
                'bedrock-runtime',
                region_name=self.bedrock_region
            )
            logger.info(f"✅ Initialized Bedrock client for region {self.bedrock_region}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Bedrock client: {e}")
            self.bedrock_client = None
        
        # Investigation templates with MCP context
        self.investigation_templates = {
            "root_cause": """🔍 **Root Cause Investigation for {incident_id}**

**Incident Overview:**
• **Title:** {title}
• **Description:** {description}  
• **Severity:** {severity}
• **Affected Systems:** {affected_systems}
• **Created:** {created_at}
• **Event Count:** {event_count}

I have access to the following MCP tools:
{available_tools}

**Investigation Plan:**
1. 📊 Gather relevant log data and metrics using MCP tools
2. 🔍 Analyze patterns and correlations in the data
3. 🎯 Identify the root cause based on evidence
4. ⚠️ Assess impact and affected components
5. 🛠️ Provide specific remediation steps

Please start the investigation by using the most relevant MCP tools to gather data about this incident. Format your response for Slack with proper markdown, emojis, and code blocks for technical details.""",
            
            "performance": """⚡ **Performance Investigation for {incident_id}**

**Incident Overview:**
• **Title:** {title}
• **Description:** {description}
• **Affected Systems:** {affected_systems}
• **Event Count:** {event_count}

Available MCP Tools:
{available_tools}

**Performance Analysis Plan:**
1. 📈 Gather performance metrics and resource utilization data
2. 🔍 Identify bottlenecks and resource constraints
3. 📊 Analyze trends and patterns in performance data
4. ⚡ Recommend optimization strategies
5. 🛠️ Provide specific tuning recommendations

Please begin by using MCP tools to collect performance data. Format your analysis for Slack with metrics in `code blocks` and clear visual indicators.""",
            
            "error_analysis": """🚨 **Error Analysis for {incident_id}**

**Incident Overview:**
• **Title:** {title}
• **Description:** {description}
• **Error Count:** {event_count} events
• **Affected Systems:** {affected_systems}

Available MCP Tools:
{available_tools}

**Error Analysis Strategy:**
1. 📊 Categorize and count error types using MCP tools
2. 🔍 Identify error patterns and correlations
3. 🎯 Trace error sources and propagation paths
4. ⚠️ Assess error impact and severity
5. 🛠️ Recommend specific remediation actions

Please start by gathering error data using the available MCP tools. Present findings with error counts, patterns, and specific log excerpts in `code blocks`.""",
            
            "security": """🛡️ **Security Investigation for {incident_id}**

**Incident Overview:**
• **Title:** {title}
• **Description:** {description}
• **Affected Systems:** {affected_systems}
• **Event Count:** {event_count}

Available MCP Tools:
{available_tools}

**Security Analysis Framework:**
1. 🔍 Gather security event data and access logs
2. 🚨 Identify potential indicators of compromise (IOCs)
3. 📊 Analyze authentication and authorization patterns
4. ⚠️ Assess security impact and data exposure risk
5. 🛠️ Recommend immediate containment and remediation steps

Please begin security analysis using MCP tools. Include specific security events, IP addresses, user accounts, and timestamps in `code blocks` for evidence."""
        }
    
    async def connect(self) -> bool:
        """
        Connect to MCP servers following best practices.
        Uses existing clients if provided, otherwise creates new connections.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        async with self._connection_lock:
            if self.connected:
                return True
            
            try:
                logger.info("🔌 Connecting to MCP servers...")
                
                # Use existing clients if available
                if self.existing_splunk_client and self.existing_pagerduty_client:
                    logger.info("✅ Using existing MCP client connections")
                    self.connected = True
                    
                    # Discover tools from existing clients
                    await self._discover_tools_from_existing_clients()
                    
                    logger.info("✅ Successfully connected using existing MCP clients")
                    return True
                
                # Create exit stack for resource management
                self.exit_stack = AsyncExitStack()
                
                # Connect to Splunk MCP server
                await self._connect_splunk_server()
                
                # Connect to PagerDuty MCP server
                await self._connect_pagerduty_server()
                
                # Discover available tools
                await self._discover_tools()
                
                self.connected = True
                logger.info("✅ Successfully connected to all MCP servers")
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to connect to MCP servers: {e}")
                await self.disconnect()
                return False
    
    async def _discover_tools_from_existing_clients(self):
        """Discover tools from existing MCP clients"""
        try:
            # Create mock tool lists for existing clients (they don't have list_tools method)
            if self.existing_splunk_client:
                # Define available Splunk tools with detailed descriptions
                splunk_tools = [
                    {
                        'name': 'get_splunk_results',
                        'description': 'Execute Splunk queries to search AWS CloudTrail, CloudWatch, and application logs. Use SPL syntax with index=main. Examples: "search index=main sourcetype=aws:cloudtrail errorCode=AccessDenied | stats count by eventSource" or "search index=main error | head 10"'
                    },
                    {
                        'name': 'search_aws_sourcetypes',
                        'description': 'List available AWS data sources. Use awssourcetype parameter to filter (e.g., "aws:cloudtrail"). Returns sourcetypes like aws:cloudtrail, aws:cloudwatch, aws:s3accesslogs.'
                    },
                    {
                        'name': 'get_splunk_fields',
                        'description': 'Get available fields for a specific sourcetype. Use sourcetype parameter (e.g., "aws:cloudtrail"). Returns fields like eventName, errorCode, userIdentity, sourceIPAddress.'
                    },
                    {
                        'name': 'get_splunk_lookups',
                        'description': 'Get lookup tables available for a sourcetype. Use sourcetype parameter. Returns lookup tables for data enrichment like aws_services, error_codes.'
                    },
                    {
                        'name': 'get_splunk_lookup_values',
                        'description': 'Get values from a specific lookup table. Use lookup_name parameter. Returns the actual values stored in the lookup table for enrichment.'
                    }
                ]
                self.available_tools['splunk'] = splunk_tools
                logger.info(f"✅ Discovered {len(splunk_tools)} Splunk tools from existing client")
            
            # Get tools from existing PagerDuty client  
            if self.existing_pagerduty_client:
                # Define available PagerDuty tools with detailed descriptions
                pagerduty_tools = [
                    {
                        'name': 'list_incidents',
                        'description': 'List PagerDuty incidents with optional filtering by status, urgency, service, etc. Use limit parameter to control results (default 25).'
                    },
                    {
                        'name': 'get_incident',
                        'description': 'Get detailed information about a specific PagerDuty incident by incident_id. Returns full incident details including status, service, assignments.'
                    },
                    {
                        'name': 'resolve_incident',
                        'description': 'Resolve a PagerDuty incident by setting status to resolved. Use incident_id and optional resolution_note parameters.'
                    },
                    {
                        'name': 'update_incident',
                        'description': 'Update a PagerDuty incident status (acknowledged, resolved). Use incident_id, status, and optional resolution_note parameters.'
                    },
                    {
                        'name': 'manage_incidents',
                        'description': 'Bulk manage multiple PagerDuty incidents. Use incident_ids array and status parameter to update multiple incidents at once.'
                    },
                    {
                        'name': 'add_note_to_incident',
                        'description': 'Add a note/comment to a PagerDuty incident. Use incident_id and note parameters. Useful for documenting investigation findings.'
                    },
                    {
                        'name': 'list_services',
                        'description': 'List all PagerDuty services. Returns service IDs, names, and details needed for incident creation and management.'
                    },
                    {
                        'name': 'get_service',
                        'description': 'Get detailed information about a specific PagerDuty service by service_id.'
                    },
                    {
                        'name': 'create_incident',
                        'description': 'Create a new PagerDuty incident. Use title, service_id, urgency (high/low), and optional description parameters.'
                    },
                    {
                        'name': 'list_oncalls',
                        'description': 'List current on-call schedules and who is currently on-call for different services and escalation policies.'
                    },
                    {
                        'name': 'list_tools',
                        'description': 'List all available PagerDuty MCP tools with their names and descriptions.'
                    }
                ]
                self.available_tools['pagerduty'] = pagerduty_tools
                logger.info(f"✅ Discovered {len(pagerduty_tools)} PagerDuty tools from existing client")
                
        except Exception as e:
            logger.error(f"❌ Failed to discover tools from existing clients: {e}")
            raise
    
    async def _connect_splunk_server(self):
        """Connect to the Splunk MCP server"""
        try:
            from pathlib import Path
            
            # Get the absolute path to the server directory
            current_dir = Path(__file__).parent.parent
            server_dir = current_dir / "server"
            server_script = server_dir / "splunk-server.py"
            
            if not server_script.exists():
                raise FileNotFoundError(f"Splunk server script not found: {server_script}")
            
            logger.info(f"Using Splunk server at: {server_dir}")
            
            # Create server parameters
            server_params = StdioServerParameters(
                command="python",
                args=[str(server_script)],
                cwd=str(server_dir),
                env=None
            )
            
            # Connect using stdio
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            # Create session
            self.splunk_session = await self.exit_stack.enter_async_context(
                ClientSession(stdio_transport[0], stdio_transport[1])
            )
            
            # Initialize the session
            await self.splunk_session.initialize()
            
            logger.info("✅ Connected to Splunk MCP server")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Splunk MCP server: {e}")
            raise
    
    async def _connect_pagerduty_server(self):
        """Connect to the PagerDuty MCP server"""
        try:
            from pathlib import Path
            
            # Get the absolute path to the PagerDuty server directory
            current_dir = Path(__file__).parent.parent
            pagerduty_dir = current_dir / "pagerduty-mcp-server"
            server_script = pagerduty_dir / "src" / "pagerduty_mcp" / "server.py"
            
            if not server_script.exists():
                raise FileNotFoundError(f"PagerDuty server script not found: {server_script}")
            
            logger.info(f"Using PagerDuty server at: {pagerduty_dir}")
            
            # Create server parameters
            server_params = StdioServerParameters(
                command="python",
                args=["-m", "pagerduty_mcp.server"],
                cwd=str(pagerduty_dir),
                env=None
            )
            
            # Connect using stdio
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            
            # Create session
            self.pagerduty_session = await self.exit_stack.enter_async_context(
                ClientSession(stdio_transport[0], stdio_transport[1])
            )
            
            # Initialize the session
            await self.pagerduty_session.initialize()
            
            logger.info("✅ Connected to PagerDuty MCP server")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to PagerDuty MCP server: {e}")
            raise
    
    async def _discover_tools(self):
        """Discover available tools from all connected MCP servers"""
        try:
            logger.info("🔍 Discovering available MCP tools...")
            
            # Discover Splunk tools
            if self.splunk_session:
                splunk_tools = await self.splunk_session.list_tools()
                self.available_tools['splunk'] = splunk_tools.tools
                logger.info(f"Found {len(splunk_tools.tools)} Splunk tools: {[t.name for t in splunk_tools.tools]}")
            
            # Discover PagerDuty tools
            if self.pagerduty_session:
                pagerduty_tools = await self.pagerduty_session.list_tools()
                self.available_tools['pagerduty'] = pagerduty_tools.tools
                logger.info(f"Found {len(pagerduty_tools.tools)} PagerDuty tools: {[t.name for t in pagerduty_tools.tools]}")
            
            # Build tool capabilities summary
            self._build_tool_capabilities()
            
            logger.info("✅ Tool discovery completed")
            
        except Exception as e:
            logger.error(f"❌ Failed to discover tools: {e}")
            raise
    
    def _build_tool_capabilities(self):
        """Build a summary of tool capabilities for Claude"""
        self.tool_capabilities = {}
        
        for server_name, tools in self.available_tools.items():
            capabilities = []
            for tool in tools:
                if isinstance(tool, dict):
                    # Tool is already in dict format (from existing clients)
                    capability = {
                        'name': tool['name'],
                        'description': tool['description'],
                        'server': server_name
                    }
                else:
                    # Tool is an MCP Tool object (from sessions)
                    capability = {
                        'name': tool.name,
                        'description': tool.description,
                        'server': server_name
                    }
                capabilities.append(capability)
            
            self.tool_capabilities[server_name] = capabilities
    
    async def disconnect(self):
        """Disconnect from all MCP servers and cleanup resources"""
        try:
            if self.exit_stack:
                await self.exit_stack.aclose()
                self.exit_stack = None
            
            self.splunk_session = None
            self.pagerduty_session = None
            self.connected = False
            
            logger.info("✅ Disconnected from all MCP servers")
            
        except Exception as e:
            logger.error(f"❌ Error during disconnect: {e}")
    
    async def start_ai_investigation(self, incident_id: str, investigation_type: str, 
                                   user_id: str, channel_id: str, thread_ts: str = None) -> Dict[str, Any]:
        """
        Start an AI-powered investigation session using MCP tools.
        
        Args:
            incident_id: ID of the incident to investigate
            investigation_type: Type of investigation (root_cause, performance, etc.)
            user_id: Slack user ID who started the investigation
            channel_id: Slack channel ID
            thread_ts: Thread timestamp for threaded conversation
            
        Returns:
            Dictionary with investigation session details
        """
        try:
            # Check if AI investigation is enabled
            if not self.ai_investigation_enabled:
                return {
                    "success": False,
                    "error": "AI Investigation is disabled. Set ENABLE_AI_INVESTIGATION=true to enable."
                }
            
            # Ensure MCP connections are established
            if not self.connected:
                connected = await self.connect()
                if not connected:
                    return {
                        "success": False,
                        "error": "Failed to connect to MCP servers"
                    }
            
            # Get incident data
            incident_data = await self._get_incident_data(incident_id)
            if not incident_data:
                return {
                    "success": False,
                    "error": f"Could not find incident data for {incident_id}"
                }
            
            # Create investigation session
            session_id = f"mcp_ai_inv_{incident_id}_{user_id}_{int(datetime.now().timestamp())}"
            
            # Create investigation session FIRST so conversation history is preserved
            self.active_investigations[session_id] = {
                'incident_id': incident_id,
                'incident_data': incident_data,
                'investigation_type': investigation_type,
                'user_id': user_id,
                'channel_id': channel_id,
                'thread_ts': thread_ts,
                'started_at': datetime.now().isoformat(),
                'conversation_history': [],
                'mcp_tool_calls': []
            }
            
            # Build enhanced prompt with MCP tool information
            initial_prompt = self._build_mcp_enhanced_prompt(
                investigation_type, incident_data
            )
            
            # Start conversation with Claude
            claude_response = await self._chat_with_claude(initial_prompt, session_id)
            if not claude_response or claude_response.startswith("❌"):
                return {
                    "success": False,
                    "error": f"Claude AI error: {claude_response}"
                }
            
            # Parse and execute any MCP tool calls suggested by Claude
            enhanced_response = await self._execute_mcp_tool_calls(claude_response, session_id, iteration=1)
            
            # Send response to Slack
            try:
                await self._send_investigation_response(
                    enhanced_response, session_id, incident_id, 
                    investigation_type, channel_id, thread_ts
                )
                logger.info(f"✅ Posted AI investigation results to Slack for session {session_id}")
            except Exception as slack_error:
                logger.error(f"❌ Failed to post AI investigation results to Slack: {slack_error}")
                # Continue anyway - the investigation was successful even if Slack posting failed
            
            logger.info(f"✅ Started MCP AI investigation session {session_id} for incident {incident_id}")
            return {
                "success": True,
                "session_id": session_id,
                "message": f"MCP AI investigation started for {incident_id}"
            }
            
        except Exception as e:
            logger.error(f"❌ Error starting MCP AI investigation: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_mcp_enhanced_prompt(self, investigation_type: str, incident_data: Dict[str, Any]) -> str:
        """Build enhanced prompt with MCP tool information"""
        # Get the investigation template
        template = self.investigation_templates.get(investigation_type, self.investigation_templates["root_cause"])
        
        # Build available tools summary
        available_tools_text = self._format_available_tools()
        
        # Add detection query context if available
        detection_context = ""
        if 'source_query' in incident_data:
            detection_context = f"""

**🔍 Detection Query Context:**
This incident was detected using the following Splunk query:
```
{incident_data['source_query']}
```
**IMPORTANT**: Start your investigation by running this exact query first to see the data that triggered the alert, then expand your investigation from there."""
        
        # Use safe string replacement to avoid format specifier issues
        # Replace placeholders one by one to avoid conflicts with JSON braces
        enhanced_prompt = template
        enhanced_prompt = enhanced_prompt.replace('{incident_id}', incident_data.get('id', 'Unknown'))
        enhanced_prompt = enhanced_prompt.replace('{title}', incident_data.get('title', 'Unknown'))
        enhanced_prompt = enhanced_prompt.replace('{description}', incident_data.get('description', 'No description'))
        enhanced_prompt = enhanced_prompt.replace('{severity}', incident_data.get('severity', 'UNKNOWN'))
        enhanced_prompt = enhanced_prompt.replace('{affected_systems}', ', '.join(incident_data.get('affected_systems', [])))
        enhanced_prompt = enhanced_prompt.replace('{created_at}', incident_data.get('created_at', 'Unknown'))
        enhanced_prompt = enhanced_prompt.replace('{event_count}', str(incident_data.get('event_count', 0)))
        enhanced_prompt = enhanced_prompt.replace('{available_tools}', available_tools_text)
        
        # Add detection context
        enhanced_prompt += detection_context
        
        # Add MCP-specific instructions
        enhanced_prompt += """

**MCP Tool Call Instructions:**
When you want to use an MCP tool, format your request as a JSON tool call like this:

```json
{
  "tool_calls": [
    {
      "server": "splunk",
      "tool": "get_splunk_results", 
      "arguments": {
        "query": "search index=main error | head 10"
      }
    }
  ]
}
```

**PagerDuty Incident Management Examples:**
To resolve an incident:
```json
{
  "tool_calls": [
    {
      "server": "pagerduty",
      "tool": "resolve_incident",
      "arguments": {
        "incident_id": "INC-12345",
        "resolution_note": "Root cause identified and fixed"
      }
    }
  ]
}
```

To update incident status:
```json
{
  "tool_calls": [
    {
      "server": "pagerduty",
      "tool": "update_incident",
      "arguments": {
        "incident_id": "INC-12345",
        "status": "acknowledged",
        "resolution_note": "Investigation in progress"
      }
    }
  ]
}
```

I will execute these tool calls and provide you with the results. Then continue your analysis with the real data.

**Investigation Limits:**
- You have up to 12 iterations of tool calls to complete this investigation
- Each iteration can include multiple tool calls
- Use your tool calls efficiently - start with broad queries, then narrow down based on findings
- If you reach the limit, I'll ask you to provide a final analysis based on all gathered data

**IMPORTANT: You MUST start by making MCP tool calls to gather actual data. Do not provide any analysis until you have real data from the tools. Begin immediately with the appropriate tool calls in JSON format.**"""
        
        return enhanced_prompt
    
    def _format_available_tools(self) -> str:
        """Format available tools for the prompt"""
        tools_text = ""
        
        for server_name, capabilities in self.tool_capabilities.items():
            tools_text += f"\n**{server_name.title()} MCP Server:**\n"
            for tool in capabilities:
                tools_text += f"- `{tool['name']}`: {tool['description']}\n"
        
        return tools_text
    
    def _generate_investigation_summary(self, session_id: str, current_iteration: int) -> str:
        """Generate a summary of what was accomplished during the investigation"""
        try:
            if session_id not in self.active_investigations:
                return "No investigation session found."
            
            session = self.active_investigations[session_id]
            tool_calls = session.get('mcp_tool_calls', [])
            
            if not tool_calls:
                return "No tool calls were executed during this investigation."
            
            # Group tool calls by server and tool type
            tool_summary = {}
            for call in tool_calls:
                server = call.get('server', 'unknown')
                tool = call.get('tool', 'unknown')
                key = f"{server}.{tool}"
                
                if key not in tool_summary:
                    tool_summary[key] = {
                        'count': 0,
                        'queries': [],
                        'results_found': 0
                    }
                
                tool_summary[key]['count'] += 1
                
                # Extract query if it's a Splunk search
                if 'arguments' in call and 'query' in call['arguments']:
                    query = call['arguments']['query']
                    tool_summary[key]['queries'].append(query[:100] + "..." if len(query) > 100 else query)
                
                # Check if results were found using the new formatting
                result = call.get('result', '')
                if result and (
                    'SPLUNK QUERY SUCCESSFUL' in result or 
                    'Found' in result and 'results' in result or
                    (result != 'No results found' and 'No content' not in result and '❌ NO RESULTS FOUND' not in result)
                ):
                    tool_summary[key]['results_found'] += 1
            
            # Build summary text
            summary_parts = [
                f"**Investigation Progress:** {current_iteration-1} iterations completed",
                f"**Total Tool Calls:** {len(tool_calls)}",
                "",
                "**Tool Usage Summary:**"
            ]
            
            for tool_key, stats in tool_summary.items():
                summary_parts.append(f"• **{tool_key}**: {stats['count']} calls, {stats['results_found']} with results")
                if stats['queries']:
                    summary_parts.append(f"  - Recent queries: {', '.join(stats['queries'][-3:])}")
            
            # Add conversation context
            conversation = session.get('conversation_history', [])
            if len(conversation) > 2:
                summary_parts.extend([
                    "",
                    f"**Conversation History:** {len(conversation)} exchanges with Claude",
                    f"**Investigation Type:** {session.get('investigation_type', 'unknown')}"
                ])
            
            return "\n".join(summary_parts)
            
        except Exception as e:
            logger.error(f"Error generating investigation summary: {e}")
            return f"Error generating summary: {str(e)}"
    
    def _generate_tool_results_summary(self, session_id: str) -> str:
        """Generate a summary of actual tool results for the final prompt"""
        try:
            if session_id not in self.active_investigations:
                return "No investigation session found."
            
            session = self.active_investigations[session_id]
            tool_calls = session.get('mcp_tool_calls', [])
            
            if not tool_calls:
                return "No tool calls were executed during this investigation."
            
            # Build a summary of actual results
            results_parts = []
            
            for i, call in enumerate(tool_calls, 1):
                server = call.get('server', 'unknown')
                tool = call.get('tool', 'unknown')
                result = call.get('result', '')
                
                # Only include calls that returned data
                if result and (
                    'SPLUNK QUERY SUCCESSFUL' in result or 
                    'Found' in result and 'results' in result or
                    (result != 'No results found' and 'No content' not in result and '❌ NO RESULTS FOUND' not in result)
                ):
                    results_parts.append(f"**Tool Call {i} ({server}.{tool}):**")
                    
                    # Extract just the key parts of the result
                    if 'SPLUNK QUERY SUCCESSFUL' in result:
                        # Extract the "Found X results" part
                        import re
                        found_match = re.search(r'Found (\d+) results', result)
                        if found_match:
                            count = found_match.group(1)
                            results_parts.append(f"✅ Found {count} results from Splunk")
                            
                            # Extract JSON data if present
                            json_match = re.search(r'```json\n(.*?)\n```', result, re.DOTALL)
                            if json_match:
                                json_data = json_match.group(1)
                                results_parts.append(f"```json\n{json_data[:500]}{'...' if len(json_data) > 500 else ''}\n```")
                        else:
                            results_parts.append("✅ Query executed successfully")
                    else:
                        # For other types of results, show a truncated version
                        truncated_result = result[:300] + "..." if len(result) > 300 else result
                        results_parts.append(truncated_result)
                    
                    results_parts.append("")  # Add spacing
            
            if not results_parts:
                return "❌ No successful tool results found - all queries returned empty results."
            
            return "\n".join(results_parts)
            
        except Exception as e:
            logger.error(f"Error generating tool results summary: {e}")
            return f"Error generating tool results summary: {str(e)}"
    
    async def _execute_mcp_tool_calls(self, claude_response: str, session_id: str, iteration: int = 1, max_iterations: int = 12) -> str:
        """Parse and execute MCP tool calls from Claude's response"""
        try:
            # Safety check to prevent infinite loops
            if iteration > max_iterations:
                logger.warning(f"Maximum tool call iterations ({max_iterations}) reached for session {session_id}")
                
                # Provide comprehensive feedback to Claude about what was accomplished
                investigation_summary = self._generate_investigation_summary(session_id, iteration)
                
                # Include actual tool results in the final prompt
                tool_results_summary = self._generate_tool_results_summary(session_id)
                
                final_prompt = f"""You have reached the maximum number of tool call iterations ({max_iterations}) for this investigation. 

**Investigation Summary:**
{investigation_summary}

**Tool Results Data:**
{tool_results_summary}

**IMPORTANT**: The tool results above show the ACTUAL DATA that was returned from your queries. Use this data for your analysis.

**Please provide your final analysis and recommendations based on all the data you've gathered so far. Include:**

1. 🎯 **Key Findings**: What did you discover from the {iteration-1} iterations of tool calls?
2. 🔍 **Root Cause Analysis**: Based on the available data, what is the most likely cause?
3. ⚠️ **Impact Assessment**: What systems/users are affected?
4. 🛠️ **Immediate Actions**: What should be done right now to address this incident?
5. 📋 **Follow-up Tasks**: What additional investigation or monitoring is needed?
6. 🚨 **Escalation**: Should this be escalated to other teams?

Format your response for Slack with clear sections, bullet points, and code blocks for technical details."""
                
                # Get Claude's final analysis
                final_analysis = await self._chat_with_claude(final_prompt, session_id)
                
                if final_analysis and not final_analysis.startswith("❌"):
                    return final_analysis
                else:
                    return claude_response + f"\n\n⚠️ *Investigation stopped after {max_iterations} tool call iterations. Please review the data gathered above and provide your analysis.*"
            # Look for JSON tool calls in Claude's response
            import re
            json_pattern = r'```json\s*(\{[^`]+\})\s*```'
            json_matches = re.findall(json_pattern, claude_response, re.MULTILINE | re.DOTALL)
            
            if not json_matches:
                # No tool calls found, this is the final response
                logger.info(f"No MCP tool calls found in Claude response for session {session_id} (iteration {iteration}) - investigation complete")
                return claude_response
            
            # Execute all tool calls and collect results
            all_tool_results = []
            total_tool_calls = 0
            
            for json_match in json_matches:
                try:
                    tool_call_data = json.loads(json_match)
                    
                    if 'tool_calls' in tool_call_data:
                        num_calls = len(tool_call_data['tool_calls'])
                        total_tool_calls += num_calls
                        logger.info(f"Found {num_calls} tool calls in Claude response (iteration {iteration})")
                        results = await self._execute_tool_calls(tool_call_data['tool_calls'], session_id)
                        all_tool_results.append(results)
                
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool call JSON: {e}")
                    continue
            
            logger.info(f"Executed {total_tool_calls} total tool calls in iteration {iteration} for session {session_id}")
            
            # If we have tool results, send them back to Claude for analysis
            if all_tool_results:
                logger.info(f"🔄 TOOL RESULTS TO CLAUDE: Sending {len(all_tool_results)} tool result sets back to Claude (session {session_id}, iteration {iteration})")
                
                # Build follow-up prompt with tool results
                tool_results_text = "\n\n".join(all_tool_results)
                logger.info(f"🔄 TOOL RESULTS COMBINED: {len(tool_results_text)} chars total")
                
                # Count successful vs failed results in the combined text
                successful_count = tool_results_text.count("SPLUNK QUERY SUCCESSFUL")
                failed_count = tool_results_text.count("NO RESULTS FOUND")
                logger.info(f"🔄 TOOL RESULTS ANALYSIS: {successful_count} successful, {failed_count} failed results being sent to Claude")
                
                follow_up_prompt = f"""Based on the tool execution results below, please continue your investigation. If you need more data, make additional tool calls. If you have enough data, provide your complete investigation analysis:

**Tool Results:**
{tool_results_text}

Continue your investigation by either making more tool calls or providing your final analysis using the format specified in the system prompt."""
                
                logger.info(f"🔄 FOLLOW-UP PROMPT: {len(follow_up_prompt)} chars being sent to Claude")
                logger.info(f"🔄 FOLLOW-UP PREVIEW: {follow_up_prompt[:400]}{'...' if len(follow_up_prompt) > 400 else ''}")
                
                # Get Claude's analysis of the tool results (conversation history is managed in _chat_with_claude)
                analysis_response = await self._chat_with_claude(follow_up_prompt, session_id)
                
                if analysis_response and not analysis_response.startswith("❌"):
                    logger.info(f"🔄 CLAUDE ANALYSIS SUCCESS: Got {len(analysis_response)} chars response from Claude (session {session_id})")
                    
                    # Check what Claude said about the data
                    if "no data found" in analysis_response.lower():
                        logger.warning(f"🔄 CLAUDE ANALYSIS ISSUE: Claude claims no data despite {successful_count} successful tool results!")
                        logger.warning(f"🔄 CLAUDE ANALYSIS ISSUE: This indicates a prompt or context issue")
                    elif successful_count > 0 and ("found" in analysis_response.lower() or "results" in analysis_response.lower()):
                        logger.info(f"🔄 CLAUDE ANALYSIS GOOD: Claude acknowledges the {successful_count} successful results")
                    
                    # Check if Claude's response contains more tool calls
                    # If so, recursively process them
                    final_response = await self._execute_mcp_tool_calls(analysis_response, session_id, iteration + 1, max_iterations)
                    return final_response
                else:
                    logger.error(f"Failed to get Claude analysis: {analysis_response}")
                    return f"❌ Tool execution completed but analysis failed: {analysis_response}"
            
            return claude_response
            
        except Exception as e:
            logger.error(f"Error executing MCP tool calls: {e}")
            return claude_response
    
    async def _execute_tool_calls(self, tool_calls: List[Dict[str, Any]], session_id: str) -> str:
        """Execute a list of MCP tool calls"""
        results = []
        
        logger.info(f"🔧 TOOL EXECUTION START: Processing {len(tool_calls)} tool calls for session {session_id}")
        
        for i, tool_call in enumerate(tool_calls, 1):
            try:
                server = tool_call.get('server')
                tool_name = tool_call.get('tool')
                arguments = tool_call.get('arguments', {})
                
                logger.info(f"🔧 TOOL CALL {i}: Executing {server}.{tool_name} with args: {arguments}")
                
                # Get the appropriate client (existing or session)
                client = None
                if server == 'splunk':
                    client = self.existing_splunk_client or self.splunk_session
                elif server == 'pagerduty':
                    client = self.existing_pagerduty_client or self.pagerduty_session
                
                if not client:
                    error_msg = f"❌ Tool {i}: Server '{server}' not available"
                    logger.error(f"🔧 TOOL CALL {i} FAILED: {error_msg}")
                    results.append(error_msg)
                    continue
                
                # Execute the tool call using the appropriate client
                if hasattr(client, 'call_tool'):
                    # MCP session client
                    logger.info(f"🔧 TOOL CALL {i}: Using MCP session client")
                    result = await client.call_tool(tool_name, arguments)
                else:
                    # Existing client - call the tool method directly
                    logger.info(f"🔧 TOOL CALL {i}: Using existing client wrapper")
                    if server == 'splunk':
                        result = await self._call_splunk_tool(client, tool_name, arguments)
                    elif server == 'pagerduty':
                        result = await self._call_pagerduty_tool(client, tool_name, arguments)
                    else:
                        error_msg = f"❌ Tool {i}: Unknown server type '{server}'"
                        logger.error(f"🔧 TOOL CALL {i} FAILED: {error_msg}")
                        results.append(error_msg)
                        continue
                
                # Format the result and log detailed information
                if result.content:
                    content_text = ""
                    logger.info(f"🔧 TOOL CALL {i} CONTENT DEBUG: {len(result.content)} content items")
                    
                    for j, content in enumerate(result.content):
                        logger.info(f"🔧 TOOL CALL {i} CONTENT {j}: Type={type(content)}, HasText={hasattr(content, 'text')}")
                        if hasattr(content, 'text'):
                            logger.info(f"🔧 TOOL CALL {i} CONTENT {j} TEXT: {len(content.text)} chars - {content.text[:100]}{'...' if len(content.text) > 100 else ''}")
                            content_text += content.text
                        elif isinstance(content, TextContent):
                            content_text += content.text
                        elif isinstance(content, ImageContent):
                            content_text += f"[Image: {content.data[:50]}...]"
                        else:
                            logger.warning(f"🔧 TOOL CALL {i} CONTENT {j}: Unknown content type {type(content)}")
                    
                    # Log the raw result for debugging
                    logger.info(f"🔧 TOOL CALL {i} RAW RESULT: Length={len(content_text)} chars")
                    logger.info(f"🔧 TOOL CALL {i} RESULT PREVIEW: {content_text[:200]}{'...' if len(content_text) > 200 else ''}")
                    
                    # Check if this looks like successful data
                    if "SPLUNK QUERY SUCCESSFUL" in content_text and "Found" in content_text:
                        import re
                        match = re.search(r'Found (\d+) results', content_text)
                        record_count = match.group(1) if match else "unknown"
                        logger.info(f"🔧 TOOL CALL {i} SUCCESS DETECTED: Found {record_count} records")
                    elif "NO RESULTS FOUND" in content_text or "Error" in content_text:
                        logger.warning(f"🔧 TOOL CALL {i} NO DATA: Query returned no results or error")
                    else:
                        logger.info(f"🔧 TOOL CALL {i} RESULT TYPE: Unknown format")
                    
                    formatted_result = f"✅ Tool {i} ({server}.{tool_name}):\n{content_text}"
                    results.append(formatted_result)
                    
                    # Log what will be sent to Claude
                    logger.info(f"🔧 TOOL CALL {i} TO CLAUDE: Sending {len(formatted_result)} chars to Claude")
                    
                else:
                    no_content_msg = f"✅ Tool {i} ({server}.{tool_name}): No content returned"
                    logger.warning(f"🔧 TOOL CALL {i} NO CONTENT: Result object had no content")
                    results.append(no_content_msg)
                
                # Store tool call in session
                if session_id in self.active_investigations:
                    stored_result = content_text if 'content_text' in locals() else 'No content'
                    self.active_investigations[session_id]['mcp_tool_calls'].append({
                        'server': server,
                        'tool': tool_name,
                        'arguments': arguments,
                        'result': stored_result
                    })
                    logger.info(f"🔧 TOOL CALL {i} STORED: Added to session {session_id} with {len(stored_result)} chars")
                
            except Exception as e:
                error_msg = f"❌ Tool {i}: Error - {str(e)}"
                logger.error(f"🔧 TOOL CALL {i} EXCEPTION: {e}")
                results.append(error_msg)
        
        # Log the final combined result that will be sent to Claude
        combined_results = "\n\n".join(results)
        logger.info(f"🔧 TOOL EXECUTION COMPLETE: Returning {len(combined_results)} chars to Claude")
        logger.info(f"🔧 COMBINED RESULTS PREVIEW: {combined_results[:300]}{'...' if len(combined_results) > 300 else ''}")
        
        # Count successful vs failed tool calls
        successful_calls = len([r for r in results if r.startswith("✅")])
        failed_calls = len([r for r in results if r.startswith("❌")])
        logger.info(f"🔧 TOOL EXECUTION SUMMARY: {successful_calls} successful, {failed_calls} failed out of {len(tool_calls)} total")
        
        return combined_results
    
    async def _call_splunk_tool(self, client, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on the existing Splunk client"""
        try:
            result_text = ""
            
            logger.info(f"🔍 SPLUNK TOOL CALL: {tool_name} with args: {arguments}")
            
            # Map MCP tool names to the actual client methods
            if tool_name == 'get_splunk_results':
                query = arguments.get('query', '')
                logger.info(f"🔍 SPLUNK QUERY START: {query}")
                
                # Try different method names based on the client type
                result_data = None
                client_method_used = None
                
                if hasattr(client, 'execute_detection_query'):
                    # SplunkIncidentClient wrapper
                    client_method_used = 'execute_detection_query'
                    logger.info(f"🔍 SPLUNK CLIENT: Using {client_method_used} method")
                    result_data = await client.execute_detection_query(query)
                elif hasattr(client, 'execute_search'):
                    # Direct RealSplunkMCPClient
                    client_method_used = 'execute_search'
                    logger.info(f"🔍 SPLUNK CLIENT: Using {client_method_used} method")
                    result_data = await client.execute_search(query)
                elif hasattr(client, 'search_events'):
                    # Alternative method name
                    client_method_used = 'search_events'
                    logger.info(f"🔍 SPLUNK CLIENT: Using {client_method_used} method")
                    result_data = await client.search_events(query)
                else:
                    available_methods = [method for method in dir(client) if not method.startswith('_')]
                    logger.error(f"🔍 SPLUNK CLIENT ERROR: No expected search method found. Available methods: {available_methods}")
                    result_text = f"Error: Splunk client method not available for {tool_name}. Client type: {type(client).__name__}"
                
                # Log the raw result data from Splunk
                if result_data is not None:
                    logger.info(f"🔍 SPLUNK RAW RESULT: Type={type(result_data)}, Length={len(result_data) if hasattr(result_data, '__len__') else 'N/A'}")
                    
                    if isinstance(result_data, list):
                        logger.info(f"🔍 SPLUNK RAW RESULT: List with {len(result_data)} items")
                        if result_data:
                            logger.info(f"🔍 SPLUNK RAW RESULT SAMPLE: {result_data[0] if result_data else 'Empty list'}")
                        else:
                            logger.warning(f"🔍 SPLUNK RAW RESULT: Empty list returned")
                    elif isinstance(result_data, dict):
                        logger.info(f"🔍 SPLUNK RAW RESULT: Dict with keys: {list(result_data.keys())}")
                    else:
                        logger.info(f"🔍 SPLUNK RAW RESULT: {str(result_data)[:200]}{'...' if len(str(result_data)) > 200 else ''}")
                else:
                    logger.warning(f"🔍 SPLUNK RAW RESULT: None returned from {client_method_used}")
                    
                # Format results in a Claude-friendly way
                if result_data:
                    record_count = len(result_data) if hasattr(result_data, '__len__') else 1
                    logger.info(f"🔍 SPLUNK FORMATTING: Creating success response for {record_count} records")
                    
                    # Create a clear, structured response for Claude
                    result_text = f"""✅ SPLUNK QUERY SUCCESSFUL - Found {record_count} results

Query: {query}

📊 Results Summary:
- Total records found: {record_count}
- Data source: Splunk index
- Query execution: Successful
- Client method: {client_method_used}

📋 Raw Data:
```json
{json.dumps(result_data, indent=2)}
```

🔍 Data Analysis:
- Time range: {result_data[0].get('_time', 'N/A') if isinstance(result_data, list) and result_data else 'N/A'} to {result_data[-1].get('_time', 'N/A') if isinstance(result_data, list) and result_data else 'N/A'}
- Unique fields: {', '.join(sorted(set().union(*(d.keys() for d in result_data if isinstance(d, dict)))))[:200] if isinstance(result_data, list) else 'N/A'}
- Sample record count: {record_count}

✅ This data represents ACTUAL EVENTS found in Splunk matching your search criteria. Use this data for your analysis."""
                    
                    logger.info(f"🔍 SPLUNK SUCCESS: Formatted {len(result_text)} chars for Claude")
                else:
                    logger.warning(f"🔍 SPLUNK NO DATA: Query returned empty/null result")
                    result_text = "❌ NO RESULTS FOUND - The Splunk query returned an empty result set. Consider modifying the search criteria, time range, or index."
                    
            elif tool_name == 'search_aws_sourcetypes':
                aws_sourcetype = arguments.get('awssourcetype', 'aws:')
                logger.info(f"🔍 Searching AWS sourcetypes: {aws_sourcetype}")
                
                # Use the available search method to find AWS sourcetypes
                query = f"| metadata type=sourcetypes | search sourcetype={aws_sourcetype}* | table sourcetype"
                result_data = None
                if hasattr(client, 'execute_detection_query'):
                    result_data = await client.execute_detection_query(query)
                elif hasattr(client, 'execute_search'):
                    result_data = await client.execute_search(query)
                else:
                    result_text = f"Error: Cannot search AWS sourcetypes - no search method available on client type {type(client).__name__}"
                    
                if result_data:
                    result_text = f"""✅ AWS SOURCETYPES FOUND - {len(result_data)} sourcetypes discovered

Search pattern: {aws_sourcetype}*

📋 Available AWS Sourcetypes:
```json
{json.dumps(result_data, indent=2)}
```

✅ Use these sourcetypes in your Splunk queries to search AWS data."""
                else:
                    result_text = f"❌ NO AWS SOURCETYPES FOUND - No sourcetypes matching pattern '{aws_sourcetype}*' were found in Splunk."
                    
            elif tool_name == 'get_splunk_fields':
                sourcetype = arguments.get('sourcetype', 'aws:cloudtrail')
                logger.info(f"🔍 Getting fields for sourcetype: {sourcetype}")
                
                # Use the available search method to get fields
                query = f"search index=main sourcetype={sourcetype} | head 1 | fieldsummary | table field"
                result_data = None
                if hasattr(client, 'execute_detection_query'):
                    result_data = await client.execute_detection_query(query)
                elif hasattr(client, 'execute_search'):
                    result_data = await client.execute_search(query)
                else:
                    result_text = f"Error: Cannot get fields - no search method available on client type {type(client).__name__}"
                    
                if result_data:
                    result_text = f"""✅ FIELDS DISCOVERED - {len(result_data)} fields found for sourcetype '{sourcetype}'

📋 Available Fields:
```json
{json.dumps(result_data, indent=2)}
```

✅ Use these field names in your Splunk queries to filter and analyze {sourcetype} data."""
                else:
                    result_text = f"❌ NO FIELDS FOUND - No fields discovered for sourcetype '{sourcetype}'. The sourcetype may not exist or have no data."
                    
            elif tool_name == 'get_splunk_lookups':
                sourcetype = arguments.get('sourcetype', 'aws:cloudtrail')
                logger.info(f"🔍 Getting lookups for sourcetype: {sourcetype}")
                
                # Use the available search method to get lookups
                query = f"| rest /services/data/lookup-table-files | table title"
                if hasattr(client, 'execute_detection_query'):
                    result_data = await client.execute_detection_query(query)
                    result_text = json.dumps(result_data) if result_data else f"No lookups found"
                elif hasattr(client, 'execute_search'):
                    result_data = await client.execute_search(query)
                    result_text = json.dumps(result_data) if result_data else f"No lookups found"
                else:
                    result_text = f"Error: Cannot get lookups - no search method available on client type {type(client).__name__}"
                    
            elif tool_name == 'get_splunk_lookup_values':
                lookup_name = arguments.get('lookup_name', '')
                logger.info(f"🔍 Getting lookup values for: {lookup_name}")
                
                # Use the available search method to get lookup values
                query = f"| inputlookup {lookup_name} | head 10"
                if hasattr(client, 'execute_detection_query'):
                    result_data = await client.execute_detection_query(query)
                    result_text = json.dumps(result_data) if result_data else f"No values found for lookup {lookup_name}"
                elif hasattr(client, 'execute_search'):
                    result_data = await client.execute_search(query)
                    result_text = json.dumps(result_data) if result_data else f"No values found for lookup {lookup_name}"
                else:
                    result_text = f"Error: Cannot get lookup values - no search method available on client type {type(client).__name__}"
            else:
                logger.warning(f"⚠️  Unknown Splunk tool: {tool_name}")
                result_text = f"Error: Tool '{tool_name}' not implemented"
            
            # Log the final result before creating ToolResult
            logger.info(f"🔍 SPLUNK FINAL RESULT: {len(result_text)} chars - {result_text[:100]}{'...' if len(result_text) > 100 else ''}")
            
            # Create a proper result object with correct TextContent structure
            class TextContent:
                def __init__(self, text):
                    self.text = str(text)
            
            class ToolResult:
                def __init__(self, text):
                    self.content = [TextContent(text)]
            
            return ToolResult(result_text)
                
        except Exception as e:
            logger.error(f"Error calling Splunk tool {tool_name}: {e}")
            # Create an error result with actual error details
            class TextContent:
                def __init__(self, text):
                    self.text = str(text)
            
            class ToolResult:
                def __init__(self, text):
                    self.content = [TextContent(text)]
            
            return ToolResult(f"❌ Error calling Splunk tool {tool_name}: {str(e)}")
    
    async def _find_pagerduty_incident_id(self, mcp_client, internal_incident_id: str) -> Optional[str]:
        """
        Find the actual PagerDuty incident ID from our internal incident ID.
        
        Args:
            mcp_client: The PagerDuty MCP client
            internal_incident_id: Our internal incident ID (e.g., INC-20250811121551-AWSCloudTrailErrors)
            
        Returns:
            The actual PagerDuty incident ID (e.g., P123456) or None if not found
        """
        try:
            # First, try to find the mapping in the detected_incidents global list
            # Import here to avoid circular imports
            import sys
            from pathlib import Path
            
            # Get the run_api module to access detected_incidents
            current_dir = Path(__file__).parent.parent
            if str(current_dir) not in sys.path:
                sys.path.insert(0, str(current_dir))
            
            try:
                import run_api
                if hasattr(run_api, 'detected_incidents'):
                    for incident in run_api.detected_incidents:
                        if incident.get('id') == internal_incident_id:
                            # Check if this incident has a stored PagerDuty ID
                            pagerduty_id = incident.get('pagerduty_incident_id')
                            if pagerduty_id:
                                logger.info(f"Found stored PagerDuty incident {pagerduty_id} for internal ID {internal_incident_id}")
                                return pagerduty_id
                            break
                
                # Also check the incident_cache
                if hasattr(run_api, 'incident_cache'):
                    incident_data = run_api.incident_cache.get(internal_incident_id)
                    if incident_data:
                        pagerduty_id = incident_data.get('pagerduty_incident_id')
                        if pagerduty_id:
                            logger.info(f"Found cached PagerDuty incident {pagerduty_id} for internal ID {internal_incident_id}")
                            return pagerduty_id
            except ImportError:
                logger.warning("Could not import run_api to check detected_incidents")
            
            # If not found in detected_incidents, search PagerDuty incidents
            if not hasattr(mcp_client, 'list_incidents'):
                return None
                
            incidents = await mcp_client.list_incidents(limit=100)
            logger.info(f"Searching {len(incidents)} PagerDuty incidents for internal ID {internal_incident_id}")
            
            for incident in incidents:
                # Check if our internal ID matches the incident_key, title, or summary
                incident_key = incident.get('incident_key', '')
                title = incident.get('title', '')
                summary = incident.get('summary', '')
                
                # More flexible matching - look for the incident ID anywhere in the text
                if (incident_key == internal_incident_id or 
                    internal_incident_id in title or
                    internal_incident_id in summary or
                    # Also check if the title contains key parts of our incident ID
                    any(part in title for part in internal_incident_id.split('-') if len(part) > 3)):
                    pagerduty_id = incident.get('id')
                    logger.info(f"Found PagerDuty incident {pagerduty_id} for internal ID {internal_incident_id}")
                    return pagerduty_id
            
            logger.warning(f"No PagerDuty incident found for internal ID {internal_incident_id}")
            return None
            
        except Exception as e:
            logger.warning(f"Could not search for PagerDuty incident: {e}")
            return None

    async def _call_pagerduty_tool(self, client, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool on the PagerDuty client.
        
        This method handles the complexity of the current wrapper architecture
        but should be simplified in the future to connect directly to MCP servers.
        
        IMPORTANT: This method now handles ID mapping between internal incident IDs
        and PagerDuty incident IDs to resolve the "Invalid Id Provided" errors.
        """
        try:
            result_text = ""
            
            # Try to get the actual MCP client (unwrap if needed)
            mcp_client = None
            if hasattr(client, 'client'):
                mcp_client = client.client  # PagerDutyIncidentClient -> PagerDutyMCPClient
            else:
                mcp_client = client  # Direct MCP client
            
            # Handle each tool with proper error checking
            if tool_name == 'list_incidents':
                limit = arguments.get('limit', 50)
                if hasattr(mcp_client, 'list_incidents'):
                    incidents = await mcp_client.list_incidents(limit=limit)
                    result_text = f"✅ Found {len(incidents)} incidents"
                else:
                    result_text = f"❌ Error: Client does not support listing incidents"
                    
            elif tool_name == 'get_incident':
                incident_id = arguments.get('incident_id', '')
                if hasattr(mcp_client, 'get_incident'):
                    incident = await mcp_client.get_incident(incident_id)
                    result_text = f"✅ Retrieved incident {incident_id}: {incident.get('title', 'No title')}"
                else:
                    result_text = f"❌ Error: Client does not support getting incident details"
                    
            elif tool_name == 'resolve_incident':
                incident_id = arguments.get('incident_id', '')
                resolution_note = arguments.get('resolution_note', '')
                
                # Find the actual PagerDuty incident ID from our internal ID
                pagerduty_incident_id = await self._find_pagerduty_incident_id(mcp_client, incident_id)
                target_incident_id = pagerduty_incident_id or incident_id
                
                # Try MCP client's manage_incident method
                if hasattr(mcp_client, 'manage_incident'):
                    await mcp_client.manage_incident(incident_id=target_incident_id, status="resolved")
                    if resolution_note and hasattr(mcp_client, 'add_note_to_incident'):
                        await mcp_client.add_note_to_incident(target_incident_id, f"✅ **Incident Resolved**\n\n{resolution_note}")
                    result_text = f"✅ Successfully resolved incident {incident_id}" + (f" (PagerDuty ID: {target_incident_id})" if pagerduty_incident_id else "")
                # Try wrapper client's resolve_incident method
                elif hasattr(client, 'resolve_incident'):
                    result = await client.resolve_incident(target_incident_id, 'system', resolution_note)
                    if result.get('success'):
                        result_text = f"✅ Successfully resolved incident {incident_id}" + (f" (PagerDuty ID: {target_incident_id})" if pagerduty_incident_id else "")
                    else:
                        result_text = f"❌ Failed to resolve incident {incident_id}: {result.get('error', 'Unknown error')}"
                else:
                    result_text = f"❌ Error: No incident resolution methods available"
                    
            elif tool_name == 'update_incident':
                incident_id = arguments.get('incident_id', '')
                status = arguments.get('status', '')
                resolution_note = arguments.get('resolution_note', '')
                
                # Find the actual PagerDuty incident ID from our internal ID
                pagerduty_incident_id = await self._find_pagerduty_incident_id(mcp_client, incident_id)
                target_incident_id = pagerduty_incident_id or incident_id
                
                if hasattr(mcp_client, 'manage_incident'):
                    await mcp_client.manage_incident(incident_id=target_incident_id, status=status)
                    if resolution_note and hasattr(mcp_client, 'add_note_to_incident'):
                        await mcp_client.add_note_to_incident(target_incident_id, f"📝 **Incident Updated**\n\nStatus: {status}\n\n{resolution_note}")
                    result_text = f"✅ Successfully updated incident {incident_id} to status: {status}" + (f" (PagerDuty ID: {target_incident_id})" if pagerduty_incident_id else "")
                else:
                    result_text = f"❌ Error: No incident update methods available"
                    
            elif tool_name == 'manage_incidents':
                incident_ids = arguments.get('incident_ids', [])
                status = arguments.get('status', '')
                
                if hasattr(mcp_client, 'manage_incident'):
                    results = []
                    for incident_id in incident_ids:
                        # Find the actual PagerDuty incident ID for each internal ID
                        pagerduty_incident_id = await self._find_pagerduty_incident_id(mcp_client, incident_id)
                        target_incident_id = pagerduty_incident_id or incident_id
                        
                        await mcp_client.manage_incident(incident_id=target_incident_id, status=status)
                        results.append(f"Updated {incident_id}" + (f" (PD: {target_incident_id})" if pagerduty_incident_id else ""))
                    result_text = f"✅ Managed {len(incident_ids)} incidents: {', '.join(results)}"
                else:
                    result_text = f"❌ Error: No bulk incident management methods available"
                    
            elif tool_name == 'add_note_to_incident':
                incident_id = arguments.get('incident_id', '')
                note = arguments.get('note', '')
                
                # Find the actual PagerDuty incident ID from our internal ID
                pagerduty_incident_id = await self._find_pagerduty_incident_id(mcp_client, incident_id)
                target_incident_id = pagerduty_incident_id or incident_id
                
                if hasattr(mcp_client, 'add_note_to_incident'):
                    await mcp_client.add_note_to_incident(target_incident_id, note)
                    result_text = f"✅ Successfully added note to incident {incident_id}" + (f" (PagerDuty ID: {target_incident_id})" if pagerduty_incident_id else "")
                else:
                    result_text = f"❌ Error: No note-adding methods available"
                    
            elif tool_name == 'list_services':
                if hasattr(mcp_client, 'list_services'):
                    services = await mcp_client.list_services()
                    result_text = f"✅ Found {len(services)} services"
                else:
                    result_text = f"❌ Error: Client does not support listing services"
                    
            elif tool_name == 'create_incident':
                title = arguments.get('title', '')
                service_id = arguments.get('service_id', '')
                
                if hasattr(mcp_client, 'create_incident'):
                    incident = await mcp_client.create_incident(title=title, service_id=service_id)
                    result_text = f"✅ Created incident: {incident.get('id', 'Unknown ID')}"
                else:
                    result_text = f"❌ Error: Client does not support creating incidents"
                    
            elif tool_name == 'list_tools':
                available_tools = [
                    'list_incidents', 'get_incident', 'list_services', 'create_incident',
                    'resolve_incident', 'update_incident', 'manage_incidents', 'add_note_to_incident'
                ]
                result_text = f"✅ Available PagerDuty tools: {', '.join(available_tools)}"
                
            else:
                available_tools = [
                    'list_incidents', 'get_incident', 'list_services', 'create_incident',
                    'resolve_incident', 'update_incident', 'manage_incidents', 'add_note_to_incident', 'list_tools'
                ]
                result_text = f"❌ Error: Tool '{tool_name}' not available. Available tools: {', '.join(available_tools)}"
            
            # Create a proper result object
            class ToolResult:
                def __init__(self, text):
                    self.content = [type('TextContent', (), {'text': str(text)})()]
            
            return ToolResult(result_text)
                
        except Exception as e:
            logger.error(f"Error calling PagerDuty tool {tool_name}: {e}")
            # Create an error result with actual error details
            class ToolResult:
                def __init__(self, text):
                    self.content = [type('TextContent', (), {'text': text})()]
            
            return ToolResult(f"❌ Error calling PagerDuty tool {tool_name}: {str(e)}")
    
    async def _chat_with_claude(self, message: str, session_id: str) -> str:
        """Send message to Claude via AWS Bedrock"""
        try:
            logger.info(f"🤖 CLAUDE CHAT START: Session {session_id}")
            logger.info(f"🤖 CLAUDE INPUT: {len(message)} chars - {message[:200]}{'...' if len(message) > 200 else ''}")
            
            if not self.bedrock_client:
                error_msg = "❌ AWS Bedrock client not configured. Please check AWS credentials and region."
                logger.error(f"🤖 CLAUDE ERROR: {error_msg}")
                return error_msg
            
            session = self.active_investigations.get(session_id, {})
            conversation_history = session.get('conversation_history', [])
            
            logger.info(f"🤖 CLAUDE CONTEXT: {len(conversation_history)} messages in conversation history")
            
            # Add the current message to conversation history
            current_message = {'role': 'user', 'content': message}
            if session_id in self.active_investigations:
                self.active_investigations[session_id]['conversation_history'].append(current_message)
                # Update the conversation_history reference
                conversation_history = self.active_investigations[session_id]['conversation_history']
                logger.info(f"🤖 CLAUDE CONTEXT: Added message, now {len(conversation_history)} total messages")
            
            # Build system prompt with MCP capabilities
            system_prompt = self._build_mcp_system_prompt()
            logger.info(f"🤖 CLAUDE SYSTEM: {len(system_prompt)} chars in system prompt")
            
            # Prepare messages for Claude (don't add the message again since it's already in history)
            messages = conversation_history
            
            # Log what we're sending to Claude
            total_input_chars = len(system_prompt) + sum(len(msg['content']) for msg in messages)
            logger.info(f"🤖 CLAUDE REQUEST: {total_input_chars} total chars ({len(system_prompt)} system + {total_input_chars - len(system_prompt)} messages)")
            
            # Check if the current message contains tool results
            if "Tool Results:" in message or "SPLUNK QUERY SUCCESSFUL" in message:
                logger.info(f"🤖 CLAUDE TOOL RESULTS: Message contains tool results data")
                # Count how many successful tool results are in the message
                successful_results = message.count("SPLUNK QUERY SUCCESSFUL")
                failed_results = message.count("NO RESULTS FOUND")
                logger.info(f"🤖 CLAUDE TOOL RESULTS: {successful_results} successful, {failed_results} failed results detected")
            
            # Prepare Bedrock request payload
            bedrock_payload = {
                'anthropic_version': 'bedrock-2023-05-31',
                'max_tokens': 4000,
                'system': system_prompt,
                'messages': messages,
                'temperature': 0.1,
                'top_p': 0.9
            }
            
            logger.info(f"🤖 CLAUDE BEDROCK: Calling model {self.bedrock_model_id}")
            
            # Call Bedrock
            response = self.bedrock_client.invoke_model(
                modelId=self.bedrock_model_id,
                body=json.dumps(bedrock_payload),
                contentType='application/json'
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            logger.info(f"🤖 CLAUDE BEDROCK: Response received, parsing...")
            
            if 'content' in response_body and len(response_body['content']) > 0:
                claude_response = response_body['content'][0]['text']
                
                logger.info(f"🤖 CLAUDE RESPONSE: {len(claude_response)} chars received")
                logger.info(f"🤖 CLAUDE RESPONSE PREVIEW: {claude_response[:300]}{'...' if len(claude_response) > 300 else ''}")
                
                # Check if Claude's response mentions data
                if "no data found" in claude_response.lower() or "no results" in claude_response.lower():
                    logger.warning(f"🤖 CLAUDE RESPONSE: Claude claims no data found despite tool results")
                elif "found" in claude_response.lower() and ("results" in claude_response.lower() or "data" in claude_response.lower()):
                    logger.info(f"🤖 CLAUDE RESPONSE: Claude acknowledges data was found")
                elif "tool_calls" in claude_response:
                    logger.info(f"🤖 CLAUDE RESPONSE: Claude is making more tool calls")
                else:
                    logger.info(f"🤖 CLAUDE RESPONSE: Response type unclear")
                
                # Add Claude's response to conversation history
                if session_id in self.active_investigations:
                    self.active_investigations[session_id]['conversation_history'].append({
                        'role': 'assistant', 
                        'content': claude_response
                    })
                    logger.info(f"🤖 CLAUDE CONTEXT: Added response to history, now {len(self.active_investigations[session_id]['conversation_history'])} total messages")
                
                return claude_response
            else:
                error_msg = f"Unexpected Bedrock response format: {response_body}"
                logger.error(f"🤖 CLAUDE ERROR: {error_msg}")
                return "❌ Unexpected response format from Claude"
                        
        except Exception as e:
            error_msg = f"Error calling Claude via Bedrock: {e}"
            logger.error(f"🤖 CLAUDE EXCEPTION: {error_msg}")
            return f"❌ {error_msg}"
    
    def _add_raw_data_section(self, response: str, tool_results: List[Dict[str, Any]]) -> str:
        """Add a raw data section to show actual tool results"""
        if not tool_results:
            return response
            
        # Find where to insert the raw data section (after Key Findings)
        raw_data_section = "\n\n📋 *Raw Data*\n"
        raw_data_section += "```json\n"
        
        # Extract actual data from tool results
        for i, result in enumerate(tool_results, 1):
            raw_data_section += f"// Tool {i}: {result['server']}.{result['tool']}\n"
            if hasattr(result['result'], 'content') and result['result'].content:
                for content in result['result'].content:
                    if hasattr(content, 'text'):
                        try:
                            # Try to parse and pretty-print JSON
                            data = json.loads(content.text)
                            raw_data_section += json.dumps(data, indent=2) + "\n\n"
                        except:
                            # If not JSON, show as text
                            raw_data_section += content.text + "\n\n"
            else:
                raw_data_section += str(result['result']) + "\n\n"
        
        raw_data_section += "```\n"
        
        # Insert after "📊 Key Findings" or at the beginning if not found
        if "📊" in response and "*Key Findings*" in response:
            # Find the end of Key Findings section
            key_findings_end = response.find("🎯", response.find("📊"))
            if key_findings_end != -1:
                return response[:key_findings_end] + raw_data_section + "\n" + response[key_findings_end:]
        
        # Fallback: add after Investigation Summary
        if "🔍" in response:
            summary_end = response.find("📊", response.find("🔍"))
            if summary_end != -1:
                return response[:summary_end] + raw_data_section + "\n" + response[summary_end:]
        
        # Last resort: add at the beginning
        return raw_data_section + "\n" + response

    def _build_mcp_system_prompt(self) -> str:
        """Build system prompt with MCP capabilities"""
        available_tools_text = self._format_available_tools()
        
        # Use string concatenation instead of f-string to avoid brace interpretation issues
        system_prompt = """You are an expert incident response investigator with access to powerful MCP (Model Context Protocol) tools for monitoring and alerting systems.

**Available MCP Tools:**
""" + available_tools_text + """

**Data Sources Available:**
- **AWS CloudTrail**: API calls, authentication events, resource access logs
- **AWS CloudWatch**: Metrics, alarms, application logs, performance data
- **Application Logs**: Error logs, access logs, system logs from various sources
- **PagerDuty**: Incident management, on-call schedules, escalation policies

**Splunk Query Guidelines:**
- Always use `index=main` for searches
- AWS CloudTrail data: `sourcetype=aws:cloudtrail`
- AWS CloudWatch data: `sourcetype=aws:cloudwatch`
- Application logs: `sourcetype=application` or `sourcetype=syslog`
- Common fields: `_time`, `source`, `sourcetype`, `host`, `eventName`, `errorCode`, `userIdentity`, `sourceIPAddress`
- For errors: `error OR failed OR exception`
- For AWS issues: `errorCode!=success` or `errorCode=AccessDenied`
- Use stats for aggregation: `| stats count by field1, field2`
- Use head to limit results: `| head 10`

**MCP Tool Call Format:**
When you need data, use this EXACT JSON format in code blocks:

```json
{
  "tool_calls": [
    {
      "server": "splunk",
      "tool": "get_splunk_results",
      "arguments": {
        "query": "search index=main sourcetype=aws:cloudtrail errorCode=AccessDenied | head 10 | stats count by eventSource, userIdentity.arn"
      }
    }
  ]
}
```

**CRITICAL INSTRUCTIONS:**
1. **ALWAYS START WITH TOOL CALLS** - Your first response must contain tool calls in JSON format
2. **Always use the exact JSON format above** - no variations
3. **Never show tool call JSON to users** - execute them silently and show only results
4. **Use specific Splunk queries** based on the incident type
5. **ALWAYS base your analysis on ACTUAL tool results** - never hallucinate or make up data
6. **If tool calls fail, explicitly mention the failure** - don't pretend you have data when you don't
7. **Include specific numbers and details from the actual tool results** in your response
8. **If no data is returned, say so clearly** - don't invent findings
9. **MANDATORY: Always include a "Raw Data" section showing the actual tool results** - use code blocks to display the exact JSON/data returned by tools
10. **Never invent specific details like bucket names, user ARNs, or IP addresses** - only use what's actually returned by the tools
11. **DO NOT PROVIDE ANALYSIS WITHOUT DATA** - If you don't make tool calls, you cannot provide investigation results

**Your Role:**
- Investigate incidents using real-time data from MCP tools
- Provide intelligent analysis and guided investigation
- Make specific tool calls to collect evidence (hidden from user)
- Correlate data across AWS services and systems
- Identify root causes based on actual data

**Investigation Approach:**
1. **IMMEDIATELY make MCP tool calls** - Start every investigation with tool calls to gather data
2. **Wait for tool results** - Do not proceed with analysis until you have actual data
3. **Analyze patterns and correlations** in the real results from tools
4. **Make additional targeted tool calls** as needed based on initial findings
5. **Present findings and root cause analysis** based only on actual tool data
6. **Suggest specific remediation steps** with supporting evidence from the data

**Communication Style for Slack:**
- Use *bold text* for headers and important points (single asterisks, not double)
- Use `code blocks` for technical details, queries, and log excerpts
- Use bullet points (•) for lists, not dashes or asterisks
- Use emojis (🔍, 📊, ⚠️, 🛠️, ✅) to make sections visually distinct
- Structure responses with clear sections using emojis as headers
- Keep paragraphs concise and scannable
- Use numbered lists for action items with priority indicators
- Include specific metrics and evidence from actual data
- Format technical details in code blocks for readability
- Never use "Part 1/2" or similar splitting indicators
- Use proper Slack markdown formatting throughout

**Response Format Template:**
Use this structure for investigation responses:

🔍 *Investigation Summary*
Brief overview of what was analyzed

📊 *Key Findings*  
• Specific data points and metrics
• Evidence from tool calls

📋 *Raw Data*
```json
[Show the actual JSON data returned by tools here - this is MANDATORY]
```

🎯 *Root Cause*
Technical analysis based on data (only use details from the raw data above)

⚠️ *Impact Assessment*
Business and technical impact

🛠️ *Immediate Actions*
1. **Priority 1:** Critical actions
2. **Priority 2:** Important follow-ups

🔒 *Prevention*
Long-term recommendations

Remember: Execute tool calls silently, but ALWAYS show the raw data results to users so they can verify your analysis."""
        
        return system_prompt
    
    async def _get_incident_data(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Get incident data from various sources"""
        try:
            # Try to get from detected incidents first
            try:
                from run_api import detected_incidents, incident_cache, load_incident_cache
                
                # Reload cache from file
                load_incident_cache()
                
                # Check detected_incidents
                for incident in detected_incidents:
                    if incident.get('id') == incident_id:
                        logger.info(f"✅ Found incident {incident_id} in detected_incidents")
                        return incident
                
                # Check persistent cache
                if incident_id in incident_cache:
                    logger.info(f"✅ Found incident {incident_id} in incident_cache")
                    return incident_cache[incident_id]
                    
            except ImportError as e:
                logger.error(f"❌ Could not import from run_api: {e}")
            except Exception as e:
                logger.error(f"❌ Error accessing incident data from run_api: {e}")
            
            # Fallback: try to load from file directly
            try:
                import json
                from pathlib import Path
                
                cache_file = Path(__file__).parent.parent / "incident_cache.json"
                if cache_file.exists():
                    with open(cache_file, 'r') as f:
                        file_cache = json.load(f)
                        if incident_id in file_cache:
                            logger.info(f"✅ Found incident {incident_id} in cache file")
                            return file_cache[incident_id]
                        
            except Exception as e:
                logger.error(f"❌ Error reading incident cache file: {e}")
            
            logger.warning(f"⚠️  Could not find incident data for {incident_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error getting incident data: {e}")
            return None
    
    async def _send_investigation_response(self, response: str, session_id: str, 
                                         incident_id: str, investigation_type: str,
                                         channel_id: str, thread_ts: str = None):
        """Send investigation response to Slack"""
        try:
            if not self.slack_client:
                return
            
            # Log response length for debugging
            logger.info(f"🔧 AI response length: {len(response)} characters")
            
            # Check if response is too long and needs to be split
            # Slack has strict limits: ~3000 chars per text field, so be more conservative
            if len(response) > 4000:  # More conservative limit for Slack text fields
                logger.warning(f"AI response is very long ({len(response)} chars), splitting into multiple messages")
                await self._send_long_response_in_chunks(response, channel_id, thread_ts, incident_id, investigation_type, session_id)
                return
            
            # Build Slack blocks
            blocks = self._build_slack_blocks(response, session_id, incident_id, investigation_type)
            
            # Check total block size
            blocks_size = len(str(blocks))
            if blocks_size > 40000:  # Slack has limits on block size
                logger.warning(f"Slack blocks are very large ({blocks_size} chars), splitting response")
                await self._send_long_response_in_chunks(response, channel_id, thread_ts, incident_id, investigation_type, session_id)
                return
            
            message_params = {
                'channel': channel_id,
                'text': f"🤖 MCP AI {investigation_type.replace('_', ' ').title()} Investigation for {incident_id}",
                'blocks': blocks
            }
            
            if thread_ts:
                message_params['thread_ts'] = thread_ts
            
            result = await self.slack_client.chat_postMessage(**message_params)
            logger.info(f"✅ Posted AI investigation results to Slack for session {session_id}")
            logger.info(f"✅ Slack response: {result.get('ok', False)}, ts: {result.get('ts', 'unknown')}")
            
        except Exception as e:
            logger.error(f"❌ Failed to post AI investigation results to Slack: {e}")
            logger.error(f"❌ Response length: {len(response)} chars")
            
            # Try to post a simple error message with the first part of the response
            try:
                truncated_response = response[:2000] + "..." if len(response) > 2000 else response
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"❌ AI Investigation completed but response was too long to post.\n\n**First 2000 characters:**\n{truncated_response}\n\n**Error:** {str(e)[:200]}..."
                )
            except Exception as slack_error:
                logger.error(f"❌ Failed to post error message to Slack: {slack_error}")
    
    def _build_slack_blocks(self, response: str, session_id: str, 
                           incident_id: str, investigation_type: str) -> List[Dict[str, Any]]:
        """Build Slack blocks for the investigation response"""
        blocks = []
        
        # Header
        investigation_type_display = investigation_type.replace('_', ' ').title()
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🤖 MCP AI {investigation_type_display} Investigation"
            }
        })
        
        # Incident info
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Incident: `{incident_id}` • Powered by Claude 3.7 + MCP"
                }
            ]
        })
        
        # Response content - convert to proper Slack markdown format
        # Clean up the response to use proper Slack formatting
        slack_formatted_response = self._format_response_for_slack(response)
        
        # Use more conservative chunking to avoid Slack text field limits
        if len(slack_formatted_response) > 2500:  # More conservative limit
            # Split into smaller chunks at natural boundaries
            chunks = self._split_response_intelligently(slack_formatted_response, 2000)
            for i, chunk in enumerate(chunks):
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": chunk
                    }
                })
                # Add divider between chunks (except for the last one)
                if i < len(chunks) - 1:
                    blocks.append({"type": "divider"})
        else:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": slack_formatted_response
                }
            })
        
        # Action buttons
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "💬 Continue Chat"
                    },
                    "action_id": "ai_continue_chat",
                    "value": session_id,
                    "style": "primary"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 Get More Data"
                    },
                    "action_id": "ai_get_more_data",
                    "value": session_id
                }
            ]
        })
        
        return blocks
    
    def _format_response_for_slack(self, response: str) -> str:
        """Convert AI response to proper Slack markdown format"""
        try:
            # Remove "Part X/Y" statements that are causing issues
            import re
            response = re.sub(r'\*\*Part \d+/\d+:\*\*', '', response)
            
            # Convert markdown headers to Slack format
            response = re.sub(r'^### (.*?)$', r'*\1*', response, flags=re.MULTILINE)
            response = re.sub(r'^## (.*?)$', r'*\1*', response, flags=re.MULTILINE)
            response = re.sub(r'^# (.*?)$', r'*\1*', response, flags=re.MULTILINE)
            
            # Convert code blocks to Slack format
            response = re.sub(r'```(\w+)?\n(.*?)\n```', r'```\2```', response, flags=re.DOTALL)
            
            # Convert inline code to Slack format (already correct with backticks)
            
            # Convert bold text to Slack format
            response = re.sub(r'\*\*(.*?)\*\*', r'*\1*', response)
            
            # Convert bullet points to proper format
            response = re.sub(r'^\* ', r'• ', response, flags=re.MULTILINE)
            response = re.sub(r'^\- ', r'• ', response, flags=re.MULTILINE)
            
            # Clean up multiple newlines
            response = re.sub(r'\n{3,}', '\n\n', response)
            
            # Remove any remaining markdown artifacts
            response = response.strip()
            
            return response
            
        except Exception as e:
            logger.error(f"Error formatting response for Slack: {e}")
            return response  # Return original if formatting fails
    
    def _split_response_intelligently(self, response: str, max_chunk_size: int) -> List[str]:
        """Split response at natural boundaries while respecting Slack limits"""
        try:
            chunks = []
            
            # First try to split by major sections (double newlines)
            sections = response.split('\n\n')
            current_chunk = ""
            
            for section in sections:
                # If adding this section would exceed the limit
                if len(current_chunk + section) > max_chunk_size:
                    # Save current chunk if it has content
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    
                    # If the section itself is too large, split it further
                    if len(section) > max_chunk_size:
                        # Split by sentences or lines
                        lines = section.split('\n')
                        current_chunk = ""
                        for line in lines:
                            if len(current_chunk + line) > max_chunk_size:
                                if current_chunk.strip():
                                    chunks.append(current_chunk.strip())
                                current_chunk = line + '\n'
                            else:
                                current_chunk += line + '\n'
                    else:
                        current_chunk = section + '\n\n'
                else:
                    current_chunk += section + '\n\n'
            
            # Add the last chunk
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            return chunks if chunks else [response]
            
        except Exception as e:
            logger.error(f"Error splitting response: {e}")
            # Fallback to simple character-based splitting
            return [response[i:i+max_chunk_size] for i in range(0, len(response), max_chunk_size)]
    
    async def _send_long_response_in_chunks(self, response: str, channel_id: str, thread_ts: str, 
                                          incident_id: str, investigation_type: str, session_id: str):
        """Send a long AI response in multiple smaller messages with proper Slack formatting"""
        try:
            # Format the response for Slack first
            formatted_response = self._format_response_for_slack(response)
            
            # Use intelligent splitting
            chunks = self._split_response_intelligently(formatted_response, 2000)
            
            # Send header message
            investigation_type_display = investigation_type.replace('_', ' ').title()
            header_blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🤖 MCP AI {investigation_type_display} Investigation"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Incident: `{incident_id}` • Powered by Claude 3.7 + MCP"
                        }
                    ]
                }
            ]
            
            await self.slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=header_blocks,
                text=f"🤖 MCP AI {investigation_type_display} Investigation Results"
            )
            
            # Send each chunk with proper formatting (no "Part X/Y" labels)
            for i, chunk in enumerate(chunks, 1):
                chunk_blocks = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": chunk
                        }
                    }
                ]
                
                # Add divider between chunks (except for the last one)
                if i < len(chunks):
                    chunk_blocks.append({"type": "divider"})
                
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    blocks=chunk_blocks,
                    text=f"Investigation Results - Section {i}"
                )
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)
            
            # Send follow-up buttons
            follow_up_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*🔄 Continue Investigation:*"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "💬 Continue Chat"
                            },
                            "action_id": "ai_continue_chat",
                            "value": session_id,
                            "style": "primary"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "📊 Get More Data"
                            },
                            "action_id": "ai_get_more_data",
                            "value": session_id
                        }
                    ]
                }
            ]
            
            await self.slack_client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=follow_up_blocks,
                text="Continue Investigation Options"
            )
            
            logger.info(f"✅ Posted long AI response in {len(chunks)} chunks for session {session_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to send long response in chunks: {e}")
            # Fallback to simple text message
            try:
                await self.slack_client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=f"❌ AI Investigation completed but response was too long to display properly.\n\nError: {str(e)}"
                )
            except Exception as fallback_error:
                logger.error(f"❌ Fallback message also failed: {fallback_error}")
    
    async def handle_ai_chat(self, message: str, user_id: str, channel_id: str, 
                           thread_ts: str = None, session_id: str = None) -> Dict[str, Any]:
        """Handle follow-up AI chat messages"""
        try:
            # Find or create session
            if not session_id:
                session_id = self._find_session_by_thread(channel_id, thread_ts)
            
            if not session_id or session_id not in self.active_investigations:
                return {
                    "success": False,
                    "error": "No active MCP AI investigation session found"
                }
            
            session = self.active_investigations[session_id]
            
            # Add context about previous tool calls
            enhanced_message = await self._enhance_message_with_mcp_context(message, session)
            
            # Get Claude's response
            claude_response = await self._chat_with_claude(enhanced_message, session_id)
            
            # Execute any new tool calls
            enhanced_response = await self._execute_mcp_tool_calls(claude_response, session_id, iteration=1)
            
            # Update conversation history
            session['conversation_history'].extend([
                {'role': 'user', 'content': message},
                {'role': 'assistant', 'content': enhanced_response}
            ])
            
            # Send response to Slack
            await self._send_investigation_response(
                enhanced_response, session_id, session['incident_id'],
                session['investigation_type'], channel_id, thread_ts
            )
            
            return {
                "success": True,
                "response": enhanced_response
            }
            
        except Exception as e:
            logger.error(f"Error handling MCP AI chat: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _find_session_by_thread(self, channel_id: str, thread_ts: str) -> Optional[str]:
        """Find investigation session by thread"""
        for session_id, session in self.active_investigations.items():
            if (session.get('channel_id') == channel_id and 
                session.get('thread_ts') == thread_ts):
                return session_id
        return None
    
    async def _enhance_message_with_mcp_context(self, message: str, session: Dict[str, Any]) -> str:
        """Enhance message with MCP context from previous tool calls"""
        context_parts = [message]
        
        # Add previous tool call results
        tool_calls = session.get('mcp_tool_calls', [])
        if tool_calls:
            context_parts.append("\n**Previous MCP Tool Results:**")
            for call in tool_calls[-3:]:  # Last 3 tool calls
                context_parts.append(f"- {call['server']}.{call['tool']}: {call['result'][:100]}...")
        
        # Add available tools reminder
        context_parts.append(f"\n**Available MCP Tools:** {self._format_available_tools()}")
        
        return "\n".join(context_parts)
    

    
    def get_investigation_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get investigation session by ID"""
        return self.active_investigations.get(session_id)
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """Clean up old investigation sessions"""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        
        sessions_to_remove = []
        for session_id, session in self.active_investigations.items():
            session_time = datetime.fromisoformat(session['started_at']).timestamp()
            if session_time < cutoff_time:
                sessions_to_remove.append(session_id)
        
        for session_id in sessions_to_remove:
            del self.active_investigations[session_id]
        
        if sessions_to_remove:
            logger.info(f"🧹 Cleaned up {len(sessions_to_remove)} old MCP AI investigation sessions")


# Test function
async def test_mcp_ai_investigator():
    """Test the MCP AI investigator"""
    print("🧪 Testing MCP AI Incident Investigator")
    print("=" * 50)
    
    investigator = MCPAIInvestigator()
    
    try:
        # Test connection
        connected = await investigator.connect()
        if connected:
            print("✅ Successfully connected to MCP servers")
            print(f"   Available tools: {list(investigator.available_tools.keys())}")
            
            # Test tool discovery
            for server, tools in investigator.available_tools.items():
                print(f"   {server}: {len(tools)} tools")
        else:
            print("❌ Failed to connect to MCP servers")
        
        # Cleanup
        await investigator.disconnect()
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("✅ MCP AI investigator test completed")

if __name__ == "__main__":
    asyncio.run(test_mcp_ai_investigator())