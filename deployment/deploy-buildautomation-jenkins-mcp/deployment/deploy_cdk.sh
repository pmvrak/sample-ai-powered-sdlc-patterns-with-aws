#!/bin/bash

# Jenkins MCP Server CDK Deployment Script

set -e

# Get environment parameter (default to 'dev')
ENVIRONMENT=${1:-dev}

echo "🚀 Deploying Jenkins MCP Server to environment: $ENVIRONMENT"

# Source environment variables
source deployment/.env_var_export.sh

# Validate Jenkins configuration
if [ -z "$JENKINS_URL" ] || [ -z "$JENKINS_USERNAME" ] || [ -z "$JENKINS_API_TOKEN" ]; then
    echo "❌ Error: Jenkins configuration is incomplete!"
    echo "Please check your .env file or environment variables."
    exit 1
fi

# Build Lambda packages
echo "📦 Building Lambda deployment packages..."
./deployment/package_lambda.sh
./deployment/package_oauth_server.sh

# Change to CDK directory
cd deployment/cdk

# Install CDK dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing CDK dependencies..."
    npm install
fi

# Package Lambda functions
echo "📦 Packaging Lambda functions..."
cd ../..
./deployment/package_lambda.sh
./deployment/package_oauth_server.sh

# Return to CDK directory
cd deployment/cdk

# Bootstrap CDK if needed (only run once per account/region)
echo "🔧 Checking CDK bootstrap status..."
if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $AWS_REGION >/dev/null 2>&1; then
    echo "🔧 Bootstrapping CDK..."
    npx cdk bootstrap --context environment=$ENVIRONMENT
fi

# Deploy stacks
echo "🚀 Deploying Jenkins MCP Server stacks..."
npx cdk deploy --all --require-approval never --context environment=$ENVIRONMENT

# Get deployed URLs
echo "📋 Getting deployed API URLs..."
OAUTH_API_URL=$(aws cloudformation describe-stacks \
    --stack-name "JenkinsMcpOAuthStack-$ENVIRONMENT" \
    --query 'Stacks[0].Outputs[?OutputKey==`OAuthApiEndpoint`].OutputValue' \
    --output text --region $AWS_REGION)

MCP_API_URL=$(aws cloudformation describe-stacks \
    --stack-name "JenkinsMcpServerStack-$ENVIRONMENT" \
    --query 'Stacks[0].Outputs[?OutputKey==`McpApiEndpoint`].OutputValue' \
    --output text --region $AWS_REGION)

echo ""
echo "✅ Deployment completed successfully!"
echo ""
echo "📋 Deployment Information:"
echo "  Environment: $ENVIRONMENT"
echo "  AWS Region: $AWS_REGION"
echo "  OAuth API URL: $OAUTH_API_URL"
echo "  MCP API URL: $MCP_API_URL"
echo ""
echo "🔧 Next steps:"
echo "  1. Update your proxy configuration with these URLs"
echo "  2. Run ./get_fresh_token.sh to get an OAuth token"
echo "  3. Configure Amazon Q with the MCP server"
echo ""
echo "📊 Monitor logs:"
echo "  OAuth Server: aws logs tail /aws/lambda/jenkins-mcp-oauth-server-$ENVIRONMENT --follow"
echo "  MCP Server: aws logs tail /aws/lambda/jenkins-mcp-server-$ENVIRONMENT --follow"
