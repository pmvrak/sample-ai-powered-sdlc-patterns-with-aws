"""
Architecture Analyzer Module
Analyzes architecture documents to understand system components, interactions, and data flows
"""

import json
import logging
import os
import uuid
from typing import Dict, Any, List
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def analyze_documents(documents_path: str, session_id: str, s3_client, bedrock_client) -> Dict[str, Any]:
    """
    Analyze architecture documents and extract system information
    
    Args:
        documents_path: S3 path or local path to documents
        session_id: Session ID for state management
        s3_client: AWS S3 client
        bedrock_client: AWS Bedrock client
    
    Returns:
        Analysis results with components, workflows, and NFR suggestions
    """
    try:
        logger.info(f"Starting architecture analysis for session {session_id}")
        
        # Read documents
        documents_content = _read_documents(documents_path, s3_client)
        
        # Analyze with Bedrock
        analysis_result = _analyze_with_bedrock(documents_content, bedrock_client)
        
        # Store results in S3
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        s3_key = f"perf-pipeline/{session_id}/analysis.json"
        
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=json.dumps(analysis_result, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Analysis completed and stored at s3://{bucket_name}/{s3_key}")
        
        return {
            'session_id': session_id,
            'status': 'completed',
            'analysis': analysis_result,
            's3_location': f"s3://{bucket_name}/{s3_key}"
        }
        
    except Exception as e:
        logger.warning(f"Architecture analysis failed for session {session_id}: {str(e)}")
        return {
            'session_id': session_id,
            'status': 'error',
            'error': str(e)
        }

def _read_documents(documents_path: str, s3_client) -> str:
    """Read documents from S3 or local path"""
    try:
        if documents_path.startswith('s3://'):
            # Parse S3 path
            path_parts = documents_path.replace('s3://', '').split('/', 1)
            bucket = path_parts[0]
            prefix = path_parts[1] if len(path_parts) > 1 else ''
            
            # List and read all documents in the prefix
            response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            documents = []
            
            for obj in response.get('Contents', []):
                if obj['Key'].endswith(('.txt', '.md', '.json', '.yaml', '.yml')):
                    doc_response = s3_client.get_object(Bucket=bucket, Key=obj['Key'])
                    content = doc_response['Body'].read().decode('utf-8')
                    documents.append(f"Document: {obj['Key']}\n{content}\n\n")
            
            return '\n'.join(documents)
        else:
            # Local file path
            with open(documents_path, 'r', encoding='utf-8') as f:
                return f.read()
                
    except Exception as e:
        logger.warning(f"Failed to read documents from {documents_path}: {str(e)}")
        return f"Error reading documents: {str(e)}"

def _analyze_with_bedrock(documents_content: str, bedrock_client) -> Dict[str, Any]:
    """Analyze documents using Bedrock to extract architecture information"""
    
    system_prompt = """You are an expert system architect and performance testing specialist. 
    Analyze the provided architecture documents and extract information for performance testing.
    
    CRITICAL: The document may have nested JSON structure. Look for:
    - API endpoints in "api_specifications" -> "endpoints" arrays
    - Business workflows in "business_flows" arrays  
    - NFRs in "non_functional_requirements" -> "performance" objects
    - Extract nested values like "max_concurrent_users", "max_test_duration"
    
    Extract:
    1. System Components: List all services, databases, APIs, and infrastructure components
    2. API Endpoints: Identify all REST/GraphQL endpoints with methods from nested structures
    3. Data Flows: Map how data moves between components
    4. Workflows: Identify complete user/business workflows that span multiple APIs
    5. NFR Suggestions: Extract actual NFR values from nested performance requirements
    
    Return your analysis as a JSON object with these exact keys:
    - components: array of component objects with {name, type, description}
    - endpoints: array of endpoint objects with {path, method, service, description}
    - dataFlows: array of flow objects with {from, to, data_type, description}
    - workflows: array of workflow objects with {name, steps, description}
    - nfrSuggestions: object with performance requirements extracted from the document
    
    EXAMPLE: If you see "max_concurrent_users": "3" in nested JSON, use that exact value.
    """
    
    user_prompt = f"""Analyze this architecture documentation:

{documents_content}

Please provide a comprehensive analysis focusing on performance testing requirements."""
    
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
        content_list = response_body.get("content", [])
        if content_list and isinstance(content_list, list) and len(content_list) > 0:
            result_text = content_list[0].get("text", "")
        else:
            raise Exception("Invalid response format from Claude")
        
        # Clean up markdown formatting if present
        cleaned_text = result_text.strip()
        if cleaned_text.startswith('```json'):
            cleaned_text = cleaned_text[7:]  # Remove ```json
        if cleaned_text.startswith('```'):
            cleaned_text = cleaned_text[3:]   # Remove ```
        if cleaned_text.endswith('```'):
            cleaned_text = cleaned_text[:-3]  # Remove trailing ```
        cleaned_text = cleaned_text.strip()
        
        # Try to parse as JSON - no fallback allowed
        try:
            return json.loads(cleaned_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Bedrock response as JSON: {e}")
            logger.debug(f"Raw response: {result_text[:500]}...")
            raise Exception(f"Bedrock AI returned invalid JSON: {e} - no fallback available")
            
    except Exception as e:
        logger.warning(f"Bedrock call failed for architecture analysis: {str(e)}")
        raise Exception(f"Bedrock AI architecture analysis failed: {str(e)} - no fallback available")

# Text parsing fallback removed - AI must return valid JSON

# Fallback analysis removed - AI-only generation