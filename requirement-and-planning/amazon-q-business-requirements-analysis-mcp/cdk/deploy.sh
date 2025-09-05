#!/bin/bash

# Load environment variables from deployment_config.env
if [ -f "../deployment_config.env" ]; then
    source ../deployment_config.env
    echo "✅ Loaded configuration from deployment_config.env"
else
    echo "❌ deployment_config.env not found. Please create it first."
    exit 1
fi

# Check if required variables are set
required_vars=("ACCOUNT_ID" "REGION" "Q_BUSINESS_APP_ID" "IDC_INSTANCE_ID" "EXISTING_COGNITO_USER_POOL_ID" "EXISTING_COGNITO_CLIENT_ID")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required variable $var is not set in deployment_config.env"
        exit 1
    fi
done

echo "🚀 Starting CDK deployment..."
echo "Account: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Stack: $STACK_NAME"

# Set up virtual environment and install dependencies
echo "📦 Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅ Created virtual environment"
fi

echo "📦 Activating virtual environment and installing CDK dependencies..."
source .venv/bin/activate
pip install -r requirements.txt

# Bootstrap CDK if needed
echo "🔧 Bootstrapping CDK..."
source .venv/bin/activate
cdk bootstrap aws://$ACCOUNT_ID/$REGION

# Create ECR repository if it doesn't exist
echo "🏗️ Creating ECR repository if needed..."
aws ecr create-repository --repository-name $REPOSITORY_NAME --region $REGION || echo "Repository already exists"

# Clean up Docker images first
echo "🧹 Cleaning up existing Docker images..."
docker rmi ${REPOSITORY_NAME}:${IMAGE_TAG} 2>/dev/null || true
docker rmi ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPOSITORY_NAME}:${IMAGE_TAG} 2>/dev/null || true
docker system prune -f

# Build and push Docker image
echo "🔨 Building Docker image..."
cd ../mcp_server
DOCKER_BUILDKIT=1 docker buildx build --no-cache --pull --platform=linux/amd64 --load -t ${REPOSITORY_NAME}:${IMAGE_TAG} .

echo "🔑 Logging in to ECR..."
aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

echo "📦 Tagging and pushing image..."
docker tag ${REPOSITORY_NAME}:${IMAGE_TAG} ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPOSITORY_NAME}:${IMAGE_TAG}
docker push ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPOSITORY_NAME}:${IMAGE_TAG}

echo "✅ Docker image pushed successfully!"
cd ../cdk

# Deploy the stack
echo "🚀 Deploying CDK stack..."
source .venv/bin/activate
cdk deploy --require-approval never

echo "✅ Deployment complete!"
echo ""
echo "📋 Stack outputs:"
echo "Check the AWS Console or run 'aws cloudformation describe-stacks --stack-name $STACK_NAME' for outputs"