#!/bin/bash

# Jenkins MCP Server Environment Variable Export Script
# This script exports environment variables needed for CDK deployment

# Check if .env file exists
if [ -f .env ]; then
    echo "Loading environment variables from .env file..."
    source .env
else
    echo "Warning: .env file not found. Using environment variables or defaults."
fi

# Export Jenkins configuration
export JENKINS_URL="${JENKINS_URL:-}"
export JENKINS_USERNAME="${JENKINS_USERNAME:-}"
export JENKINS_API_TOKEN="${JENKINS_API_TOKEN:-}"

# Export AWS configuration
export AWS_REGION="${AWS_REGION:-us-east-1}"
export ENVIRONMENT="${ENVIRONMENT:-dev}"

# Validate required variables
if [ -z "$JENKINS_URL" ] || [ -z "$JENKINS_USERNAME" ] || [ -z "$JENKINS_API_TOKEN" ]; then
    echo "❌ Error: Missing required Jenkins configuration!"
    echo "Please set the following environment variables:"
    echo "  - JENKINS_URL"
    echo "  - JENKINS_USERNAME" 
    echo "  - JENKINS_API_TOKEN"
    echo ""
    echo "You can set these in a .env file or export them directly."
    exit 1
fi

echo "✅ Environment variables exported successfully!"
echo "Jenkins URL: $JENKINS_URL"
echo "Jenkins Username: $JENKINS_USERNAME"
echo "AWS Region: $AWS_REGION"
echo "Environment: $ENVIRONMENT"
