# src/mcp_server/protocol.py
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel
from enum import Enum

class MCPRequestMethod(str, Enum):
    """MCP protocol methods"""
    LIST_RESOURCES = "resources/list"
    READ_RESOURCE = "resources/read"
    LIST_TOOLS = "tools/list"
    CALL_TOOL = "tools/call"
    INITIALIZE = "initialize"

class MCPRequest(BaseModel):
    """MCP request structure"""
    jsonrpc: str = "2.0"
    id: Union[str, int]
    method: str
    params: Optional[Dict[str, Any]] = None

class MCPResponse(BaseModel):
    """MCP response structure"""
    jsonrpc: str = "2.0"
    id: Union[str, int]
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None

class MCPResource(BaseModel):
    """MCP resource definition"""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: str = "application/json"

class MCPTool(BaseModel):
    """MCP tool definition"""
    name: str
    description: str
    inputSchema: Dict[str, Any]

class MCPError(BaseModel):
    """MCP error structure"""
    code: int
    message: str
    data: Optional[Dict[str, Any]] = None

# Common MCP error codes
class MCPErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    RESOURCE_NOT_FOUND = -404
    TOOL_NOT_FOUND = -404