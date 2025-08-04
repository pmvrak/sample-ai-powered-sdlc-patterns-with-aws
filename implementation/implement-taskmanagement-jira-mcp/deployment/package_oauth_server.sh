#!/bin/bash
set -e

echo "📦 Creating OAuth Server deployment package..."

# Clean previous package
rm -rf deployment/oauth-server-package
rm -f deployment/oauth-server-deployment.zip
mkdir -p deployment/oauth-server-package

# Copy OAuth server code
echo "📁 Copying OAuth server code..."
cp deployment/oauth_handler.py deployment/oauth-server-package/

# Install minimal dependencies for OAuth server
echo "📚 Installing dependencies..."
pip install boto3 -t deployment/oauth-server-package/ \
    --upgrade \
    --no-cache-dir 

# Remove unnecessary files to reduce package size
echo "🧹 Cleaning up unnecessary files..."
find deployment/oauth-server-package/ -type d -name "__pycache__" -exec rm -rf {} +
find deployment/oauth-server-package/ -name "*.pyc" -delete
find deployment/oauth-server-package/ -name "*.pyo" -delete
find deployment/oauth-server-package/ -name "*.dist-info" -exec rm -rf {} +
find deployment/oauth-server-package/ -name "tests" -type d -exec rm -rf {} +

# Create ZIP file
echo "🗜️  Creating ZIP package..."
cd deployment/oauth-server-package
zip -r ../oauth-server-deployment.zip . -q
cd ../..

# Check package size
PACKAGE_SIZE=$(du -sh deployment/oauth-server-deployment.zip | cut -f1)
echo "✅ OAuth Server package created: deployment/oauth-server-deployment.zip"
echo "📊 Package size: $PACKAGE_SIZE"
