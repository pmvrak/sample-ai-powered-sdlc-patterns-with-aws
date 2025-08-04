#!/bin/bash
# Refresh token and start Amazon Q

echo "🔄 Refreshing JIRA MCP OAuth token..."

# Get fresh token
./get_fresh_token.sh

if [ $? -eq 0 ]; then
    echo "✅ Token refreshed successfully!"
    echo "🚀 Starting Amazon Q..."
    q chat
else
    echo "❌ Token refresh failed. Please check your setup."
    exit 1
fi
