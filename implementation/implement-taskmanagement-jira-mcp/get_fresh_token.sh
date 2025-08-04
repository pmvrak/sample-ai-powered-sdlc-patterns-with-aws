#!/bin/bash
# Simple script to get a fresh JIRA MCP OAuth token

echo "🔄 Getting fresh JIRA MCP OAuth token..."

# Step 1: Register client
CLIENT_ID=$(curl -s -X POST https://15n9kzprcd.execute-api.us-east-1.amazonaws.com/dev/register \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris": ["https://example.com/callback"], "client_name": "JIRA MCP Token Refresh", "scope": "mcp:read mcp:write"}' | jq -r '.client_id')

echo "✅ Registered client: $CLIENT_ID"

# Step 2: Generate PKCE
CODE_VERIFIER=$(python3 -c "import base64, secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('='))")
CODE_CHALLENGE=$(python3 -c "import base64, hashlib; print(base64.urlsafe_b64encode(hashlib.sha256('$CODE_VERIFIER'.encode()).digest()).decode('utf-8').rstrip('='))")

echo "✅ Generated PKCE challenge"

# Step 3: Get authorization code
AUTH_CODE=$(curl -s "https://15n9kzprcd.execute-api.us-east-1.amazonaws.com/dev/authorize?response_type=code&client_id=$CLIENT_ID&redirect_uri=https://example.com/callback&scope=mcp:read%20mcp:write&code_challenge=$CODE_CHALLENGE&code_challenge_method=S256&state=refresh" | grep -o 'code=[^&"]*' | cut -d= -f2 | head -1)

echo "✅ Got authorization code: ${AUTH_CODE:0:10}..."

# Step 4: Exchange for access token
ACCESS_TOKEN=$(curl -s -X POST https://15n9kzprcd.execute-api.us-east-1.amazonaws.com/dev/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code&code=$AUTH_CODE&redirect_uri=https://example.com/callback&client_id=$CLIENT_ID&code_verifier=$CODE_VERIFIER" | jq -r '.access_token')

echo "✅ Got fresh access token: ${ACCESS_TOKEN:0:10}..."

# Step 5: Update the working MCP server
sed -i.bak "s/ACCESS_TOKEN = \".*\"/ACCESS_TOKEN = \"$ACCESS_TOKEN\"/" proxy_jira_mcp.py

echo "✅ Updated proxy_jira_mcp.py with fresh token"
echo "🎉 Token refresh complete! Your JIRA MCP server is ready."
echo ""
echo "💡 This token will expire in 1 hour. Run this script again when needed."
