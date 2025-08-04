#!/bin/bash

# JIRA MCP Server CDK Deployment Script
# Deploys both OAuth and MCP servers using AWS CDK

set -e

ENVIRONMENT=${1:-dev}

echo "🚀 Starting JIRA MCP Server CDK deployment for environment: $ENVIRONMENT"

# Check if required environment variables are set
if [ -z "$JIRA_URL" ] || [ -z "$JIRA_USERNAME" ] || [ -z "$JIRA_API_TOKEN" ]; then
    echo "❌ Missing required environment variables. Please set:"
    echo "   JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN"
    echo ""
    echo "💡 You can source the environment variables:"
    echo "   source deployment/.env_var_export.sh"
    exit 1
fi

# Navigate to CDK directory
cd "$(dirname "$0")/cdk"

echo "📦 Installing CDK dependencies..."
if [ ! -d "node_modules" ]; then
    npm install
else
    echo "   Dependencies already installed"
fi

echo "🔨 Building CDK project..."
npm run build

echo "📋 Checking if deployment packages exist..."
if [ ! -f "../lambda-deployment.zip" ]; then
    echo "❌ Lambda deployment package not found. Creating it..."
    cd ..
    ./package_lambda.sh
    cd cdk
fi

if [ ! -f "../oauth-server-deployment.zip" ]; then
    echo "❌ OAuth server deployment package not found. Creating it..."
    cd ..
    ./package_oauth_server.sh
    cd cdk
fi

echo "🔍 Synthesizing CDK stacks..."
npm run synth

echo "📊 Showing deployment plan..."
npm run diff

echo "🚀 Deploying CDK stacks..."
export ENVIRONMENT=$ENVIRONMENT
npm run deploy -- --require-approval never

echo ""
echo "✅ CDK Deployment complete!"
echo ""
echo "📊 Deployment Information:"
echo "Environment: $ENVIRONMENT"
echo "Region: ${AWS_REGION:-us-east-1}"
echo ""
echo "🔗 Next steps:"
echo "1. Get fresh OAuth token: ./get_fresh_token.sh"
echo "2. Start Amazon Q: q chat"
echo ""
echo "🎉 Your JIRA MCP server is now deployed with CDK!"
