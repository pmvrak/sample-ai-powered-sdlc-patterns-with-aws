#!/usr/bin/env python3
"""
OAuth Authorization Server for MCP Authentication
Implements RFC 8414, RFC 7591, RFC 7636 (PKCE), and RFC 9728
"""

import json
import os
import uuid
import hashlib
import base64
import time
from typing import Dict, Any, Optional
import boto3
from urllib.parse import parse_qs, urlencode, urlparse

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('DYNAMODB_TABLE', 'oauth-clients'))

class MCPOAuthServer:
    def __init__(self):
        self.environment = os.environ.get('ENVIRONMENT', 'dev')
        self.mcp_server_url = os.environ.get('MCP_SERVER_URL', '')
        self.oauth_issuer = os.environ.get('OAUTH_ISSUER', '')
        
    def handle_authorization_server_metadata(self) -> Dict[str, Any]:
        """
        RFC 8414: OAuth 2.0 Authorization Server Metadata
        Returns metadata about the OAuth authorization server
        """
        return {
            "issuer": self.oauth_issuer,
            "authorization_endpoint": f"{self.oauth_issuer}/authorize",
            "token_endpoint": f"{self.oauth_issuer}/token",
            "registration_endpoint": f"{self.oauth_issuer}/register",
            "introspection_endpoint": f"{self.oauth_issuer}/introspect",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
            "scopes_supported": ["mcp:read", "mcp:write"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"]
        }
    
    def handle_dynamic_client_registration(self, request_body: str) -> Dict[str, Any]:
        """
        RFC 7591: OAuth 2.0 Dynamic Client Registration Protocol
        Registers a new OAuth client dynamically
        """
        try:
            registration_request = json.loads(request_body)
        except json.JSONDecodeError:
            return self._error_response("invalid_request", "Invalid JSON in request body")
        
        # Validate required fields
        redirect_uris = registration_request.get('redirect_uris', [])
        if not redirect_uris:
            return self._error_response("invalid_redirect_uri", "redirect_uris is required")
        
        # Generate client credentials
        client_id = str(uuid.uuid4())
        client_secret = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
        
        # Store client registration
        client_data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uris': redirect_uris,
            'grant_types': registration_request.get('grant_types', ['authorization_code']),
            'response_types': registration_request.get('response_types', ['code']),
            'scope': registration_request.get('scope', 'mcp:read mcp:write'),
            'client_name': registration_request.get('client_name', 'MCP Client'),
            'created_at': int(time.time()),
            'expires_at': int(time.time()) + (30 * 24 * 60 * 60)  # 30 days
        }
        
        # Store in DynamoDB
        table.put_item(Item=client_data)
        
        # Return client registration response
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": redirect_uris,
            "grant_types": client_data['grant_types'],
            "response_types": client_data['response_types'],
            "client_name": client_data['client_name'],
            "scope": client_data['scope']
        }
    
    def handle_authorization_request(self, query_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        OAuth 2.0 Authorization Request with PKCE
        """
        # Extract parameters
        client_id = query_params.get('client_id', [''])[0]
        redirect_uri = query_params.get('redirect_uri', [''])[0]
        response_type = query_params.get('response_type', [''])[0]
        scope = query_params.get('scope', [''])[0]
        state = query_params.get('state', [''])[0]
        code_challenge = query_params.get('code_challenge', [''])[0]
        code_challenge_method = query_params.get('code_challenge_method', [''])[0]
        
        # Validate client
        try:
            response = table.get_item(Key={'client_id': client_id})
            if 'Item' not in response:
                return self._error_response("invalid_client", "Client not found")
            
            client = response['Item']
        except Exception as e:
            return self._error_response("server_error", f"Database error: {str(e)}")
        
        # Validate redirect URI
        if redirect_uri not in client['redirect_uris']:
            return self._error_response("invalid_request", "Invalid redirect_uri")
        
        # Validate PKCE (RFC 7636)
        if not code_challenge or code_challenge_method != 'S256':
            return self._error_response("invalid_request", "PKCE required with S256 method")
        
        # Generate authorization code
        auth_code = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
        
        # Store authorization code with PKCE challenge
        auth_data = {
            'client_id': f"auth_code_{auth_code}",
            'code': auth_code,
            'client_id_original': client_id,
            'redirect_uri': redirect_uri,
            'scope': scope,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method,
            'created_at': int(time.time()),
            'expires_at': int(time.time()) + 600  # 10 minutes
        }
        
        table.put_item(Item=auth_data)
        
        # For demo purposes, auto-approve (in production, redirect to consent page)
        redirect_url = f"{redirect_uri}?code={auth_code}"
        if state:
            redirect_url += f"&state={state}"
        
        return {
            "statusCode": 302,
            "headers": {
                "Location": redirect_url,
                "Content-Type": "text/html"
            },
            "body": f'<html><body>Redirecting to <a href="{redirect_url}">{redirect_url}</a></body></html>'
        }
    
    def handle_token_request(self, request_body: str, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        OAuth 2.0 Token Request with PKCE verification
        """
        try:
            # Parse form data - handle both string and bytes
            if isinstance(request_body, bytes):
                request_body = request_body.decode('utf-8')
            
            # Parse URL-encoded form data
            from urllib.parse import parse_qs
            params = parse_qs(request_body)
            
            # Extract parameters (parse_qs returns lists, so get first item)
            grant_type = params.get('grant_type', [''])[0]
            code = params.get('code', [''])[0]
            redirect_uri = params.get('redirect_uri', [''])[0]
            client_id = params.get('client_id', [''])[0]
            code_verifier = params.get('code_verifier', [''])[0]
            
            print(f"Token request - grant_type: {grant_type}, code: {code[:10]}..., client_id: {client_id}")
            
            if grant_type != 'authorization_code':
                return self._error_response("unsupported_grant_type", "Only authorization_code supported")
            
            if not all([code, redirect_uri, client_id, code_verifier]):
                return self._error_response("invalid_request", "Missing required parameters")
            
            # Retrieve authorization code
            try:
                response = table.get_item(Key={'client_id': f"auth_code_{code}"})
                if 'Item' not in response:
                    return self._error_response("invalid_grant", "Authorization code not found")
                
                auth_data = response['Item']
                print(f"Found auth data for code: {code[:10]}...")
            except Exception as e:
                print(f"Database error: {e}")
                return self._error_response("server_error", f"Database error: {str(e)}")
            
            # Verify PKCE code verifier (RFC 7636)
            if not self._verify_pkce(code_verifier, auth_data['code_challenge']):
                return self._error_response("invalid_grant", "PKCE verification failed")
            
            # Verify client and redirect URI
            if (client_id != auth_data['client_id_original'] or 
                redirect_uri != auth_data['redirect_uri']):
                return self._error_response("invalid_grant", "Client or redirect URI mismatch")
            
            # Generate access token
            access_token = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').rstrip('=')
            
            # Store access token
            token_data = {
                'client_id': f"access_token_{access_token}",
                'access_token': access_token,
                'client_id_original': client_id,
                'scope': auth_data['scope'],
                'created_at': int(time.time()),
                'expires_at': int(time.time()) + 3600  # 1 hour
            }
            
            table.put_item(Item=token_data)
            print(f"Generated access token for client: {client_id}")
            
            # Delete authorization code (one-time use)
            table.delete_item(Key={'client_id': f"auth_code_{code}"})
            
            return {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": auth_data['scope']
            }
            
        except Exception as e:
            print(f"Token generation error: {e}")
            return self._error_response("server_error", f"Token generation error: {str(e)}")
    
    def handle_token_introspection(self, request_body: str) -> Dict[str, Any]:
        """
        RFC 7662: OAuth 2.0 Token Introspection
        """
        try:
            # Parse form data - handle both string and bytes
            if isinstance(request_body, bytes):
                request_body = request_body.decode('utf-8')
            
            from urllib.parse import parse_qs
            params = parse_qs(request_body)
            token = params.get('token', [''])[0]
            
            print(f"Introspecting token: {token[:10]}...")
            
            if not token:
                return {"active": False}
            
            # Look up token
            try:
                response = table.get_item(Key={'client_id': f"access_token_{token}"})
                if 'Item' not in response:
                    print(f"Token not found in database")
                    return {"active": False}
                
                token_data = response['Item']
                print(f"Found token data: {token_data.get('client_id_original', 'unknown')}")
            except Exception as e:
                print(f"Database error during introspection: {e}")
                return {"active": False}
            
            # Check if token is expired
            expires_at = int(token_data['expires_at'])  # Convert Decimal to int
            created_at = int(token_data['created_at'])  # Convert Decimal to int
            
            if int(time.time()) > expires_at:
                print(f"Token expired")
                return {"active": False}
            
            return {
                "active": True,
                "client_id": str(token_data['client_id_original']),
                "scope": str(token_data['scope']),
                "exp": expires_at,
                "iat": created_at
            }
            
        except Exception as e:
            print(f"Introspection error: {e}")
            return {"active": False}
    
    def _verify_pkce(self, code_verifier: str, code_challenge: str) -> bool:
        """Verify PKCE code challenge"""
        if not code_verifier or not code_challenge:
            return False
        
        # S256: code_challenge = BASE64URL(SHA256(code_verifier))
        verifier_hash = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        expected_challenge = base64.urlsafe_b64encode(verifier_hash).decode('utf-8').rstrip('=')
        
        return expected_challenge == code_challenge
    
    def _error_response(self, error: str, description: str) -> Dict[str, Any]:
        """Generate OAuth error response"""
        return {
            "error": error,
            "error_description": description
        }

def lambda_handler(event, context):
    """AWS Lambda handler for OAuth Authorization Server"""
    try:
        oauth_server = MCPOAuthServer()
        
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'GET')
        path = event.get('path') or event.get('rawPath', '/')
        query_params = event.get('queryStringParameters') or {}
        headers = event.get('headers', {})
        body = event.get('body', '')
        
        # Handle base64 encoded body
        if event.get('isBase64Encoded', False) and body:
            import base64
            body = base64.b64decode(body).decode('utf-8')
        
        # Remove stage prefix if present
        if path.startswith('/dev'):
            path = path[4:] or '/'
        
        print(f"OAuth Request: {http_method} {path}")
        print(f"Body: {body[:100]}..." if body else "No body")
        
        # Convert query params to expected format
        if query_params:
            formatted_params = {}
            for key, value in query_params.items():
                formatted_params[key] = [value] if isinstance(value, str) else value
            query_params = formatted_params
        
        # Route requests
        if path == '/.well-known/oauth-authorization-server' and http_method == 'GET':
            result = oauth_server.handle_authorization_server_metadata()
            
        elif path == '/register' and http_method == 'POST':
            result = oauth_server.handle_dynamic_client_registration(body)
            
        elif path == '/authorize' and http_method == 'GET':
            result = oauth_server.handle_authorization_request(query_params)
            # Handle redirect response
            if 'statusCode' in result:
                return result
                
        elif path == '/token' and http_method == 'POST':
            result = oauth_server.handle_token_request(body, headers)
            
        elif path == '/introspect' and http_method == 'POST':
            result = oauth_server.handle_token_introspection(body)
            
        elif path == '/introspect' and http_method == 'POST':
            result = oauth_server.handle_token_introspection(body)
            
        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'not_found', 'error_description': 'Endpoint not found'})
            }
        
        # Handle error responses
        if 'error' in result:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(result)
            }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps(result)
        }
        
    except Exception as e:
        print(f"OAuth server error: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'server_error',
                'error_description': 'Internal server error'
            })
        }
