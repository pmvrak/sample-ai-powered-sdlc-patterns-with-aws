#!/bin/bash

# Jenkins MCP Server - Update API Gateway URLs Script

set -e

# Get environment parameter (default to 'dev')
ENVIRONMENT=${1:-dev}

echo "🔧 Updating API Gateway URLs for environment: $ENVIRONMENT"

# Check if AWS CLI is available
if ! command -v aws &> /dev/null; then
    echo "❌ Error: AWS CLI is required but not installed."
    exit 1
fi

# Get AWS region
AWS_REGION=${AWS_REGION:-us-east-1}

echo "🌍 Using AWS region: $AWS_REGION"

# Get OAuth API URL
echo "📡 Retrieving OAuth API URL..."
OAUTH_API_URL=$(aws cloudformation describe-stacks \
    --stack-name "JenkinsMcpOAuthStack-$ENVIRONMENT" \
    --query 'Stacks[0].Outputs[?OutputKey==`OAuthApiEndpoint`].OutputValue' \
    --output text --region $AWS_REGION 2>/dev/null)

if [ -z "$OAUTH_API_URL" ] || [ "$OAUTH_API_URL" = "None" ]; then
    echo "❌ Error: Could not retrieve OAuth API URL from CloudFormation stack."
    echo "Make sure the stack 'JenkinsMcpOAuthStack-$ENVIRONMENT' exists and is deployed."
    exit 1
fi

# Get MCP API URL
echo "📡 Retrieving MCP API URL..."
MCP_API_URL=$(aws cloudformation describe-stacks \
    --stack-name "JenkinsMcpServerStack-$ENVIRONMENT" \
    --query 'Stacks[0].Outputs[?OutputKey==`McpApiEndpoint`].OutputValue' \
    --output text --region $AWS_REGION 2>/dev/null)

if [ -z "$MCP_API_URL" ] || [ "$MCP_API_URL" = "None" ]; then
    echo "❌ Error: Could not retrieve MCP API URL from CloudFormation stack."
    echo "Make sure the stack 'JenkinsMcpServerStack-$ENVIRONMENT' exists and is deployed."
    exit 1
fi

echo "✅ Retrieved API URLs:"
echo "  OAuth API: $OAUTH_API_URL"
echo "  MCP API: $MCP_API_URL"

# Update proxy_jenkins_mcp.py
echo "🔧 Updating proxy_jenkins_mcp.py..."
if [ -f "proxy_jenkins_mcp.py" ]; then
    # Create backup
    cp proxy_jenkins_mcp.py proxy_jenkins_mcp.py.bak
    
    # Update URLs in the file
    sed -i.tmp "s|MCP_API_URL = os.getenv('MCP_API_URL', '.*')|MCP_API_URL = os.getenv('MCP_API_URL', '$MCP_API_URL')|g" proxy_jenkins_mcp.py
    sed -i.tmp "s|OAUTH_API_URL = os.getenv('OAUTH_API_URL', '.*')|OAUTH_API_URL = os.getenv('OAUTH_API_URL', '$OAUTH_API_URL')|g" proxy_jenkins_mcp.py
    
    # Remove temporary file
    rm proxy_jenkins_mcp.py.tmp
    
    echo "✅ Updated proxy_jenkins_mcp.py"
else
    echo "⚠️  proxy_jenkins_mcp.py not found, skipping update"
fi

# Update token_config.py
echo "🔧 Updating token_config.py..."
if [ -f "token_config.py" ]; then
    # Create backup
    cp token_config.py token_config.py.bak
    
    # Update OAuth API URL in the file
    sed -i.tmp "s|OAUTH_API_URL = os.getenv('OAUTH_API_URL', '.*')|OAUTH_API_URL = os.getenv('OAUTH_API_URL', '$OAUTH_API_URL')|g" token_config.py
    
    # Remove temporary file
    rm token_config.py.tmp
    
    echo "✅ Updated token_config.py"
else
    echo "⚠️  token_config.py not found, skipping update"
fi

# Update .env file if it exists
if [ -f ".env" ]; then
    echo "🔧 Updating .env file..."
    
    # Create backup
    cp .env .env.bak
    
    # Update or add URLs
    if grep -q "^MCP_API_URL=" .env; then
        sed -i.tmp "s|^MCP_API_URL=.*|MCP_API_URL=$MCP_API_URL|g" .env
    else
        echo "MCP_API_URL=$MCP_API_URL" >> .env
    fi
    
    if grep -q "^OAUTH_API_URL=" .env; then
        sed -i.tmp "s|^OAUTH_API_URL=.*|OAUTH_API_URL=$OAUTH_API_URL|g" .env
    else
        echo "OAUTH_API_URL=$OAUTH_API_URL" >> .env
    fi
    
    # Remove temporary file
    rm .env.tmp
    
    echo "✅ Updated .env file"
else
    echo "📝 Creating .env file with API URLs..."
    cat >> .env << EOF

# API Gateway URLs (auto-generated)
MCP_API_URL=$MCP_API_URL
OAUTH_API_URL=$OAUTH_API_URL
EOF
    echo "✅ Created .env file with API URLs"
fi

echo ""
echo "🎉 URL update completed successfully!"
echo ""
echo "📋 Configuration Summary:"
echo "  Environment: $ENVIRONMENT"
echo "  AWS Region: $AWS_REGION"
echo "  OAuth API URL: $OAUTH_API_URL"
echo "  MCP API URL: $MCP_API_URL"
echo ""
echo "🔄 Next steps:"
echo "1. Get a fresh OAuth token: ./get_fresh_token.sh"
echo "2. Test the connection: python3 -m src.jenkins_client.client"
echo "3. Start Amazon Q: q chat"
echo ""
echo "📊 Monitor deployment:"
echo "  OAuth Server logs: aws logs tail /aws/lambda/jenkins-mcp-oauth-server-$ENVIRONMENT --follow"
echo "  MCP Server logs: aws logs tail /aws/lambda/jenkins-mcp-server-$ENVIRONMENT --follow"
