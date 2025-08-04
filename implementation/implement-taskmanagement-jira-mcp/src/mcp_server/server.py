# src/mcp_server/server.py
import asyncio
import json
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import logging

from .protocol import (
    MCPRequest, MCPResponse, MCPResource, MCPTool, MCPError, 
    MCPErrorCode, MCPRequestMethod
)
from .handlers.jira_handlers import JiraResourceHandler, JiraToolHandler

logger = logging.getLogger(__name__)

class MCPServer:
    def __init__(self):
        self.app = FastAPI(title="JIRA MCP Server", version="1.0.0")
        self.resource_handlers = {}
        self.tool_handlers = {}
        self.setup_routes()
        self.setup_handlers()
    
    def setup_routes(self):
        """Setup FastAPI routes for MCP protocol"""
        
        @self.app.post("/mcp")
        async def handle_mcp_request(request: Request):
            """Main MCP protocol endpoint"""
            try:
                body = await request.json()
                mcp_request = MCPRequest(**body)
                response = await self.process_request(mcp_request)
                return response.dict(exclude_none=True)
            except Exception as e:
                logger.error(f"MCP request error: {e}")
                return MCPResponse(
                    id=getattr(body, 'id', 0),
                    error=MCPError(
                        code=MCPErrorCode.INTERNAL_ERROR,
                        message=str(e)
                    ).dict()
                ).dict(exclude_none=True)
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "service": "jira-mcp-server"}
        
        @self.app.get("/capabilities")
        async def get_capabilities():
            """Get server capabilities"""
            return {
                "resources": len(self.resource_handlers) > 0,
                "tools": len(self.tool_handlers) > 0,
                "transport": "http"
            }
    
    def setup_handlers(self):
        """Setup JIRA resource and tool handlers"""
        # Resource handlers
        jira_resource_handler = JiraResourceHandler()
        self.resource_handlers.update(jira_resource_handler.get_handlers())
        
        # Tool handlers
        jira_tool_handler = JiraToolHandler()
        self.tool_handlers.update(jira_tool_handler.get_handlers())
    
    async def process_request(self, request: MCPRequest) -> MCPResponse:
        """Process MCP request and return response"""
        try:
            if request.method == MCPRequestMethod.LIST_RESOURCES:
                return await self.list_resources(request)
            elif request.method == MCPRequestMethod.READ_RESOURCE:
                return await self.read_resource(request)
            elif request.method == MCPRequestMethod.LIST_TOOLS:
                return await self.list_tools(request)
            elif request.method == MCPRequestMethod.CALL_TOOL:
                return await self.call_tool(request)
            elif request.method == MCPRequestMethod.INITIALIZE:
                return await self.initialize(request)
            else:
                return MCPResponse(
                    id=request.id,
                    error=MCPError(
                        code=MCPErrorCode.METHOD_NOT_FOUND,
                        message=f"Method {request.method} not found"
                    ).dict()
                )
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return MCPResponse(
                id=request.id,
                error=MCPError(
                    code=MCPErrorCode.INTERNAL_ERROR,
                    message=str(e)
                ).dict()
            )
    
    async def initialize(self, request: MCPRequest) -> MCPResponse:
        """Initialize MCP server"""
        return MCPResponse(
            id=request.id,
            result={
                "capabilities": {
                    "resources": {"subscribe": False, "listChanged": False},
                    "tools": {"listChanged": False},
                    "logging": {},
                },
                "serverInfo": {
                    "name": "jira-mcp-server",
                    "version": "1.0.0"
                }
            }
        )
    
    async def list_resources(self, request: MCPRequest) -> MCPResponse:
        """List available resources"""
        resources = []
        for handler_name, handler_func in self.resource_handlers.items():
            if handler_name.endswith('_list'):
                try:
                    handler_resources = await handler_func(request.params or {})
                    resources.extend(handler_resources)
                except Exception as e:
                    logger.error(f"Error listing resources from {handler_name}: {e}")
        
        return MCPResponse(
            id=request.id,
            result={"resources": resources}
        )
    
    async def read_resource(self, request: MCPRequest) -> MCPResponse:
        """Read specific resource"""
        if not request.params or 'uri' not in request.params:
            return MCPResponse(
                id=request.id,
                error=MCPError(
                    code=MCPErrorCode.INVALID_PARAMS,
                    message="Missing 'uri' parameter"
                ).dict()
            )
        
        uri = request.params['uri']
        
        # Find appropriate handler based on URI
        for handler_name, handler_func in self.resource_handlers.items():
            if handler_name.endswith('_read') and await self._uri_matches_handler(uri, handler_name):
                try:
                    result = await handler_func(request.params)
                    return MCPResponse(id=request.id, result=result)
                except Exception as e:
                    logger.error(f"Error reading resource {uri}: {e}")
                    return MCPResponse(
                        id=request.id,
                        error=MCPError(
                            code=MCPErrorCode.INTERNAL_ERROR,
                            message=str(e)
                        ).dict()
                    )
        
        return MCPResponse(
            id=request.id,
            error=MCPError(
                code=MCPErrorCode.RESOURCE_NOT_FOUND,
                message=f"Resource {uri} not found"
            ).dict()
        )
    
    async def list_tools(self, request: MCPRequest) -> MCPResponse:
        """List available tools"""
        tools = []
        for handler_name, handler_func in self.tool_handlers.items():
            if handler_name.endswith('_list'):
                try:
                    handler_tools = await handler_func(request.params or {})
                    tools.extend(handler_tools)
                except Exception as e:
                    logger.error(f"Error listing tools from {handler_name}: {e}")
        
        return MCPResponse(
            id=request.id,
            result={"tools": tools}
        )
    
    async def call_tool(self, request: MCPRequest) -> MCPResponse:
        """Call specific tool"""
        if not request.params or 'name' not in request.params:
            return MCPResponse(
                id=request.id,
                error=MCPError(
                    code=MCPErrorCode.INVALID_PARAMS,
                    message="Missing 'name' parameter"
                ).dict()
            )
        
        tool_name = request.params['name']
        handler_name = f"{tool_name}_call"
        
        if handler_name in self.tool_handlers:
            try:
                result = await self.tool_handlers[handler_name](request.params)
                return MCPResponse(id=request.id, result=result)
            except Exception as e:
                logger.error(f"Error calling tool {tool_name}: {e}")
                return MCPResponse(
                    id=request.id,
                    error=MCPError(
                        code=MCPErrorCode.INTERNAL_ERROR,
                        message=str(e)
                    ).dict()
                )
        
        return MCPResponse(
            id=request.id,
            error=MCPError(
                code=MCPErrorCode.TOOL_NOT_FOUND,
                message=f"Tool {tool_name} not found"
            ).dict()
        )
    
    async def _uri_matches_handler(self, uri: str, handler_name: str) -> bool:
        """Check if URI matches handler"""
        if 'projects' in handler_name and uri.startswith('jira://projects'):
            return True
        if 'issues' in handler_name and uri.startswith('jira://issues'):
            return True
        return False

# Global MCP server instance
mcp_server = MCPServer()