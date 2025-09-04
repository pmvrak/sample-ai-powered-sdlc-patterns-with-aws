#!/bin/bash

# Jenkins MCP Server CDK Destroy Script

set -e

# Get environment parameter (default to 'dev')
ENVIRONMENT=${1:-dev}

echo "🗑️  Destroying Jenkins MCP Server from environment: $ENVIRONMENT"

# Confirm destruction
read -p "Are you sure you want to destroy the Jenkins MCP Server stacks for environment '$ENVIRONMENT'? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Destruction cancelled."
    exit 1
fi

# Change to CDK directory
cd deployment/cdk

# Destroy stacks (reverse order of dependencies)
echo "🗑️  Destroying Jenkins MCP Server stacks..."
npx cdk destroy --all --force --context environment=$ENVIRONMENT

echo ""
echo "✅ Destruction completed successfully!"
echo ""
echo "🧹 Cleanup completed for environment: $ENVIRONMENT"
echo ""
echo "Note: The following may still exist and require manual cleanup:"
echo "  - CloudWatch log groups (if retention policy prevents auto-deletion)"
echo "  - Any custom resources created outside of CDK"
