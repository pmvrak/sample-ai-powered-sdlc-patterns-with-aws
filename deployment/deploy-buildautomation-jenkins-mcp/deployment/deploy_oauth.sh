#!/bin/bash
set -e

echo "🚀 Deploying MCP Server with OAuth Authentication..."
echo "=================================================="

# Check if environment is provided
ENVIRONMENT=${1:-dev}
echo "📋 Environment: $ENVIRONMENT"

# Load environment variables
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

# Create deployment packages
echo "📦 Creating deployment packages..."
source venv/bin/activate

# Package main MCP server
echo "📦 Packaging MCP server..."
./deployment/package_lambda.sh

# Package OAuth server
echo "📦 Packaging OAuth server..."
./deployment/package_oauth_server.sh

# Deploy with Terraform
echo "🏗️  Deploying infrastructure..."
cd deployment/terraform

# Initialize Terraform
terraform init

# Plan deployment
echo "📋 Planning deployment..."
terraform plan \
    -var="jira_url=$JIRA_URL" \
    -var="jira_username=$JIRA_USERNAME" \
    -var="jira_api_token=$JIRA_API_TOKEN" \
    -var="environment=$ENVIRONMENT" \
    -var="aws_region=${AWS_REGION:-us-east-1}"

# Apply deployment
echo "🚀 Applying deployment..."
terraform apply -auto-approve \
    -var="jira_url=$JIRA_URL" \
    -var="jira_username=$JIRA_USERNAME" \
    -var="jira_api_token=$JIRA_API_TOKEN" \
    -var="environment=$ENVIRONMENT" \
    -var="aws_region=${AWS_REGION:-us-east-1}"

# Get outputs
echo ""
echo "✅ Deployment complete!"
echo "=================================================="
echo "📊 Deployment Information:"
terraform output

echo ""
echo "🔒 OAuth Endpoints:"
OAUTH_API_ID=$(terraform output -raw oauth_api_gateway_id 2>/dev/null || echo "N/A")
if [ "$OAUTH_API_ID" != "N/A" ]; then
    echo "Authorization Server: https://$OAUTH_API_ID.execute-api.${AWS_REGION:-us-east-1}.amazonaws.com/$ENVIRONMENT"
    echo "Metadata: https://$OAUTH_API_ID.execute-api.${AWS_REGION:-us-east-1}.amazonaws.com/$ENVIRONMENT/.well-known/oauth-authorization-server"
    echo "Registration: https://$OAUTH_API_ID.execute-api.${AWS_REGION:-us-east-1}.amazonaws.com/$ENVIRONMENT/register"
fi

echo ""
echo "🔗 MCP Server Endpoints:"
MCP_API_ID=$(terraform output -raw api_gateway_id 2>/dev/null || echo "N/A")
if [ "$MCP_API_ID" != "N/A" ]; then
    echo "MCP Server: https://$MCP_API_ID.execute-api.${AWS_REGION:-us-east-1}.amazonaws.com/$ENVIRONMENT"
    echo "Protected Resource Metadata: https://$MCP_API_ID.execute-api.${AWS_REGION:-us-east-1}.amazonaws.com/$ENVIRONMENT/.well-known/oauth-protected-resource"
    echo "Health Check: https://$MCP_API_ID.execute-api.${AWS_REGION:-us-east-1}.amazonaws.com/$ENVIRONMENT/health"
fi

echo ""
echo "🎉 Your MCP server is now deployed with OAuth authentication!"
echo "📚 See README.md for client configuration instructions."

cd ../..
