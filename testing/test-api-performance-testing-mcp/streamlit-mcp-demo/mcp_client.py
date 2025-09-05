"""
MCP Client for AWS Lambda Function URL with SigV4 authentication
"""
import os
import json
import urllib3
from typing import Dict, Any
from botocore.session import get_session
from botocore.awsrequest import AWSRequest
from botocore.auth import SigV4Auth

# Configuration from environment
FN_URL = os.environ.get("MCP_FUNCTION_URL", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() == "true"

# HTTP client
_http = urllib3.PoolManager()

def sign_and_post(tool: str, arguments: dict) -> dict:
    """
    Build {method:'tools/call', params:{name, arguments}}, SigV4 sign (service='lambda'),
    POST to MCP_FUNCTION_URL, return JSON. No hard-coded tool args here.
    
    Args:
        tool: MCP tool name (e.g., 'analyze_architecture')
        arguments: Tool-specific arguments including session_id
    
    Returns:
        Parsed JSON response from Lambda
    
    Raises:
        RuntimeError: If request fails or returns non-200 status
        ValueError: If environment variables are missing
    """
    if not FN_URL:
        raise ValueError("MCP_FUNCTION_URL environment variable is required")
    
    if DEMO_MODE:
        return _demo_response(tool, arguments)
    
    # Build MCP payload (JSON-RPC 2.0 format)
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool,
            "arguments": arguments
        }
    }
    
    try:
        # Create AWS request
        req = AWSRequest(
            method="POST",
            url=FN_URL,
            data=json.dumps(payload),
            headers={"content-type": "application/json"}
        )
        
        # Get AWS credentials and sign request
        creds = get_session().get_credentials().get_frozen_credentials()
        SigV4Auth(creds, "lambda", REGION).add_auth(req)
        
        # Make HTTP request
        resp = _http.request(
            "POST", 
            FN_URL, 
            body=req.data, 
            headers=dict(req.headers),
            timeout=300.0  # 5 minute timeout for large document processing
        )
        
        if resp.status != 200:
            error_text = resp.data.decode('utf-8', 'ignore')
            raise RuntimeError(f"MCP call failed ({resp.status}): {error_text}")
        
        response_data = json.loads(resp.data.decode("utf-8"))
        
        # Add debugging for generate_test_plans specifically
        if tool == "generate_test_plans":
            print(f"🔍 DEBUG - MCP Response for {tool}:")
            print(f"📊 Status: {resp.status}")
            print(f"📝 Response keys: {list(response_data.keys())}")
            
            # Extract and parse the result content
            if 'result' in response_data and 'content' in response_data['result']:
                content = response_data['result']['content']
                if content and len(content) > 0:
                    text_content = content[0].get('text', '')
                    try:
                        parsed_content = json.loads(text_content)
                        print(f"📋 Parsed content keys: {list(parsed_content.keys())}")
                        print(f"🎯 Status: {parsed_content.get('status', 'unknown')}")
                        print(f"📊 Total plans: {parsed_content.get('total_plans', 0)}")
                        print(f"📁 Plans generated: {parsed_content.get('plans_generated', [])}")
                        
                        if parsed_content.get('total_plans', 0) == 0:
                            print("⚠️  WARNING: No test plans were generated!")
                            print(f"🔍 Full response: {text_content[:500]}...")
                    except json.JSONDecodeError:
                        print(f"❌ Could not parse content as JSON: {text_content[:200]}...")
        
        return response_data
        
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Failed to call MCP tool '{tool}': {str(e)}")

def _demo_response(tool: str, arguments: dict) -> dict:
    """Generate demo responses when DEMO_MODE=true"""
    session_id = arguments.get("session_id", "demo-001")
    
    demo_responses = {
        "analyze_architecture": {
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "session_id": session_id,
                        "status": "completed",
                        "analysis": {
                            "components": ["API Gateway", "Lambda", "DynamoDB"],
                            "endpoints": ["/api/users", "/api/orders"],
                            "workflows": ["User Registration", "Order Processing"]
                        }
                    })
                }]
            }
        },
        "generate_test_scenarios": {
            "result": {
                "content": [{
                    "type": "text", 
                    "text": json.dumps({
                        "session_id": session_id,
                        "status": "completed",
                        "scenarios": {
                            "load_test": {"users": 100, "duration": "10m"},
                            "stress_test": {"users": 500, "duration": "15m"}
                        }
                    })
                }]
            }
        },
        "generate_test_plans": {
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "session_id": session_id,
                        "status": "completed",
                        "plans_generated": ["TestPlan01.java", "TestPlan02.java"],
                        "total_plans": 2
                    })
                }]
            }
        },
        "validate_test_plans": {
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "session_id": session_id,
                        "status": "success",
                        "validated_plans": {"TestPlan01.java": "valid", "TestPlan02.java": "valid"},
                        "fixes_applied": []
                    })
                }]
            }
        },
        "execute_performance_test": {
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "session_id": session_id,
                        "status": "started",
                        "execution": {
                            "cluster_name": "performance-testing-cluster",
                            "running_tasks": [{"task_arn": "arn:aws:ecs:us-east-1:123:task/demo"}],
                            "total_tasks": 2
                        }
                    })
                }]
            }
        },
        "get_test_artifacts": {
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "session_id": session_id,
                        "artifacts": [
                            {"name": "scenarios.json", "size": 1024},
                            {"name": "plans/TestPlan01.java", "size": 2048},
                            {"name": "results/test_results.jtl", "size": 4096}
                        ],
                        "total_count": 3
                    })
                }]
            }
        },
        "analyze_test_results": {
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "session_id": session_id,
                        "status": "completed",
                        "analysis": {
                            "performance_grade": "A",
                            "summary": "Excellent performance with 99.9% success rate",
                            "recommendations": ["Consider increasing load", "Monitor memory usage"]
                        }
                    })
                }]
            }
        }
    }
    
    return demo_responses.get(tool, {
        "result": {
            "content": [{
                "type": "text",
                "text": json.dumps({"status": "demo_mode", "tool": tool})
            }]
        }
    })