"""
Scenario Generator Module
Generates comprehensive performance test scenarios based on architecture analysis
"""

import json
import logging
import os
from typing import Dict, Any, List
import boto3

logger = logging.getLogger(__name__)

def generate_scenarios(session_id: str, workflow_apis: List[Dict], nfrs: Dict, 
                      scenario_types: List[str], s3_client, bedrock_client) -> Dict[str, Any]:
    """
    Generate performance test scenarios based on workflow and NFRs
    
    Args:
        session_id: Session ID linking to previous analysis
        workflow_apis: Array of API endpoints in execution order
        nfrs: Non-functional requirements
        scenario_types: Types of scenarios to generate
        s3_client: AWS S3 client
        bedrock_client: AWS Bedrock client
    
    Returns:
        Generated scenarios with test parameters
    """
    try:
        logger.info(f"Generating scenarios for session {session_id}")
        
        # Load previous analysis if available
        analysis_data = _load_analysis(session_id, s3_client)
        
        # Generate scenarios using Bedrock
        scenarios = _generate_with_bedrock(
            workflow_apis, nfrs, scenario_types, analysis_data, bedrock_client
        )
        
        # Store scenarios in S3
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_key = f"perf-pipeline/{session_id}/scenarios.json"
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(scenarios, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Scenarios generated and stored at s3://{bucket_name}/{s3_key}")
        
        return {
            'session_id': session_id,
            'status': 'completed',
            'scenarios': scenarios,
            's3_location': f"s3://{bucket_name}/{s3_key}"
        }
        
    except Exception as e:
        logger.warning(f"Scenario generation failed for session {session_id}: {str(e)}")
        return {
            'session_id': session_id,
            'status': 'error',
            'error': str(e)
        }

def _load_analysis(session_id: str, s3_client) -> Dict[str, Any]:
    """Load previous analysis from S3"""
    try:
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_key = f"perf-pipeline/{session_id}/analysis.json"
        
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        return json.loads(content)
        
    except Exception as e:
        logger.warning(f"Could not load analysis for session {session_id}: {str(e)}")
        return {}

def _generate_with_bedrock(workflow_apis: List[Dict], nfrs: Dict, scenario_types: List[str], 
                          analysis_data: Dict, bedrock_client) -> Dict[str, Any]:
    """Generate scenarios using Bedrock"""
    
    system_prompt = """You are an expert performance testing engineer specializing in JMeter and load testing.
    Generate comprehensive performance test scenarios based on the provided workflow APIs and NFRs.
    
    CRITICAL: Extract test configuration values from the NFRs object:
    - Use "max_concurrent_users" for the number of users
    - Use "max_test_duration" for the test duration 
    - Use "max_loops_per_user" for loop configuration
    - Convert time strings like "30 seconds" to numeric values
    
    For each scenario type, provide:
    1. Test configuration (users, ramp-up, duration) - MUST use NFR values
    2. Load patterns and timing
    3. Success criteria and thresholds
    4. Specific test parameters
    
    Return a JSON object with scenarios for each requested type.
    
    EXAMPLE OUTPUT FORMAT:
    {
      "scenarios": {
        "load": {
          "name": "Load Test",
          "users": 3,
          "ramp_up_time": "10s", 
          "duration": "30s",
          "test_steps": [...]
        }
      }
    }"""
    
    user_prompt = f"""Generate performance test scenarios with these parameters:

Workflow APIs:
{json.dumps(workflow_apis, indent=2)}

Non-Functional Requirements:
{json.dumps(nfrs, indent=2)}

Scenario Types: {scenario_types}

Architecture Context:
{json.dumps(analysis_data.get('analysis', {}), indent=2) if analysis_data else 'No previous analysis available'}

Create detailed scenarios for: {', '.join(scenario_types)}"""
    
    try:
        prompt_config = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_prompt}]
                }
            ]
        }
        
        body = json.dumps(prompt_config)
        model_id = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")
        
        response = bedrock_client.invoke_model(
            body=body,
            modelId=model_id,
            accept="application/json",
            contentType="application/json"
        )
        
        response_body = json.loads(response.get("body").read())
        content = response_body.get("content")
        
        if not content or len(content) == 0:
            logger.warning("No content in Bedrock response")
            raise Exception("Bedrock AI failed to generate content - no fallback available")
        
        result_text = content[0].get("text")
        
        if not result_text:
            logger.warning("No text in Bedrock response content")
            raise Exception("Bedrock AI returned empty response - no fallback available")
        
        # Extract JSON from markdown code blocks
        cleaned_text = result_text.strip()
        
        # Look for JSON code blocks
        if '```json' in cleaned_text:
            # Extract content between ```json and ```
            start_marker = '```json'
            end_marker = '```'
            start_idx = cleaned_text.find(start_marker)
            if start_idx != -1:
                start_idx += len(start_marker)
                end_idx = cleaned_text.find(end_marker, start_idx)
                if end_idx != -1:
                    cleaned_text = cleaned_text[start_idx:end_idx].strip()
        elif '```' in cleaned_text:
            # Handle generic code blocks
            start_idx = cleaned_text.find('```')
            if start_idx != -1:
                start_idx = cleaned_text.find('\n', start_idx) + 1
                end_idx = cleaned_text.find('```', start_idx)
                if end_idx != -1:
                    cleaned_text = cleaned_text[start_idx:end_idx].strip()
        
        # If no code blocks found, try to find JSON by looking for { at start
        if not cleaned_text.startswith('{'):
            # Look for the first { character
            json_start = cleaned_text.find('{')
            if json_start != -1:
                cleaned_text = cleaned_text[json_start:].strip()
        
        # Try to parse as JSON
        try:
            parsed_result = json.loads(cleaned_text)
            # Add metadata to indicate AI generation
            if isinstance(parsed_result, dict):
                if 'metadata' not in parsed_result:
                    parsed_result['metadata'] = {}
                parsed_result['metadata']['generated_from'] = 'bedrock_ai'
            return parsed_result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Bedrock response as JSON: {e}")
            logger.debug(f"Raw response: {result_text[:500]}...")
            raise Exception(f"Bedrock AI returned invalid JSON: {e} - no fallback available")
            
    except Exception as e:
        logger.warning(f"Bedrock call failed for scenario generation: {str(e)}")
        raise Exception(f"Bedrock AI scenario generation failed: {str(e)} - no fallback available")

# Text parsing fallback removed - AI must return valid JSON

# All fallback functions removed - AI-only generation enforced