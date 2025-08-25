"""
Real Splunk MCP Client Integration
Connects to the existing Splunk MCP server in ../server/splunk-server.py
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from contextlib import AsyncExitStack

logger = logging.getLogger(__name__)

class RealSplunkMCPClient:
    """
    Real integration with the existing Splunk MCP server
    Uses the actual tools: get_splunk_results, get_splunk_fields, etc.
    """
    
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None
        self.connected = False
        self._connection_lock = asyncio.Lock()
        
    async def connect(self):
        """Connect to the existing Splunk MCP server"""
        async with self._connection_lock:
            if self.connected:
                return True
                
            try:
                logger.info("Connecting to Splunk MCP server...")
                
                # Create new exit stack for this connection
                self.exit_stack = AsyncExitStack()
                
                # Connect to the existing Splunk server
                import os
                from pathlib import Path
                
                # Get the absolute path to the server directory
                current_dir = Path(__file__).parent.parent  # Go up from integrations/ to incident_management/
                server_dir = current_dir / "server"  # Go to incident_management/server (copied in Docker)
                
                # Verify server directory exists
                if not server_dir.exists():
                    raise FileNotFoundError(f"Splunk server directory not found: {server_dir}")
                
                server_script = server_dir / "splunk-server.py"
                if not server_script.exists():
                    raise FileNotFoundError(f"Splunk server script not found: {server_script}")
                
                logger.info(f"Using Splunk server at: {server_dir}")
                
                # Set up environment variables for the server
                server_env = os.environ.copy()
                server_env.update({
                    'secret_arn': os.getenv('SECRET_ARN', 'splunk-bedrock-secret'),
                    'FASTMCP_DEBUG': 'true'
                })
                
                server_params = StdioServerParameters(
                    command="python",
                    args=["splunk-server.py"],
                    cwd=str(server_dir),  # Use absolute path
                    env=server_env
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
                logger.info(f"Connected to Splunk MCP server. Available tools: {available_tools}")
                
                self.connected = True
                return True
                
            except Exception as e:
                logger.error(f"Failed to connect to Splunk MCP server: {e}")
                logger.error(f"Server directory: {server_dir}")
                logger.error(f"Current working directory: {os.getcwd()}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception details: {str(e)}")
                
                self.connected = False
                # Clean up on failure
                if self.exit_stack:
                    try:
                        await self.exit_stack.aclose()
                    except Exception as cleanup_error:
                        logger.warning(f"Error during cleanup: {cleanup_error}")
                    self.exit_stack = None
                return False
    
    async def execute_search(self, query: str, earliest_time: str = "-1h") -> List[Dict]:
        """
        Execute Splunk search using the real get_splunk_results tool
        """
        if not self.connected or not self.session:
            logger.error("Not connected to Splunk MCP server")
            return []
        
        try:
            logger.info(f"Executing Splunk search: {query}")
            
            # Call the real get_splunk_results tool with timeout
            result = await asyncio.wait_for(
                self.session.call_tool(
                    "get_splunk_results",
                    arguments={"search_query": query}
                ),
                timeout=30.0  # 30 second timeout
            )
            
            if result.isError:
                logger.error(f"Splunk search error: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                # The tool returns a list of TextContent objects
                content = result.content[0]
                if hasattr(content, 'text'):
                    # Parse the JSON response
                    import json
                    try:
                        if content.text == "Query did not return any results, please rewrite the SPL query":
                            logger.info("Query returned no results")
                            return []
                        
                        # The tool returns the results as a JSON string or list
                        if isinstance(content.text, str):
                            results = json.loads(content.text)
                        else:
                            results = content.text
                        
                        logger.info(f"Search returned {len(results)} results")
                        return results if isinstance(results, list) else [results]
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse Splunk results: {e}")
                        return []
            
            return []
            
        except asyncio.TimeoutError:
            logger.error(f"Splunk search timed out after 30 seconds: {query}")
            return []
        except Exception as e:
            logger.error(f"Error executing Splunk search: {e}")
            # If connection is broken, mark as disconnected
            if "connection" in str(e).lower() or "broken" in str(e).lower():
                self.connected = False
            return []
    
    async def get_sourcetype_fields(self, sourcetype: str) -> List[str]:
        """
        Get fields for a sourcetype using the real get_splunk_fields tool
        """
        if not self.connected or not self.session:
            logger.error("Not connected to Splunk MCP server")
            return []
        
        try:
            logger.info(f"Getting fields for sourcetype: {sourcetype}")
            
            result = await self.session.call_tool(
                "get_splunk_fields",
                arguments={"sourcetype": sourcetype}
            )
            
            if result.isError:
                logger.error(f"Error getting fields: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    try:
                        fields = json.loads(content.text)
                        return fields if isinstance(fields, list) else []
                    except json.JSONDecodeError:
                        # If it's not JSON, it might be a direct list
                        return content.text if isinstance(content.text, list) else []
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting sourcetype fields: {e}")
            return []
    
    async def search_aws_sourcetypes(self, aws_sourcetype: str) -> List[str]:
        """
        Search AWS sourcetypes using the real search_aws_sourcetypes tool
        """
        if not self.connected or not self.session:
            logger.error("Not connected to Splunk MCP server")
            return []
        
        try:
            logger.info(f"Searching AWS sourcetypes for: {aws_sourcetype}")
            
            result = await self.session.call_tool(
                "search_aws_sourcetypes",
                arguments={"awssourcetype": aws_sourcetype}
            )
            
            if result.isError:
                logger.error(f"Error searching sourcetypes: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    try:
                        sourcetypes = json.loads(content.text)
                        return sourcetypes if isinstance(sourcetypes, list) else [sourcetypes]
                    except json.JSONDecodeError:
                        return [content.text] if content.text != "No sourcetypes found" else []
            
            return []
            
        except Exception as e:
            logger.error(f"Error searching AWS sourcetypes: {e}")
            return []
    
    async def get_lookups(self, sourcetype: str) -> List[str]:
        """
        Get lookups for a sourcetype using the real get_splunk_lookups tool
        """
        if not self.connected or not self.session:
            logger.error("Not connected to Splunk MCP server")
            return []
        
        try:
            logger.info(f"Getting lookups for sourcetype: {sourcetype}")
            
            result = await self.session.call_tool(
                "get_splunk_lookups",
                arguments={"sourcetype": sourcetype}
            )
            
            if result.isError:
                logger.error(f"Error getting lookups: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    try:
                        lookups = json.loads(content.text)
                        return lookups if isinstance(lookups, list) else []
                    except json.JSONDecodeError:
                        return content.text if isinstance(content.text, list) else []
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting lookups: {e}")
            return []
    
    async def get_lookup_values(self, lookup_name: str) -> List[Dict]:
        """
        Get lookup values using the real get_splunk_lookup_values tool
        """
        if not self.connected or not self.session:
            logger.error("Not connected to Splunk MCP server")
            return []
        
        try:
            logger.info(f"Getting lookup values for: {lookup_name}")
            
            result = await self.session.call_tool(
                "get_splunk_lookup_values",
                arguments={"lookup_name": lookup_name}
            )
            
            if result.isError:
                logger.error(f"Error getting lookup values: {result.content}")
                return []
            
            # Parse the result
            if isinstance(result.content, list) and len(result.content) > 0:
                content = result.content[0]
                if hasattr(content, 'text'):
                    import json
                    try:
                        values = json.loads(content.text)
                        return values if isinstance(values, list) else []
                    except json.JSONDecodeError:
                        return content.text if isinstance(content.text, list) else []
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting lookup values: {e}")
            return []
    
    async def disconnect(self):
        """Disconnect from the Splunk MCP server"""
        async with self._connection_lock:
            if not self.connected:
                return
                
            try:
                self.connected = False
                self.session = None
                
                if self.exit_stack:
                    # Use asyncio.create_task to handle the cleanup in the correct context
                    cleanup_task = asyncio.create_task(self.exit_stack.aclose())
                    try:
                        await asyncio.wait_for(cleanup_task, timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning("MCP cleanup timed out, forcing cancellation")
                        cleanup_task.cancel()
                        try:
                            await cleanup_task
                        except asyncio.CancelledError:
                            pass
                    except Exception as cleanup_error:
                        logger.warning(f"Error during MCP cleanup: {cleanup_error}")
                    finally:
                        self.exit_stack = None
                
                logger.info("Disconnected from Splunk MCP server")
                
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
                # Force cleanup
                self.exit_stack = None

# Convenience wrapper for incident detection
class SplunkIncidentClient:
    """
    Wrapper specifically for incident detection queries
    """
    
    def __init__(self):
        self.client = RealSplunkMCPClient()
    
    async def connect(self):
        """Connect to Splunk"""
        return await self.client.connect()
    
    async def execute_detection_query(self, query: str) -> List[Dict]:
        """Execute a detection query and return results"""
        return await self.client.execute_search(query)
    
    async def test_connection(self) -> bool:
        """Test the connection with a simple query"""
        try:
            results = await self.client.execute_search(
                "search index=main | head 1 | stats count"
            )
            return len(results) >= 0  # Even 0 results means connection works
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    async def search_events(self, query: str, earliest_time: str = "-1h", latest_time: str = "now") -> List[Dict]:
        """Search events - bridge method for incident management service"""
        return await self.execute_detection_query(query)
    
    async def disconnect(self):
        """Disconnect from Splunk"""
        await self.client.disconnect()

# Test function
async def test_real_splunk_integration():
    """Test the real Splunk MCP integration"""
    client = SplunkIncidentClient()
    
    try:
        # Connect
        print("🔌 Connecting to Splunk MCP server...")
        connected = await client.connect()
        if not connected:
            print("❌ Failed to connect to Splunk MCP server")
            return False
        
        print("✅ Connected successfully!")
        
        # Test connection
        print("🧪 Testing connection...")
        test_passed = await client.test_connection()
        if not test_passed:
            print("❌ Connection test failed")
            return False
        
        print("✅ Connection test passed!")
        
        # Test a real detection query
        print("🔍 Testing incident detection query...")
        results = await client.execute_detection_query(
            "search index=main sourcetype=aws:cloudtrail errorCode!=success | head 5 | stats count by eventSource, errorCode"
        )
        
        print(f"📊 Query returned {len(results)} results")
        if results:
            print("Sample results:")
            for i, result in enumerate(results[:3]):
                print(f"  {i+1}. {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False
    
    finally:
        await client.disconnect()

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_real_splunk_integration())