"""
AWS Architecture Design MCP Server
Implements the Model Context Protocol for AWS architecture design tools
"""

import json
import logging
import os
import time
import threading
from typing import Any, Dict, List, Optional
import boto3
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent
)
import mcp.server.stdio
import mcp.types as types

# Import integrated modules
import sa_tools_module
import drawing_module

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BedrockRateLimiter:
    """Rate limiter for Bedrock API calls to prevent throttling"""
    
    def __init__(self, requests_per_minute=10):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute  # Minimum seconds between requests
        self.last_request_time = 0
        self.lock = threading.Lock()
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limits"""
        with self.lock:
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            
            if time_since_last < self.min_interval:
                sleep_time = self.min_interval - time_since_last
                logger.info(f"Rate limiting: waiting {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
            
            self.last_request_time = time.time()

# Global rate limiter instance
bedrock_rate_limiter = BedrockRateLimiter(requests_per_minute=50)  # Optimized rate limit for better performance

class AWSArchitectureMCPServer:
    def __init__(self):
        self.server = Server("aws-architecture-design")
        self.bedrock_client = None
        self.setup_handlers()
    
    def initialize_aws_clients(self, region: str = "us-east-1"):
        """Initialize AWS clients with provided configuration"""
        # Configure retry settings for better handling of rate limits
        from botocore.config import Config
        retry_config = Config(
            retries={
                'max_attempts': 10,  # Increased from default 4 to 10
                'mode': 'adaptive'   # Use adaptive retry mode for better handling
            }
        )
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=region, config=retry_config)
        logger.info(f"Initialized AWS clients in region {region}")
    
    def setup_handlers(self):
        """Setup MCP protocol handlers"""
        # Store handlers in instance variables for Lambda access
        self.resource_handlers = {
            'list_resources': self._handle_list_resources,
            'read_resource': self._handle_read_resource
        }
        
        self.tool_handlers = {
            'list_tools': self._handle_list_tools,
            'call_tool': self._handle_call_tool
        }
    
    async def _handle_list_resources(self) -> List[Resource]:
        """List available AWS architecture resources"""
        return [
            Resource(
                uri="aws://well-architected-framework",
                name="AWS Well-Architected Framework",
                description="Access to AWS Well-Architected Framework principles and best practices",
                mimeType="text/plain"
            ),
            Resource(
                uri="aws://architecture-patterns",
                name="AWS Architecture Patterns",
                description="Common AWS architecture patterns and solutions",
                mimeType="text/plain"
            )
        ]
    
    async def _handle_read_resource(self, uri: str) -> str:
        """Read AWS architecture resource content"""
        if uri == "aws://well-architected-framework":
            return "AWS Well-Architected Framework provides architectural best practices across six pillars: Operational Excellence, Security, Reliability, Performance Efficiency, Cost Optimization, and Sustainability."
        elif uri == "aws://architecture-patterns":
            return "Common AWS patterns include: Microservices with ECS/EKS, Serverless with Lambda, Event-driven with EventBridge, Data lakes with S3/Glue, and Multi-tier web applications."
        else:
            raise ValueError(f"Unknown resource: {uri}")
    
    async def _handle_list_tools(self) -> List[Tool]:
        """List available AWS architecture design tools"""
        return [
            Tool(
                name="query_aws_knowledge",
                description="Query AWS Well-Architected Framework and best practices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Question about AWS architecture or best practices"
                        },
                        "pillar": {
                            "type": "string",
                            "enum": ["operational-excellence", "security", "reliability", "performance-efficiency", "cost-optimization", "sustainability"],
                            "description": "Specific Well-Architected pillar to focus on (optional)"
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="generate_architecture_code",
                description="Generate AWS infrastructure code (CloudFormation, CDK, Terraform)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "requirements": {
                            "type": "string",
                            "description": "Architecture requirements and specifications"
                        },
                        "format": {
                            "type": "string",
                            "enum": ["cloudformation", "cdk-python", "cdk-typescript", "terraform", "pulumi-python", "pulumi-typescript", "sam", "serverless"],
                            "description": "Output format for the infrastructure code"
                        },
                        "services": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific AWS services to include"
                        }
                    },
                    "required": ["requirements", "format"]
                }
            ),
            Tool(
                name="create_architecture_diagram",
                description="Create AWS architecture diagrams",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Description of the architecture to diagram"
                        },
                        "components": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "AWS services and components to include"
                        },
                        "style": {
                            "type": "string",
                            "enum": ["technical", "conceptual", "detailed", "simple", "high-level", "comprehensive", "minimal", "enterprise"],
                            "description": "Diagram style and level of detail (technical=detailed technical view, conceptual=high-level overview, detailed=comprehensive with all components, simple=clean minimal view, high-level=strategic overview, comprehensive=complete architecture, minimal=essential components only, enterprise=complex organizational view)"
                        }
                    },
                    "required": ["description"]
                }
            ),
            Tool(
                name="analyze_architecture",
                description="Analyze existing architecture against AWS best practices",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "architecture_description": {
                            "type": "string",
                            "description": "Description of the current architecture"
                        },
                        "focus_areas": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["security", "reliability", "performance", "cost", "operational-excellence", "sustainability", "scalability", "availability", "disaster-recovery", "compliance", "monitoring", "networking", "data-protection"]
                            },
                            "description": "Specific areas to analyze against AWS Well-Architected Framework pillars and best practices"
                        }
                    },
                    "required": ["architecture_description"]
                }
            ),

        ]
    
    async def _handle_call_tool(self, name: str, arguments: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool calls by using integrated modules directly"""
        try:
            # Format the tool call as a natural language request for the Bedrock agent
            if name == "query_aws_knowledge":
                query = arguments.get("query", "")
                pillar = arguments.get("pillar", "")
                
                # Call the AWS Well-Architected tool directly
                result = sa_tools_module.aws_well_arch_tool(query)
                return [TextContent(type="text", text=result)]
            
            elif name == "generate_architecture_code":
                requirements = arguments.get("requirements", "")
                format_type = arguments.get("format", "cdk-python")
                services = arguments.get("services", [])
                
                # Format the prompt for code generation
                code_prompt = f"Generate {format_type} code for: {requirements}"
                if services:
                    code_prompt += f" Include these AWS services: {', '.join(services)}"
                
                # Call the code generation tool directly
                result = sa_tools_module.code_gen_tool(code_prompt)
                return [TextContent(type="text", text=result)]
            
            elif name == "create_architecture_diagram":
                description = arguments.get("description", "")
                components = arguments.get("components", [])
                style = arguments.get("style", "technical")
                
                # Call the fixed drawing function
                result = drawing_module.create_architecture_diagram(description, components, style)
                
                if result and isinstance(result, dict) and result.get("content"):
                    # Handle new multi-part response format
                    logger.info(f"Returning {result.get('type', 'unknown')} diagram result")
                    
                    response_content = []
                    for content_item in result["content"]:
                        if content_item["type"] == "text":
                            response_content.append(TextContent(type="text", text=content_item["text"]))
                        elif content_item["type"] == "image":
                            response_content.append(ImageContent(type="image", data=content_item["data"], mimeType=content_item["mimeType"]))
                    
                    return response_content
                elif isinstance(result, str):
                    # Handle legacy single URL response - return only image to save tokens
                    logger.info(f"Returning legacy single image URL: {result}")
                    return [
                        ImageContent(type="image", data=result, mimeType="image/url")
                    ]
                else:
                    # Fallback to using Bedrock model for text description
                    input_text = f"Create a {style} architecture diagram for: {description}"
                    if components:
                        input_text += f" Include these components: {', '.join(components)}"
                    
                    # Use direct Bedrock call for fallback
                    prompt_config = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 4096,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"I couldn't create a diagram, but I can describe the architecture: {input_text}"},
                                ],
                            }
                        ],
                    }
                    
                    body = json.dumps(prompt_config)
                    # Use the model ID from environment variable or default to Claude 3.7 Sonnet cross-region inference
                    modelId = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
                    accept = "application/json"
                    contentType = "application/json"
                    
                    # Apply rate limiting before making the request
                    bedrock_rate_limiter.wait_if_needed()
                    
                    response = self.bedrock_client.invoke_model(
                        body=body, modelId=modelId, accept=accept, contentType=contentType
                    )
                    response_body = json.loads(response.get("body").read())
                    result_text = response_body.get("content")[0].get("text")
                    
                    return [TextContent(type="text", text=result_text)]
            
            elif name == "analyze_architecture":
                arch_desc = arguments.get("architecture_description", "")
                focus_areas = arguments.get("focus_areas", [])
                
                # Format the prompt for architecture analysis
                analysis_prompt = f"Analyze this architecture against AWS best practices: {arch_desc}"
                if focus_areas:
                    analysis_prompt += f" Focus on: {', '.join(focus_areas)}"
                
                # Call the AWS Well-Architected tool directly for analysis
                result = sa_tools_module.aws_well_arch_tool(analysis_prompt)
                return [TextContent(type="text", text=result)]
            

            
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
            
        except Exception as e:
            logger.error(f"Error calling tool {name}: {str(e)}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

# Global server instance
mcp_server = AWSArchitectureMCPServer()

async def run_server():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await mcp_server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="aws-architecture-design",
                server_version="1.0.0",
                capabilities=mcp_server.server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None,
                )
            )
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_server())