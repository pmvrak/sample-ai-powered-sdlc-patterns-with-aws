#!/bin/bash

# Update Environment Variables Script
# This script updates the .env file with the newly deployed AWS resource ARNs and IDs

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to get stack outputs
get_stack_outputs() {
    print_status "Retrieving stack outputs..."
    
    # Get Lambda function ARNs
    DOMAIN_ANALYZER_ARN=$(aws cloudformation describe-stacks --stack-name LambdaStack --query 'Stacks[0].Outputs[?OutputKey==`DomainAnalyzerFunctionArn`].OutputValue' --output text 2>/dev/null || echo "")
    DOC_GENERATOR_ARN=$(aws cloudformation describe-stacks --stack-name LambdaStack --query 'Stacks[0].Outputs[?OutputKey==`DocGeneratorFunctionArn`].OutputValue' --output text 2>/dev/null || echo "")
    
    # Get Bedrock Agent details
    BEDROCK_AGENT_ID=$(aws cloudformation describe-stacks --stack-name BedrockStack --query 'Stacks[0].Outputs[?OutputKey==`AgentId`].OutputValue' --output text 2>/dev/null || echo "")
    KNOWLEDGE_BASE_ID=$(aws cloudformation describe-stacks --stack-name BedrockStack --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' --output text 2>/dev/null || echo "")
    
    # Get S3 bucket names
    KNOWLEDGE_BUCKET=$(aws cloudformation describe-stacks --stack-name StorageStack --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseBucketName`].OutputValue' --output text 2>/dev/null || echo "")
    DOMAIN_BUCKET=$(aws cloudformation describe-stacks --stack-name StorageStack --query 'Stacks[0].Outputs[?OutputKey==`DomainAnalyzerBucketName`].OutputValue' --output text 2>/dev/null || echo "")
    
    # Get Backend Lambda Function URL
    BACKEND_FUNCTION_URL=$(aws cloudformation describe-stacks --stack-name LambdaStack --query 'Stacks[0].Outputs[?OutputKey==`BackendFunctionUrl`].OutputValue' --output text 2>/dev/null || echo "")
    BACKEND_FUNCTION_ARN=$(aws cloudformation describe-stacks --stack-name LambdaStack --query 'Stacks[0].Outputs[?OutputKey==`BackendFunctionArn`].OutputValue' --output text 2>/dev/null || echo "")
    
    # Get Cognito authentication details
    USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name AmplifyAuthStack --query 'Stacks[0].Outputs[?OutputKey==`UserPoolId`].OutputValue' --output text 2>/dev/null || echo "")
    USER_POOL_CLIENT_ID=$(aws cloudformation describe-stacks --stack-name AmplifyAuthStack --query 'Stacks[0].Outputs[?OutputKey==`UserPoolClientId`].OutputValue' --output text 2>/dev/null || echo "")
    IDENTITY_POOL_ID=$(aws cloudformation describe-stacks --stack-name AmplifyAuthStack --query 'Stacks[0].Outputs[?OutputKey==`IdentityPoolId`].OutputValue' --output text 2>/dev/null || echo "")
    AUTH_DOMAIN=$(aws cloudformation describe-stacks --stack-name AmplifyAuthStack --query 'Stacks[0].Outputs[?OutputKey==`AuthDomain`].OutputValue' --output text 2>/dev/null || echo "")
    AMPLIFY_APP_URL=$(aws cloudformation describe-stacks --stack-name AmplifyAuthStack --query 'Stacks[0].Outputs[?OutputKey==`AmplifyAppUrl`].OutputValue' --output text 2>/dev/null || echo "")
    
    print_success "Stack outputs retrieved!"
    echo "  Domain Analyzer Lambda ARN: $DOMAIN_ANALYZER_ARN"
    echo "  Doc Generator Lambda ARN: $DOC_GENERATOR_ARN"
    echo "  Backend Function URL: $BACKEND_FUNCTION_URL"
    echo "  Backend Function ARN: $BACKEND_FUNCTION_ARN"
    echo "  Bedrock Agent ID: $BEDROCK_AGENT_ID"
    echo "  Knowledge Base ID: $KNOWLEDGE_BASE_ID"
    echo "  Knowledge Base Bucket: $KNOWLEDGE_BUCKET"
    echo "  Domain Analyzer Bucket: $DOMAIN_BUCKET"
    echo "  User Pool ID: $USER_POOL_ID"
    echo "  User Pool Client ID: $USER_POOL_CLIENT_ID"
    echo "  Identity Pool ID: $IDENTITY_POOL_ID"
    echo "  Auth Domain: $AUTH_DOMAIN"
    echo "  Amplify App URL: $AMPLIFY_APP_URL"
}

# Function to update .env file
update_env_file() {
    print_status "Updating .env file..."
    
    ENV_FILE="../.env"
    
    # Create backup of existing .env file
    if [ -f "$ENV_FILE" ]; then
        cp "$ENV_FILE" "${ENV_FILE}.backup"
        print_status "Created backup: ${ENV_FILE}.backup"
    fi
    
    # Create new .env file with updated values
    cat > "$ENV_FILE" << EOF
# Lambda function ARNs (Updated by CDK deployment)
DOMAIN_ANALYZER_LAMBDA_ARN=$DOMAIN_ANALYZER_ARN
LAMBDA_FUNCTION_ARN=$DOC_GENERATOR_ARN

# Bedrock Agent details (Updated by CDK deployment)
BEDROCK_AGENT_ID=$BEDROCK_AGENT_ID
BEDROCK_AGENT_ALIAS_ID=TSTALIASID
KNOWLEDGE_BASE_ID=$KNOWLEDGE_BASE_ID

# S3 Bucket names (Updated by CDK deployment)
KNOWLEDGE_BASE_BUCKET=$KNOWLEDGE_BUCKET
DOMAIN_ANALYZER_BUCKET=$DOMAIN_BUCKET

# AWS Region
AWS_REGION=${AWS_DEFAULT_REGION:-eu-west-1}

# Backend Lambda Function URL (Updated by CDK deployment)
REACT_APP_API_URL=$BACKEND_FUNCTION_URL

# Backend Lambda Function ARN for direct invocation (Updated by CDK deployment)
REACT_APP_BACKEND_FUNCTION_ARN=$BACKEND_FUNCTION_ARN

# Cognito Authentication (Updated by CDK deployment)
REACT_APP_USER_POOL_ID=$USER_POOL_ID
REACT_APP_USER_POOL_CLIENT_ID=$USER_POOL_CLIENT_ID
REACT_APP_AUTH_DOMAIN=$AUTH_DOMAIN
REACT_APP_AWS_REGION=${AWS_DEFAULT_REGION:-eu-west-1}

# Vite environment variables (for client build)
VITE_USER_POOL_ID=$USER_POOL_ID
VITE_USER_POOL_CLIENT_ID=$USER_POOL_CLIENT_ID
VITE_IDENTITY_POOL_ID=$IDENTITY_POOL_ID
VITE_AUTH_DOMAIN=$AUTH_DOMAIN
VITE_AWS_REGION=${AWS_DEFAULT_REGION:-eu-west-1}
VITE_API_URL=$BACKEND_FUNCTION_URL

# Lambda environment variables (for backend)
USER_POOL_ID=$USER_POOL_ID
USER_POOL_CLIENT_ID=$USER_POOL_CLIENT_ID

# Server port
PORT=3000

# Make sure AWS credentials are configured in ~/.aws/credentials or set these environment variables
# AWS_ACCESS_KEY_ID=your-access-key
# AWS_SECRET_ACCESS_KEY=your-secret-key

EOF
    
    print_success ".env file updated successfully!"
}

# Function to update hardcoded values in source code
update_source_code() {
    print_status "Checking source code configuration..."
    
    # Check if openapi-generator.js is using environment variables
    if [ -f "../server/services/openapi-generator.js" ]; then
        if grep -q "process.env.BEDROCK_AGENT_ID" "../server/services/openapi-generator.js"; then
            print_success "openapi-generator.js is already configured to use environment variables"
        else
            print_warning "openapi-generator.js may need manual update to use environment variables"
        fi
    fi
    
    print_success "Source code check completed!"
}

# Function to verify updates
verify_updates() {
    print_status "Verifying updates..."
    
    if [ -f "../.env" ]; then
        print_success ".env file exists and has been updated"
        echo "Current .env contents:"
        echo "========================"
        cat "../.env"
        echo "========================"
    else
        print_error ".env file not found!"
        return 1
    fi
    
    print_success "Verification completed!"
}

# Main function
main() {
    echo "=========================================="
    echo "  Update Environment Variables"
    echo "=========================================="
    echo ""
    
    print_status "This script will update your .env file with newly deployed AWS resource ARNs and IDs."
    
    # Check if AWS CLI is available
    if ! command -v aws >/dev/null 2>&1; then
        print_error "AWS CLI is not installed or not in PATH"
        exit 1
    fi
    
    # Check if we can access AWS
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        print_error "AWS credentials are not configured or invalid"
        exit 1
    fi
    
    # Run update steps
    get_stack_outputs
    
    # Check if we got valid outputs
    if [ -z "$DOMAIN_ANALYZER_ARN" ] || [ -z "$BEDROCK_AGENT_ID" ]; then
        print_error "Failed to retrieve stack outputs. Make sure all stacks are deployed successfully."
        exit 1
    fi
    
    update_env_file
    update_source_code
    verify_updates
    
    print_success "Environment variables updated successfully! 🎉"
    echo ""
    echo "Your application will now use the newly deployed AWS resources."
    echo "Restart your server to pick up the new environment variables."
}

# Run main function
main "$@"