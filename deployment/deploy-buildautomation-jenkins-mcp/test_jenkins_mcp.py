#!/usr/bin/env python3
"""
Test script for Jenkins MCP Server
"""

import json
import urllib.request
from typing import Dict, Any

# Configuration
MCP_SERVER_URL = "https://your-mcp-api-gateway-url.amazonaws.com/dev"
ACCESS_TOKEN = "your-access-token-here"  # Get this from ./get_fresh_token.sh

def make_mcp_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Make authenticated request to MCP server"""
    data = json.dumps(request_data).encode('utf-8')
    req = urllib.request.Request(f"{MCP_SERVER_URL}/", data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Authorization', f'Bearer {ACCESS_TOKEN}')
    
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))

def test_tool(tool_name: str, arguments: Dict[str, Any] = None):
    """Test a specific Jenkins tool"""
    if arguments is None:
        arguments = {}
    
    print(f"\n🔧 Testing {tool_name}...")
    
    request_data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    
    try:
        response = make_mcp_request(request_data)
        if "result" in response:
            content = response["result"]["content"][0]["text"]
            print(f"✅ {tool_name}: Success")
            print(f"   Response: {content[:200]}...")
        else:
            print(f"❌ {tool_name}: Error - {response}")
    except Exception as e:
        print(f"❌ {tool_name}: Exception - {e}")

def main():
    """Test all Jenkins MCP tools"""
    print("🚀 Testing Jenkins MCP Server Tools")
    print("=" * 50)
    
    # Test basic tools
    test_tool("jenkins_health_check")
    test_tool("jenkins_list_jobs")
    test_tool("jenkins_get_queue_info")
    test_tool("jenkins_get_nodes")
    
    # Test job-specific tools (using the test-job we found)
    test_tool("jenkins_get_job_info", {"job_name": "test-job"})
    test_tool("jenkins_list_builds", {"job_name": "test-job", "limit": 5})
    
    # Test job creation
    test_tool("jenkins_create_job", {
        "job_name": "mcp-test-job",
        "job_type": "freestyle",
        "description": "Test job created by MCP",
        "script": "echo 'Hello from MCP Jenkins!'"
    })
    
    print("\n🎉 Jenkins MCP Server testing completed!")

if __name__ == "__main__":
    main()
