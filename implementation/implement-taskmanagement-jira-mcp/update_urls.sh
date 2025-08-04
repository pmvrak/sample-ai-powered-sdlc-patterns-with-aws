#!/bin/bash
set -e

echo "🔄 Updating API Gateway URLs after deployment..."

# Get the deployed API Gateway URLs from CDK outputs
echo "📡 Getting OAuth server URL..."
OAUTH_URL=$(aws cloudformation describe-stacks --stack-name JiraMcpOAuthStack-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`OAuthApiEndpoint`].OutputValue' --output text)

echo "📡 Getting MCP server URL..."
MCP_URL=$(aws cloudformation describe-stacks --stack-name JiraMcpServerStack-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`McpApiEndpoint`].OutputValue' --output text)

if [ -z "$OAUTH_URL" ] || [ -z "$MCP_URL" ]; then
    echo "❌ Error: Could not retrieve API Gateway URLs from CloudFormation"
    echo "   Make sure the CDK stacks are deployed successfully"
    exit 1
fi

echo "✅ Retrieved URLs:"
echo "   OAuth Server: $OAUTH_URL"
echo "   MCP Server: $MCP_URL"

# Update proxy_jira_mcp.py
echo "📝 Updating proxy_jira_mcp.py..."
if [ -f "proxy_jira_mcp.py" ]; then
    # Remove trailing slash and add /dev if not present
    MCP_URL_CLEAN=$(echo "$MCP_URL" | sed 's/\/$//')
    if [[ ! "$MCP_URL_CLEAN" == *"/dev" ]]; then
        MCP_URL_CLEAN="${MCP_URL_CLEAN}/dev"
    fi
    
    sed -i.bak "s|MCP_SERVER_URL = \".*\"|MCP_SERVER_URL = \"$MCP_URL_CLEAN\"|" proxy_jira_mcp.py
    echo "   ✅ Updated proxy_jira_mcp.py"
else
    echo "   ⚠️  proxy_jira_mcp.py not found"
fi

# Update get_fresh_token.sh
echo "📝 Updating get_fresh_token.sh..."
if [ -f "get_fresh_token.sh" ]; then
    # Remove trailing slash and add dev if not present
    OAUTH_URL_CLEAN=$(echo "$OAUTH_URL" | sed 's/\/$//')
    if [[ ! "$OAUTH_URL_CLEAN" == *"/dev" ]]; then
        OAUTH_URL_CLEAN="${OAUTH_URL_CLEAN}/dev"
    fi
    
    # Update the OAuth URLs in get_fresh_token.sh
    sed -i.bak "s|https://[^/]*\.execute-api\.[^/]*\.amazonaws\.com/dev|$OAUTH_URL_CLEAN|g" get_fresh_token.sh
    echo "   ✅ Updated get_fresh_token.sh"
else
    echo "   ⚠️  get_fresh_token.sh not found"
fi

echo ""
echo "🎉 URL update completed!"
echo ""
echo "📋 Next steps:"
echo "   1. Get fresh OAuth token: ./get_fresh_token.sh"
echo "   2. Start Amazon Q: q chat"
echo ""
echo "🔗 Your API Gateway URLs:"
echo "   OAuth Server: $OAUTH_URL_CLEAN"
echo "   MCP Server: $MCP_URL_CLEAN"
