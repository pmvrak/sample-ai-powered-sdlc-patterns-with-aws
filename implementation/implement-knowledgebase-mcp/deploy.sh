#!/bin/bash

# Project KB MCP Server - Deployment Script
# This script builds and prepares the MCP server for deployment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project information
PROJECT_NAME="Project KB MCP Server"
VERSION=$(node -p "require('./package.json').version" 2>/dev/null || echo "unknown")

echo -e "${BLUE}🚀 ${PROJECT_NAME} Deployment Script${NC}"
echo -e "${BLUE}📦 Version: ${VERSION}${NC}"
echo ""

# Function to print status messages
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    print_error "package.json not found. Please run this script from the project root directory."
    exit 1
fi

if [ ! -f "src/index.ts" ]; then
    print_error "src/index.ts not found. This doesn't appear to be the MCP server project."
    exit 1
fi

print_info "Starting deployment process..."
echo ""

# Step 1: Clean previous build
print_info "Step 1: Cleaning previous build artifacts..."
if [ -d "dist" ]; then
    rm -rf dist
    print_status "Removed existing dist directory"
else
    print_status "No previous build artifacts found"
fi

# Step 2: Install dependencies
print_info "Step 2: Installing/updating dependencies..."
if npm ci --silent; then
    print_status "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Step 3: Run security audit (non-blocking)
print_info "Step 3: Running security audit..."
if npm audit --audit-level=high --silent; then
    print_status "No high-severity vulnerabilities found"
else
    print_warning "Security vulnerabilities detected. Consider running 'npm audit fix'"
fi

# Step 4: Build the project
print_info "Step 4: Building TypeScript project..."
if npm run build --silent; then
    print_status "TypeScript compilation completed successfully"
else
    print_error "Build failed"
    exit 1
fi

# Step 5: Verify build output
print_info "Step 5: Verifying build output..."
if [ -f "dist/index.js" ]; then
    print_status "Main entry point created: dist/index.js"
else
    print_error "Build verification failed: dist/index.js not found"
    exit 1
fi

# Count built files
BUILT_FILES=$(find dist -name "*.js" | wc -l | tr -d ' ')
print_status "Built ${BUILT_FILES} JavaScript files"

# Step 6: Environment configuration check
print_info "Step 6: Environment configuration..."
print_status "Environment variables will be passed through MCP configuration"
print_warning "Remember to update the generated MCP template with your actual AWS credentials"

# Step 7: Display deployment information
echo ""
print_info "🎉 Deployment completed successfully!"
echo ""
echo -e "${BLUE}📋 Deployment Summary:${NC}"
echo -e "   • Project: ${PROJECT_NAME}"
echo -e "   • Version: ${VERSION}"
echo -e "   • Built files: ${BUILT_FILES}"
echo -e "   • Entry point: $(pwd)/dist/index.js"
echo -e "   • Working directory: $(pwd)"
echo ""

# Step 8: Generate MCP configuration template
print_info "Step 8: Generating MCP configuration template..."
MCP_CONFIG_FILE="mcp-config-template.json"

cat > "${MCP_CONFIG_FILE}" << EOF
{
  "mcpServers": {
    "project-kb": {
      "command": "node",
      "args": ["$(pwd)/dist/index.js"],
      "cwd": "$(pwd)",
      "env": {
        "COGNITO_USER_POOL_ID": "us-east-1_YOUR_POOL_ID",
        "COGNITO_CLIENT_ID": "YOUR_CLIENT_ID",
        "COGNITO_IDENTITY_POOL_ID": "us-east-1:YOUR_IDENTITY_POOL_ID",
        "COGNITO_USERNAME": "your-username",
        "COGNITO_PASSWORD": "your-password",
        "DEFAULT_BACKEND": "bedrock",
        "BEDROCK_KNOWLEDGE_BASE_ID": "YOUR_KB_ID",
        "BEDROCK_REGION": "us-east-1",
        "AWS_REGION": "us-east-1",
        "NODE_ENV": "development",
        "MCP_SERVER": "true"
      },
      "disabled": false,
      "autoApprove": [
        "list_projects",
        "set_active_project",
        "search_all_projects",
        "search",
        "get_document",
        "get_backend_info",
        "switch_backend"
      ]
    }
  }
}
EOF

print_status "MCP configuration template created: ${MCP_CONFIG_FILE}"

# Step 9: Display next steps
echo ""
print_info "🔧 Next Steps:"
echo -e "   1. Update the configuration in ${MCP_CONFIG_FILE} with your actual AWS credentials"
echo -e "   2. Copy the configuration to your Kiro MCP settings (.kiro/settings/mcp.json)"
echo -e "   3. Restart Kiro or reconnect to the MCP server"
echo ""

print_info "📚 For detailed setup instructions, see README.md"
print_info "🔍 For troubleshooting, check the Troubleshooting section in README.md"

echo ""
print_status "Deployment script completed successfully! 🎉"