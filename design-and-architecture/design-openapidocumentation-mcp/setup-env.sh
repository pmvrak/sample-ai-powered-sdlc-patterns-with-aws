#!/bin/bash
# Setup script for environment variables
# This script helps users configure their environment variables for deployment

set -e

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

# Get the absolute path to the script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CDK_DIR="$SCRIPT_DIR/cdk"
ENV_FILE="$CDK_DIR/.env"
EXAMPLE_FILE="$CDK_DIR/.env.example"

print_status "Setting up environment variables for OpenAPI Documentation MCP Server"
echo ""

# Check if .env.example exists
if [ ! -f "$EXAMPLE_FILE" ]; then
    print_error ".env.example file not found at $EXAMPLE_FILE"
    exit 1
fi

# Check if .env already exists
if [ -f "$ENV_FILE" ]; then
    print_warning ".env file already exists at $ENV_FILE"
    read -p "Do you want to overwrite it? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Keeping existing .env file. You can edit it manually if needed."
        exit 0
    fi
fi

# Copy the example file
cp "$EXAMPLE_FILE" "$ENV_FILE"
print_success "Created .env file from template"

# Get AWS account ID automatically if possible
print_status "Detecting AWS account information..."
if command -v aws &> /dev/null; then
    if aws sts get-caller-identity >/dev/null 2>&1; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        CURRENT_REGION=$(aws configure get region || echo "us-east-1")
        
        print_success "Detected AWS Account ID: $ACCOUNT_ID"
        print_success "Detected AWS Region: $CURRENT_REGION"
        
        # Update the .env file with detected values
        sed -i.bak "s/CDK_DEFAULT_ACCOUNT=123456789012/CDK_DEFAULT_ACCOUNT=$ACCOUNT_ID/" "$ENV_FILE"
        sed -i.bak "s/CDK_DEFAULT_REGION=us-east-1/CDK_DEFAULT_REGION=$CURRENT_REGION/" "$ENV_FILE"
        
        # Remove backup file
        rm "$ENV_FILE.bak"
        
        print_success "Updated .env file with detected AWS information"
    else
        print_warning "AWS credentials not configured. Please run 'aws configure' first."
        print_warning "You'll need to manually update the AWS account ID in .env"
    fi
else
    print_warning "AWS CLI not found. Please install it and configure your credentials."
    print_warning "You'll need to manually update the AWS account ID in .env"
fi

# Prompt for optional customizations
echo ""
print_status "Optional customizations (press Enter to keep defaults):"

# Ask for Bedrock region
read -p "Bedrock region (default: eu-west-1): " BEDROCK_REGION
if [ -n "$BEDROCK_REGION" ]; then
    sed -i.bak "s/BEDROCK_REGION=eu-west-1/BEDROCK_REGION=$BEDROCK_REGION/" "$ENV_FILE"
    rm "$ENV_FILE.bak"
fi

# Ask for MCP server name
read -p "MCP server name (default: openapi-documentation-mcp-prod): " MCP_NAME
if [ -n "$MCP_NAME" ]; then
    sed -i.bak "s/MCP_SERVER_NAME=openapi-documentation-mcp-prod/MCP_SERVER_NAME=$MCP_NAME/" "$ENV_FILE"
    rm "$ENV_FILE.bak"
fi

# Ask for log level
read -p "Log level (default: info): " LOG_LEVEL
if [ -n "$LOG_LEVEL" ]; then
    sed -i.bak "s/LOG_LEVEL=info/LOG_LEVEL=$LOG_LEVEL/" "$ENV_FILE"
    rm "$ENV_FILE.bak"
fi

echo ""
print_success "Environment setup complete!"
print_status "Your configuration is saved in: $ENV_FILE"
echo ""
print_status "Next steps:"
echo "1. Review and customize the .env file if needed:"
echo "   nano $ENV_FILE"
echo ""
echo "2. Deploy the infrastructure:"
echo "   ./deploy-all.sh --my-ip"
echo ""
echo "3. Or deploy with custom settings:"
echo "   ./deploy-all.sh --domain-name your-domain.com --allowed-ips \"1.2.3.4/32\""
echo ""
print_warning "Important: Never commit the .env file to version control!"
print_warning "It contains sensitive configuration that should remain private."