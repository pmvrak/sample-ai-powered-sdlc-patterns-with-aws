#!/bin/bash

# Jenkins MCP Server - Lambda Packaging Script

set -e

echo "📦 Packaging Jenkins MCP Server Lambda function..."

# Clean up previous builds
rm -rf lambda-package
rm -f lambda-deployment.zip

# Create package directory
mkdir -p lambda-package

# Copy source code
echo "📁 Copying source code..."
cp -r src/ lambda-package/
cp deployment/lambda_handler.py lambda-package/
cp deployment/lambda_mcp_server.py lambda-package/

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements-minimal.txt -t lambda-package/

# Remove unnecessary files to reduce package size
echo "🧹 Cleaning up package..."
find lambda-package -name "*.pyc" -delete
find lambda-package -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find lambda-package -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
find lambda-package -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true

# Remove large unnecessary files
rm -rf lambda-package/boto3* 2>/dev/null || true
rm -rf lambda-package/botocore* 2>/dev/null || true

# Create deployment zip
echo "🗜️  Creating deployment package..."
cd lambda-package
zip -r ../lambda-deployment.zip . -q
cd ..

# Get package size
PACKAGE_SIZE=$(du -h lambda-deployment.zip | cut -f1)
echo "✅ Lambda package created: lambda-deployment.zip ($PACKAGE_SIZE)"

# Verify package contents
echo "📋 Package contents:"
unzip -l lambda-deployment.zip | head -20

# Clean up temporary directory
rm -rf lambda-package

echo "🎉 Jenkins MCP Server Lambda package ready for deployment!"
