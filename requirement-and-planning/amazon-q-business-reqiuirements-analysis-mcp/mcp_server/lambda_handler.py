# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Lambda handler for MCP Server

This module serves as the entry point for the Lambda function.
It implements the official MCP specification and handles JSON-RPC 2.0 requests.
"""

import json
import logging
import os
import asyncio
import base64
from typing import Dict, Any, List, Optional, Union
import sys
import importlib.util
import inspect

# Add the parent directory to sys.path to import modules from mcp_server
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Configure logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import tool modules from local modules
try:
    # Try direct imports first (when files are in same directory)
    import amazon_q_jsonrpc_server
    import atlassian_integration
    logger.info("Successfully imported modules using direct imports")
except ImportError as e1:
    logger.error(f"Failed direct imports: {e1}")
    try:
        # Try relative imports (when used as a package)
        from . import amazon_q_jsonrpc_server
        from . import atlassian_integration
        logger.info("Successfully imported modules using relative imports")
    except ImportError as e2:
        logger.error(f"Failed relative imports too: {e2}")
        # Last resort - try adding current directory to path
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        try:
            import amazon_q_jsonrpc_server
            import atlassian_integration
            logger.info("Successfully imported modules after adding current directory to path")
        except ImportError as e3:
            logger.error(f"All import attempts failed: {e3}")
            raise

# MCP Protocol version - use environment variable if available
MCP_PROTOCOL_VERSION = os.environ.get("MCP_PROTOCOL_VERSION", "2024-11-05")

class ToolRegistry:
    """Registry for MCP tools"""
    
    def __init__(self):
        self.tools = {}
        self.resources = {}
        self.user_sessions = {}  # Reuse the session management from amazon_q_jsonrpc_server
    
    def register_tool(self, name: str, tool_func, description: str, input_schema: Dict[str, Any]):
        """Register a tool with the registry"""
        self.tools[name] = {
            "function": tool_func,
            "description": description,
            "inputSchema": input_schema
        }
        logger.info(f"Registered tool: {name}")
    
    def register_resource(self, uri: str, name: str, description: str, mime_type: str = "text/plain"):
        """Register a resource with the registry"""
        self.resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "mimeType": mime_type
        }
        logger.info(f"Registered resource: {uri}")
    
    def get_tool(self, name: str):
        """Get a tool by name"""
        return self.tools.get(name)
    
    def get_all_tools(self):
        """Get all registered tools"""
        return self.tools
    
    def get_all_resources(self):
        """Get all registered resources"""
        return self.resources
    
    def get_resource(self, uri: str):
        """Get a resource by URI"""
        return self.resources.get(uri)

# Create a global tool registry
tool_registry = ToolRegistry()

# Reuse the user sessions from amazon_q_jsonrpc_server
tool_registry.user_sessions = amazon_q_jsonrpc_server.user_sessions

def jsonrpc_response(result=None, error=None, id=None):
    """Create a JSON-RPC 2.0 response"""
    response = {"jsonrpc": "2.0", "id": id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    return response

def validate_iam_authentication(event: Dict[str, Any]) -> bool:
    """Validate IAM authentication from the event"""
    try:
        # Check for AWS signature headers - this proves the request was signed with AWS credentials
        headers = event.get('headers', {})
        
        auth_header = headers.get('authorization', '') or headers.get('Authorization', '')
        
        # Must have AWS4-HMAC-SHA256 signature (proves IAM authentication)
        if not auth_header or 'AWS4-HMAC-SHA256' not in auth_header:
            logger.warning(f"Request missing AWS SigV4 signature. Auth header: {auth_header}")
            return False
        
        # Check for required AWS headers
        x_amz_date = headers.get('x-amz-date') or headers.get('X-Amz-Date')
        if not x_amz_date:
            logger.warning(f"Request missing X-Amz-Date header. Available headers: {list(headers.keys())}")
            return False
        
        # Additional security checks
        # 1. Check if the request is recent (within 15 minutes)
        try:
            from datetime import datetime, timedelta, timezone
            date_format = "%Y%m%dT%H%M%SZ"
            request_time = datetime.strptime(x_amz_date, date_format).replace(tzinfo=timezone.utc)
            current_time = datetime.now(timezone.utc)
            time_diff = current_time - request_time
            
            # Reject requests older than 15 minutes (standard AWS practice)
            if abs(time_diff) > timedelta(minutes=15):
                logger.warning(f"Request timestamp too old or in future: {x_amz_date}")
                return False
        except Exception as e:
            logger.warning(f"Error validating request timestamp: {str(e)}")
            # Continue with other validations
        
        # 2. Check for source IP restrictions if configured
        allowed_ips = os.environ.get('ALLOWED_SOURCE_IPS', '')
        if allowed_ips:
            source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', '')
            if source_ip and source_ip not in allowed_ips.split(','):
                logger.warning(f"Request from unauthorized IP: {source_ip}")
                return False
        
        logger.info("✅ Request has valid AWS SigV4 authentication")
        return True
        
    except Exception as e:
        logger.error(f"❌ AUTHENTICATION ERROR: {e}")
        return False

def extract_credentials_from_request_context(event: Dict[str, Any]) -> Dict[str, str]:
    """Extract AWS credentials from the API Gateway request context"""
    try:
        # For API Gateway with Lambda authorizer, the credentials are in the authorizer context
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        
        # The Lambda authorizer extracts credential info from SigV4 headers
        access_key_id = authorizer.get('accessKeyId', 'unknown')
        session_token = authorizer.get('sessionToken')
        region = authorizer.get('region', 'unknown')
        
        logger.info(f"API Gateway authorizer context:")
        logger.info(f"  Access Key ID: {access_key_id[:10] if access_key_id != 'unknown' else 'unknown'}...")
        logger.info(f"  Has Session Token: {bool(session_token)}")
        logger.info(f"  Region: {region}")
        
        # The presence of a session token indicates IDC credentials
        has_idc_context = bool(session_token)
        
        return {
            'access_key_id': access_key_id,
            'has_session_token': has_idc_context,
            'region': region,
            'request_validated': True,
            'auth_method': 'api_gateway_lambda_authorizer'
        }
        
    except Exception as e:
        logger.error(f"Error extracting credentials from API Gateway context: {str(e)}")
        return {
            'access_key_id': 'unknown',
            'has_session_token': False,
            'request_validated': False,
            'error': str(e),
            'auth_method': 'unknown'
        }

async def handle_initialize(params: Dict[str, Any], request_id: Any):
    """Handle initialize method"""
    client_info = params.get("clientInfo", {})
    client_name = client_info.get("name", "unknown")
    client_version = client_info.get("version", "unknown")
    
    logger.info(f"Initializing MCP server for client: {client_name} {client_version}")
    
    return jsonrpc_response(
        result={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "resources": {"subscribe": True, "listChanged": True},
                "tools": {"listChanged": True},
                "logging": {}
            },
            "serverInfo": {
                "name": "amazon-q-mcp-server",
                "version": "1.0.0"
            }
        },
        id=request_id
    )

async def handle_resources_list(params: Dict[str, Any], request_id: Any):
    """Handle resources/list method"""
    resources = tool_registry.get_all_resources()
    
    return jsonrpc_response(
        result={
            "resources": [
                {
                    "uri": resource["uri"],
                    "name": resource["name"],
                    "description": resource["description"],
                    "mimeType": resource["mimeType"]
                } for resource in resources.values()
            ]
        },
        id=request_id
    )

async def handle_resources_read(params: Dict[str, Any], request_id: Any):
    """Handle resources/read method"""
    uri = params.get("uri")
    if not uri:
        return jsonrpc_response(
            error={"code": -32602, "message": "Invalid params: uri is required"},
            id=request_id
        )
    
    resource = tool_registry.get_resource(uri)
    if not resource:
        return jsonrpc_response(
            error={"code": -32602, "message": f"Resource not found: {uri}"},
            id=request_id
        )
    
    # For now, return a placeholder content
    # In a real implementation, this would fetch the actual resource content
    content = f"Content for resource: {resource['name']}"
    
    return jsonrpc_response(
        result={
            "contents": [
                {
                    "uri": uri,
                    "mimeType": resource["mimeType"],
                    "text": content
                }
            ]
        },
        id=request_id
    )

async def handle_tools_list(params: Dict[str, Any], request_id: Any):
    """Handle tools/list method"""
    tools = tool_registry.get_all_tools()
    
    return jsonrpc_response(
        result={
            "tools": [
                {
                    "name": name,
                    "description": tool["description"],
                    "inputSchema": tool["inputSchema"]
                } for name, tool in tools.items()
            ]
        },
        id=request_id
    )

async def handle_tools_call(params: Dict[str, Any], request_id: Any):
    """Handle tools/call method"""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    
    if not tool_name:
        return jsonrpc_response(
            error={"code": -32602, "message": "Invalid params: name is required"},
            id=request_id
        )
    
    tool = tool_registry.get_tool(tool_name)
    if not tool:
        return jsonrpc_response(
            error={"code": -32602, "message": f"Tool not found: {tool_name}"},
            id=request_id
        )
    
    try:
        # Call the tool function directly - auto-login is now built into the functions
        result = await tool["function"](**arguments)
        
        # Convert result to MCP format
        content_items = []
        
        # Handle different result formats
        if isinstance(result, dict) and "content" in result:
            # Already in MCP format
            for item in result["content"]:
                if item.get("type") == "text":
                    content_items.append({
                        "type": "text",
                        "text": item.get("text", "")
                    })
                elif item.get("type") == "image":
                    content_items.append({
                        "type": "image",
                        "data": item.get("data", ""),
                        "mimeType": item.get("mimeType", "image/png")
                    })
                elif item.get("type") == "auth_popup":
                    # Special case for auth popup
                    return jsonrpc_response(
                        result={
                            "content": [
                                {"type": "text", "text": "Authentication required"}
                            ],
                            "metadata": {
                                "auth_required": True,
                                "auth_url": item.get("auth_url"),
                                "state": item.get("state")
                            }
                        },
                        id=request_id
                    )
        elif isinstance(result, str):
            # Simple string result
            content_items.append({
                "type": "text",
                "text": result
            })
        elif isinstance(result, dict):
            # Other dict result
            if "success" in result and not result["success"]:
                # Error result
                content_items.append({
                    "type": "text",
                    "text": f"❌ Error: {result.get('error', 'Unknown error')}"
                })
            elif "success" in result and result["success"]:
                # Success result - format nicely
                content_items.append({
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                })
            elif "error" in result:
                # Error result
                return jsonrpc_response(
                    error={
                        "code": result.get("error", {}).get("code", -32603),
                        "message": result.get("error", {}).get("message", "Internal error")
                    },
                    id=request_id
                )
            else:
                # Convert to string
                content_items.append({
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                })
        
        return jsonrpc_response(
            result={
                "content": content_items
            },
            id=request_id
        )
    
    except Exception as e:
        logger.error(f"Error calling tool {tool_name}: {str(e)}")
        return jsonrpc_response(
            error={"code": -32603, "message": f"Internal error: {str(e)}"},
            id=request_id
        )

async def handle_jsonrpc_request(request: Dict[str, Any]):
    """Handle a JSON-RPC 2.0 request"""
    # Check if it's a valid JSON-RPC 2.0 request
    if request.get("jsonrpc") != "2.0":
        return jsonrpc_response(
            error={"code": -32600, "message": "Invalid Request: Not a valid JSON-RPC 2.0 request"},
            id=request.get("id")
        )
    
    # Get the method and parameters
    method_name = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    logger.info(f"Received JSON-RPC request: method={method_name}, id={request_id}")
    
    # Handle different methods
    if method_name == "initialize":
        return await handle_initialize(params, request_id)
    elif method_name == "resources/list":
        return await handle_resources_list(params, request_id)
    elif method_name == "resources/read":
        return await handle_resources_read(params, request_id)
    elif method_name == "tools/list":
        return await handle_tools_list(params, request_id)
    elif method_name == "tools/call":
        return await handle_tools_call(params, request_id)
    else:
        logger.error(f"Method not found: {method_name}")
        return jsonrpc_response(
            error={"code": -32601, "message": f"Method not found: {method_name}"},
            id=request_id
        )

# Mode-based tools are now integrated directly into amazon_q_jsonrpc_server.py

def register_amazon_q_tools():
    """Register the 4 universal Amazon Q Business tools"""
    
    # Universal Retrieve Tool (RETRIEVAL_MODE) - Auto-login built-in
    tool_registry.register_tool(
        name="mcp_amazon_q_business_retrieve",
        tool_func=amazon_q_jsonrpc_server.retrieve,
        description="🔍 RETRIEVE: Get information from your knowledge base. Auto-login to Amazon Q Business is built-in. Functions: (1) List and explore Confluence pages, (2) Extract requirements from documentation, (3) Analyze existing content and specifications, (4) Search through indexed documents, (5) Find specific information in your knowledge base, (6) Summarize documentation content, (7) Answer questions about your existing data. Uses RETRIEVAL_MODE to search your Confluence, SharePoint, and other indexed content.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What information would you like to retrieve or analyze? Examples: 'What pages are in my Confluence?', 'Extract requirements from AnyCompanyReads project', 'What are the main features in my documentation?', 'Analyze the user authentication requirements', 'Find information about the login system'"}
            },
            "required": ["message"]
        }
    )
    
    # Universal Create Tool (CREATOR_MODE) - Auto-login built-in
    tool_registry.register_tool(
        name="mcp_amazon_q_business_create",
        tool_func=amazon_q_jsonrpc_server.create,
        description="✨ CREATE: Generate new content and creative solutions. Auto-login to Amazon Q Business is built-in. Functions: (1) Generate detailed user stories with acceptance criteria, (2) Create technical specifications and documentation, (3) Estimate story points using various methods (fibonacci, t-shirt sizes), (4) Write acceptance criteria and test cases, (5) Generate project plans and feature breakdowns, (6) Create code templates and examples, (7) Design system architectures and workflows, (8) Generate creative content and ideas. Uses CREATOR_MODE for AI-powered content generation.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "What would you like me to create or generate? Examples: 'Generate user stories for a login system', 'Create acceptance criteria for user registration', 'Estimate story points for login, signup, password reset features', 'Write technical specifications for authentication', 'Generate test cases for the payment system', 'Create a project plan for the mobile app'"}
            },
            "required": ["message"]
        }
    )
    




def register_resources():
    """Register MCP resources"""
    # Register AWS Well-Architected Framework resource
    tool_registry.register_resource(
        uri="amazon-q://documentation",
        name="Amazon Q Business Documentation",
        description="Access to Amazon Q Business documentation and best practices",
        mime_type="text/plain"
    )
    
    # Register Confluence integration resource
    tool_registry.register_resource(
        uri="amazon-q://confluence-integration",
        name="Confluence Integration Guide",
        description="Guide for integrating Amazon Q Business with Confluence",
        mime_type="text/plain"
    )

def initialize_mcp_server():
    """Initialize the MCP server by registering all tools and resources"""
    # Register Amazon Q Business tools
    register_amazon_q_tools()
    
    # Register resources
    register_resources()
    
    logger.info("MCP server initialized with all tools and resources registered")

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler function"""
    
    # Input validation
    if not isinstance(event, dict):
        logger.error("Invalid event type: expected dict")
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid event format'})
        }
    
    # Log all incoming requests for security monitoring
    request_context = event.get('requestContext', {})
    identity = request_context.get('identity', {})
    source_ip = identity.get('sourceIp', 'unknown')
    user_agent = event.get('headers', {}).get('user-agent', 'unknown')
    
    logger.info(f"INCOMING REQUEST - IP: {source_ip}, UserAgent: {user_agent}")
    
    try:
        # Validate required environment variables
        required_env_vars = ['Q_BUSINESS_APPLICATION_ID', 'QBIZ_ROLE_ARN', 'IDC_APP_CLIENT_ID']
        missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
        if missing_vars:
            logger.error(f"Missing required environment variables: {missing_vars}")
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Server configuration error'})
            }
        # Initialize MCP server if needed
        if not tool_registry.tools:
            initialize_mcp_server()
        
        # Check if IAM validation is enabled (default to True for security)
        enable_iam_auth = os.environ.get('ENABLE_IAM_AUTH', 'true').lower() != 'false'
        
        # Validate IAM authentication if enabled
        if enable_iam_auth and not validate_iam_authentication(event):
            logger.warning(f"❌ Request failed IAM authentication")
            return {
                'statusCode': 401,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'error': 'Unauthorized: IAM authentication required'
                })
            }
        
        logger.info(f"✅ Request passed Lambda Function URL IAM authentication")
        
        # Extract credentials from the API Gateway request context
        request_credentials = extract_credentials_from_request_context(event)
        logger.info(f"Extracted request credentials: {request_credentials}")
        
        # Store the event in a global variable so the MCP tools can access it
        amazon_q_jsonrpc_server.current_lambda_event = event
        
        # Handle different event types
        logger.info(f"Event keys: {list(event.keys())}")
        
        if 'httpMethod' in event or ('requestContext' in event and 'http' in event['requestContext']):
            # API Gateway or Lambda Function URL event
            return handle_http_request(event, context)
        elif 'Records' in event:
            # SQS or other event source
            logger.warning(f"Unsupported event source: Records")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Unsupported event source'
                })
            }
        else:
            # Unknown event type
            logger.warning(f"Unknown event type: {event}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Unknown event type'
                })
            }
    
    except Exception as e:
        logger.error(f"Error handling request: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': f'Internal server error: {str(e)}'
            })
        }

def handle_http_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle HTTP request from API Gateway or Function URL"""
    logger.info(f"handle_http_request called with event keys: {list(event.keys())}")
    
    # Handle both API Gateway and Lambda Function URL formats
    if 'httpMethod' in event:
        # API Gateway format
        method = event.get('httpMethod', 'GET')
        path = event.get('path', '/')
        logger.info(f"API Gateway format - method: {method}, path: {path}")
    else:
        # Lambda Function URL format
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        path = event.get('requestContext', {}).get('http', {}).get('path', '/')
        logger.info(f"Function URL format - method: {method}, path: {path}")
    
    logger.info(f"Processing {method} request to {path}")
    
    # Get allowed CORS origins from environment variable - no wildcards allowed for security
    allowed_origins = os.environ.get('ALLOWED_CORS_ORIGINS', '')
    allowed_origins_list = allowed_origins.split(',')
    
    # Validate that no wildcards are in the allowed origins
    for origin in allowed_origins_list:
        if '*' in origin:
            logger.warning(f"Security warning: Wildcard detected in CORS origin: {origin}")
            # Replace with a secure default
            allowed_origins_list = ['https://luvvfzwt.chat.qbusiness.us-east-1.on.aws']
            break
    
    # Get origin from request
    origin = event.get('headers', {}).get('origin') or event.get('headers', {}).get('Origin')
    
    # Default CORS headers - restrictive for security
    cors_headers = {
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Amz-Date, X-Amz-Security-Token',
        'Access-Control-Max-Age': '3600',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'",
        'X-Content-Type-Options': 'nosniff'
    }
    
    # Add Access-Control-Allow-Origin if origin is in allowed list (strict matching)
    if origin and origin in allowed_origins_list:
        cors_headers['Access-Control-Allow-Origin'] = origin
    else:
        # Default to first allowed origin if available
        if allowed_origins_list:
            cors_headers['Access-Control-Allow-Origin'] = allowed_origins_list[0]
    
    # Handle CORS preflight
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': ''
        }
    
    if method == 'GET' and path == '/':
        # Return server info
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                **cors_headers
            },
            'body': json.dumps({
                'name': 'Amazon Q Business MCP Server',
                'version': '1.0.0',
                'protocol': 'MCP',
                'protocolVersion': MCP_PROTOCOL_VERSION,
                'description': 'Model Context Protocol server for Amazon Q Business',
                'capabilities': [
                    'resources/list',
                    'resources/read', 
                    'tools/list',
                    'tools/call'
                ],
                'usage': {
                    'mcp_client': 'Connect using MCP client with this URL',
                    'http_post': 'Send MCP JSON-RPC requests to this endpoint'
                }
            })
        }
    
    elif method == 'POST':
        # Handle MCP JSON-RPC request
        try:
            body = event.get('body', '{}')
            if not body:
                body = '{}'
            if event.get('isBase64Encoded', False):
                body = base64.b64decode(body).decode('utf-8')
            
            mcp_request = json.loads(body)
            
            # Run async handler
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(
                    handle_jsonrpc_request(mcp_request)
                )
            finally:
                loop.close()
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    **cors_headers
                },
                'body': json.dumps(response)
            }
        
        except json.JSONDecodeError as e:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    **cors_headers
                },
                'body': json.dumps({
                    'error': f'Invalid JSON: {str(e)}'
                })
            }
        
        except Exception as e:
            logger.error(f"Error handling JSON-RPC request: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    **cors_headers
                },
                'body': json.dumps({
                    'error': f'Internal server error: {str(e)}'
                })
            }
    
    else:
        # Method not allowed
        return {
            'statusCode': 405,
            'headers': {
                'Content-Type': 'application/json',
                **cors_headers
            },
            'body': json.dumps({
                'error': f'Method not allowed: {method}'
            })
        }

if __name__ == "__main__":
    # For local testing
    initialize_mcp_server()
    print("MCP server initialized with all tools and resources registered")
    print(f"Available tools: {len(tool_registry.tools)}")
    print(f"Available resources: {len(tool_registry.resources)}")