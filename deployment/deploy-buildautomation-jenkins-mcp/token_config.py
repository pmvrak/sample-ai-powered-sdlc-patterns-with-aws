#!/usr/bin/env python3
"""
OAuth Token Configuration for Jenkins MCP Server
Handles OAuth token management and refresh logic
"""

import asyncio
import aiohttp
import json
import logging
import os
import time
from typing import Optional, Dict, Any
import hashlib
import base64
import secrets
import urllib.parse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
OAUTH_API_URL = os.getenv('OAUTH_API_URL', 'https://your-oauth-api-gateway-url.amazonaws.com/dev/')
TOKEN_FILE = os.path.expanduser('~/.jenkins_mcp_token.json')

class TokenManager:
    """Manages OAuth tokens for Jenkins MCP Server"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._token_cache: Optional[Dict[str, Any]] = None
    
    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def cleanup(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()
    
    def _load_token_from_file(self) -> Optional[Dict[str, Any]]:
        """Load token from local file"""
        try:
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'r') as f:
                    token_data = json.load(f)
                    logger.info("Loaded token from file")
                    return token_data
        except Exception as e:
            logger.warning(f"Failed to load token from file: {str(e)}")
        return None
    
    def _save_token_to_file(self, token_data: Dict[str, Any]):
        """Save token to local file"""
        try:
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            with open(TOKEN_FILE, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.info("Saved token to file")
        except Exception as e:
            logger.error(f"Failed to save token to file: {str(e)}")
    
    def _is_token_expired(self, token_data: Dict[str, Any]) -> bool:
        """Check if token is expired"""
        expires_at = token_data.get('expires_at', 0)
        current_time = time.time()
        # Add 60 second buffer
        return current_time >= (expires_at - 60)
    
    async def register_oauth_client(self) -> Dict[str, Any]:
        """Register OAuth client with the server"""
        try:
            session = await self.get_session()
            
            # Generate client registration data
            client_data = {
                "redirect_uris": ["https://example.com/callback"],
                "client_name": "Jenkins MCP Client",
                "client_uri": "https://github.com/aws-samples/jenkins-mcp-server",
                "scope": "jenkins:read jenkins:write"
            }
            
            register_url = f"{OAUTH_API_URL.rstrip('/')}/register"
            
            async with session.post(
                register_url,
                json=client_data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                
                if response.status not in [200, 201]:
                    error_text = await response.text()
                    raise Exception(f"Client registration failed: {response.status} - {error_text}")
                
                client_info = await response.json()
                logger.info("Successfully registered OAuth client")
                return client_info
                
        except Exception as e:
            logger.error(f"OAuth client registration failed: {str(e)}")
            raise
    
    def _generate_pkce_challenge(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge"""
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # Generate code challenge
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    async def get_oauth_token(self, force_refresh: bool = False) -> Optional[str]:
        """Get OAuth token, refreshing if necessary"""
        try:
            # Check cache first
            if not force_refresh and self._token_cache:
                if not self._is_token_expired(self._token_cache):
                    return self._token_cache.get('access_token')
            
            # Load from file
            token_data = self._load_token_from_file()
            
            if token_data and not force_refresh:
                if not self._is_token_expired(token_data):
                    self._token_cache = token_data
                    return token_data.get('access_token')
                
                # Try to refresh token
                if 'refresh_token' in token_data:
                    refreshed_token = await self._refresh_token(token_data)
                    if refreshed_token:
                        return refreshed_token.get('access_token')
            
            # Get new token via PKCE flow
            new_token = await self._get_new_token()
            if new_token:
                self._token_cache = new_token
                self._save_token_to_file(new_token)
                return new_token.get('access_token')
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get OAuth token: {str(e)}")
            return None
    
    async def _refresh_token(self, token_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Refresh OAuth token"""
        try:
            session = await self.get_session()
            refresh_token = token_data.get('refresh_token')
            client_id = token_data.get('client_id')
            
            if not refresh_token or not client_id:
                logger.warning("Missing refresh token or client ID")
                return None
            
            token_url = f"{OAUTH_API_URL.rstrip('/')}/token"
            
            data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'client_id': client_id
            }
            
            async with session.post(
                token_url,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                
                if response.status != 200:
                    logger.warning(f"Token refresh failed: {response.status}")
                    return None
                
                new_token_data = await response.json()
                
                # Update token data
                new_token_data['client_id'] = client_id
                new_token_data['expires_at'] = time.time() + new_token_data.get('expires_in', 3600)
                
                logger.info("Successfully refreshed OAuth token")
                return new_token_data
                
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            return None
    
    async def _get_new_token(self) -> Optional[Dict[str, Any]]:
        """Get new OAuth token via PKCE flow"""
        try:
            # Register client
            client_info = await self.register_oauth_client()
            client_id = client_info.get('client_id')
            
            if not client_id:
                raise Exception("Failed to get client ID from registration")
            
            # Generate PKCE challenge
            code_verifier, code_challenge = self._generate_pkce_challenge()
            
            session = await self.get_session()
            
            # Step 1: Get authorization code via automated flow
            auth_url = f"{OAUTH_API_URL.rstrip('/')}/authorize"
            
            auth_params = {
                'response_type': 'code',
                'client_id': client_id,
                'redirect_uri': 'https://example.com/callback',
                'scope': 'jenkins:read jenkins:write',
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256',
                'state': secrets.token_urlsafe(32)
            }
            
            # For automated testing, simulate the authorization flow
            # In production, this would require user interaction
            auth_query = urllib.parse.urlencode(auth_params)
            full_auth_url = f"{auth_url}?{auth_query}"
            
            # Simulate getting authorization code (this is a simplified approach)
            # In a real scenario, the user would visit the auth URL and get redirected
            async with session.get(full_auth_url, allow_redirects=False) as auth_response:
                if auth_response.status == 302:
                    # Extract code from redirect location
                    location = auth_response.headers.get('Location', '')
                    if 'code=' in location:
                        parsed_url = urllib.parse.urlparse(location)
                        query_params = urllib.parse.parse_qs(parsed_url.query)
                        auth_code = query_params.get('code', [None])[0]
                    else:
                        # Try to get code from response body for testing
                        response_text = await auth_response.text()
                        if 'authorization_code' in response_text:
                            import re
                            match = re.search(r'"authorization_code":\s*"([^"]+)"', response_text)
                            auth_code = match.group(1) if match else None
                        else:
                            auth_code = None
                else:
                    # Check if the response contains the code directly (for testing)
                    response_data = await auth_response.json()
                    auth_code = response_data.get('authorization_code')
            
            if not auth_code:
                raise Exception("Failed to obtain authorization code")
            
            # Step 2: Exchange authorization code for access token
            token_url = f"{OAUTH_API_URL.rstrip('/')}/token"
            
            token_data = {
                'grant_type': 'authorization_code',
                'code': auth_code,
                'redirect_uri': 'https://example.com/callback',
                'client_id': client_id,
                'code_verifier': code_verifier
            }
            
            async with session.post(
                token_url,
                data=token_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Token request failed: {response.status} - {error_text}")
                
                token_response = await response.json()
                
                # Add metadata
                token_response['client_id'] = client_id
                token_response['expires_at'] = time.time() + token_response.get('expires_in', 3600)
                token_response['obtained_at'] = time.time()
                
                logger.info("Successfully obtained new OAuth token")
                return token_response
                
        except Exception as e:
            logger.error(f"Failed to get new token: {str(e)}")
            return None

# Global token manager instance
_token_manager = TokenManager()

async def get_oauth_token() -> Optional[str]:
    """Get OAuth token (convenience function)"""
    return await _token_manager.get_oauth_token()

async def refresh_oauth_token_if_needed(current_token: str, force_refresh: bool = False) -> str:
    """Refresh OAuth token if needed"""
    try:
        new_token = await _token_manager.get_oauth_token(force_refresh=force_refresh)
        return new_token if new_token else current_token
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        return current_token

async def cleanup_token_manager():
    """Clean up token manager resources"""
    await _token_manager.cleanup()

# Test function
async def test_token_flow():
    """Test the OAuth token flow"""
    try:
        logger.info("Testing OAuth token flow...")
        token = await get_oauth_token()
        
        if token:
            logger.info("✅ Successfully obtained OAuth token")
            logger.info(f"Token (first 20 chars): {token[:20]}...")
        else:
            logger.error("❌ Failed to obtain OAuth token")
        
        return token is not None
        
    except Exception as e:
        logger.error(f"Token flow test failed: {str(e)}")
        return False
    finally:
        await cleanup_token_manager()

if __name__ == "__main__":
    # Test the token flow
    asyncio.run(test_token_flow())
