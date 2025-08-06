#!/bin/bash

# Test Podman Setup Script
# Verifies that Podman environment is working correctly

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_test() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

print_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo "🧪 Testing Podman Setup for MCP Server"
echo "======================================"

# Test 1: Check Podman installation
print_test "Checking Podman installation..."
if command -v podman &> /dev/null; then
    PODMAN_VERSION=$(podman --version)
    print_pass "Podman is installed: $PODMAN_VERSION"
else
    print_fail "Podman is not installed"
    exit 1
fi

# Test 2: Check podman-compose installation
print_test "Checking podman-compose installation..."
if command -v podman-compose &> /dev/null; then
    COMPOSE_VERSION=$(podman-compose --version 2>/dev/null || echo "version unknown")
    print_pass "podman-compose is installed: $COMPOSE_VERSION"
else
    print_fail "podman-compose is not installed"
    echo "Install with: pip install podman-compose"
    exit 1
fi

# Test 3: Check Podman functionality
print_test "Testing basic Podman functionality..."
if podman run --rm hello-world &> /dev/null; then
    print_pass "Podman can run containers"
else
    print_fail "Podman cannot run containers"
    echo "Check Podman installation and permissions"
    exit 1
fi

# Test 4: Check if running rootless
print_test "Checking rootless mode..."
if podman system info | grep -q "rootless.*true"; then
    print_pass "Running in rootless mode (recommended)"
else
    print_warn "Not running in rootless mode"
fi

# Test 5: Check network creation
print_test "Testing network creation..."
TEST_NETWORK="test-mcp-network"
if podman network create $TEST_NETWORK &> /dev/null; then
    print_pass "Can create networks"
    podman network rm $TEST_NETWORK &> /dev/null
else
    print_fail "Cannot create networks"
fi

# Test 6: Check volume mounting
print_test "Testing volume mounting..."
TEST_DIR="/tmp/podman-test-$$"
mkdir -p "$TEST_DIR"
echo "test" > "$TEST_DIR/test.txt"

if podman run --rm -v "$TEST_DIR:/test:Z" alpine cat /test/test.txt 2>/dev/null | grep -q "test"; then
    print_pass "Volume mounting works"
else
    print_warn "Volume mounting had issues (may work in actual usage)"
fi
rm -rf "$TEST_DIR"

# Test 7: Check AWS CLI
print_test "Checking AWS CLI..."
if command -v aws &> /dev/null; then
    print_pass "AWS CLI is installed"
    
    # Test AWS credentials
    if aws sts get-caller-identity &> /dev/null; then
        AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
        print_pass "AWS credentials are configured (Account: $AWS_ACCOUNT)"
    else
        print_warn "AWS credentials not configured"
    fi
else
    print_fail "AWS CLI is not installed"
fi

# Test 8: Check environment file
print_test "Checking environment configuration..."
if [ -f .env ]; then
    print_pass ".env file exists"
    
    # Check for required variables
    REQUIRED_VARS=("AWS_REGION" "BUCKET_NAME")
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^$var=" .env; then
            print_pass "$var is configured"
        else
            print_warn "$var is not configured in .env"
        fi
    done
else
    print_warn ".env file not found - run setup-podman-dev.sh first"
fi

# Test 9: Test compose file syntax
print_test "Validating Podman Compose file..."
if podman-compose -f podman-compose.yml config &> /dev/null; then
    print_pass "podman-compose.yml is valid"
else
    print_fail "podman-compose.yml has syntax errors"
fi

# Test 10: Check required ports
print_test "Checking port availability..."
REQUIRED_PORTS=(3000 3001)
for port in "${REQUIRED_PORTS[@]}"; do
    if ! nc -z localhost $port 2>/dev/null; then
        print_pass "Port $port is available"
    else
        print_warn "Port $port is already in use"
    fi
done

# Test 11: Test image build
print_test "Testing image build..."
if podman build -t mcp-server-test . &> /dev/null; then
    print_pass "Can build MCP server image"
    podman rmi mcp-server-test &> /dev/null
else
    print_fail "Cannot build MCP server image"
fi

# Summary
echo ""
echo "🎯 Test Summary"
echo "==============="

# Count passed/failed tests
TOTAL_TESTS=11
echo "Completed $TOTAL_TESTS tests"

echo ""
echo "✅ If all tests passed, you can start the MCP server with:"
echo "   ./scripts/podman-dev.sh start"
echo ""
echo "📚 For more information, see PODMAN_SETUP.md"