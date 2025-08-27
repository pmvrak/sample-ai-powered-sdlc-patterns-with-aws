# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Amazon Q Business JSON-RPC 2.0 Server

This server implements the JSON-RPC 2.0 protocol for Amazon Q Business integration
using SigV4 authentication through API Gateway Lambda authorizer.

Core functionality:
- retrieve: Get information from knowledge base (RETRIEVAL_MODE)
- create: Generate new content (CREATOR_MODE)
"""

import boto3
import json
import logging
import asyncio
import time
import os
import datetime
import jwt
from typing import Any, Dict, Optional, Callable

# Export main functions for MCP server
__all__ = [
    "handle_jsonrpc_request",
    "retrieve", "create", 
    "user_sessions",
    "query_amazon_q_business"
]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration - use environment variables for Lambda compatibility
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
Q_BUSINESS_APPLICATION_ID = os.environ.get("Q_BUSINESS_APPLICATION_ID")
# Default username for MCP operations
MCP_DEFAULT_USERNAME = os.environ.get("MCP_DEFAULT_USERNAME", "default_user")

# Store user sessions
user_sessions = {}

# Global variable to store the current Lambda event (set by lambda_handler.py)
current_lambda_event = None

# Dictionary to store registered methods
methods = {}

# ===== INTEGRATED AUTH MODULE =====
class IntegratedAuth:
    """
    Integrated authentication module that handles Cognito to IDC to STS credential exchange
    This replaces the separate auth lambda with functionality built into the MCP server
    """
    
    def __init__(self):
        self.sts_client = boto3.client('sts')
        self.oidc_client = boto3.client('sso-oidc')
        self.idc_app_client_id = os.environ.get('IDC_APP_CLIENT_ID')
        self.qbiz_role_arn = os.environ.get('QBIZ_ROLE_ARN')
        self.jwt = jwt
    
    def exchange_cognito_token_for_credentials(self, cognito_id_token: str) -> Dict[str, Any]:
        """
        Exchange Cognito ID token for AWS credentials with IDC context
        
        Args:
            cognito_id_token: The Cognito ID token from user authentication
            
        Returns:
            Dictionary containing AWS credentials and metadata
        """
        try:
            logger.info("🔐 AUTH: Starting integrated credential exchange")
            
            if not self.idc_app_client_id:
                raise ValueError("IDC_APP_CLIENT_ID environment variable not set")
            
            if not self.qbiz_role_arn:
                raise ValueError("QBIZ_ROLE_ARN environment variable not set")
            
            # Step 1: Exchange Cognito ID token for IDC token
            logger.info("🔐 AUTH: Step 1 - Exchanging Cognito token for IDC token")
            oidc_token_response = self.oidc_client.create_token_with_iam(
                clientId=self.idc_app_client_id,
                grantType='urn:ietf:params:oauth:grant-type:jwt-bearer',
                assertion=cognito_id_token
            )
            
            # Step 2: Extract identity context from IDC token
            logger.info("🔐 AUTH: Step 2 - Extracting identity context from IDC token")
            claims = self.jwt.decode(oidc_token_response["idToken"], options={"verify_signature": False})
            logger.info(f"🔐 AUTH: IDC token claims keys: {list(claims.keys())}")
            
            # Step 3: Assume role with IDC identity context
            logger.info("🔐 AUTH: Step 3 - Assuming role with IDC identity context")
            timestamp = datetime.datetime.now()
            session_name = f"mcp_integrated_auth_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}"
            
            assume_role_response = self.sts_client.assume_role(
                RoleArn=self.qbiz_role_arn,
                RoleSessionName=session_name,
                DurationSeconds=3600,  # 1 hour
                ProvidedContexts=[
                    {
                        'ProviderArn': "arn:aws:iam::aws:contextProvider/IdentityCenter",
                        'ContextAssertion': claims["sts:identity_context"]
                    }
                ]
            )
            
            # Step 4: Format credentials response
            credentials = assume_role_response['Credentials']
            result = {
                'credentials': {
                    'accessKeyId': credentials['AccessKeyId'],
                    'secretAccessKey': credentials['SecretAccessKey'],
                    'sessionToken': credentials['SessionToken'],
                    'expiration': credentials['Expiration'].isoformat()
                },
                'status': 'SUCCESS',
                'sessionName': session_name,
                'identityContext': {
                    'userId': claims.get('sub'),
                    'userName': claims.get('username', claims.get('email')),
                    'email': claims.get('email')
                },
                'auth_method': 'integrated_cognito_idc_sts'
            }
            
            logger.info("🔐 AUTH: Credential exchange completed successfully")
            logger.info(f"🔐 AUTH: Session name: {session_name}")
            logger.info(f"🔐 AUTH: Credentials expire at: {credentials['Expiration']}")
            
            return result
            
        except Exception as e:
            logger.error(f"🔐 AUTH: Error during credential exchange: {str(e)}")
            raise Exception(f"Integrated auth failed: {str(e)}")

# Initialize integrated auth
integrated_auth = IntegratedAuth()

def register_method(name: str, func: Callable):
    """Register a method with the JSON-RPC server"""
    methods[name] = func
    logger.info(f"Registered method: {name}")

def jsonrpc_response(result=None, error=None, id=None):
    """Create a JSON-RPC 2.0 response"""
    response = {"jsonrpc": "2.0", "id": id}
    if error is not None:
        response["error"] = error
    else:
        response["result"] = result
    return response

def format_result(result):
    """Format a result for JSON-RPC response"""
    if isinstance(result, dict) and "content" in result:
        # Extract text content from MCP response format
        content_text = ""
        for content_item in result["content"]:
            if content_item.get("type") == "text":
                content_text += content_item.get("text", "")
        
        return {
            "success": True,
            "message": content_text
        }
    else:
        # Use the result as is
        return result

async def handle_jsonrpc_request(request):
    """Handle a JSON-RPC 2.0 request"""
    # Check if it's a valid JSON-RPC 2.0 request
    if request.get("jsonrpc") != "2.0":
        return jsonrpc_response(
            error={"code": -32600, "message": "Invalid Request: Not a valid JSON-RPC 2.0 request"},
            id=request.get("id")
        )
    
    # Get the method and parameters
    method_name = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    logger.info(f"Received JSON-RPC request: method={method_name}, id={request_id}")
    
    # Check if the method exists
    if method_name not in methods:
        logger.error(f"Method not found: {method_name}")
        return jsonrpc_response(
            error={"code": -32601, "message": f"Method not found: {method_name}"},
            id=request_id
        )
    
    try:
        # Call the method with the parameters
        logger.info(f"Calling method {method_name} with params: {params}")
        method = methods[method_name]
        result = await method(**params)
        
        # Format the result
        formatted_result = format_result(result)
        
        # Return the result
        logger.info(f"Method {method_name} completed successfully")
        return jsonrpc_response(result=formatted_result, id=request_id)
    
    except Exception as e:
        logger.error(f"Error calling method {method_name}: {str(e)}")
        return jsonrpc_response(
            error={"code": -32603, "message": f"Internal error: {str(e)}"},
            id=request_id
        )

def query_amazon_q_business(credentials, message, conversation_id=None, parent_message_id=None, chat_mode=None):
    """Query Amazon Q Business using temporary credentials"""
    try:
        logger.info(f"Querying Amazon Q Business")
        
        # Create Q Business client with temporary credentials
        qbusiness_client = boto3.client(
            'qbusiness',
            region_name=AWS_REGION,
            aws_access_key_id=credentials['accessKeyId'],
            aws_secret_access_key=credentials['secretAccessKey'],
            aws_session_token=credentials['sessionToken']
        )
        
        # Always use RETRIEVAL_MODE unless explicitly specified
        if not chat_mode:
            chat_mode = 'RETRIEVAL_MODE'
            logger.info(f"Using default RETRIEVAL_MODE")
        
        # Prepare the request for Q Business
        request_params = {
            'applicationId': Q_BUSINESS_APPLICATION_ID,
            'userMessage': message,
            'chatMode': chat_mode  # Valid modes: RETRIEVAL_MODE, CREATOR_MODE
        }
        
        # Add conversation ID if provided
        if conversation_id:
            logger.info(f"Using existing conversation ID: {conversation_id}")
            request_params['conversationId'] = conversation_id
            
        # Add parent message ID if provided
        if parent_message_id:
            logger.info(f"Using parent message ID: {parent_message_id}")
            request_params['parentMessageId'] = parent_message_id
        
        logger.info(f"Sending request to Q Business with params: {request_params}")
        
        # Call Q Business
        response = qbusiness_client.chat_sync(**request_params)
        
        # Log detailed response information
        logger.info(f"Received response from Q Business with keys: {response.keys()}")
        
        if 'systemMessage' in response:
            system_message = response.get('systemMessage', '')
            logger.info(f"System message length: {len(system_message)}")
            logger.info(f"System message preview: {system_message[:100]}...")
        else:
            logger.warning("No systemMessage in response")
            
        if 'systemMessageId' in response:
            logger.info(f"System message ID: {response.get('systemMessageId')}")
        
        # Process the response
        result = {
            'response': response.get('systemMessage', ''),
            'conversationId': response.get('conversationId'),
            'sourceAttributions': response.get('sourceAttributions', []),
            'userMessageId': response.get('userMessageId'),
            'systemMessageId': response.get('systemMessageId')
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error querying Amazon Q Business: {str(e)}")
        raise Exception(f"Q Business query failed: {str(e)}")

def extract_idc_context_from_jwt(jwt_token):
    """
    Extract IDC context from Cognito JWT token
    
    The JWT token contains the sts:identity_context claim that we need for Q Business
    """
    try:
        import base64
        
        logger.debug(f"Extracting IDC context from JWT token")
        
        # JWT tokens have 3 parts: header.payload.signature
        # We need the payload (middle part)
        parts = jwt_token.split('.')
        if len(parts) != 3:
            raise Exception("Invalid JWT token format")
        
        # Decode the payload (add padding if needed)
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        
        # Decode base64
        decoded_payload = base64.b64decode(payload)
        claims = json.loads(decoded_payload)
        
        logger.debug(f"JWT claims keys: {list(claims.keys())}")
        
        # Extract username
        username = claims.get('username') or claims.get('email') or claims.get('sub')
        logger.debug(f"Extracted username: {username}")
        
        # Extract IDC context
        idc_context = claims.get('sts:identity_context')
        logger.debug(f"IDC context present: {bool(idc_context)}")
        
        if idc_context:
            logger.debug(f"IDC context length: {len(idc_context)}")
        
        return {
            'username': username,
            'idc_context': idc_context,
            'claims': claims
        }
        
    except Exception as e:
        logger.error(f"Error extracting IDC context: {str(e)}")
        return None

def get_username_from_request(event):
    """
    Extract the username from the Lambda event context
    
    Now we extract it from the Cognito JWT token in the headers
    """
    try:
        logger.info(f"Extracting username from Lambda event")
        
        # Check headers for JWT token
        headers = event.get('headers', {})
        logger.debug(f"Available headers: {list(headers.keys())}")
        
        # Check the actual header value
        jwt_header_value = headers.get('x-cognito-jwt')
        
        jwt_token = jwt_header_value
        
        if jwt_token:
            logger.info(f"Found JWT token in headers")
            jwt_data = extract_idc_context_from_jwt(jwt_token)
            if jwt_data and jwt_data.get('username'):
                logger.info(f"Extracted username from JWT: {jwt_data['username']}")
                return jwt_data['username']
            else:
                logger.warning(f"Failed to extract username from JWT data")
        else:
            logger.warning(f"JWT token not found in headers")
        
        # Fallback to default username
        logger.warning(f"No JWT token found, using default username: {MCP_DEFAULT_USERNAME}")
        return MCP_DEFAULT_USERNAME
            
    except Exception as e:
        logger.error(f"Error extracting username: {str(e)}")
        return MCP_DEFAULT_USERNAME

# get_credentials_from_request function removed - using integrated auth instead

async def ensure_credentials_available(username: str = None):
    """
    Ensure credentials are available for Q Business calls using integrated auth
    
    This uses the integrated auth module to exchange Cognito tokens for AWS credentials
    with IDC context, eliminating the need for a separate auth lambda.
    """
    if not username:
        username = MCP_DEFAULT_USERNAME or "default_user"
    
    session_id = f"session_{username}"
    
    logger.info(f"Starting integrated auth for username: {username}")
    logger.debug(f"Session ID: {session_id}")
    
    # Check if we already have credentials cached
    if session_id in user_sessions:
        logger.info(f"Using cached credentials for {username}")
        return True
    
    try:
        # Extract Cognito JWT token from request headers
        if not current_lambda_event:
            raise Exception("No Lambda event available for JWT token extraction")
        
        headers = current_lambda_event.get('headers', {})
        logger.debug(f"Available headers: {list(headers.keys())}")
        
        # API Gateway converts headers to lowercase
        jwt_token = headers.get('x-cognito-jwt') or headers.get('X-Cognito-JWT') or headers.get('X-Cognito-Jwt')
        
        if not jwt_token:
            raise Exception("No Cognito JWT token found in request headers")
        
        logger.info(f"Found JWT token, using integrated auth")
        
        # Use integrated auth to exchange token for credentials
        auth_result = integrated_auth.exchange_cognito_token_for_credentials(jwt_token)
        
        if auth_result['status'] != 'SUCCESS':
            raise Exception(f"Integrated auth failed: {auth_result.get('status', 'Unknown error')}")
        
        credentials = auth_result['credentials']
        identity_context = auth_result.get('identityContext', {})
        
        # Extract actual username from identity context
        actual_username = identity_context.get('userName') or identity_context.get('email') or username
        logger.info(f"Actual username from IDC: {actual_username}")
        
        # Update session_id to use actual username
        session_id = f"session_{actual_username}"
        
        # Store credentials in session
        user_sessions[session_id] = {
            "credentials": {
                'accessKeyId': credentials['accessKeyId'],
                'secretAccessKey': credentials['secretAccessKey'],
                'sessionToken': credentials['sessionToken'],
                'expiration': credentials['expiration']
            },
            "conversation_id": None,
            "system_message_id": None,
            "auth_method": auth_result['auth_method'],
            "identity_context": identity_context,
            "session_name": auth_result['sessionName']
        }
        
        logger.info(f"Integrated auth successful for {actual_username}")
        logger.debug(f"Credentials expire at: {credentials['expiration']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Integrated auth failed for {username}: {str(e)}")
        return False

async def retrieve(message: str = "", username: str = MCP_DEFAULT_USERNAME):
    """
    Universal retrieval tool - Get information from your knowledge base
    
    Examples:
    - "What pages are in my Confluence?"
    - "Extract requirements from AnyCompanyReads project"
    - "What are the main features described in my documentation?"
    - "Analyze my Confluence content"
    """
    try:
        logger.info(f"RETRIEVE mode: {message[:100]}...")
        
        # Get the actual username from the authenticated request
        if current_lambda_event:
            actual_username = get_username_from_request(current_lambda_event)
            logger.info(f"Using actual username from request: {actual_username}")
        else:
            actual_username = username
            logger.info(f"No lambda event, using parameter username: {actual_username}")
        
        # Ensure credentials are available from SigV4 request context
        session_id = f"session_{actual_username}"
        logger.debug(f"Checking session for {actual_username}, session_id: {session_id}")
        
        if session_id not in user_sessions:
            logger.info(f"No session found for {actual_username}, getting credentials from Lambda context")
            try:
                credentials_available = await ensure_credentials_available(actual_username)
                if not credentials_available:
                    raise Exception(f"Failed to get credentials from SigV4 request context")
            except Exception as e:
                logger.error(f"Exception in ensure_credentials_available: {str(e)}")
                raise
        else:
            logger.info(f"Found existing session for {actual_username}")
        
        session = user_sessions[session_id]
        
        # Check if this is a new conversation or continuing one
        if "conversation_id" in session and session["conversation_id"]:
            parent_message_id = session.get("system_message_id")
            logger.info(f"Continuing conversation with ID: {session['conversation_id']}")
        else:
            parent_message_id = None
            logger.info("Starting new conversation")
        
        # Query Amazon Q Business in RETRIEVAL_MODE
        result = query_amazon_q_business(
            session["credentials"],
            message,
            session.get("conversation_id"),
            parent_message_id,
            "RETRIEVAL_MODE"
        )
        
        # Update conversation ID and system message ID for next request
        session["conversation_id"] = result["conversationId"]
        session["system_message_id"] = result["systemMessageId"]
        
        # Check if we got a meaningful response
        response_text = result["response"]
        if not response_text or response_text == "No answer is found":
            response_text = (
                "I don't have specific information about that in my knowledge base. "
                "As an AI assistant, I can still try to help based on my general knowledge. "
                "What would you like to know?"
            )
        
        return {
            "content": [
                {"type": "text", "text": response_text}
            ]
        }
    
    except Exception as e:
        logger.error(f"Retrieve failed: {str(e)}")
        # If we get a mismatched message ID error, reset the conversation
        if "mismatched message IDs" in str(e):
            logger.info("Resetting conversation due to mismatched message IDs")
            if session_id in user_sessions:
                user_sessions[session_id]["conversation_id"] = None
                user_sessions[session_id]["system_message_id"] = None
            raise Exception(f"Retrieve failed: Conversation reset due to error. Please try again.")
        else:
            raise Exception(f"Retrieve failed: {str(e)}")

async def create(message: str = "", username: str = MCP_DEFAULT_USERNAME):
    """
    Universal creation tool - Generate new content
    
    Examples:
    - "Generate user stories for a login system"
    - "Create acceptance criteria for user registration"
    - "Estimate story points for these features: login, signup, password reset"
    - "Write a technical specification for user authentication"
    """
    try:
        logger.info(f"✨ CREATE mode: {message[:100]}...")
        
        # Get the actual username from the authenticated request
        if current_lambda_event:
            actual_username = get_username_from_request(current_lambda_event)
            logger.info(f"Using actual username from request: {actual_username}")
        else:
            actual_username = username
            logger.info(f"No lambda event, using parameter username: {actual_username}")
        
        # Ensure credentials are available from SigV4 request context
        session_id = f"session_{actual_username}"
        if session_id not in user_sessions:
            logger.info(f"No session found for {actual_username}, getting credentials from Lambda context")
            credentials_available = await ensure_credentials_available(actual_username)
            if not credentials_available:
                raise Exception(f"Failed to get credentials from SigV4 request context")
        
        session = user_sessions[session_id]
        
        # Check if this is a new conversation or continuing one
        if "conversation_id" in session and session["conversation_id"]:
            parent_message_id = session.get("system_message_id")
            logger.info(f"Continuing conversation with ID: {session['conversation_id']}")
        else:
            parent_message_id = None
            logger.info("Starting new conversation")
        
        # Query Amazon Q Business in CREATOR_MODE
        result = query_amazon_q_business(
            session["credentials"],
            message,
            session.get("conversation_id"),
            parent_message_id,
            "CREATOR_MODE"
        )
        
        # Update conversation ID and system message ID for next request
        session["conversation_id"] = result["conversationId"]
        session["system_message_id"] = result["systemMessageId"]
        
        return {
            "content": [
                {"type": "text", "text": result["response"]}
            ]
        }
    
    except Exception as e:
        logger.error(f"Create failed: {str(e)}")
        # If we get a mismatched message ID error, reset the conversation
        if "mismatched message IDs" in str(e):
            logger.info("Resetting conversation due to mismatched message IDs")
            if session_id in user_sessions:
                user_sessions[session_id]["conversation_id"] = None
                user_sessions[session_id]["system_message_id"] = None
            raise Exception(f"Create failed: Conversation reset due to error. Please try again.")
        else:
            raise Exception(f"Create failed: {str(e)}")

# Register the core methods
register_method("retrieve", retrieve)
register_method("create", create)