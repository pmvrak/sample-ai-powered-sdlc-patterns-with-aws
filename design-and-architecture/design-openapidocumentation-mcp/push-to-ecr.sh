#!/bin/bash

# Script to build and push MCP server image to ECR using Podman

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

# Configuration
REGION=${AWS_REGION:-"us-east-1"}
ECR_URI=""
IMAGE_TAG="latest"
FORCE_BUILD=false
PLATFORM="linux/amd64"  # Ensure x86_64 architecture

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --ecr-uri)
      ECR_URI="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --force-build)
      FORCE_BUILD=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --ecr-uri URI       ECR repository URI (required)"
      echo "  --region REGION     AWS region (default: eu-west-1)"
      echo "  --tag TAG           Image tag (default: latest)"
      echo "  --force-build       Force rebuild even if image exists"
      echo "  --platform PLATFORM Target platform (default: linux/amd64)"
      echo "  --help, -h          Show this help message"
      echo ""
      echo "Example:"
      echo "  $0 --ecr-uri 246217239581.dkr.ecr.eu-west-1.amazonaws.com/mcp-server-246217239581"
      exit 0
      ;;
    *)
      print_error "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Check if ECR URI is provided
if [ -z "$ECR_URI" ]; then
    # Try to get it from the deployment outputs
    if [ -f "mcp-server-outputs.json" ]; then
        ECR_URI=$(cat mcp-server-outputs.json | grep -o '"EcrRepositoryUri": "[^"]*"' | cut -d'"' -f4)
        if [ -n "$ECR_URI" ]; then
            print_status "Found ECR URI from deployment outputs: $ECR_URI"
        fi
    fi
    
    if [ -z "$ECR_URI" ]; then
        print_error "ECR URI is required!"
        print_error "Either provide --ecr-uri or ensure mcp-server-outputs.json exists"
        print_error "You can find the ECR URI in the deployment outputs"
        exit 1
    fi
fi

# Extract account ID and repository name from ECR URI
ACCOUNT_ID=$(echo $ECR_URI | cut -d'.' -f1)
REPO_NAME=$(echo $ECR_URI | cut -d'/' -f2)

print_status "Using ECR repository: $ECR_URI"
print_status "Region: $REGION"
print_status "Image tag: $IMAGE_TAG"

# Navigate to mcp-server directory
if [ -d "mcp-server" ]; then
    # mcp-server is a subdirectory
    cd mcp-server
elif [ -d "../mcp-server" ]; then
    # mcp-server is at the same level (sibling directory)
    cd ../mcp-server
else
    print_error "mcp-server directory not found!"
    print_error "Expected to find mcp-server either as a subdirectory or sibling directory"
    print_error "Current directory: $(pwd)"
    print_error "Available directories:"
    ls -la
    exit 1
fi

# Check if Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    print_error "Dockerfile not found in mcp-server directory!"
    exit 1
fi

# Check if podman is available
if ! command -v podman &> /dev/null; then
    print_error "Podman is not installed or not in PATH"
    print_error "Please install podman first"
    exit 1
fi

# Local image name
LOCAL_IMAGE="mcp-server:$IMAGE_TAG"

# Check if image exists locally and build if needed
if podman image exists $LOCAL_IMAGE && [ "$FORCE_BUILD" = false ]; then
    print_status "Local image $LOCAL_IMAGE already exists"
    print_status "Use --force-build to rebuild"
else
    print_status "Building MCP server image with Podman..."
    
    # Build the image using podman with specific platform (x86_64/amd64)
    if [ "$FORCE_BUILD" = true ]; then
        print_status "Force rebuilding (no cache) for platform $PLATFORM..."
        podman build --no-cache --platform=$PLATFORM -t $LOCAL_IMAGE .
    else
        print_status "Building for platform $PLATFORM..."
        podman build --platform=$PLATFORM -t $LOCAL_IMAGE .
    fi
    
    print_success "Image built successfully: $LOCAL_IMAGE"
fi

# Login to ECR
print_status "Logging in to ECR..."
aws ecr get-login-password --region $REGION | podman login --username AWS --password-stdin $ECR_URI

if [ $? -ne 0 ]; then
    print_error "Failed to login to ECR"
    print_error "Make sure your AWS credentials are configured"
    exit 1
fi

print_success "Successfully logged in to ECR"

# Tag the image for ECR
ECR_IMAGE="$ECR_URI:$IMAGE_TAG"
print_status "Tagging image for ECR: $ECR_IMAGE"
podman tag $LOCAL_IMAGE $ECR_IMAGE

# Push the image to ECR
print_status "Pushing image to ECR..."
podman push $ECR_IMAGE

if [ $? -eq 0 ]; then
    print_success "Successfully pushed image to ECR!"
    print_success "Image: $ECR_IMAGE"
    
    # Show next steps
    echo ""
    print_status "Next steps:"
    print_status "1. Scale up your ECS service to start containers:"
    print_status "   aws ecs update-service --cluster mcp-server-cluster --service McpServerStack-McpServerService39099FFD-REbstBpfdnzd --desired-count 1 --region $REGION"
    print_status ""
    print_status "2. Or use the AWS Console to update the service desired count"
    print_status ""
    print_status "3. Monitor the deployment:"
    print_status "   aws ecs describe-services --cluster mcp-server-cluster --services McpServerStack-McpServerService39099FFD-REbstBpfdnzd --region $REGION"
    
else
    print_error "Failed to push image to ECR"
    exit 1
fi

# Clean up local ECR-tagged image to save space
print_status "Cleaning up ECR-tagged image locally..."
podman rmi $ECR_IMAGE 2>/dev/null || true

print_success "Build and push completed!"