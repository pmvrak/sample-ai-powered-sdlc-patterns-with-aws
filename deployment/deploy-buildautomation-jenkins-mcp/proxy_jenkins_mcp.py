#!/usr/bin/env python3
"""
Working Jenkins MCP Server
Uses a pre-authenticated token to connect to your Jenkins MCP server
"""

import asyncio
import json
import sys
import urllib.request
from typing import Any, Dict, List
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Configuration - Use the fresh access token
MCP_SERVER_URL = "https://example-mcp-api-gateway-url.amazonaws.com/dev"
ACCESS_TOKEN = "example-access-token-here"  # Get this from ./get_fresh_token.sh

def make_mcp_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Make authenticated request to MCP server"""
    data = json.dumps(request_data).encode('utf-8')
    req = urllib.request.Request(f"{MCP_SERVER_URL}/", data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {ACCESS_TOKEN}')
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

# Create MCP server
server = Server("working-jenkins-mcp")

@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available Jenkins tools"""
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list"
    }
    
    try:
        response = make_mcp_request(request_data)
        if "result" in response and "tools" in response["result"]:
            return [
                Tool(
                    name=tool["name"],
                    description=tool["description"],
                    inputSchema=tool["inputSchema"]
                )
                for tool in response["result"]["tools"]
            ]
        else:
            print(f"Unexpected response format: {response}")
            return []
    except Exception as e:
        print(f"Error listing tools: {e}")
        return []

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Call a Jenkins tool"""
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments
        }
    }
    
    try:
        response = make_mcp_request(request_data)
        if "result" in response and "content" in response["result"]:
            return [
                TextContent(
                    type="text",
                    text=content["text"]
                )
                for content in response["result"]["content"]
            ]
        else:
            error_msg = response.get("error", {}).get("message", "Unknown error")
            return [TextContent(type="text", text=f"Error: {error_msg}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error calling tool {name}: {str(e)}")]

async def main():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
