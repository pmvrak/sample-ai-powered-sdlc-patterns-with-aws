#!/bin/bash
set -e

echo "📦 Creating Lambda deployment package..."

# Clean previous package
rm -rf deployment/lambda-package
rm -f deployment/lambda-deployment.zip
mkdir -p deployment/lambda-package

# Copy source code
echo "📁 Copying source code..."
cp -r src/ deployment/lambda-package/
cp deployment/minimal_mcp_handler.py deployment/lambda-package/lambda_handler.py

# Install minimal dependencies for Lambda
echo "📚 Installing minimal dependencies..."
pip install -r requirements-minimal.txt -t deployment/lambda-package/ \
    --upgrade \
    --no-cache-dir 

# Remove unnecessary files to reduce package size
echo "🧹 Cleaning up unnecessary files..."
find deployment/lambda-package/ -type d -name "__pycache__" -exec rm -rf {} +
find deployment/lambda-package/ -name "*.pyc" -delete
find deployment/lambda-package/ -name "*.pyo" -delete
find deployment/lambda-package/ -name "*.dist-info" -exec rm -rf {} +
find deployment/lambda-package/ -name "tests" -type d -exec rm -rf {} +

# Create ZIP file
echo "🗜️  Creating ZIP package..."
cd deployment/lambda-package
zip -r ../lambda-deployment.zip . -q
cd ../..

# Check package size (Lambda limit is 50MB compressed)
PACKAGE_SIZE=$(du -sh deployment/lambda-deployment.zip | cut -f1)
echo "✅ Lambda package created: deployment/lambda-deployment.zip"
echo "📊 Package size: $PACKAGE_SIZE"

# Warn if package is getting large
# Check if we're on macOS (BSD du) or Linux (GNU du)
if du -b /dev/null >/dev/null 2>&1; then
    # GNU du (Linux) - supports -b flag
    PACKAGE_SIZE_BYTES=$(du -b deployment/lambda-deployment.zip | cut -f1)
else
    # BSD du (macOS) - use stat instead
    PACKAGE_SIZE_BYTES=$(stat -f%z deployment/lambda-deployment.zip)
fi

if [ $PACKAGE_SIZE_BYTES -gt 45000000 ]; then  # 45MB warning threshold
    echo "⚠️  Warning: Package size is getting close to Lambda's 50MB limit!"
fi