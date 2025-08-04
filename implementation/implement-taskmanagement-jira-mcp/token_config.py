#!/usr/bin/env python3
"""
Token Configuration Manager
Stores and manages OAuth tokens with automatic refresh
"""

import json
import os
import time
from pathlib import Path

class TokenConfig:
    def __init__(self):
        self.config_file = Path.home() / '.jira_mcp_token.json'
        self.config = self.load_config()
    
    def load_config(self):
        """Load token configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            'access_token': None,
            'expires_at': 0,
            'client_id': None
        }
    
    def save_config(self):
        """Save token configuration to file"""
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def set_token(self, access_token: str, expires_in: int = 3600):
        """Set new access token"""
        self.config['access_token'] = access_token
        self.config['expires_at'] = time.time() + expires_in
        self.save_config()
        print(f"✅ Token saved: {access_token[:10]}... (expires in {expires_in//60} minutes)")
    
    def get_token(self):
        """Get current token if valid"""
        if self.config['access_token'] and time.time() < self.config['expires_at']:
            return self.config['access_token']
        return None
    
    def is_expired(self):
        """Check if token is expired"""
        return time.time() >= self.config['expires_at']

if __name__ == "__main__":
    import sys
    
    config = TokenConfig()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == 'set' and len(sys.argv) > 2:
            # Set new token
            token = sys.argv[2]
            expires_in = int(sys.argv[3]) if len(sys.argv) > 3 else 3600
            config.set_token(token, expires_in)
        elif sys.argv[1] == 'get':
            # Get current token
            token = config.get_token()
            if token:
                print(token)
            else:
                print("No valid token available", file=sys.stderr)
                sys.exit(1)
        elif sys.argv[1] == 'status':
            # Show token status
            token = config.get_token()
            if token:
                remaining = int(config.config['expires_at'] - time.time())
                print(f"✅ Valid token: {token[:10]}... (expires in {remaining//60} minutes)")
            else:
                print("❌ No valid token available")
    else:
        print("Usage:")
        print("  python3 token_config.py set <token> [expires_in_seconds]")
        print("  python3 token_config.py get")
        print("  python3 token_config.py status")
