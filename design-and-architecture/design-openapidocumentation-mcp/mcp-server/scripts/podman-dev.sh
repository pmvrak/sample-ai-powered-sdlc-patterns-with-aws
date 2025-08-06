#!/bin/bash

# Podman Development Helper Script
# Provides convenient commands for Podman-based development

set -e

COMPOSE_FILE="podman-compose.yml"
PROJECT_NAME="mcp-server"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Function to check if .env file exists
check_env_file() {
    if [ ! -f .env ]; then
        print_error ".env file not found!"
        print_status "Run './scripts/setup-podman-dev.sh' first to create the environment file"
        exit 1
    fi
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start           Start the MCP server"
    echo "  stop            Stop all services"
    echo "  restart         Restart the MCP server"
    echo "  logs            Show logs (follow mode)"
    echo "  logs-once       Show logs (one-time)"
    echo "  build           Build the MCP server image"
    echo "  rebuild         Rebuild the MCP server image (no cache)"
    echo "  shell           Open shell in MCP server container"
    echo "  dev-tools       Start with development tools"
    echo "  status          Show container status"
    echo "  clean           Clean up containers and images"
    echo "  health          Check health status"
    echo "  env             Show environment configuration"
    echo "  test            Run a quick test of the server"
    echo "  info            Show MCP server information and capabilities"
    echo "  tools           List available MCP tools"
    echo "  test-tools      Test individual MCP tools with sample data"
    echo ""
    echo "Examples:"
    echo "  $0 start                    # Start MCP server"
    echo "  $0 dev-tools               # Start with dev tools"
    echo "  $0 logs                    # Follow logs"
    echo "  $0 shell                   # Open shell in container"
}

# Main command handling
case "${1:-}" in
    "start")
        print_header "Starting HTTP MCP Server with Podman"
        check_env_file
        
        # Try podman-compose first, fallback to direct podman commands
        if command -v podman-compose &> /dev/null; then
            podman-compose -f $COMPOSE_FILE up -d
        else
            print_warning "podman-compose not found, using direct podman commands"
            # Build image if it doesn't exist
            if ! podman image exists localhost/mcp-server_mcp-server:latest; then
                print_status "Building MCP server image..."
                podman build -t localhost/mcp-server_mcp-server:latest .
            fi
            
            # Create network if it doesn't exist
            if ! podman network exists mcp-network 2>/dev/null; then
                podman network create mcp-network
            fi
            
            # Run container
            podman run -d \
                --name mcp-server-dev \
                --network mcp-network \
                -p 3000:3000 \
                -p 3001:3001 \
                --env-file .env \
                -v ./logs:/app/logs:Z \
                -v ~/.aws:/home/mcp/.aws:ro,Z \
                localhost/mcp-server_mcp-server:latest
        fi
        
        print_status "HTTP MCP Server started!"
        print_status "Health check: http://localhost:3000/health"
        print_status "Server info: http://localhost:3001/mcp/info"
        print_status "Tools list: http://localhost:3001/mcp/tools"
        print_status "MCP HTTP API: http://localhost:3001"
        ;;
    
    "stop")
        print_header "Stopping Services"
        if command -v podman-compose &> /dev/null; then
            podman-compose -f $COMPOSE_FILE down
        else
            # Fallback to direct podman commands
            podman stop mcp-server-dev 2>/dev/null || true
            podman rm mcp-server-dev 2>/dev/null || true
        fi
        print_status "Services stopped"
        ;;
    
    "restart")
        print_header "Restarting MCP Server"
        $0 stop
        sleep 2
        $0 start
        print_status "MCP Server restarted"
        ;;
    
    "logs")
        print_header "Following Logs"
        if command -v podman-compose &> /dev/null && podman-compose -f $COMPOSE_FILE ps | grep -q "mcp-server"; then
            podman-compose -f $COMPOSE_FILE logs -f
        else
            # Fallback to direct podman logs
            podman logs -f mcp-server-dev 2>/dev/null || print_error "Container not found. Start it first with: $0 start"
        fi
        ;;
    
    "logs-once")
        print_header "Showing Logs"
        if command -v podman-compose &> /dev/null && podman-compose -f $COMPOSE_FILE ps | grep -q "mcp-server"; then
            podman-compose -f $COMPOSE_FILE logs
        else
            # Fallback to direct podman logs
            podman logs mcp-server-dev 2>/dev/null || print_error "Container not found. Start it first with: $0 start"
        fi
        ;;
    
    "build")
        print_header "Building MCP Server Image"
        if command -v podman-compose &> /dev/null; then
            podman-compose -f $COMPOSE_FILE build
        else
            # Fallback to direct podman build
            podman build -t localhost/mcp-server_mcp-server:latest .
        fi
        print_status "Build completed"
        ;;
    
    "rebuild")
        print_header "Rebuilding MCP Server Image (No Cache)"
        if command -v podman-compose &> /dev/null; then
            podman-compose -f $COMPOSE_FILE build --no-cache
        else
            # Fallback to direct podman build
            podman build --no-cache -t localhost/mcp-server_mcp-server:latest .
        fi
        print_status "Rebuild completed"
        ;;
    
    "shell")
        print_header "Opening Shell in MCP Server Container"
        # Try to find running container
        if podman ps --format "{{.Names}}" | grep -q "mcp-server"; then
            CONTAINER_NAME=$(podman ps --format "{{.Names}}" | grep "mcp-server" | head -1)
            podman exec -it $CONTAINER_NAME sh
        elif podman ps --format "{{.Names}}" | grep -q "mcp-server-dev"; then
            podman exec -it mcp-server-dev sh
        else
            print_error "MCP Server container is not running"
            print_status "Start it first with: $0 start"
        fi
        ;;
    
    "dev-tools")
        print_header "Starting with Development Tools"
        check_env_file
        if command -v podman-compose &> /dev/null; then
            podman-compose -f $COMPOSE_FILE --profile dev-tools up -d
            print_status "Services started with development tools"
            print_status "Access dev-tools container: podman exec -it \$(podman ps -q --filter name=dev-tools) sh"
        else
            print_warning "podman-compose not available. Starting main server only."
            $0 start
        fi
        ;;
    
    "status")
        print_header "Container Status"
        if command -v podman-compose &> /dev/null; then
            podman-compose -f $COMPOSE_FILE ps 2>/dev/null || print_warning "podman-compose status unavailable"
        fi
        
        echo ""
        print_header "Running Containers"
        podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        
        echo ""
        print_header "Podman System Info"
        podman system info --format "{{.Host.Hostname}} - {{.Host.OS}}" 2>/dev/null || echo "System info unavailable"
        ;;
    
    "clean")
        print_header "Cleaning Up"
        print_warning "This will remove containers and unused images"
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Stop and remove containers
            if command -v podman-compose &> /dev/null; then
                podman-compose -f $COMPOSE_FILE down -v 2>/dev/null || true
            fi
            
            # Clean up direct podman containers
            podman stop mcp-server-dev 2>/dev/null || true
            podman rm mcp-server-dev 2>/dev/null || true
            
            # System cleanup
            podman system prune -f
            print_status "Cleanup completed"
        else
            print_status "Cleanup cancelled"
        fi
        ;;
    
    "health")
        print_header "Health Check"
        if curl -f -s http://localhost:3000/health > /dev/null 2>&1; then
            print_status "✅ MCP Server is healthy"
            curl -s http://localhost:3000/health | jq . 2>/dev/null || curl -s http://localhost:3000/health
        else
            print_error "❌ MCP Server health check failed"
            print_status "Check if the server is running: $0 status"
        fi
        ;;
    
    "env")
        print_header "Environment Configuration"
        if [ -f .env ]; then
            echo "Environment variables from .env:"
            grep -v '^#' .env | grep -v '^$' | sort
        else
            print_error ".env file not found"
        fi
        ;;
    
    "test")
        print_header "Quick HTTP MCP Server Test"
        check_env_file
        
        # Check if server is running, start if not
        if ! curl -f -s http://localhost:3000/health > /dev/null 2>&1; then
            print_status "Starting HTTP MCP Server for testing..."
            $0 start
            print_status "Waiting for server to fully initialize..."
            
            # Wait up to 60 seconds for the server to be ready
            for i in {1..12}; do
                sleep 5
                if curl -f -s http://localhost:3000/health > /dev/null 2>&1; then
                    print_status "✅ Server is ready after ${i}0 seconds"
                    break
                fi
                print_status "Waiting... (${i}0s)"
            done
        fi
        
        # Test health endpoint
        print_status "Testing health endpoint..."
        if curl -f -s http://localhost:3000/health > /dev/null; then
            print_status "✅ Health check passed"
        else
            print_error "❌ Health check failed"
        fi
        
        # Test readiness endpoint
        print_status "Testing readiness endpoint..."
        if curl -f -s http://localhost:3000/ready > /dev/null; then
            print_status "✅ Readiness check passed"
        else
            print_error "❌ Readiness check failed"
        fi
        
        # Test MCP HTTP endpoints
        print_status "Testing MCP HTTP endpoints..."
        
        # Test server info
        if curl -f -s http://localhost:3001/mcp/info > /dev/null; then
            print_status "✅ MCP server info endpoint accessible"
        else
            print_error "❌ MCP server info endpoint failed"
        fi
        
        # Test tools list
        if curl -f -s http://localhost:3001/mcp/tools > /dev/null; then
            print_status "✅ MCP tools endpoint accessible"
        else
            print_error "❌ MCP tools endpoint failed"
        fi
        
        # Test port accessibility
        print_status "Testing port accessibility..."
        if nc -z localhost 3001 2>/dev/null; then
            print_status "✅ MCP HTTP port (3001) is accessible"
        else
            print_error "❌ MCP HTTP port (3001) is not accessible"
        fi
        
        if nc -z localhost 3000 2>/dev/null; then
            print_status "✅ Health port (3000) is accessible"
        else
            print_error "❌ Health port (3000) is not accessible"
        fi
        ;;
    
    "info")
        print_header "MCP Server Information"
        if curl -f -s http://localhost:3001/mcp/info > /dev/null 2>&1; then
            print_status "📋 Server Information:"
            curl -s http://localhost:3001/mcp/info | jq . 2>/dev/null || curl -s http://localhost:3001/mcp/info
        else
            print_error "❌ Cannot connect to MCP server"
            print_status "Make sure the server is running: $0 start"
        fi
        ;;
    
    "tools")
        print_header "Available MCP Tools"
        if curl -f -s http://localhost:3001/mcp/tools > /dev/null 2>&1; then
            print_status "🔧 Available Tools:"
            curl -s http://localhost:3001/mcp/tools | jq . 2>/dev/null || curl -s http://localhost:3001/mcp/tools
        else
            print_error "❌ Cannot connect to MCP server"
            print_status "Make sure the server is running: $0 start"
        fi
        ;;
    
    "test-tools")
        print_header "Testing MCP Tools with Sample Data"
        
        # Check if server is running
        if ! curl -f -s http://localhost:3001/mcp/info > /dev/null 2>&1; then
            print_error "❌ MCP server is not running"
            print_status "Start it first with: $0 start"
            exit 1
        fi
        
        print_status "🧪 Testing Domain Analysis Tool..."
        curl -X POST http://localhost:3001/mcp/tools/domain_analysis \
            -H "Content-Type: application/json" \
            -d '{
                "arguments": {
                    "domains": ["user-management", "order-processing"],
                    "business_context": "E-commerce platform with user accounts and order management",
                    "analysis_depth": "basic"
                }
            }' \
            -s | jq '.success // false' > /dev/null 2>&1 && \
            print_status "✅ Domain Analysis tool responded" || \
            print_warning "⚠️  Domain Analysis tool may have issues (check AWS credentials)"
        
        print_status "🧪 Testing Documentation Generation Tool..."
        curl -X POST http://localhost:3001/mcp/tools/generate_documentation \
            -H "Content-Type: application/json" \
            -d '{
                "arguments": {
                    "domain_model": "User entity with properties: id, email, name, created_at",
                    "api_type": "REST",
                    "include_security": true,
                    "output_format": "openapi"
                }
            }' \
            -s | jq '.success // false' > /dev/null 2>&1 && \
            print_status "✅ Documentation Generation tool responded" || \
            print_warning "⚠️  Documentation Generation tool may have issues (check AWS credentials)"
        
        print_status "🧪 Testing OpenAPI Generator Tool..."
        curl -X POST http://localhost:3001/mcp/tools/generate_openapi_spec \
            -H "Content-Type: application/json" \
            -d '{
                "arguments": {
                    "info": {
                        "title": "Test API",
                        "version": "1.0.0",
                        "description": "Test API for validation"
                    },
                    "apiStyle": "REST",
                    "authenticationScheme": "bearer"
                }
            }' \
            -s | jq '.success // false' > /dev/null 2>&1 && \
            print_status "✅ OpenAPI Generator tool responded" || \
            print_warning "⚠️  OpenAPI Generator tool may have issues (check AWS credentials)"
        
        print_status "🎯 Tool testing completed!"
        print_status "Note: Tool failures are expected if AWS credentials are not properly configured"
        ;;
    
    "help"|"--help"|"-h"|"")
        show_usage
        ;;
    
    *)
        print_error "Unknown command: $1"
        echo ""
        show_usage
        exit 1
        ;;
esac