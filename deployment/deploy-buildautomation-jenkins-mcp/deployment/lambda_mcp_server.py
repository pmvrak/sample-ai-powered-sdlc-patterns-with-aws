#!/usr/bin/env python3
"""
Simple implementation without FastAPI dependencies
"""

import json
from typing import Dict, List, Any, Optional

class JenkinsMCPServer:
    """Simple Jenkins MCP Server for Lambda"""
    
    def __init__(self):
        self.tools = [
            {
                "name": "jenkins_health_check",
                "description": "Check Jenkins server health and connection",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "jenkins_list_jobs",
                "description": "List all Jenkins jobs you have access to",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "jenkins_get_job_info",
                "description": "Get detailed information about a specific Jenkins job",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_name": {
                            "type": "string",
                            "description": "Name of the Jenkins job"
                        }
                    },
                    "required": ["job_name"]
                }
            },
            {
                "name": "jenkins_trigger_build",
                "description": "Trigger a build for a Jenkins job",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_name": {
                            "type": "string",
                            "description": "Name of the Jenkins job to build"
                        },
                        "parameters": {
                            "type": "object",
                            "description": "Build parameters (optional)",
                            "additionalProperties": {"type": "string"}
                        }
                    },
                    "required": ["job_name"]
                }
            },
            {
                "name": "jenkins_get_build_info",
                "description": "Get detailed information about a specific build",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_name": {
                            "type": "string",
                            "description": "Name of the Jenkins job"
                        },
                        "build_number": {
                            "type": "integer",
                            "description": "Build number"
                        }
                    },
                    "required": ["job_name", "build_number"]
                }
            },
            {
                "name": "jenkins_get_build_log",
                "description": "Get console log for a specific build",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_name": {
                            "type": "string",
                            "description": "Name of the Jenkins job"
                        },
                        "build_number": {
                            "type": "integer",
                            "description": "Build number"
                        }
                    },
                    "required": ["job_name", "build_number"]
                }
            },
            {
                "name": "jenkins_list_builds",
                "description": "List recent builds for a Jenkins job",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_name": {
                            "type": "string",
                            "description": "Name of the Jenkins job"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of builds to return",
                            "default": 10
                        }
                    },
                    "required": ["job_name"]
                }
            },
            {
                "name": "jenkins_get_queue_info",
                "description": "Get current Jenkins build queue information",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "jenkins_get_nodes",
                "description": "Get information about Jenkins nodes/agents",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "jenkins_abort_build",
                "description": "Abort a running Jenkins build",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_name": {
                            "type": "string",
                            "description": "Name of the Jenkins job"
                        },
                        "build_number": {
                            "type": "integer",
                            "description": "Build number to abort"
                        }
                    },
                    "required": ["job_name", "build_number"]
                }
            },
            {
                "name": "jenkins_create_job",
                "description": "Create a new Jenkins job with basic configuration",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "job_name": {
                            "type": "string",
                            "description": "Name for the new Jenkins job"
                        },
                        "job_type": {
                            "type": "string",
                            "description": "Type of job to create",
                            "enum": ["freestyle", "pipeline"],
                            "default": "freestyle"
                        },
                        "description": {
                            "type": "string",
                            "description": "Job description (optional)"
                        },
                        "script": {
                            "type": "string",
                            "description": "Build script/commands to execute"
                        }
                    },
                    "required": ["job_name", "script"]
                }
            }
        ]
    
    def list_tools(self) -> Dict[str, Any]:
        """List available tools"""
        return {
            "tools": self.tools
        }
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a specific tool"""
        try:
            # Import Jenkins client
            from jenkins_client.client import JenkinsClient
            jenkins_client = JenkinsClient()
            
            # Set up asyncio loop for async methods
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                if tool_name == "jenkins_health_check":
                    result = loop.run_until_complete(jenkins_client.test_connection())
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Jenkins Health Check:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_list_jobs":
                    result = loop.run_until_complete(jenkins_client.list_jobs())
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Jenkins Jobs ({len(result)} found):\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_get_job_info":
                    job_name = arguments.get("job_name")
                    result = loop.run_until_complete(jenkins_client.get_job_info(job_name))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Job Info for '{job_name}':\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_trigger_build":
                    job_name = arguments.get("job_name")
                    parameters = arguments.get("parameters")
                    result = loop.run_until_complete(jenkins_client.trigger_build(job_name, parameters))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Build Triggered:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_get_build_info":
                    job_name = arguments.get("job_name")
                    build_number = arguments.get("build_number")
                    result = loop.run_until_complete(jenkins_client.get_build_info(job_name, build_number))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Build Info for '{job_name}#{build_number}':\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_get_build_log":
                    job_name = arguments.get("job_name")
                    build_number = arguments.get("build_number")
                    result = loop.run_until_complete(jenkins_client.get_build_log(job_name, build_number))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Build Log for '{job_name}#{build_number}':\n{result}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_list_builds":
                    job_name = arguments.get("job_name")
                    limit = arguments.get("limit", 10)
                    result = loop.run_until_complete(jenkins_client.list_builds(job_name, limit))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Recent Builds for '{job_name}' (limit {limit}):\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_get_queue_info":
                    result = loop.run_until_complete(jenkins_client.get_queue_info())
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Jenkins Build Queue:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_get_nodes":
                    result = loop.run_until_complete(jenkins_client.get_nodes())
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Jenkins Nodes/Agents:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_abort_build":
                    job_name = arguments.get("job_name")
                    build_number = arguments.get("build_number")
                    result = loop.run_until_complete(jenkins_client.abort_build(job_name, build_number))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Build Abort Result:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                elif tool_name == "jenkins_create_job":
                    job_name = arguments.get("job_name")
                    job_type = arguments.get("job_type", "freestyle")
                    description = arguments.get("description", "")
                    script = arguments.get("script")
                    
                    # Generate basic job configuration XML
                    if job_type == "pipeline":
                        config_xml = self._generate_pipeline_config(job_name, description, script)
                    else:
                        config_xml = self._generate_freestyle_config(job_name, description, script)
                    
                    result = loop.run_until_complete(jenkins_client.create_job(job_name, config_xml))
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Job Creation Result:\n{json.dumps(result, indent=2)}"
                            }
                        ]
                    }
                
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Unknown tool: {tool_name}"
                            }
                        ],
                        "isError": True
                    }
            
            finally:
                loop.close()
                
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error calling tool {tool_name}: {str(e)}"
                    }
                ],
                "isError": True
            }
    
    def _generate_freestyle_config(self, job_name: str, description: str, script: str) -> str:
        """Generate XML configuration for a freestyle job"""
        return f"""<?xml version='1.1' encoding='UTF-8'?>
<project>
  <description>{description}</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <scm class="hudson.scm.NullSCM"/>
  <canRoam>true</canRoam>
  <disabled>false</disabled>
  <blockBuildWhenDownstreamBuilding>false</blockBuildWhenDownstreamBuilding>
  <blockBuildWhenUpstreamBuilding>false</blockBuildWhenUpstreamBuilding>
  <triggers/>
  <concurrentBuild>false</concurrentBuild>
  <builders>
    <hudson.tasks.Shell>
      <command>{script}</command>
    </hudson.tasks.Shell>
  </builders>
  <publishers/>
  <buildWrappers/>
</project>"""
    
    def _generate_pipeline_config(self, job_name: str, description: str, script: str) -> str:
        """Generate XML configuration for a pipeline job"""
        return f"""<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>{description}</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps">
    <script>{script}</script>
    <sandbox>true</sandbox>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>"""

def lambda_handler(event, context):
    """AWS Lambda handler"""
    try:
        # Parse the request
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        server = JenkinsMCPServer()
        
        # Handle different MCP methods
        method = body.get('method', '')
        
        if method == 'tools/list':
            result = server.list_tools()
        elif method == 'tools/call':
            tool_name = body.get('params', {}).get('name', '')
            arguments = body.get('params', {}).get('arguments', {})
            result = server.call_tool(tool_name, arguments)
        else:
            result = {
                "error": f"Unknown method: {method}"
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps({
                "jsonrpc": "2.0",
                "id": body.get('id', 1),
                "result": result
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
                "jsonrpc": "2.0",
                "id": body.get('id', 1) if 'body' in locals() else 1,
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                }
            })
        }

# Health check endpoint
def health_check():
    """Health check for the MCP server"""
    try:
        from jenkins_client.client import JenkinsClient
        import asyncio
        
        client = JenkinsClient()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            health_result = loop.run_until_complete(client.test_connection())
            return {
                "status": "healthy",
                "message": "Jenkins MCP Server is running",
                "health_check": health_result
            }
        finally:
            loop.close()
            
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": f"Jenkins MCP Server error: {str(e)}"
        }
