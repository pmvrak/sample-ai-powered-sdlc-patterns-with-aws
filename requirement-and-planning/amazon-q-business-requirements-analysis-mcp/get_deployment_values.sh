#!/bin/bash

echo "🔍 AWS Resource Discovery Script"
echo "This script will help you gather the required values for deployment"
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "❌ AWS CLI is not configured or you don't have permissions"
    echo "Please run 'aws configure' first"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region || echo "us-east-1")

echo "📋 Current AWS Configuration:"
echo "  Account ID: ${ACCOUNT_ID}"
echo "  Region: ${REGION}"
echo ""

echo "🔍 1. Finding Identity Center Instance..."
IDC_INSTANCES=$(aws sso-admin list-instances --query 'Instances[*].[InstanceArn,Status]' --output table 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$IDC_INSTANCES" ]; then
    echo "$IDC_INSTANCES"
    IDC_INSTANCE_ARN=$(aws sso-admin list-instances --query 'Instances[0].InstanceArn' --output text 2>/dev/null)
    if [ "$IDC_INSTANCE_ARN" != "None" ] && [ -n "$IDC_INSTANCE_ARN" ]; then
        IDC_INSTANCE_ID=$(echo "$IDC_INSTANCE_ARN" | sed 's/.*\///')
        echo "✅ Found Identity Center Instance ID: ${IDC_INSTANCE_ID}"
    else
        echo "❌ No Identity Center instance found"
        IDC_INSTANCE_ID="your-idc-instance-id"
    fi
else
    echo "❌ Unable to list Identity Center instances (may not exist or no permissions)"
    IDC_INSTANCE_ID="your-idc-instance-id"
fi
echo ""

echo "🔍 2. Finding Amazon Q Business Applications..."
Q_APPS=$(aws qbusiness list-applications --query 'applications[*].[applicationId,displayName,status]' --output table 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$Q_APPS" ]; then
    echo "$Q_APPS"
    Q_BUSINESS_APP_ID=$(aws qbusiness list-applications --query 'applications[0].applicationId' --output text 2>/dev/null)
    if [ "$Q_BUSINESS_APP_ID" != "None" ] && [ -n "$Q_BUSINESS_APP_ID" ]; then
        echo "✅ Found Q Business Application ID: ${Q_BUSINESS_APP_ID}"
    else
        echo "❌ No Q Business applications found"
        Q_BUSINESS_APP_ID="your-q-business-app-id"
    fi
else
    echo "❌ Unable to list Q Business applications (may not exist or no permissions)"
    Q_BUSINESS_APP_ID="your-q-business-app-id"
fi
echo ""

echo "🔍 3. Finding Cognito User Pools..."
COGNITO_POOLS=$(aws cognito-idp list-user-pools --max-results 10 --query 'UserPools[*].[Id,Name]' --output table 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$COGNITO_POOLS" ]; then
    echo "$COGNITO_POOLS"
    echo ""
    echo "📝 Please select a Cognito User Pool ID from the list above:"
    read -p "Enter Cognito User Pool ID: " COGNITO_USER_POOL_ID
    
    if [ -n "$COGNITO_USER_POOL_ID" ]; then
        echo ""
        echo "🔍 4. Finding Cognito User Pool Clients for pool: ${COGNITO_USER_POOL_ID}..."
        COGNITO_CLIENTS=$(aws cognito-idp list-user-pool-clients --user-pool-id "$COGNITO_USER_POOL_ID" --query 'UserPoolClients[*].[ClientId,ClientName]' --output table 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$COGNITO_CLIENTS" ]; then
            echo "$COGNITO_CLIENTS"
            echo ""
            echo "📝 Please select a Cognito Client ID from the list above:"
            read -p "Enter Cognito Client ID: " COGNITO_CLIENT_ID
        else
            echo "❌ Unable to list Cognito clients for this pool"
            COGNITO_CLIENT_ID="your-cognito-client-id"
        fi
    else
        COGNITO_USER_POOL_ID="your-cognito-user-pool-id"
        COGNITO_CLIENT_ID="your-cognito-client-id"
    fi
else
    echo "❌ Unable to list Cognito User Pools (may not exist or no permissions)"
    COGNITO_USER_POOL_ID="your-cognito-user-pool-id"
    COGNITO_CLIENT_ID="your-cognito-client-id"
fi
echo ""

echo "📋 DEPLOYMENT VALUES SUMMARY:"
echo "================================"
echo "Account ID: ${ACCOUNT_ID}"
echo "Region: ${REGION}"
echo "Identity Center Instance ID: ${IDC_INSTANCE_ID}"
echo "Q Business Application ID: ${Q_BUSINESS_APP_ID}"
echo "Cognito User Pool ID: ${COGNITO_USER_POOL_ID}"
echo "Cognito Client ID: ${COGNITO_CLIENT_ID}"
echo ""

echo "📝 NEXT STEPS:"
echo "1. Update deploy_with_existing_cognito.sh with these values:"
echo "   - Set AWS_PROFILE to your profile name"
echo "   - Set IDC_INSTANCE_ID=\"${IDC_INSTANCE_ID}\""
echo "   - Set Q_BUSINESS_APP_ID=\"${Q_BUSINESS_APP_ID}\""
echo "   - Set EXISTING_COGNITO_USER_POOL_ID=\"${COGNITO_USER_POOL_ID}\""
echo "   - Set EXISTING_COGNITO_CLIENT_ID=\"${COGNITO_CLIENT_ID}\""
echo ""
echo "2. Run the deployment:"
echo "   ./deploy_with_existing_cognito.sh"
echo ""

# Optionally create a config file
read -p "Would you like to create a config file with these values? (y/n): " CREATE_CONFIG
if [ "$CREATE_CONFIG" = "y" ] || [ "$CREATE_CONFIG" = "Y" ]; then
    cat > deployment_config.env << EOF
# AWS Deployment Configuration
# Generated on $(date)

export AWS_PROFILE=default  # Change this to your AWS profile
export ACCOUNT_ID=${ACCOUNT_ID}
export REGION=${REGION}
export IDC_INSTANCE_ID=${IDC_INSTANCE_ID}
export Q_BUSINESS_APP_ID=${Q_BUSINESS_APP_ID}
export EXISTING_COGNITO_USER_POOL_ID=${COGNITO_USER_POOL_ID}
export EXISTING_COGNITO_CLIENT_ID=${COGNITO_CLIENT_ID}

# Optional: Customize these values
export REPOSITORY_NAME=amazon-q-mcp-server
export IMAGE_TAG=latest
export STACK_NAME=mcp-existing-cognito-v9
EOF
    echo "✅ Created deployment_config.env file"
    echo "   You can source this file: source deployment_config.env"
fi