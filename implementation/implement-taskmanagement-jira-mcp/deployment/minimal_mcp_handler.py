#!/usr/bin/env python3
"""
Fixed Lambda Handler for JIRA MCP Server
Uses simple MCP server without FastAPI dependencies
"""

import json
import os

def lambda_handler(event, context):
    """Fixed Lambda handler that works"""
    try:
        # Import the simple MCP server
        import sys
        sys.path.append('/opt/python')
        sys.path.append('.')
        from lambda_mcp_server import JiraMCPServer
        
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        path = event.get('path') or event.get('rawPath', '/')
        headers = event.get('headers', {})
        body = event.get('body', '')
        
        # Remove stage prefix if present
        if path.startswith('/dev'):
            path = path[4:] or '/'
        
        print(f"Fixed MCP Request: {http_method} {path}")
        
        # Handle different endpoints
        if path == '/health' and http_method == 'GET':
            return handle_health_check()
        
        elif path == '/.well-known/oauth-protected-resource' and http_method == 'GET':
            return handle_protected_resource_metadata()
        
        elif path == '/mcp' and http_method == 'POST':
            return handle_mcp_request(event, context)
        
        elif path == '/' and http_method == 'POST':
            # Check if this is an MCP request
            try:
                if body:
                    parsed_body = json.loads(body)
                    if parsed_body.get('jsonrpc') == '2.0':
                        return handle_mcp_request(event, context)
            except:
                pass
            return handle_health_check()
        
        else:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'message': 'Not Found'})
            }
            
    except Exception as e:
        print(f"Lambda handler error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': 'internal_server_error',
                'error_description': f'Server error: {str(e)}'
            })
        }

def handle_health_check():
    """Handle health check requests"""
    try:
        from jira_client.client import JiraClient
        jira_client = JiraClient()
        
        # Use asyncio to run the async method
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        health_result = loop.run_until_complete(jira_client.test_connection())
        loop.close()
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'healthy',
                'message': 'Fixed JIRA MCP Server is running',
                'mode': 'fixed_lambda_server',
                'health_check': health_result
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'unhealthy',
                'error': str(e)
            })
        }

def handle_protected_resource_metadata():
    """Handle OAuth protected resource metadata"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'resource_server': 'https://4p8xg1e2ii.execute-api.us-east-1.amazonaws.com/dev',
            'authorization_servers': ['https://0bmc3y5o9h.execute-api.us-east-1.amazonaws.com/dev'],
            'scopes_supported': ['mcp:read', 'mcp:write'],
            'bearer_methods_supported': ['header'],
            'resource_documentation': 'https://github.com/your-org/jira-mcp-server'
        })
    }

def handle_mcp_request(event, context):
    """Handle MCP requests with OAuth authentication"""
    try:
        # Check for OAuth token
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization', '')
        
        if not auth_header.startswith('Bearer '):
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'unauthorized',
                    'error_description': 'Valid OAuth Bearer token required for MCP endpoints'
                })
            }
        
        # Extract token (we'll skip validation for now)
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        # Process MCP request using simple server
        from lambda_mcp_server import JiraMCPServer
        mcp_server = JiraMCPServer()
        
        body = event.get('body', '{}')
        if isinstance(body, str):
            request_data = json.loads(body)
        else:
            request_data = body
        
        # Handle MCP methods
        method = request_data.get('method', '')
        
        if method == 'tools/list':
            result = mcp_server.list_tools()
        elif method == 'tools/call':
            params = request_data.get('params', {})
            tool_name = params.get('name', '')
            arguments = params.get('arguments', {})
            result = mcp_server.call_tool(tool_name, arguments)
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'jsonrpc': '2.0',
                    'id': request_data.get('id'),
                    'error': {
                        'code': -32601,
                        'message': f'Method not found: {method}'
                    }
                })
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'jsonrpc': '2.0',
                'id': request_data.get('id'),
                'result': result
            })
        }
        
    except Exception as e:
        print(f"MCP request error: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'jsonrpc': '2.0',
                'id': request_data.get('id', 1) if 'request_data' in locals() else 1,
                'error': {
                    'code': -32603,
                    'message': f'Internal error: {str(e)}'
                }
            })
        }

if __name__ == "__main__":
    # Test locally
    test_event = {
        'httpMethod': 'GET',
        'path': '/health',
        'headers': {},
        'body': ''
    }
    result = lambda_handler(test_event, {})
    print(json.dumps(result, indent=2))
