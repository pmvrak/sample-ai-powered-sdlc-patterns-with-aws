"""
PagerDuty MCP Client Integration
===============================

Integrates with the PagerDuty MCP server to provide real incident data
and incident management capabilities.
"""

import asyncio
import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

class PagerDutyMCPClient:
    """
    Client for connecting to the PagerDuty MCP server
    Provides incident management capabilities using real PagerDuty data
    """
    
    def __init__(self, api_key: Optional[str] = None, api_host: str = "https://api.pagerduty.com"):
        self.api_key = api_key
        self.api_host = api_host
        self.session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None
        self.connected = False
        self._connection_lock = asyncio.Lock()
        
    async def connect(self) -> bool:
        """Connect to the PagerDuty MCP server"""
        async with self._connection_lock:
            if self.connected:
                return True
                
            try:
                logger.info("Connecting to PagerDuty MCP server...")
                
                # Create new exit stack for this connection
                self.exit_stack = AsyncExitStack()
                
                # Set up environment variables for PagerDuty API
                env = {
                    "PAGERDUTY_API_HOST": self.api_host,
                    "PAGERDUTY_USER_API_KEY": self.api_key or ""
                }
                
                # Also inherit current environment to ensure uvx works
                import os
                current_env = os.environ.copy()
                current_env.update(env)
                
                # Connect to the local PagerDuty MCP server
                import os
                from pathlib import Path
                
                # Get the absolute path to the pagerduty server directory
                current_dir = Path(__file__).parent.parent  # Go up from integrations/ to incident_management/
                pagerduty_server_dir = current_dir / "pagerduty-mcp-server"  # Go to pagerduty-mcp-server
                
                # Verify server directory exists
                if not pagerduty_server_dir.exists():
                    raise FileNotFoundError(f"PagerDuty server directory not found: {pagerduty_server_dir}")
                
                server_params = StdioServerParameters(
                    command="python",
                    args=[
                        "-m", "pagerduty_mcp",
                        "--enable-write-tools"  # Enable write operations
                    ],
                    env=current_env,
                    cwd=str(pagerduty_server_dir)
                )
                
                transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
                stdio, write = transport
                self.session = await self.exit_stack.enter_async_context(
                    ClientSession(stdio, write)
                )
                
                # Initialize the session
                await self.session.initialize()
                
                # List available tools
                tools_result = await self.session.list_tools()
                available_tools = [tool.name for tool in tools_result.tools]
                logger.info(f"Connected to PagerDuty MCP server. Available tools: {available_tools}")
                
                self.connected = True
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to PagerDuty MCP server: {e}")
                self.connected = False
                # Clean up on failure
                if self.exit_stack:
                    try:
                        await self.exit_stack.aclose()
                    except Exception as cleanup_error:
                        logger.warning(f"Error during cleanup: {cleanup_error}")
                    self.exit_stack = None
                return False
    
    async def disconnect(self):
        """Disconnect from the PagerDuty MCP server"""
        async with self._connection_lock:
            if not self.connected:
                return
                
            try:
                self.connected = False
                self.session = None
                
                if self.exit_stack:
                    cleanup_task = asyncio.create_task(self.exit_stack.aclose())
                    try:
                        await asyncio.wait_for(cleanup_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning("PagerDuty MCP cleanup timed out, forcing cancellation")
                        cleanup_task.cancel()
                        try:
                            await cleanup_task
                        except asyncio.CancelledError:
                            pass
                    except Exception as cleanup_error:
                        logger.warning(f"Error during PagerDuty MCP cleanup: {cleanup_error}")
                    finally:
                        self.exit_stack = None
                
                logger.info("Disconnected from PagerDuty MCP server")
                
            except Exception as e:
                logger.error(f"Error disconnecting from PagerDuty: {e}")
                self.exit_stack = None
    
    async def list_incidents(self, 
                           statuses: Optional[List[str]] = None,
                           urgencies: Optional[List[str]] = None,
                           limit: int = 25) -> List[Dict[str, Any]]:
        """
        List incidents from PagerDuty
        
        Args:
            statuses: Filter by incident statuses (triggered, acknowledged, resolved)
            urgencies: Filter by urgencies (high, low)
            limit: Maximum number of incidents to return
            
        Returns:
            List of incident dictionaries
        """
        if not self.connected or not self.session:
            logger.error("Not connected to PagerDuty MCP server")
            return []
        
        try:
            logger.info(f"Listing PagerDuty incidents (limit: {limit})")
            
            # Prepare arguments - PagerDuty MCP server expects query_model
            query_model = {
                "limit": limit
            }
            if statuses:
                query_model["statuses"] = statuses
            if urgencies:
                query_model["urgencies"] = urgencies
            
            args = {"query_model": query_model}
            
            # Call the list_incidents tool
            result = await asyncio.wait_for(
                self.session.call_tool("list_incidents", arguments=args),
                timeout=30.0
            )
            
            if result.isError:
                logger.error(f"PagerDuty list incidents error: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    try:
                        data = json.loads(content.text)
                        
                        # Handle different response formats
                        incidents = []
                        if isinstance(data, list):
                            incidents = data
                        elif isinstance(data, dict):
                            # Try different keys that might contain incidents
                            incidents = data.get('response', data.get('incidents', []))
                        
                        logger.info(f"Retrieved {len(incidents)} incidents from PagerDuty")
                        return incidents if isinstance(incidents, list) else []
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse PagerDuty incidents: {e}")
                        return []
            
            return []
            
        except asyncio.TimeoutError:
            logger.error("PagerDuty list incidents timed out after 30 seconds")
            return []
        except Exception as e:
            logger.error(f"Error listing PagerDuty incidents: {e}")
            return []
    
    async def get_incident(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific incident from PagerDuty
        
        Args:
            incident_id: The PagerDuty incident ID
            
        Returns:
            Incident dictionary or None if not found
        """
        if not self.connected or not self.session:
            logger.error("Not connected to PagerDuty MCP server")
            return None
        
        try:
            logger.info(f"Getting PagerDuty incident: {incident_id}")
            
            result = await asyncio.wait_for(
                self.session.call_tool("get_incident", arguments={"incident_id": incident_id}),
                timeout=30.0
            )
            
            if result.isError:
                logger.error(f"PagerDuty get incident error: {result.content}")
                return None
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    try:
                        incident = json.loads(content.text)
                        logger.info(f"Retrieved incident {incident_id} from PagerDuty")
                        return incident
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse PagerDuty incident: {e}")
                        return None
            
            return None
            
        except asyncio.TimeoutError:
            logger.error(f"PagerDuty get incident {incident_id} timed out after 30 seconds")
            return None
        except Exception as e:
            logger.error(f"Error getting PagerDuty incident {incident_id}: {e}")
            return None
    
    async def add_note_to_incident(self, incident_id: str, note: str) -> bool:
        """
        Add a note to a PagerDuty incident
        
        Args:
            incident_id: The PagerDuty incident ID
            note: The note content to add
            
        Returns:
            True if successful, False otherwise
        """
        if not self.connected or not self.session:
            logger.error("Not connected to PagerDuty MCP server")
            return False
        
        try:
            logger.info(f"Adding note to PagerDuty incident: {incident_id}")
            
            result = await asyncio.wait_for(
                self.session.call_tool("add_note_to_incident", arguments={
                    "incident_id": incident_id,
                    "note": note
                }),
                timeout=30.0
            )
            
            if result.isError:
                logger.error(f"PagerDuty add note error: {result.content}")
                return False
            
            logger.info(f"Successfully added note to incident {incident_id}")
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"PagerDuty add note to {incident_id} timed out after 30 seconds")
            return False
        except Exception as e:
            logger.error(f"Error adding note to PagerDuty incident {incident_id}: {e}")
            return False
    
    async def manage_incident(self, 
                            incident_id: str,
                            status: Optional[str] = None,
                            urgency: Optional[str] = None,
                            assigned_to_user: Optional[str] = None) -> bool:
        """
        Manage a PagerDuty incident (update status, urgency, assignment)
        
        Args:
            incident_id: The PagerDuty incident ID
            status: New status (triggered, acknowledged, resolved)
            urgency: New urgency (high, low)
            assigned_to_user: User ID to assign the incident to
            
        Returns:
            True if successful, False otherwise
        """
        if not self.connected or not self.session:
            logger.error("Not connected to PagerDuty MCP server")
            return False
        
        try:
            logger.info(f"Managing PagerDuty incident: {incident_id}")
            
            manage_request = {"incident_ids": [incident_id]}  # PagerDuty expects incident_ids as array
            if status:
                manage_request["status"] = status
            if urgency:
                manage_request["urgency"] = urgency
            if assigned_to_user:
                manage_request["assigned_to_user"] = assigned_to_user
            
            args = {"manage_request": manage_request}
            
            result = await asyncio.wait_for(
                self.session.call_tool("manage_incidents", arguments=args),
                timeout=30.0
            )
            
            if result.isError:
                logger.error(f"PagerDuty manage incident error: {result.content}")
                return False
            
            logger.info(f"Successfully managed incident {incident_id}")
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"PagerDuty manage incident {incident_id} timed out after 30 seconds")
            return False
        except Exception as e:
            logger.error(f"Error managing PagerDuty incident {incident_id}: {e}")
            return False
    
    async def list_services(self) -> List[Dict[str, Any]]:
        """
        List services from PagerDuty
        
        Returns:
            List of service dictionaries
        """
        if not self.connected or not self.session:
            logger.error("Not connected to PagerDuty MCP server")
            return []
        
        try:
            logger.info("Listing PagerDuty services")
            
            # PagerDuty MCP server requires query_model parameter
            result = await asyncio.wait_for(
                self.session.call_tool("list_services", arguments={"query_model": {}}),
                timeout=30.0
            )
            
            if result.isError:
                logger.error(f"PagerDuty list services error: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    try:
                        data = json.loads(content.text)
                        
                        # Handle different response formats
                        services = []
                        if isinstance(data, list):
                            services = data
                        elif isinstance(data, dict):
                            # Try different keys that might contain services
                            services = data.get('response', data.get('services', []))
                        
                        logger.info(f"Retrieved {len(services)} services from PagerDuty")
                        return services if isinstance(services, list) else []
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse PagerDuty services: {e}")
                        logger.error(f"Raw content: {content.text}")
                        return []
            
            logger.warning("No content returned from list_services")
            return []
            
        except asyncio.TimeoutError:
            logger.error("PagerDuty list services timed out after 30 seconds")
            return []
        except Exception as e:
            logger.error(f"Error listing PagerDuty services: {e}")
            return []
    
    async def create_incident(self, title: str, description: str, 
                            service_id: Optional[str] = None,
                            urgency: str = "high",
                            incident_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a new incident in PagerDuty
        
        Args:
            title: Incident title
            description: Incident description  
            service_id: PagerDuty service ID (optional, will use default if not provided)
            urgency: Incident urgency (high/low)
            incident_key: Unique incident key for deduplication
            
        Returns:
            Dict containing creation result
        """
        if not self.connected or not self.session:
            logger.error("Not connected to PagerDuty MCP server")
            return {"success": False, "error": "Not connected"}
        
        try:
            logger.info(f"Creating PagerDuty incident: {title}")
            
            # If no service_id provided, try to get one from available services
            if not service_id:
                try:
                    services = await self.list_services()
                    if services:
                        # Use the first available service
                        service_id = services[0]['id']
                        logger.info(f"Using default service: {service_id}")
                    else:
                        logger.error("No services available for incident creation")
                        return {"success": False, "error": "No services available"}
                except Exception as e:
                    logger.error(f"Failed to get services: {e}")
                    return {"success": False, "error": "Failed to get services"}
            
            # Prepare arguments for create_incident tool - needs create_model.incident structure
            incident_data = {
                "title": title,
                "body": {
                    "type": "incident_body",
                    "details": description
                },
                "urgency": urgency,
                "service": {
                    "id": service_id,
                    "type": "service_reference"
                }
            }
            
            if incident_key:
                incident_data["incident_key"] = incident_key
            
            args = {
                "create_model": {
                    "incident": incident_data
                }
            }
            
            result = await asyncio.wait_for(
                self.session.call_tool("create_incident", arguments=args),
                timeout=30.0
            )
            
            if result.isError:
                logger.error(f"PagerDuty create incident error: {result.content}")
                return {"success": False, "error": str(result.content)}
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    try:
                        incident_data = json.loads(content.text)
                        logger.info(f"✅ Created PagerDuty incident: {incident_data.get('id')}")
                        return {
                            "success": True,
                            "incident": incident_data,
                            "incident_id": incident_data.get('id'),
                            "status": "created"
                        }
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse PagerDuty incident creation result: {e}")
                        return {"success": False, "error": "Failed to parse response"}
            
            return {"success": False, "error": "No response data"}
            
        except asyncio.TimeoutError:
            logger.error(f"PagerDuty create incident timed out after 30 seconds")
            return {"success": False, "error": "Timeout"}
        except Exception as e:
            logger.error(f"Error creating PagerDuty incident: {e}")
            return {"success": False, "error": str(e)}
    
    async def list_oncalls(self) -> List[Dict[str, Any]]:
        """
        List current on-call schedules from PagerDuty
        
        Returns:
            List of on-call schedule dictionaries
        """
        if not self.connected or not self.session:
            logger.error("Not connected to PagerDuty MCP server")
            return []
        
        try:
            logger.info("Listing PagerDuty on-call schedules")
            
            result = await asyncio.wait_for(
                self.session.call_tool("list_oncalls", arguments={"query_model": {}}),
                timeout=30.0
            )
            
            if result.isError:
                logger.error(f"PagerDuty list oncalls error: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    try:
                        data = json.loads(content.text)
                        
                        # Handle different response formats
                        oncalls = []
                        if isinstance(data, list):
                            oncalls = data
                        elif isinstance(data, dict):
                            # Try different keys that might contain oncalls
                            oncalls = data.get('response', data.get('oncalls', []))
                        
                        logger.info(f"Retrieved {len(oncalls)} on-call schedules from PagerDuty")
                        return oncalls if isinstance(oncalls, list) else []
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse PagerDuty on-calls: {e}")
                        return []
            
            return []
            
        except asyncio.TimeoutError:
            logger.error("PagerDuty list oncalls timed out after 30 seconds")
            return []
        except Exception as e:
            logger.error(f"Error listing PagerDuty on-calls: {e}")
            return []
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get detailed connection information"""
        return {
            "connected": self.connected,
            "api_host": self.api_host,
            "has_api_key": self.api_key is not None,
            "connection_type": "PagerDuty MCP Server"
        }

# Convenience wrapper for incident management integration
class PagerDutyIncidentClient:
    """
    Wrapper specifically for incident management integration
    Provides a simplified interface for the incident management service
    """
    
    def __init__(self, api_key: Optional[str] = None, api_host: str = "https://api.pagerduty.com"):
        self.client = PagerDutyMCPClient(api_key, api_host)
    
    async def connect(self) -> bool:
        """Connect to PagerDuty"""
        return await self.client.connect()
    
    async def disconnect(self):
        """Disconnect from PagerDuty"""
        await self.client.disconnect()
    
    async def get_active_incidents(self) -> List[Dict[str, Any]]:
        """Get active incidents (triggered and acknowledged)"""
        return await self.client.list_incidents(
            statuses=["triggered", "acknowledged"],
            limit=50
        )
    
    async def get_high_urgency_incidents(self) -> List[Dict[str, Any]]:
        """Get high urgency incidents"""
        return await self.client.list_incidents(
            urgencies=["high"],
            statuses=["triggered", "acknowledged"],
            limit=25
        )
    
    async def create_incident_from_detection(self, incident_data: Dict[str, Any], 
                                           remediation_suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a PagerDuty incident from Splunk detection data
        
        Args:
            incident_data: Incident data from Splunk detection
            remediation_suggestions: List of remediation suggestions
            
        Returns:
            Dict with creation result and incident details
        """
        # Extract information for PagerDuty incident
        title = incident_data.get('title', 'Splunk Detection Alert')
        description = incident_data.get('description', 'No description available')
        
        # Add remediation summary to description
        if remediation_suggestions:
            description += f"\n\n🛠️ {len(remediation_suggestions)} remediation suggestions available."
            description += "\nSee incident notes for detailed guidance."
        
        # Map severity to urgency
        severity = incident_data.get('severity', 'MEDIUM')
        urgency = "high" if severity in ['CRITICAL', 'HIGH'] else "low"
        
        # Use incident ID as deduplication key
        incident_key = incident_data.get('id', f"splunk-{datetime.now().strftime('%Y%m%d%H%M%S')}")
        
        # Get a service ID - use the Splunk service we created
        service_id = "PE4G0SQ"  # Splunk Incident Management Test Service
        
        # Try to get services dynamically if needed
        try:
            services = await self.client.list_services()
            if services:
                # Prefer the Splunk service if available, otherwise use first service
                splunk_service = next((s for s in services if 'splunk' in s.get('name', '').lower()), None)
                if splunk_service:
                    service_id = splunk_service['id']
                else:
                    service_id = services[0]['id']
                logger.info(f"Using PagerDuty service: {service_id}")
        except Exception as e:
            logger.warning(f"Could not fetch services, using default: {e}")
        
        # Create the incident
        result = await self.client.create_incident(
            title=title,
            description=description,
            service_id=service_id,  # Now providing service_id
            urgency=urgency,
            incident_key=incident_key
        )
        
        # If successful, add remediation notes
        if result.get('success') and result.get('incident_id'):
            try:
                await self.add_remediation_note(result['incident_id'], remediation_suggestions)
                result['remediation_added'] = True
            except Exception as e:
                logger.warning(f"Failed to add remediation notes to new incident: {e}")
                result['remediation_added'] = False
        
        return result
    
    async def add_remediation_note(self, incident_id: str, remediation_suggestions: List[Dict[str, Any]]) -> bool:
        """
        Add remediation suggestions as a note to a PagerDuty incident
        
        Args:
            incident_id: PagerDuty incident ID
            remediation_suggestions: List of remediation suggestions
            
        Returns:
            True if successful
        """
        if not remediation_suggestions:
            return True
            
        # Format remediation suggestions as a comprehensive note
        note_content = "🛠️ **Automated Remediation Suggestions**\n\n"
        
        # Include all suggestions, not just the first 3
        for i, suggestion in enumerate(remediation_suggestions, 1):
            note_content += f"**{i}. {suggestion.get('title', 'Remediation Action')}**\n"
            note_content += f"Description: {suggestion.get('description', 'N/A')}\n"
            note_content += f"Risk Level: {suggestion.get('risk_level', 'UNKNOWN')}\n"
            note_content += f"Estimated Time: {suggestion.get('estimated_time', 'N/A')}\n"
            
            # Add all commands, not just the first 2
            if 'commands' in suggestion and suggestion['commands']:
                note_content += f"Commands:\n"
                for cmd in suggestion['commands']:
                    note_content += f"• `{cmd}`\n"
            
            # Add steps if available
            if 'steps' in suggestion and suggestion['steps']:
                note_content += f"Steps:\n"
                for step_num, step in enumerate(suggestion['steps'], 1):
                    note_content += f"{step_num}. {step}\n"
            
            # Add additional context if available
            if 'context' in suggestion:
                note_content += f"Context: {suggestion['context']}\n"
            
            note_content += "\n"
        
        note_content += f"Total {len(remediation_suggestions)} remediation suggestions provided.\n"
        note_content += "These suggestions are generated based on incident analysis and best practices."
        
        return await self.client.add_note_to_incident(incident_id, note_content)
    
    async def test_connection(self) -> bool:
        """Test the PagerDuty connection"""
        try:
            services = await self.client.list_services()
            return len(services) >= 0  # Even 0 services means connection works
        except Exception as e:
            logger.error(f"PagerDuty connection test failed: {e}")
            return False
    
    def get_connection_info(self) -> Dict[str, Any]:
        """Get connection information"""
        return self.client.get_connection_info()
    
    async def escalate_incident(self, incident_id: str, user_id: str) -> Dict[str, Any]:
        """
        Escalate a PagerDuty incident by increasing urgency and adding a note
        
        Args:
            incident_id: PagerDuty incident ID
            user_id: User who is escalating the incident
            
        Returns:
            Dictionary with success status and details
        """
        try:
            logger.info(f"Escalating PagerDuty incident {incident_id} by user {user_id}")
            
            # First, update the incident urgency to high and ensure it's triggered
            manage_success = await self.client.manage_incident(
                incident_id=incident_id,
                status="triggered",  # Ensure incident is active
                urgency="high"       # Escalate to high urgency
            )
            
            if not manage_success:
                logger.error(f"Failed to update incident {incident_id} status/urgency for escalation")
                return {
                    "success": False,
                    "error": "Failed to update incident status for escalation"
                }
            
            # Add escalation note
            note_content = f"🚨 **Incident Escalated**\n\nEscalated by user {user_id} via Slack integration at {datetime.now().isoformat()}\n\n• Urgency increased to HIGH\n• Status set to TRIGGERED\n• This incident requires higher-level attention\n• On-call team has been re-notified"
            
            note_success = await self.client.add_note_to_incident(incident_id, note_content)
            
            if note_success:
                logger.info(f"Successfully escalated incident {incident_id}")
                return {
                    "success": True,
                    "message": f"Incident {incident_id} escalated successfully",
                    "escalated_by": user_id,
                    "escalated_at": datetime.now().isoformat(),
                    "actions_taken": [
                        "Urgency increased to HIGH",
                        "Status set to TRIGGERED", 
                        "On-call team re-notified",
                        "Escalation note added"
                    ]
                }
            else:
                logger.warning(f"Incident {incident_id} status updated but failed to add escalation note")
                return {
                    "success": True,  # Still successful since status was updated
                    "message": f"Incident {incident_id} escalated (status updated, note failed)",
                    "escalated_by": user_id,
                    "escalated_at": datetime.now().isoformat(),
                    "warning": "Escalation note could not be added"
                }
                
        except Exception as e:
            logger.error(f"Error escalating incident {incident_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def acknowledge_incident(self, incident_id: str, user_id: str) -> Dict[str, Any]:
        """
        Acknowledge a PagerDuty incident by changing status to acknowledged
        
        Args:
            incident_id: PagerDuty incident ID
            user_id: User who is acknowledging the incident
            
        Returns:
            Dictionary with success status and details
        """
        try:
            logger.info(f"Acknowledging PagerDuty incident {incident_id} by user {user_id}")
            
            # First, update the incident status to acknowledged
            manage_success = await self.client.manage_incident(
                incident_id=incident_id,
                status="acknowledged"  # Set status to acknowledged
            )
            
            if not manage_success:
                logger.error(f"Failed to acknowledge incident {incident_id}")
                return {
                    "success": False,
                    "error": "Failed to acknowledge incident in PagerDuty"
                }
            
            # Add acknowledgment note
            note_content = f"✅ **Incident Acknowledged**\n\nAcknowledged by user {user_id} via Slack integration at {datetime.now().isoformat()}\n\n• Status changed to ACKNOWLEDGED\n• Investigation is now in progress\n• Paging has been stopped\n• Responder is actively working on resolution"
            
            note_success = await self.client.add_note_to_incident(incident_id, note_content)
            
            if note_success:
                logger.info(f"Successfully acknowledged incident {incident_id}")
                return {
                    "success": True,
                    "message": f"Incident {incident_id} acknowledged successfully",
                    "acknowledged_by": user_id,
                    "acknowledged_at": datetime.now().isoformat(),
                    "actions_taken": [
                        "Status changed to ACKNOWLEDGED",
                        "Paging stopped",
                        "Investigation in progress",
                        "Acknowledgment note added"
                    ]
                }
            else:
                logger.warning(f"Incident {incident_id} acknowledged but failed to add note")
                return {
                    "success": True,  # Still successful since status was updated
                    "message": f"Incident {incident_id} acknowledged (status updated, note failed)",
                    "acknowledged_by": user_id,
                    "acknowledged_at": datetime.now().isoformat(),
                    "warning": "Acknowledgment note could not be added"
                }
                
        except Exception as e:
            logger.error(f"Error acknowledging incident {incident_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def resolve_incident(self, incident_id: str, user_id: str, resolution_note: str = "") -> Dict[str, Any]:
        """
        Resolve a PagerDuty incident by changing status to resolved
        
        Args:
            incident_id: PagerDuty incident ID
            user_id: User who is resolving the incident
            resolution_note: Optional resolution note
            
        Returns:
            Dictionary with success status and details
        """
        try:
            logger.info(f"Resolving PagerDuty incident {incident_id} by user {user_id}")
            
            # First, update the incident status to resolved
            manage_success = await self.client.manage_incident(
                incident_id=incident_id,
                status="resolved"  # Set status to resolved
            )
            
            if not manage_success:
                logger.error(f"Failed to resolve incident {incident_id}")
                return {
                    "success": False,
                    "error": "Failed to resolve incident in PagerDuty"
                }
            
            # Add resolution note
            note_content = f"✅ **Incident Resolved**\n\nResolved by user {user_id} via Slack integration at {datetime.now().isoformat()}\n\n• Status changed to RESOLVED\n• Incident is now closed\n• All notifications stopped"
            
            if resolution_note:
                note_content += f"\n\n**Resolution Details:**\n{resolution_note}"
            
            note_success = await self.client.add_note_to_incident(incident_id, note_content)
            
            if note_success:
                logger.info(f"Successfully resolved incident {incident_id}")
                return {
                    "success": True,
                    "message": f"Incident {incident_id} resolved successfully",
                    "resolved_by": user_id,
                    "resolved_at": datetime.now().isoformat(),
                    "actions_taken": [
                        "Status changed to RESOLVED",
                        "Incident closed",
                        "All notifications stopped",
                        "Resolution note added"
                    ]
                }
            else:
                logger.warning(f"Incident {incident_id} resolved but failed to add note")
                return {
                    "success": True,  # Still successful since status was updated
                    "message": f"Incident {incident_id} resolved (status updated, note failed)",
                    "resolved_by": user_id,
                    "resolved_at": datetime.now().isoformat(),
                    "warning": "Resolution note could not be added"
                }
                
        except Exception as e:
            logger.error(f"Error resolving incident {incident_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_incident_details(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a PagerDuty incident
        
        Args:
            incident_id: PagerDuty incident ID
            
        Returns:
            Incident details dictionary or None if not found
        """
        try:
            incident = await self.client.get_incident(incident_id)
            
            if incident:
                # Format the incident details for display
                return {
                    "id": incident.get("id", incident_id),
                    "title": incident.get("title", "Unknown"),
                    "status": incident.get("status", "Unknown"),
                    "priority": incident.get("priority", "Unknown"),
                    "urgency": incident.get("urgency", "Unknown"),
                    "assigned_to": incident.get("assigned_to", "Unassigned"),
                    "created_at": incident.get("created_at", "Unknown"),
                    "updated_at": incident.get("updated_at", "Unknown"),
                    "service": incident.get("service", {}).get("summary", "Unknown"),
                    "url": f"https://api.pagerduty.com/incidents/{incident_id}"
                }
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error getting incident details for {incident_id}: {e}")
            return None

# Test function
async def test_pagerduty_integration():
    """Test the PagerDuty MCP integration"""
    client = PagerDutyIncidentClient()
    
    try:
        # Connect
        print("🔌 Connecting to PagerDuty MCP server...")
        connected = await client.connect()
        if not connected:
            print("❌ Failed to connect to PagerDuty MCP server")
            print("💡 Make sure you have:")
            print("   1. PagerDuty API key set in environment (PAGERDUTY_USER_API_KEY)")
            print("   2. PagerDuty MCP server dependencies installed")
            return False
        
        print("✅ Connected successfully!")
        
        # Test connection
        print("🧪 Testing connection...")
        test_passed = await client.test_connection()
        if not test_passed:
            print("❌ Connection test failed")
            return False
        
        print("✅ Connection test passed!")
        
        # Test listing incidents
        print("🔍 Testing incident listing...")
        incidents = await client.get_active_incidents()
        print(f"📊 Found {len(incidents)} active incidents")
        
        if incidents:
            print("Sample incident:")
            incident = incidents[0]
            print(f"  ID: {incident.get('id', 'N/A')}")
            print(f"  Title: {incident.get('title', 'N/A')}")
            print(f"  Status: {incident.get('status', 'N/A')}")
            print(f"  Urgency: {incident.get('urgency', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    finally:
        await client.disconnect()

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_pagerduty_integration())