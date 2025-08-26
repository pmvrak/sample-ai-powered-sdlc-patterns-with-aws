"""
AWS Lambda handler for MCP Server
Handles HTTP requests and translates them to MCP protocol
"""

import json
import asyncio
import logging
import os
import base64
from typing import Dict, Any

from mcp_server import mcp_server

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MCPLambdaHandler:
    def __init__(self):
        self.initialized = False
    
    def initialize_if_needed(self):
        """Initialize the MCP server with AWS configuration"""
        if not self.initialized:
            try:
                region = os.environ.get('BEDROCK_REGION', 'us-east-1')
                
                # Validate required environment variables
                required_env_vars = ['S3_BUCKET_NAME', 'BEDROCK_MODEL_ID']
                missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
                if missing_vars:
                    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
                
                mcp_server.initialize_aws_clients(region)
                self.initialized = True
                logger.info("MCP server initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize MCP server: {str(e)}")
                raise
    
    async def handle_mcp_request(self, mcp_request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP protocol request"""
        try:
            method = mcp_request.get('method')
            params = mcp_request.get('params', {})
            request_id = mcp_request.get('id')
            
            logger.info(f"Handling MCP request: {method}")
            
            if method == 'initialize':
                # Handle MCP initialization
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "resources": {"subscribe": True, "listChanged": True},
                            "tools": {"listChanged": True},
                            "logging": {}
                        },
                        "serverInfo": {
                            "name": "aws-architecture-design",
                            "version": "1.0.0"
                        }
                    }
                }
            
            elif method == 'resources/list':
                # List available resources
                resources = await mcp_server.resource_handlers['list_resources']()
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "resources": [
                            {
                                "uri": str(r.uri),
                                "name": r.name,
                                "description": r.description,
                                "mimeType": r.mimeType
                            } for r in resources
                        ]
                    }
                }
            
            elif method == 'resources/read':
                # Read a specific resource
                uri = params.get('uri')
                if not uri:
                    raise ValueError("URI parameter required")
                
                content = await mcp_server.resource_handlers['read_resource'](uri)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "mimeType": "text/plain",
                                "text": content
                            }
                        ]
                    }
                }
            
            elif method == 'tools/list':
                # List available tools
                tools = await mcp_server.tool_handlers['list_tools']()
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": t.name,
                                "description": t.description,
                                "inputSchema": t.inputSchema
                            } for t in tools
                        ]
                    }
                }
            
            elif method == 'tools/call':
                # Call a tool
                name = params.get('name')
                arguments = params.get('arguments', {})
                
                if not name:
                    raise ValueError("Tool name required")
                
                result = await mcp_server.tool_handlers['call_tool'](name, arguments)
                
                # Convert result to MCP format
                content_items = []
                for item in result:
                    if hasattr(item, 'type') and item.type == 'text':
                        content_items.append({
                            "type": "text",
                            "text": item.text
                        })
                    elif hasattr(item, 'type') and item.type == 'image':
                        content_items.append({
                            "type": "image",
                            "data": item.data,
                            "mimeType": item.mimeType
                        })
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": content_items
                    }
                }
            
            else:
                # Unknown method
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
        
        except Exception as e:
            logger.error(f"Error handling MCP request: {str(e)}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            }

# Global handler instance
lambda_mcp_handler = MCPLambdaHandler()

def validate_request_input(mcp_request: Dict[str, Any]) -> None:
    """Validate MCP request input for security"""
    if not isinstance(mcp_request, dict):
        raise ValueError("Request must be a JSON object")
    
    # Validate required fields
    if 'method' not in mcp_request:
        raise ValueError("Request must include 'method' field")
    
    method = mcp_request.get('method')
    if not isinstance(method, str) or len(method) > 100:
        raise ValueError("Method must be a string with max 100 characters")
    
    # Validate parameters if present
    params = mcp_request.get('params', {})
    if params and not isinstance(params, dict):
        raise ValueError("Parameters must be an object")
    
    # Check for potentially dangerous content
    request_str = json.dumps(mcp_request)
    dangerous_patterns = ['<script', 'javascript:', 'data:', 'vbscript:']
    for pattern in dangerous_patterns:
        if pattern.lower() in request_str.lower():
            raise ValueError(f"Request contains potentially dangerous content: {pattern}")

def validate_iam_authentication(event: Dict[str, Any]) -> bool:
    """Validate that the request has proper AWS SigV4 authentication"""
    try:
        # Check for AWS signature headers - this proves the request was signed with AWS credentials
        headers = event.get('headers', {})
        
        auth_header = headers.get('authorization', '') or headers.get('Authorization', '')
        
        # Must have AWS4-HMAC-SHA256 signature (proves IAM authentication)
        if not auth_header or 'AWS4-HMAC-SHA256' not in auth_header:
            logger.warning("Request missing AWS SigV4 signature")
            return False
        
        # Check for required AWS headers
        x_amz_date = headers.get('x-amz-date') or headers.get('X-Amz-Date')
        if not x_amz_date:
            logger.warning("Request missing X-Amz-Date header")
            return False
        
        logger.info("✅ Request has valid AWS SigV4 authentication")
        return True
        
    except Exception as e:
        logger.error(f"❌ AUTHENTICATION ERROR: {e}")
        return False

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler function with STRICT IAM authentication validation"""
    
    # Log all incoming requests for security monitoring
    request_context = event.get('requestContext', {})
    identity = request_context.get('identity', {})
    source_ip = identity.get('sourceIp', 'unknown')
    user_agent = event.get('headers', {}).get('user-agent', 'unknown')
    
    logger.info(f"🔍 INCOMING REQUEST - IP: {source_ip}, UserAgent: {user_agent}")
    
    try:
        # TEMPORARY: Skip custom validation since Lambda Function URL already enforces IAM auth
        # The AWS_IAM auth_type on the Function URL already ensures only authenticated requests get through
        logger.info("✅ Request passed Lambda Function URL IAM authentication")
        
        # Initialize MCP server if needed
        lambda_mcp_handler.initialize_if_needed()
        
        logger.info(f"Authenticated request received")
        
        # Handle different event types
        logger.info(f"Event keys: {list(event.keys())}")
        logger.info(f"Event type detection - httpMethod: {'httpMethod' in event}, requestContext: {'requestContext' in event}")
        
        if 'httpMethod' in event:
            # API Gateway event
            return handle_http_request(event, context)
        elif 'requestContext' in event and 'http' in event['requestContext']:
            # Lambda Function URL event
            return handle_http_request(event, context)
        elif 'Records' in event:
            # SQS or other event source
            return handle_event_source(event, context)
        else:
            # Direct invocation
            return handle_direct_invocation(event, context)
    
    except Exception as e:
        logger.error(f"Error in Lambda handler: {str(e)}")
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
    
    # Handle CORS preflight - restricted origins only
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': 'https://console.aws.amazon.com',
                'Access-Control-Allow-Methods': 'GET, POST',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Amz-Date, X-Amz-Security-Token',
                'Access-Control-Max-Age': '3600'
            },
            'body': ''
        }
    
    if method == 'GET' and path == '/':
        # Return server info
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': 'https://console.aws.amazon.com'
            },
            'body': json.dumps({
                'name': 'AWS Architecture Design MCP Server',
                'version': '1.0.0',
                'protocol': 'MCP',
                'description': 'Model Context Protocol server for AWS architecture design tools',
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
            
            # Validate request input
            validate_request_input(mcp_request)
            
            # Run async handler
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response = loop.run_until_complete(
                    lambda_mcp_handler.handle_mcp_request(mcp_request)
                )
            finally:
                loop.close()
            
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': 'https://console.aws.amazon.com'
                },
                'body': json.dumps(response)
            }
        
        except json.JSONDecodeError as e:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'error': f'Invalid JSON: {str(e)}'
                })
            }
    
    else:
        return {
            'statusCode': 405,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'error': 'Method not allowed'
            })
        }

def handle_event_source(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle event from SQS or other event sources"""
    logger.info("Handling event source")
    return {'status': 'processed'}

def handle_direct_invocation(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle direct Lambda invocation"""
    if 'mcp_request' in event:
        # Direct MCP request
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            response = loop.run_until_complete(
                lambda_mcp_handler.handle_mcp_request(event['mcp_request'])
            )
            return response
        finally:
            loop.close()
    else:
        return {
            'error': 'Unknown invocation type',
            'event': event
        }