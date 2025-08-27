# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Atlassian (Jira/Confluence) integration for Amazon Q Business MCP server

This module provides tools for authenticating with Atlassian services
and using them with Amazon Q Business plugins.
"""

import json
import logging
import os
import requests
import boto3
import urllib.parse
import threading
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load Atlassian credentials from environment variables
CONFLUENCE_URL = os.environ.get("CONFLUENCE_URL")
CONFLUENCE_USERNAME = os.environ.get("CONFLUENCE_USERNAME")
CONFLUENCE_API_TOKEN = os.environ.get("CONFLUENCE_PASSWORD")

# Jira OAuth credentials removed - using Confluence Basic Auth only

# Atlassian OAuth tokens removed - using Confluence Basic Auth only

# OAuth callback state removed - using Confluence Basic Auth only

# Removed request serialization - let Amazon Q Business handle concurrent requests naturally

# Token session cache - authenticate once, reuse session
authenticated_tokens = {}  # {token_hash: {"conversation_id": "...", "expires_at": timestamp}}
token_cache_lock = threading.Lock()

def get_plugin_configuration(username=None, oauth_token=None):
    """
    Get the plugin configuration for Amazon Q Business
    
    Args:
        username: Optional username for OAuth authentication
        oauth_token: Optional OAuth token for OAuth authentication
    
    Returns:
        dict: Plugin configuration for Amazon Q Business
    """
    logger.info(f"Using Jira plugin with ID: f68147f5-0930-44b1-a46a-9f22fc307d4e")
    
    # If OAuth token is provided, use OAuth authentication for Jira
    if username and oauth_token:
        logger.info(f"Using OAuth authentication for Jira with token for user {username}")
        # Create a shorter client token (max 100 chars) from the OAuth token
        # Use a hash of the token to create a unique but shorter identifier
        import hashlib
        client_token = hashlib.sha256(oauth_token.encode()).hexdigest()[:50]  # Use first 50 chars of hash
        
        config = {
            'pluginConfiguration': {
                'plugins': [{
                    'pluginId': 'jira',
                    'status': 'ENABLED',
                    'authentication': {
                        'type': 'OAUTH',
                        'username': username,
                        'clientToken': client_token,
                        'oauthToken': oauth_token  # <-- HERE IS THE TOKEN
                    }
                }]
            }
        }
        logger.info("Plugin configuration created with OAuth token")
        return config
    else:
        # Fallback to basic plugin configuration
        config = {
            'pluginConfiguration': {
                'pluginId': 'f68147f5-0930-44b1-a46a-9f22fc307d4e'
            }
        }
        logger.info("Plugin configuration created with only pluginId (no OAuth token)")
        return config



def query_amazon_q_business_with_plugins(
    credentials: Dict[str, str],
    message: str,
    q_business_application_id: str,
    conversation_id: Optional[str] = None,
    parent_message_id: Optional[str] = None,
    aws_region: str = "us-east-1",
    username: Optional[str] = None,
    oauth_token: Optional[str] = None,
    request_id: Optional[str] = None
):
    """
    Query Amazon Q Business with plugin configuration
    
    Args:
        credentials: AWS credentials (accessKeyId, secretAccessKey, sessionToken)
        message: Message to send to Amazon Q Business
        conversation_id: Conversation ID for continuing conversations
        parent_message_id: Parent message ID for continuing conversations
        aws_region: AWS region
        q_business_application_id: Amazon Q Business application ID
        username: Optional username for OAuth authentication
        oauth_token: Optional OAuth token for OAuth authentication
        
    Returns:
        dict: Response from Amazon Q Business
    """
    try:
        logger.info(f"🔍 DETAILED FLOW: Starting query_amazon_q_business_with_plugins")
        logger.info(f"🔍 DETAILED FLOW: Message length: {len(message)}")
        logger.info(f"🔍 DETAILED FLOW: Username: {username}")
        logger.info(f"🔍 DETAILED FLOW: OAuth token present: {'Yes' if oauth_token else 'No'}")
        logger.info(f"🔍 DETAILED FLOW: OAuth token length: {len(oauth_token) if oauth_token else 0}")
        logger.info(f"🔍 DETAILED FLOW: Request ID: {request_id}")
        logger.info(f"🔍 DETAILED FLOW: Q Business App ID: {q_business_application_id}")
        logger.info(f"🔍 DETAILED FLOW: AWS Region: {aws_region}")
        logger.info(f"🔍 DETAILED FLOW: Conversation ID: {conversation_id}")
        logger.info(f"🔍 DETAILED FLOW: Parent Message ID: {parent_message_id}")
        
        # Create Q Business client with temporary credentials
        logger.info(f"🔍 DETAILED FLOW: Creating Q Business client")
        logger.info(f"🔍 DETAILED FLOW: Access Key ID: {credentials['accessKeyId'][:10]}...")
        logger.info(f"🔍 DETAILED FLOW: Session Token present: {'Yes' if credentials.get('sessionToken') else 'No'}")
        
        qbusiness_client = boto3.client(
            'qbusiness',
            region_name=aws_region,
            aws_access_key_id=credentials['accessKeyId'],
            aws_secret_access_key=credentials['secretAccessKey'],
            aws_session_token=credentials['sessionToken']
        )
        logger.info(f"🔍 DETAILED FLOW: Q Business client created successfully")
        
        # Get plugin configuration with OAuth token
        logger.info(f"🔍 DETAILED FLOW: Getting plugin configuration")
        plugin_config = get_plugin_configuration(username, oauth_token)
        logger.info(f"🔍 DETAILED FLOW: Plugin configuration: {json.dumps(plugin_config, indent=2)}")
        
        # Validate plugin configuration
        if 'pluginConfiguration' not in plugin_config:
            logger.error(f"🔍 DETAILED FLOW: ERROR - No pluginConfiguration in config")
            raise Exception("Invalid plugin configuration - missing pluginConfiguration")
        
        if oauth_token and username:
            if 'plugins' in plugin_config['pluginConfiguration']:
                logger.info(f"🔍 DETAILED FLOW: Using OAuth plugin configuration with {len(plugin_config['pluginConfiguration']['plugins'])} plugins")
                for i, plugin in enumerate(plugin_config['pluginConfiguration']['plugins']):
                    logger.info(f"🔍 DETAILED FLOW: Plugin {i}: {plugin.get('pluginId', 'unknown')}, status: {plugin.get('status', 'unknown')}")
                    if 'authentication' in plugin:
                        auth = plugin['authentication']
                        logger.info(f"🔍 DETAILED FLOW: Auth type: {auth.get('type', 'unknown')}, username: {auth.get('username', 'unknown')}")
                        logger.info(f"🔍 DETAILED FLOW: OAuth token in config: {'Yes' if auth.get('oauthToken') else 'No'}")
            else:
                logger.warning(f"🔍 DETAILED FLOW: WARNING - OAuth token provided but using basic plugin config")
        else:
            logger.info(f"🔍 DETAILED FLOW: Using basic plugin configuration (no OAuth)")
        
        # Prepare the request for Q Business
        logger.info(f"🔍 DETAILED FLOW: Preparing Q Business request parameters")
        request_params = {
            'applicationId': q_business_application_id,
            'userMessage': message,
            'chatMode': 'PLUGIN_MODE',
            'chatModeConfiguration': plugin_config
        }
        logger.info(f"🔍 DETAILED FLOW: Base request params created")
        logger.info(f"🔍 DETAILED FLOW: Application ID: {request_params['applicationId']}")
        logger.info(f"🔍 DETAILED FLOW: Chat Mode: {request_params['chatMode']}")
        logger.info(f"🔍 DETAILED FLOW: User Message: {request_params['userMessage'][:100]}...")
        
        # Add clientToken for session continuity (Amazon Q Business requirement)
        if username:
            logger.info(f"🔍 DETAILED FLOW: Adding clientToken for session continuity")
            # Create extremely unique clientToken to prevent conflicts between concurrent requests
            import uuid
            import secrets
            import threading
            
            # Get current thread ID for additional uniqueness
            thread_id = threading.get_ident()
            unique_id = str(uuid.uuid4()).replace('-', '')[:10]  # 10 chars from UUID
            timestamp = int(time.time() * 1000000)  # Microsecond precision
            random_suffix = secrets.randbelow(90000) + 10000  # Cryptographically secure random 5-digit number
            
            # Include request_id if available for even more uniqueness
            request_suffix = str(hash(request_id))[-4:] if request_id else "0000"
            
            client_token = f"{username[:8]}_{timestamp}_{unique_id}_{random_suffix}_{thread_id}_{request_suffix}"[:50]
            logger.info(f"🔍 DETAILED FLOW: Generated clientToken: {client_token}")
            logger.info(f"🔍 DETAILED FLOW: ClientToken components - username: {username[:8]}, timestamp: {timestamp}, thread: {thread_id}")
            
            request_params['clientToken'] = client_token
        else:
            logger.info(f"🔍 DETAILED FLOW: No username provided, skipping clientToken")
        
        # OAuth token is now passed directly to Amazon Q Business via plugin configuration
        if oauth_token:
            logger.info(f"🔍 DETAILED FLOW: OAuth token passed to Amazon Q Business via plugin configuration")
            logger.info(f"🔍 DETAILED FLOW: OAuth token first 20 chars: {oauth_token[:20]}...")
        else:
            logger.info(f"🔍 DETAILED FLOW: No OAuth token provided")
        
        # Always start fresh conversations to avoid message ID issues
        # Don't add conversationId or parentMessageId
        logger.info(f"🔍 DETAILED FLOW: Using fresh conversation (no conversationId/parentMessageId)")
        
        logger.info(f"🔍 DETAILED FLOW: Final request preparation")
        logger.info(f"🔍 DETAILED FLOW: Using authentication type: {'OAuth' if username and oauth_token else 'Basic'}")
        
        # Generate unique request ID for tracking and conflict prevention
        import uuid
        current_request_id = request_id or f"{int(time.time() * 1000)}_{str(uuid.uuid4())[:8]}_{username}"
        logger.info(f"🔍 DETAILED FLOW: Processing request {current_request_id}")
        
        # Add delay to prevent rapid-fire requests that cause conflicts
        logger.info(f"🔍 DETAILED FLOW: Adding 1 second delay to prevent conflicts")
        time.sleep(1.0)  # 1 second delay to prevent conflicts
        logger.info(f"🔍 DETAILED FLOW: Delay completed, proceeding with Q Business call")
        
        # Call Q Business with retry logic for ConflictException
        max_retries = 3
        retry_delay = 1.0  # Start with 1 second delay
        
        logger.info(f"🔍 DETAILED FLOW: Starting Q Business API call with {max_retries} max retries")
        logger.info(f"🔍 DETAILED FLOW: Final request params keys: {list(request_params.keys())}")
        
        for attempt in range(max_retries):
            try:
                logger.info(f"🔍 DETAILED FLOW: Attempt {attempt + 1}/{max_retries} - Calling Q Business chat_sync")
                logger.info(f"🔍 DETAILED FLOW: Request params for attempt {attempt + 1}:")
                for key, value in request_params.items():
                    if key == 'chatModeConfiguration':
                        logger.info(f"🔍 DETAILED FLOW:   {key}: {json.dumps(value, indent=4)}")
                    elif key == 'userMessage':
                        logger.info(f"🔍 DETAILED FLOW:   {key}: {value[:100]}...")
                    else:
                        logger.info(f"🔍 DETAILED FLOW:   {key}: {value}")
                
                logger.info(f"🔍 DETAILED FLOW: Making chat_sync API call...")
                response = qbusiness_client.chat_sync(**request_params)
                logger.info(f"🔍 DETAILED FLOW: ✅ SUCCESS - Q Business API call completed on attempt {attempt + 1}")
                logger.info(f"🔍 DETAILED FLOW: Response keys: {list(response.keys())}")
                break  # Success, exit retry loop
                
            except Exception as e:
                logger.error(f"🔍 DETAILED FLOW: ❌ ERROR on attempt {attempt + 1}: {str(e)}")
                logger.error(f"🔍 DETAILED FLOW: Error type: {type(e).__name__}")
                
                if "ConflictException" in str(e):
                    logger.warning(f"🔍 DETAILED FLOW: ConflictException detected on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        logger.warning(f"🔍 DETAILED FLOW: Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        # Make clientToken more unique for retry
                        if 'clientToken' in request_params:
                            old_token = request_params['clientToken']
                            request_params['clientToken'] = f"{old_token}_retry_{attempt + 1}"
                            logger.info(f"🔍 DETAILED FLOW: Updated clientToken for retry: {request_params['clientToken']}")
                    else:
                        logger.error(f"🔍 DETAILED FLOW: Max retries reached for ConflictException")
                        raise e
                elif "InternalServerException" in str(e):
                    logger.error(f"🔍 DETAILED FLOW: InternalServerException detected - this is the main error!")
                    logger.error(f"🔍 DETAILED FLOW: Full error details: {str(e)}")
                    raise e
                else:
                    logger.error(f"🔍 DETAILED FLOW: Other exception type, not retrying")
                    raise e
        
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
        
        # No caching needed since we always start fresh conversations
        
        return result
        
    except Exception as e:
        logger.error(f"Error querying Amazon Q Business with plugins: {str(e)}")
        raise Exception(f"Q Business plugin query failed: {str(e)}")

# Jira OAuth URL generation removed - using Confluence Basic Auth only

# Jira OAuth token exchange removed - using Confluence Basic Auth only

# Jira OAuth token storage functions removed - using Confluence Basic Auth only

# Jira OAuth authentication check removed - using Confluence Basic Auth only



def get_auth_status(username: str) -> dict:
    """
    Get the authentication status for a user (Confluence Basic Auth)
    
    Args:
        username: Username
        
    Returns:
        dict: Authentication status
    """
    # For Confluence Basic Auth, check if credentials are configured
    is_authenticated = bool(CONFLUENCE_URL and CONFLUENCE_USERNAME and CONFLUENCE_API_TOKEN)
    
    return {
        "authenticated": is_authenticated,
        "auth_url": None  # No OAuth URL needed for Basic Auth
    }

def refresh_token_if_needed(username: str) -> bool:
    """
    Refresh the token if it's expired or about to expire
    
    Args:
        username: Username
        
    Returns:
        bool: True if token was refreshed, False otherwise
    """
    token_data = get_user_token(username)
    if not token_data or "refresh_token" not in token_data:
        return False
    
    # In a real implementation, you would check if the token is expired
    # For now, we'll assume it's not expired
    
    # If needed, refresh the token
    # new_token_data = refresh_atlassian_token(token_data["refresh_token"])
    # store_user_token(username, new_token_data)
    # return True
    
    return False

# Jira OAuth popup URL generation removed - using Confluence Basic Auth only

# Jira OAuth callback handler removed - using Confluence Basic Auth only

# Jira connection test removed - using Confluence Basic Auth only

def test_confluence_connection():
    """
    Test Confluence connection with API token
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        auth = (CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN)
        
        # Get spaces
        response = requests.get(f"{CONFLUENCE_URL}/wiki/rest/api/space", auth=auth, timeout=(30, 300))
        response.raise_for_status()
        
        return True
    
    except Exception as e:
        logger.error(f"Error testing Confluence connection: {str(e)}")
        return False

def get_jira_projects(access_token: str) -> List[Dict[str, Any]]:
    """
    Get list of Jira projects accessible to the user
    
    Args:
        access_token: Jira access token
        
    Returns:
        List of Jira projects
    """
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        # First get accessible resources
        response = requests.get("https://api.atlassian.com/oauth/token/accessible-resources", headers=headers, timeout=(30, 300))
        response.raise_for_status()
        
        resources = response.json()
        if not resources:
            logger.error("No accessible Jira resources found")
            return []
        
        # Use the first cloud resource
        cloud_id = resources[0]["id"]
        
        # Get projects
        projects_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/project"
        response = requests.get(projects_url, headers=headers, timeout=(30, 300))
        response.raise_for_status()
        
        return response.json()
    
    except Exception as e:
        logger.error(f"Error getting Jira projects: {str(e)}")
        return []

def get_confluence_spaces(username: str, api_token: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Get list of Confluence spaces accessible to the user
    
    Args:
        username: Confluence username
        api_token: Confluence API token
        base_url: Confluence base URL
        
    Returns:
        List of Confluence spaces
    """
    try:
        auth = (username, api_token)
        
        # Get spaces
        response = requests.get(f"{base_url}/wiki/rest/api/space", auth=auth, timeout=(30, 300))
        response.raise_for_status()
        
        return response.json().get("results", [])
    
    except Exception as e:
        logger.error(f"Error getting Confluence spaces: {str(e)}")
        return []

def create_jira_issue_direct(
    access_token: str, 
    project_key: str, 
    summary: str, 
    description: str, 
    issue_type: str = "Bug"
) -> Dict[str, Any]:
    """
    Create a Jira issue directly using the Jira API
    
    Args:
        access_token: Jira access token
        project_key: Jira project key
        summary: Issue summary
        description: Issue description
        issue_type: Issue type
        
    Returns:
        Created issue data
    """
    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # First get accessible resources
        response = requests.get("https://api.atlassian.com/oauth/token/accessible-resources", headers=headers, timeout=(30, 300))
        response.raise_for_status()
        
        resources = response.json()
        if not resources:
            raise Exception("No accessible Jira resources found")
        
        # Use the first cloud resource
        cloud_id = resources[0]["id"]
        
        # Create issue
        issue_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/issue"
        
        # Prepare issue data
        issue_data = {
            "fields": {
                "project": {
                    "key": project_key
                },
                "summary": summary,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [
                                {
                                    "type": "text",
                                    "text": description
                                }
                            ]
                        }
                    ]
                },
                "issuetype": {
                    "name": issue_type
                }
            }
        }
        
        response = requests.post(issue_url, headers=headers, json=issue_data, timeout=(30, 300))
        response.raise_for_status()
        
        return response.json()
    
    except Exception as e:
        logger.error(f"Error creating Jira issue: {str(e)}")
        raise Exception(f"Failed to create Jira issue: {str(e)}")

def search_confluence_content(
    username: str, 
    api_token: str, 
    base_url: str, 
    query: str, 
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search Confluence content
    
    Args:
        username: Confluence username
        api_token: Confluence API token
        base_url: Confluence base URL
        query: Search query
        limit: Maximum number of results
        
    Returns:
        List of search results
    """
    try:
        auth = (username, api_token)
        
        # URL encode the query
        encoded_query = urllib.parse.quote(query)
        
        # Search content
        search_url = f"{base_url}/wiki/rest/api/content/search?cql=text~\"{encoded_query}\"&limit={limit}"
        response = requests.get(search_url, auth=auth, timeout=(30, 300))
        response.raise_for_status()
        
        return response.json().get("results", [])
    
    except Exception as e:
        logger.error(f"Error searching Confluence content: {str(e)}")
        return []

def refresh_atlassian_token(refresh_token: str) -> Dict[str, Any]:
    """
    Refresh Atlassian access token
    
    Args:
        refresh_token: Refresh token
        
    Returns:
        New token data
    """
    try:
        payload = {
            "grant_type": "refresh_token",
            "client_id": JIRA_CLIENT_ID,
            "client_secret": JIRA_CLIENT_SECRET,
            "refresh_token": refresh_token
        }
        
        response = requests.post(JIRA_ACCESS_TOKEN_URL, data=payload, timeout=(30, 300))
        response.raise_for_status()
        
        return response.json()
    
    except Exception as e:
        logger.error(f"Error refreshing Atlassian token: {str(e)}")
        raise Exception(f"Token refresh failed: {str(e)}")

# All Jira OAuth server functions removed - using Confluence Basic Auth only

# Export functions for use in MCP server - Confluence Basic Auth only
__all__ = [
    "query_amazon_q_business_with_plugins",
    "get_auth_status", 
    "refresh_token_if_needed",
    "test_confluence_connection",
    "get_confluence_spaces",
    "search_confluence_content"
]