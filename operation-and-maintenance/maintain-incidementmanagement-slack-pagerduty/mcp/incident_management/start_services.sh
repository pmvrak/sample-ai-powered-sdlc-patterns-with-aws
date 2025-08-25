#!/bin/bash

# Start incident management service with stdio MCP integration

set -e

echo "🚀 Starting Incident Management Service"
echo "======================================="

# Set up environment for both services
export PYTHONPATH=/app:/home/appuser/.local/lib/python3.12/site-packages
export PATH=/home/appuser/.local/bin:$PATH
export PYTHONUNBUFFERED=1

# Environment variables for Splunk MCP server (stdio spawning)
export SECRET_ARN="${SECRET_ARN:-arn:aws:secretsmanager:region:account:secret:splunk-bedrock-secret-suffix}"

# Lowercase versions for the server (required by splunk-server.py)
export secret_arn="${SECRET_ARN:-arn:aws:secretsmanager:region:account:secret:splunk-bedrock-secret-suffix}"
export FASTMCP_DEBUG="true"

# Environment variables for PagerDuty MCP server
export PAGERDUTY_API_HOST="${PAGERDUTY_API_HOST:-https://api.pagerduty.com}"
export PAGERDUTY_USER_API_KEY="${PAGERDUTY_USER_API_KEY:-}"

echo "🔍 Starting Incident Management service..."
echo "   - Will spawn Splunk MCP server via stdio when needed"
echo "   - Will spawn PagerDuty MCP server via stdio when needed"
echo "   - Using server directory: /app/server"
echo "   - Using pagerduty-mcp-server directory: /app/pagerduty-mcp-server"
echo "   - Secrets are managed by AWS Secrets Manager (populated by deploy.sh)"

cd /app

# Run the incident management service
# It will spawn both MCP servers as needed via stdio
exec python run_api.py