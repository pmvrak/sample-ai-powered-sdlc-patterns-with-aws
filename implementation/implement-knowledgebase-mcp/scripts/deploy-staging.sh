#!/bin/bash

# Deploy to Staging Environment
# Usage: ./scripts/deploy-staging.sh

set -e

echo "🚀 Starting deployment to staging environment..."

# Configuration
STAGING_ENV_FILE=".env.staging"
DOCKER_IMAGE="project-kb-mcp-server:staging"
CONTAINER_NAME="project-kb-mcp-staging"
STAGING_PORT="3001"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed or not in PATH"
        exit 1
    fi
    
    if [ ! -f "$STAGING_ENV_FILE" ]; then
        print_error "Staging environment file $STAGING_ENV_FILE not found"
        print_warning "Please create $STAGING_ENV_FILE with staging configuration"
        exit 1
    fi
    
    print_status "Prerequisites check passed ✓"
}

# Run tests
run_tests() {
    print_status "Running tests..."
    npm run test
    if [ $? -ne 0 ]; then
        print_error "Tests failed. Deployment aborted."
        exit 1
    fi
    print_status "Tests passed ✓"
}

# Build application
build_application() {
    print_status "Building application..."
    npm run build
    if [ $? -ne 0 ]; then
        print_error "Build failed. Deployment aborted."
        exit 1
    fi
    print_status "Build completed ✓"
}

# Build Docker image
build_docker_image() {
    print_status "Building Docker image: $DOCKER_IMAGE"
    docker build -t "$DOCKER_IMAGE" .
    if [ $? -ne 0 ]; then
        print_error "Docker build failed. Deployment aborted."
        exit 1
    fi
    print_status "Docker image built ✓"
}

# Stop existing container
stop_existing_container() {
    print_status "Stopping existing container if running..."
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        docker stop "$CONTAINER_NAME"
        docker rm "$CONTAINER_NAME"
        print_status "Existing container stopped and removed ✓"
    else
        print_status "No existing container found"
    fi
}

# Deploy container
deploy_container() {
    print_status "Deploying new container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        --env-file "$STAGING_ENV_FILE" \
        -p "$STAGING_PORT:3000" \
        --restart unless-stopped \
        "$DOCKER_IMAGE"
    
    if [ $? -ne 0 ]; then
        print_error "Container deployment failed"
        exit 1
    fi
    
    print_status "Container deployed ✓"
}

# Health check
health_check() {
    print_status "Performing health check..."
    
    # Wait for container to start
    sleep 5
    
    # Check if container is running
    if ! docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        print_error "Container is not running"
        docker logs "$CONTAINER_NAME"
        exit 1
    fi
    
    # Check application health
    max_attempts=30
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec "$CONTAINER_NAME" node dist/index.js --health-check &> /dev/null; then
            print_status "Health check passed ✓"
            return 0
        fi
        
        print_warning "Health check attempt $attempt/$max_attempts failed, retrying..."
        sleep 2
        ((attempt++))
    done
    
    print_error "Health check failed after $max_attempts attempts"
    print_error "Container logs:"
    docker logs "$CONTAINER_NAME"
    exit 1
}

# Cleanup old images
cleanup() {
    print_status "Cleaning up old Docker images..."
    docker image prune -f
    print_status "Cleanup completed ✓"
}

# Main deployment flow
main() {
    print_status "=== Project KB MCP Server - Staging Deployment ==="
    
    check_prerequisites
    run_tests
    build_application
    build_docker_image
    stop_existing_container
    deploy_container
    health_check
    cleanup
    
    print_status "=== Deployment to staging completed successfully! ==="
    print_status "Container: $CONTAINER_NAME"
    print_status "Port: $STAGING_PORT"
    print_status "Image: $DOCKER_IMAGE"
    print_status ""
    print_status "Useful commands:"
    print_status "  View logs: docker logs -f $CONTAINER_NAME"
    print_status "  Stop container: docker stop $CONTAINER_NAME"
    print_status "  Remove container: docker rm $CONTAINER_NAME"
}

# Handle script interruption
trap 'print_error "Deployment interrupted"; exit 1' INT TERM

# Run main function
main "$@"