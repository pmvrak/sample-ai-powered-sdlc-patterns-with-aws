#!/bin/bash

# Deploy to Production Environment
# Usage: ./scripts/deploy-production.sh

set -e

echo "🚀 Starting deployment to production environment..."

# Configuration
PRODUCTION_ENV_FILE=".env.production"
DOCKER_IMAGE="project-kb-mcp-server:production"
CONTAINER_NAME="project-kb-mcp-production"
PRODUCTION_PORT="3000"
BACKUP_CONTAINER_NAME="project-kb-mcp-production-backup"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_prompt() {
    echo -e "${BLUE}[PROMPT]${NC} $1"
}

# Confirmation prompt
confirm_deployment() {
    print_prompt "⚠️  You are about to deploy to PRODUCTION environment!"
    print_prompt "This will replace the current production deployment."
    print_prompt ""
    read -p "Are you sure you want to continue? (yes/no): " -r
    echo
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        print_status "Deployment cancelled by user"
        exit 0
    fi
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
    
    if [ ! -f "$PRODUCTION_ENV_FILE" ]; then
        print_error "Production environment file $PRODUCTION_ENV_FILE not found"
        print_warning "Please create $PRODUCTION_ENV_FILE with production configuration"
        exit 1
    fi
    
    # Check if we're on main/master branch
    current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    if [[ "$current_branch" != "main" && "$current_branch" != "master" ]]; then
        print_warning "Current branch is '$current_branch', not main/master"
        read -p "Continue anyway? (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            print_status "Deployment cancelled"
            exit 0
        fi
    fi
    
    print_status "Prerequisites check passed ✓"
}

# Run comprehensive tests
run_tests() {
    print_status "Running comprehensive test suite..."
    
    # Type checking
    print_status "Running type check..."
    npm run typecheck
    if [ $? -ne 0 ]; then
        print_error "Type check failed. Deployment aborted."
        exit 1
    fi
    
    # Linting
    print_status "Running linter..."
    npm run lint
    if [ $? -ne 0 ]; then
        print_error "Linting failed. Deployment aborted."
        exit 1
    fi
    
    # Unit tests
    print_status "Running unit tests..."
    npm run test
    if [ $? -ne 0 ]; then
        print_error "Tests failed. Deployment aborted."
        exit 1
    fi
    
    # Coverage check (optional)
    if command -v npm run test:coverage &> /dev/null; then
        print_status "Running test coverage..."
        npm run test:coverage
    fi
    
    print_status "All tests passed ✓"
}

# Build application
build_application() {
    print_status "Building application for production..."
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

# Backup current container
backup_current_container() {
    print_status "Creating backup of current production container..."
    
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        # Stop current container
        docker stop "$CONTAINER_NAME"
        
        # Rename to backup
        docker rename "$CONTAINER_NAME" "$BACKUP_CONTAINER_NAME"
        print_status "Current container backed up as $BACKUP_CONTAINER_NAME ✓"
    else
        print_status "No existing production container found"
    fi
}

# Deploy new container
deploy_container() {
    print_status "Deploying new production container..."
    docker run -d \
        --name "$CONTAINER_NAME" \
        --env-file "$PRODUCTION_ENV_FILE" \
        -p "$PRODUCTION_PORT:3000" \
        --restart unless-stopped \
        --memory="512m" \
        --cpus="1.0" \
        "$DOCKER_IMAGE"
    
    if [ $? -ne 0 ]; then
        print_error "Container deployment failed"
        rollback_deployment
        exit 1
    fi
    
    print_status "Container deployed ✓"
}

# Comprehensive health check
health_check() {
    print_status "Performing comprehensive health check..."
    
    # Wait for container to start
    sleep 10
    
    # Check if container is running
    if ! docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        print_error "Container is not running"
        docker logs "$CONTAINER_NAME"
        rollback_deployment
        exit 1
    fi
    
    # Check application health
    max_attempts=60
    attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if docker exec "$CONTAINER_NAME" node dist/index.js --health-check &> /dev/null; then
            print_status "Health check passed ✓"
            break
        fi
        
        if [ $attempt -eq $max_attempts ]; then
            print_error "Health check failed after $max_attempts attempts"
            print_error "Container logs:"
            docker logs "$CONTAINER_NAME"
            rollback_deployment
            exit 1
        fi
        
        print_warning "Health check attempt $attempt/$max_attempts failed, retrying..."
        sleep 2
        ((attempt++))
    done
    
    # Additional production health checks
    print_status "Running additional production health checks..."
    
    # Check memory usage
    memory_usage=$(docker stats --no-stream --format "{{.MemPerc}}" "$CONTAINER_NAME" | sed 's/%//')
    if (( $(echo "$memory_usage > 80" | bc -l) )); then
        print_warning "High memory usage: ${memory_usage}%"
    fi
    
    # Check if container is responding to requests (if applicable)
    # Add any additional health checks specific to your application
    
    print_status "All health checks passed ✓"
}

# Rollback deployment
rollback_deployment() {
    print_error "Rolling back deployment..."
    
    # Stop and remove failed container
    if docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        docker stop "$CONTAINER_NAME"
        docker rm "$CONTAINER_NAME"
    fi
    
    # Restore backup if it exists
    if docker ps -a -q -f name="$BACKUP_CONTAINER_NAME" | grep -q .; then
        docker rename "$BACKUP_CONTAINER_NAME" "$CONTAINER_NAME"
        docker start "$CONTAINER_NAME"
        print_status "Rollback completed. Previous version restored."
    else
        print_warning "No backup container found. Manual intervention may be required."
    fi
}

# Cleanup
cleanup() {
    print_status "Cleaning up..."
    
    # Remove backup container if deployment was successful
    if docker ps -a -q -f name="$BACKUP_CONTAINER_NAME" | grep -q .; then
        docker rm "$BACKUP_CONTAINER_NAME"
        print_status "Backup container removed ✓"
    fi
    
    # Clean up old images
    docker image prune -f
    print_status "Old Docker images cleaned up ✓"
}

# Post-deployment verification
post_deployment_verification() {
    print_status "Running post-deployment verification..."
    
    # Verify container is still running after a few minutes
    sleep 30
    if ! docker ps -q -f name="$CONTAINER_NAME" | grep -q .; then
        print_error "Container stopped unexpectedly after deployment"
        docker logs "$CONTAINER_NAME"
        rollback_deployment
        exit 1
    fi
    
    # Run health check again
    if ! docker exec "$CONTAINER_NAME" node dist/index.js --health-check &> /dev/null; then
        print_error "Post-deployment health check failed"
        rollback_deployment
        exit 1
    fi
    
    print_status "Post-deployment verification passed ✓"
}

# Main deployment flow
main() {
    print_status "=== Project KB MCP Server - Production Deployment ==="
    
    confirm_deployment
    check_prerequisites
    run_tests
    build_application
    build_docker_image
    backup_current_container
    deploy_container
    health_check
    post_deployment_verification
    cleanup
    
    print_status "=== Production deployment completed successfully! ==="
    print_status "Container: $CONTAINER_NAME"
    print_status "Port: $PRODUCTION_PORT"
    print_status "Image: $DOCKER_IMAGE"
    print_status ""
    print_status "Useful commands:"
    print_status "  View logs: docker logs -f $CONTAINER_NAME"
    print_status "  Monitor stats: docker stats $CONTAINER_NAME"
    print_status "  Health check: docker exec $CONTAINER_NAME node dist/index.js --health-check"
    print_status ""
    print_status "🎉 Production deployment successful!"
}

# Handle script interruption
trap 'print_error "Deployment interrupted"; rollback_deployment; exit 1' INT TERM

# Run main function
main "$@"