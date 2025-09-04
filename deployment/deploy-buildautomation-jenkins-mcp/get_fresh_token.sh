#!/bin/bash

# Jenkins MCP Server - Get Fresh OAuth Token Script

set -e

echo "🔑 Getting fresh OAuth token for Jenkins MCP Server..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is required but not installed."
    exit 1
fi

# Check if required environment variables are set
if [ -z "$OAUTH_API_URL" ]; then
    echo "⚠️  OAUTH_API_URL not set. Checking .env file..."
    if [ -f .env ]; then
        source .env
    fi
    
    if [ -z "$OAUTH_API_URL" ]; then
        echo "❌ Error: OAUTH_API_URL is not configured."
        echo "Please set it in your .env file or environment variables."
        echo "Example: OAUTH_API_URL=https://your-oauth-api-gateway-url.amazonaws.com/dev/"
        exit 1
    fi
fi

echo "🌐 Using OAuth API URL: $OAUTH_API_URL"

# Run the token configuration test
echo "🔄 Requesting fresh OAuth token..."
python3 -c "
import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, '.')

from token_config import test_token_flow

async def main():
    success = await test_token_flow()
    if success:
        print('✅ Fresh OAuth token obtained successfully!')
        print('🚀 You can now start Amazon Q and use the Jenkins MCP server.')
        return 0
    else:
        print('❌ Failed to obtain OAuth token.')
        print('Please check your configuration and try again.')
        return 1

exit_code = asyncio.run(main())
sys.exit(exit_code)
"

exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "🎉 Success! Your Jenkins MCP server is ready to use."
    echo ""
    echo "Next steps:"
    echo "1. Start Amazon Q: q chat"
    echo "2. Try Jenkins commands like:"
    echo "   - 'Check Jenkins server health'"
    echo "   - 'List all Jenkins jobs'"
    echo "   - 'Trigger a build for job-name'"
    echo ""
else
    echo ""
    echo "❌ Token acquisition failed. Please check:"
    echo "1. Your OAUTH_API_URL is correct"
    echo "2. Your AWS deployment is working"
    echo "3. Your network connection"
    echo ""
    echo "For debugging, check the logs:"
    echo "aws logs tail /aws/lambda/jenkins-mcp-oauth-server-dev --follow"
fi

exit $exit_code
