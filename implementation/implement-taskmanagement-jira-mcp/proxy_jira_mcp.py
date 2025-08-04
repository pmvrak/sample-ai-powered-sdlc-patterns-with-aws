#!/usr/bin/env python3
"""
Working JIRA MCP Server
Uses a pre-authenticated token to connect to your JIRA MCP server
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
MCP_SERVER_URL = "https://7d6997mkp9.execute-api.us-east-1.amazonaws.com/dev"
ACCESS_TOKEN = "noLzF9E06-oXWdmJtpOofk9kFnOmMG98GhOvnQz4XVM"  # Fresh token - UPDATE THIS

def make_mcp_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Make authenticated request to MCP server"""
    data = json.dumps(request_data).encode('utf-8')
    req = urllib.request.Request(f"{MCP_SERVER_URL}/", data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {ACCESS_TOKEN}')
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

# Create MCP server
server = Server("working-jira-mcp")

@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available JIRA tools"""
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
    except Exception as e:
        print(f"Error listing tools: {e}", file=sys.stderr)
    
    return []

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[TextContent]:
    """Call a JIRA tool"""
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
                TextContent(type="text", text=content["text"])
                for content in response["result"]["content"]
                if content.get("type") == "text"
            ]
        elif "error" in response:
            return [TextContent(type="text", text=f"Error: {response['error']['message']}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error calling tool: {str(e)}")]
    
    return [TextContent(type="text", text="No response received")]

async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
