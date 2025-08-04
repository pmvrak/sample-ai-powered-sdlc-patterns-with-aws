#!/bin/bash

# Load environment variables from .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "❌ .env file not found. Please copy .env.example to .env and configure your credentials."
    exit 1
fi

# Validate required environment variables
if [ -z "$JIRA_URL" ] || [ -z "$JIRA_USERNAME" ] || [ -z "$JIRA_API_TOKEN" ]; then
    echo "❌ Missing required environment variables. Please check your .env file."
    echo "Required: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN"
    exit 1
fi

# Verify they're set (show only partial token for security)
echo "JIRA_URL: $JIRA_URL"
echo "JIRA_USERNAME: $JIRA_USERNAME"
echo "JIRA_API_TOKEN: ${JIRA_API_TOKEN:0:10}..." # Show only first 10 chars for security

echo "✅ Environment variables loaded successfully"
