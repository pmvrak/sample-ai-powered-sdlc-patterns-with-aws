#!/bin/bash

# Jenkins MCP Server - Refresh Token and Start Amazon Q Script

set -e

echo "🚀 Jenkins MCP Server - Refresh and Start"
echo "========================================"

# Get fresh OAuth token
echo "🔑 Step 1: Getting fresh OAuth token..."
./get_fresh_token.sh

if [ $? -ne 0 ]; then
    echo "❌ Failed to get OAuth token. Please check your configuration."
    exit 1
fi

echo ""
echo "🎯 Step 2: Starting Amazon Q Developer..."
echo ""
echo "You can now use Jenkins commands like:"
echo "  • 'Check Jenkins server health'"
echo "  • 'List all Jenkins jobs'"
echo "  • 'Show me details for job my-app-build'"
echo "  • 'Trigger a build for my-app-build'"
echo "  • 'Get the console log for build #42 of my-app-build'"
echo "  • 'Create a new job called test-job that runs npm test'"
echo "  • 'Show me the current build queue'"
echo ""

# Start Amazon Q
exec q chat
