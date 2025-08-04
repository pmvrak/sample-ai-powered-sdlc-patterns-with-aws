#!/bin/bash

# JIRA MCP Server CDK Destroy Script
# Destroys all CDK stacks and resources

set -e

ENVIRONMENT=${1:-dev}

echo "🗑️  Destroying JIRA MCP Server CDK deployment for environment: $ENVIRONMENT"

# Navigate to CDK directory
cd "$(dirname "$0")/cdk"

echo "🔍 Checking CDK stacks..."
if [ ! -d "node_modules" ]; then
    echo "📦 Installing CDK dependencies first..."
    npm install
fi

echo "🔨 Building CDK project..."
npm run build

echo "🗑️  Destroying CDK stacks..."
export ENVIRONMENT=$ENVIRONMENT
npm run destroy -- --force

echo ""
echo "✅ CDK Destruction complete!"
echo "🧹 All AWS resources have been removed."
