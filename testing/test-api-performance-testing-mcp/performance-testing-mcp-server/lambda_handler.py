"""
AWS Lambda handler for Performance Testing MCP Server
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
                logger.info("Performance Testing MCP server initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize MCP server: {str(e)}")
                raise
    
    async def handle_mcp_request(self, mcp_request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle MCP protocol request"""
        try:
            method = mcp_request.get('method')
            params = mcp_request.get('params', {})
            request_id = mcp_request.get('id')
            
            logger.info(f"Handling MCP request: {method}")
            
            if method == 'initialize':
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
                            "name": "performance-testing-mcp",
                            "version": "1.0.0"
                        }
                    }
                }
            
            elif method == 'resources/list':
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
                name = params.get('name')
                arguments = params.get('arguments', {})
                
                logger.info(f"🔧 === TOOLS/CALL REQUEST === 🔧")
                logger.info(f"📛 Tool name: {name}")
                logger.info(f"📋 Arguments keys: {list(arguments.keys()) if arguments else 'None'}")
                logger.info(f"📋 Full arguments: {json.dumps(arguments, indent=2)}")
                
                if not name:
                    raise ValueError("Tool name required")
                
                logger.info(f"🚀 Calling tool handler for: {name}")
                result = await mcp_server.tool_handlers['call_tool'](name, arguments)
                logger.info(f"✅ Tool handler returned result type: {type(result)}")
                logger.info(f"📏 Result length: {len(result) if hasattr(result, '__len__') else 'N/A'}")
                logger.info(f"📋 Full result: {result}")
                
                # Convert result to MCP format
                logger.info(f"🔄 === CONVERTING RESULT TO MCP FORMAT === 🔄")
                content_items = []
                for i, item in enumerate(result):
                    logger.info(f"📋 Processing result item {i}: type={type(item)}")
                    if hasattr(item, 'type'):
                        logger.info(f"📋 Item has type attribute: {item.type}")
                    if hasattr(item, 'text'):
                        logger.info(f"📋 Item has text attribute: {len(item.text) if item.text else 0} chars")
                    
                    if hasattr(item, 'type') and item.type == 'text':
                        content_items.append({
                            "type": "text",
                            "text": item.text
                        })
                        logger.info(f"✅ Added text item: {len(item.text)} characters")
                    elif hasattr(item, 'type') and item.type == 'image':
                        content_items.append({
                            "type": "image",
                            "data": item.data,
                            "mimeType": item.mimeType
                        })
                        logger.info(f"✅ Added image item")
                    else:
                        logger.warning(f"⚠️ Unknown item type: {type(item)}, attributes: {dir(item)}")
                
                logger.info(f"📋 Final content_items count: {len(content_items)}")
                
                final_response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": content_items
                    }
                }
                
                logger.info(f"🎯 === FINAL MCP RESPONSE === 🎯")
                logger.info(f"📋 Response keys: {list(final_response.keys())}")
                logger.info(f"📋 Result keys: {list(final_response['result'].keys())}")
                logger.info(f"📋 Content count: {len(final_response['result']['content'])}")
                logger.info(f"📋 Full response: {json.dumps(final_response, indent=2)}")
                
                return final_response
            
            else:
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
    
    if 'method' not in mcp_request:
        raise ValueError("Request must include 'method' field")
    
    method = mcp_request.get('method')
    if not isinstance(method, str) or len(method) > 100:
        raise ValueError("Method must be a string with max 100 characters")
    
    params = mcp_request.get('params', {})
    if params and not isinstance(params, dict):
        raise ValueError("Parameters must be an object")

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler function"""
    
    try:
        lambda_mcp_handler.initialize_if_needed()
        
        logger.info(f"Event keys: {list(event.keys())}")
        
        if 'httpMethod' in event or ('requestContext' in event and 'http' in event['requestContext']):
            return handle_http_request(event, context)
        elif 'Records' in event:
            return handle_event_source(event, context)
        else:
            return handle_direct_invocation(event, context)
    
    except Exception as e:
        logger.error(f"Error in Lambda handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Internal server error: {str(e)}'})
        }

def handle_http_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle HTTP request from API Gateway or Function URL"""
    
    if 'httpMethod' in event:
        method = event.get('httpMethod', 'GET')
        path = event.get('path', '/')
    else:
        method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        path = event.get('requestContext', {}).get('http', {}).get('path', '/')
    
    logger.info(f"Processing {method} request to {path}")
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Max-Age': '3600'
            },
            'body': ''
        }
    
    if method == 'GET' and path == '/':
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'name': 'Performance Testing MCP Server',
                'version': '1.0.0',
                'protocol': 'MCP',
                'description': 'Model Context Protocol server for performance testing tools',
                'capabilities': [
                    'resources/list',
                    'resources/read', 
                    'tools/list',
                    'tools/call'
                ]
            })
        }
    
    elif method == 'POST':
        try:
            body = event.get('body', '{}')
            if not body:
                body = '{}'
            if event.get('isBase64Encoded', False):
                body = base64.b64decode(body).decode('utf-8')
            
            logger.info(f"📥 === HTTP POST REQUEST === 📥")
            logger.info(f"📏 Body length: {len(body)} characters")
            logger.info(f"📋 Body preview (first 500 chars): {body[:500]}...")
            
            mcp_request = json.loads(body)
            logger.info(f"📋 Parsed MCP request keys: {list(mcp_request.keys())}")
            logger.info(f"📋 Full MCP request: {json.dumps(mcp_request, indent=2)}")
            
            validate_request_input(mcp_request)
            
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
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(response)
            }
        
        except json.JSONDecodeError as e:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': f'Invalid JSON: {str(e)}'})
            }
    
    else:
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'})
        }

def handle_event_source(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle event from SQS or other event sources"""
    logger.info("Handling event source")
    return {'status': 'processed'}

def handle_direct_invocation(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle direct Lambda invocation"""
    if 'mcp_request' in event:
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