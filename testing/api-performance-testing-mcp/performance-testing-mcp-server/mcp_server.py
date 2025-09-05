"""
Performance Testing MCP Server
Implements the Model Context Protocol for performance testing tools
"""

import json
import logging
import os
import time
import threading
import uuid
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
import architecture_analyzer
import scenario_generator
import test_plan_generator
import test_executor
import results_analyzer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BedrockRateLimiter:
    """Rate limiter for Bedrock API calls to prevent throttling"""
    
    def __init__(self, requests_per_minute=50):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
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
bedrock_rate_limiter = BedrockRateLimiter(requests_per_minute=50)

class PerformanceTestingMCPServer:
    def __init__(self):
        self.server = Server("performance-testing-mcp")
        self.bedrock_client = None
        self.s3_client = None
        self.ecs_client = None
        self.setup_handlers()
    
    def initialize_aws_clients(self, region: str = None):
        """Initialize AWS clients with provided configuration"""
        from botocore.config import Config
        retry_config = Config(
            retries={
                'max_attempts': 10,
                'mode': 'adaptive'
            }
        )
        
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=region, config=retry_config)
        self.s3_client = boto3.client('s3', region_name=region, config=retry_config)
        self.ecs_client = boto3.client('ecs', region_name=region, config=retry_config)
        
        logger.info(f"Initialized AWS clients in region {region}")
    
    def setup_handlers(self):
        """Setup MCP protocol handlers"""
        self.resource_handlers = {
            'list_resources': self._handle_list_resources,
            'read_resource': self._handle_read_resource
        }
        
        self.tool_handlers = {
            'list_tools': self._handle_list_tools,
            'call_tool': self._handle_call_tool
        }
    
    async def _handle_list_resources(self) -> List[Resource]:
        """List available performance testing resources"""
        return [
            Resource(
                uri="perf://test-templates",
                name="Performance Test Templates",
                description="Access to performance test scenario templates and patterns",
                mimeType="text/plain"
            ),
            Resource(
                uri="perf://jmeter-patterns",
                name="JMeter Test Patterns",
                description="Common JMeter test patterns and Java DSL examples",
                mimeType="text/plain"
            )
        ]
    
    async def _handle_read_resource(self, uri: str) -> str:
        """Read performance testing resource content"""
        if uri == "perf://test-templates":
            return "Performance test templates include: Load Testing, Stress Testing, Spike Testing, Endurance Testing, and Scalability Testing patterns."
        elif uri == "perf://jmeter-patterns":
            return "JMeter Java DSL patterns for HTTP requests, database connections, message queues, and workflow testing."
        else:
            raise ValueError(f"Unknown resource: {uri}")
    
    async def _handle_list_tools(self) -> List[Tool]:
        """List available performance testing tools"""
        return [
            Tool(
                name="analyze_architecture",
                description="Parse architecture documents and understand system components, interactions, and data flows",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "documents_path": {
                            "type": "string",
                            "description": "S3 path or local path to architecture documents"
                        },
                        "session_id": {
                            "type": "string",
                            "description": "Optional session ID for state management"
                        }
                    },
                    "required": ["documents_path"]
                }
            ),
            Tool(
                name="generate_test_scenarios",
                description="Create comprehensive test scenarios based on architecture analysis",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID linking to previous analysis"
                        },
                        "workflow_apis": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "endpoint": {"type": "string"},
                                    "method": {"type": "string"},
                                    "order": {"type": "number"}
                                }
                            },
                            "description": "Array of API endpoints in execution order"
                        },
                        "nfrs": {
                            "type": "object",
                            "properties": {
                                "response_time_p95": {"type": "string"},
                                "throughput": {"type": "string"},
                                "availability": {"type": "string"},
                                "error_rate": {"type": "string"}
                            },
                            "description": "Non-functional requirements object"
                        },
                        "scenario_types": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["load", "stress", "spike", "endurance", "scalability"]
                            },
                            "description": "Types of test scenarios to generate"
                        }
                    },
                    "required": ["workflow_apis", "nfrs", "scenario_types"]
                }
            ),
            Tool(
                name="generate_test_plans",
                description="Convert scenarios into executable JMeter Java DSL code",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID linking to scenarios"
                        },
                        "output_format": {
                            "type": "string",
                            "enum": ["java_dsl", "jmx", "both"],
                            "description": "Output format for test plans"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="execute_performance_test",
                description="End-to-end test execution and analysis",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID linking to test plans"
                        },
                        "execution_environment": {
                            "type": "object",
                            "properties": {
                                "cluster_name": {"type": "string"},
                                "task_definition": {"type": "string"},
                                "cpu": {"type": "string"},
                                "memory": {"type": "string"},
                                "target_url": {"type": "string", "description": "Target application URL or service name"}
                            },
                            "description": "ECS/Fargate execution configuration"
                        },
                        "monitoring_config": {
                            "type": "object",
                            "properties": {
                                "metrics": {"type": "array", "items": {"type": "string"}},
                                "duration": {"type": "string"}
                            },
                            "description": "Monitoring and metrics collection configuration"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="validate_test_plans",
                description="Validate and fix generated test plans by compiling them",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID linking to test plans"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="get_test_artifacts",
                description="List and retrieve test artifacts for a session",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID to query"
                        },
                        "artifact_type": {
                            "type": "string",
                            "enum": ["all", "scenarios", "plans", "results"],
                            "description": "Type of artifacts to retrieve"
                        }
                    },
                    "required": ["session_id"]
                }
            ),
            Tool(
                name="analyze_test_results",
                description="AI-powered analysis of performance test results with intelligent insights and recommendations",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID linking to test results"
                        }
                    },
                    "required": ["session_id"]
                }
            )
        ]
    
    async def _handle_call_tool(self, name: str, arguments: Dict[str, Any]) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """Handle tool calls by using integrated modules directly"""
        try:
            if name == "analyze_architecture":
                documents_path = arguments.get("documents_path", "")
                session_id = arguments.get("session_id", str(uuid.uuid4())[:8])
                
                result = architecture_analyzer.analyze_documents(
                    documents_path=documents_path,
                    session_id=session_id,
                    s3_client=self.s3_client,
                    bedrock_client=self.bedrock_client
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "generate_test_scenarios":
                session_id = arguments.get("session_id", "")
                workflow_apis = arguments.get("workflow_apis", [])
                nfrs = arguments.get("nfrs", {})
                scenario_types = arguments.get("scenario_types", ["load"])
                
                result = scenario_generator.generate_scenarios(
                    session_id=session_id,
                    workflow_apis=workflow_apis,
                    nfrs=nfrs,
                    scenario_types=scenario_types,
                    s3_client=self.s3_client,
                    bedrock_client=self.bedrock_client
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "generate_test_plans":
                session_id = arguments.get("session_id", "")
                output_format = arguments.get("output_format", "java_dsl")
                
                result = test_plan_generator.generate_plans(
                    session_id=session_id,
                    output_format=output_format,
                    s3_client=self.s3_client,
                    bedrock_client=self.bedrock_client
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "execute_performance_test":
                session_id = arguments.get("session_id", "")
                execution_environment = arguments.get("execution_environment", {})
                monitoring_config = arguments.get("monitoring_config", {})
                
                result = test_executor.execute_test(
                    session_id=session_id,
                    execution_environment=execution_environment,
                    monitoring_config=monitoring_config,
                    s3_client=self.s3_client,
                    ecs_client=self.ecs_client,
                    bedrock_client=self.bedrock_client
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "validate_test_plans":
                session_id = arguments.get("session_id", "")
                
                # Load test plans from S3
                bucket_name = os.environ.get('S3_BUCKET_NAME')
                test_plans = {}
                
                try:
                    # List and download test plan files
                    s3_prefix = f"perf-pipeline/{session_id}/plans/"
                    response = self.s3_client.list_objects_v2(Bucket=bucket_name, Prefix=s3_prefix)
                    
                    if 'Contents' in response:
                        for obj in response['Contents']:
                            if obj['Key'].endswith('.java'):
                                filename = os.path.basename(obj['Key'])
                                file_response = self.s3_client.get_object(Bucket=bucket_name, Key=obj['Key'])
                                content = file_response['Body'].read().decode('utf-8')
                                test_plans[filename] = content
                    
                    # Validate and fix the test plans
                    from code_validator import validate_and_fix_test_plans
                    validation_result = validate_and_fix_test_plans(test_plans)
                    
                    # Upload fixed plans back to S3 if validation succeeded
                    if validation_result['status'] in ['success', 'partial_success']:
                        for filename, fixed_code in validation_result['validated_plans'].items():
                            s3_key = f"perf-pipeline/{session_id}/plans/{filename}"
                            self.s3_client.put_object(
                                Bucket=bucket_name,
                                Key=s3_key,
                                Body=fixed_code,
                                ContentType='text/plain'
                            )
                    
                    return [TextContent(type="text", text=json.dumps(validation_result, indent=2))]
                    
                except Exception as e:
                    error_result = {
                        'status': 'error',
                        'error': str(e),
                        'session_id': session_id
                    }
                    return [TextContent(type="text", text=json.dumps(error_result, indent=2))]
            
            elif name == "get_test_artifacts":
                session_id = arguments.get("session_id", "")
                artifact_type = arguments.get("artifact_type", "all")
                
                result = self._get_artifacts(session_id, artifact_type)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            elif name == "analyze_test_results":
                session_id = arguments.get("session_id", "")
                
                result = results_analyzer.analyze_results(
                    session_id=session_id,
                    s3_client=self.s3_client,
                    bedrock_client=self.bedrock_client
                )
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
            
        except Exception as e:
            logger.error(f"Error calling tool {name}: {str(e)}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    def _get_artifacts(self, session_id: str, artifact_type: str) -> Dict[str, Any]:
        """Get test artifacts for a session"""
        try:
            bucket_name = os.environ.get('S3_BUCKET_NAME')
            prefix = f"perf-pipeline/{session_id}/"
            
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix
            )
            
            artifacts = []
            for obj in response.get('Contents', []):
                key = obj['Key']
                artifact_name = key.replace(prefix, '')
                
                if artifact_type == "all" or artifact_type in artifact_name:
                    artifacts.append({
                        'name': artifact_name,
                        'key': key,
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'].isoformat(),
                        'url': f"s3://{bucket_name}/{key}"
                    })
            
            return {
                'session_id': session_id,
                'artifact_type': artifact_type,
                'artifacts': artifacts,
                'total_count': len(artifacts)
            }
            
        except Exception as e:
            logger.error(f"Error getting artifacts: {str(e)}")
            return {'error': str(e)}

# Global server instance
mcp_server = PerformanceTestingMCPServer()

async def run_server():
    """Run the MCP server"""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await mcp_server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="performance-testing-mcp",
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