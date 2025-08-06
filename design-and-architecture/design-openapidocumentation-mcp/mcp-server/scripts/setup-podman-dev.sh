#!/bin/bash

# Setup Podman Development Environment Script
# This script helps configure the development environment for the MCP server using Podman

set -e

echo "🐳 Setting up MCP Server Development Environment with Podman"
echo "=========================================================="

# Check if Podman is installed
if ! command -v podman &> /dev/null; then
    echo "❌ Podman is not installed. Please install it first:"
    echo "   macOS: brew install podman"
    echo "   Linux: https://podman.io/getting-started/installation"
    exit 1
fi

# Check if podman-compose is available
if ! command -v podman-compose &> /dev/null; then
    echo "⚠️  podman-compose not found. Installing via pip..."
    if command -v pip3 &> /dev/null; then
        pip3 install podman-compose
    elif command -v pip &> /dev/null; then
        pip install podman-compose
    else
        echo "❌ pip not found. Please install podman-compose manually:"
        echo "   pip install podman-compose"
        exit 1
    fi
fi

echo "✅ Podman and podman-compose are available"

# Initialize Podman machine on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "🍎 Detected macOS - checking Podman machine..."
    
    if ! podman machine list | grep -q "Currently running"; then
        echo "🚀 Starting Podman machine..."
        if ! podman machine list | grep -q "podman-machine-default"; then
            echo "📦 Creating Podman machine..."
            podman machine init
        fi
        podman machine start
        echo "✅ Podman machine started"
    else
        echo "✅ Podman machine is already running"
    fi
fi

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install it first:"
    echo "   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

echo "✅ Prerequisites check passed"

# Check AWS credentials
echo "🔐 Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Please run 'aws configure' first"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region || echo "eu-west-1")

echo "✅ AWS credentials configured"
echo "   Account ID: $AWS_ACCOUNT_ID"
echo "   Region: $AWS_REGION"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.development .env
    
    # Update .env with actual AWS account ID and region
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS sed syntax
        sed -i '' "s/123456789012/$AWS_ACCOUNT_ID/g" .env
        sed -i '' "s/eu-west-1/$AWS_REGION/g" .env
    else
        # Linux sed syntax
        sed -i "s/123456789012/$AWS_ACCOUNT_ID/g" .env
        sed -i "s/eu-west-1/$AWS_REGION/g" .env
    fi
    
    echo "✅ Created .env file with your AWS account details"
    echo "⚠️  Please update the Lambda ARNs and other resource names in .env"
else
    echo "✅ .env file already exists"
fi

# Get CDK outputs to help populate environment variables
echo "🔍 Fetching CDK stack outputs..."
if aws cloudformation describe-stacks --stack-name LambdaStack --region $AWS_REGION &> /dev/null; then
    echo "📋 CDK Stack Outputs:"
    aws cloudformation describe-stacks \
        --stack-name LambdaStack \
        --region $AWS_REGION \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
        --output table
    
    echo ""
    echo "💡 Copy the ARN values above to your .env file"
else
    echo "⚠️  LambdaStack not found. Make sure you've deployed the CDK stacks first"
fi

# Create logs directory with proper permissions
mkdir -p logs
chmod 755 logs
echo "✅ Created logs directory"

# Install dependencies if package.json exists
if [ -f package.json ]; then
    echo "📦 Installing Node.js dependencies..."
    npm install
    echo "✅ Dependencies installed"
fi

# Set up Podman-specific configurations
echo "🔧 Setting up Podman configurations..."

# Create Podman network if it doesn't exist
if ! podman network exists mcp-network 2>/dev/null; then
    podman network create mcp-network
    echo "✅ Created Podman network: mcp-network"
else
    echo "✅ Podman network already exists: mcp-network"
fi

# Test Podman functionality
echo "🧪 Testing Podman functionality..."
if podman run --rm hello-world &> /dev/null; then
    echo "✅ Podman is working correctly"
else
    echo "⚠️  Podman test failed. You may need to check your Podman installation"
fi

echo ""
echo "🎉 Podman development environment setup complete!"
echo ""
echo "Next steps:"
echo "1. Update .env file with your actual Lambda ARNs and resource names"
echo "2. Run 'podman-compose -f podman-compose.yml up mcp-server' to start the MCP server"
echo "3. Run 'podman-compose -f podman-compose.yml --profile dev-tools up' to include development tools"
echo ""
echo "Useful Podman commands:"
echo "- View logs: podman-compose -f podman-compose.yml logs -f mcp-server"
echo "- Stop services: podman-compose -f podman-compose.yml down"
echo "- Rebuild: podman-compose -f podman-compose.yml build mcp-server"
echo "- List containers: podman ps"
echo "- List images: podman images"
echo ""
echo "Podman-specific notes:"
echo "- Containers run rootless by default"
echo "- SELinux contexts are handled automatically (:Z flag)"
echo "- User namespace mapping preserves file ownership"