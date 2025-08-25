#!/bin/bash

# Consolidated Incident Management Infrastructure Deployment Script
# Supports both Lambda and ECS deployments with full secret management

set -e

# Default values - Development only
ENVIRONMENT="dev"
ACTION="deploy"
STACK_NAME=""
PROFILE=""
DEPLOYMENT_TYPE="ecs"  # ECS only
POPULATE_SECRETS="true"



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

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy incident management infrastructure using AWS CDK

OPTIONS:
    -r, --region REGION      AWS region [default: from .env file or us-east-1]
    -a, --account ACCOUNT    AWS account ID [default: from .env file]
    -p, --profile PROFILE    AWS profile to use
    -s, --stack STACK        Specific stack to deploy (ecs) [default: ecs]
    -c, --action ACTION      Action to perform (deploy, destroy, diff, synth) [default: deploy]
    --skip-secrets          Skip populating secrets from .env
    -h, --help              Show this help message

EXAMPLES:
    # Deploy ECS stack (using .env file configuration)
    $0

    # Deploy ECS stack with specific account override
    $0 -a 123456789012

    # Deploy ECS stack without updating secrets
    $0 --skip-secrets

    # Show diff for deployment
    $0 -c diff

    # Destroy environment
    $0 -c destroy

DEPLOYMENT TYPE:
    ECS Fargate containerized deployment only

STACK OPTIONS:
    ecs                     Deploy the ECS-based containerized stack

ENVIRONMENT VARIABLES:
    AWS_ACCOUNT_ID          AWS account ID (alternative to -a flag)
    CDK_DEFAULT_ACCOUNT     AWS account ID (CDK default)
    CDK_DEFAULT_REGION      AWS region (CDK default)

EOF
}

# Load environment variables from .env file
ENV_FILE="$(dirname "$0")/../.env"
if [[ -f "$ENV_FILE" ]]; then
    print_status "Loading configuration from .env file..."
    source "$ENV_FILE"
    # Use the standardized variable names
    AWS_REGION="${AWS_REGION:-us-east-1}"
    AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
else
    print_warning ".env file not found at $ENV_FILE"
    # Set defaults
    AWS_REGION="us-east-1"
    AWS_ACCOUNT_ID=""
fi

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -a|--account)
            AWS_ACCOUNT_ID="$2"
            shift 2
            ;;
        -p|--profile)
            PROFILE="$2"
            shift 2
            ;;
        -s|--stack)
            STACK_NAME="$2"
            shift 2
            ;;
        -c|--action)
            ACTION="$2"
            shift 2
            ;;
        --skip-secrets)
            POPULATE_SECRETS="false"
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Environment is always dev for this simplified version
ENVIRONMENT="dev"

# Validate required configuration
if [[ -z "$AWS_ACCOUNT_ID" ]]; then
    print_error "AWS account ID is required. Set AWS_ACCOUNT_ID in .env file or use -a flag."
    exit 1
fi

if [[ -z "$AWS_REGION" ]]; then
    print_error "AWS region is required. Set AWS_REGION in .env file or use -r flag."
    exit 1
fi

# Validate action
if [[ ! "$ACTION" =~ ^(deploy|destroy|diff|synth)$ ]]; then
    print_error "Invalid action: $ACTION. Must be deploy, destroy, diff, or synth."
    exit 1
fi

# Set default stack (ECS only)
if [[ -z "$STACK_NAME" ]]; then
    STACK_NAME="ecs"
fi

# Validate stack name (ECS only)
if [[ "$STACK_NAME" != "ecs" ]]; then
    print_error "Invalid stack name: $STACK_NAME. Only 'ecs' is supported."
    exit 1
fi

# Set AWS profile if provided
if [[ -n "$PROFILE" ]]; then
    export AWS_PROFILE="$PROFILE"
    print_status "Using AWS profile: $PROFILE"
fi

# Export environment variables for CDK
export ENVIRONMENT="$ENVIRONMENT"
export CDK_DEFAULT_ACCOUNT="$AWS_ACCOUNT_ID"
export CDK_DEFAULT_REGION="$AWS_REGION"
export AWS_DEFAULT_REGION="$AWS_REGION"
export DEPLOYMENT_TYPE="$DEPLOYMENT_TYPE"

print_status "Starting development ECS deployment with the following configuration:"
echo "  Environment: $ENVIRONMENT (development only)"
echo "  Region: $AWS_REGION"
echo "  Account: $AWS_ACCOUNT_ID"
echo "  Deployment Type: ECS Fargate"
echo "  Stack: $STACK_NAME"
echo "  Action: $ACTION"
echo "  Populate Secrets: $POPULATE_SECRETS"
echo ""

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed"
        exit 1
    fi
    
    # Check if CDK is installed
    if ! command -v cdk &> /dev/null; then
        print_error "AWS CDK is not installed. Please install it first:"
        echo "  npm install -g aws-cdk"
        exit 1
    fi
    
    # Check if Docker is installed and running (required for ECS)
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed (required for ECS deployment)"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker is not running (required for ECS deployment)"
        exit 1
    fi
    
    # Check if Python dependencies are installed
    if [[ ! -f "requirements.txt" ]]; then
        print_error "requirements.txt not found. Please run from the infrastructure directory."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured"
        exit 1
    fi
    
    # Verify account ID matches
    CURRENT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
    if [[ "$CURRENT_ACCOUNT" != "$AWS_ACCOUNT_ID" ]]; then
        print_error "Current AWS account ($CURRENT_ACCOUNT) doesn't match specified account ($AWS_ACCOUNT_ID)"
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to populate secrets from .env
populate_secrets() {
    if [[ "$POPULATE_SECRETS" == "false" ]]; then
        print_status "Skipping secret population (--skip-secrets flag used)"
        return
    fi
    
    print_status "Populating AWS Secrets Manager from .env..."
    
    # Change to parent directory to access .env
    cd "$(dirname "$0")/.."
    
    # Check if .env exists
    if [[ ! -f ".env" ]]; then
        print_warning ".env file not found, creating minimal secrets..."
        cd infrastructure
        create_minimal_secrets
        return
    fi
    
    # Source the .env file
    source .env
    
    # Validate required variables
    validate_secrets_configuration
    
    # Update Slack secrets
    SLACK_SECRET_NAME="incident-management/slack-config-$ENVIRONMENT"
    print_status "Updating Slack secrets: $SLACK_SECRET_NAME"
    
    SLACK_SECRET_JSON=$(cat <<EOF
{
  "webhook_url": "${SLACK_WEBHOOK_URL:-}",
  "bot_token": "${SLACK_BOT_TOKEN:-}",
  "signing_secret": "${SLACK_SIGNING_SECRET:-}",
  "app_token": "${SLACK_APP_TOKEN:-}",
  "channel": "${SLACK_CHANNEL:-#incidents}"
}
EOF
)
    
    aws secretsmanager update-secret \
        --secret-id "$SLACK_SECRET_NAME" \
        --secret-string "$SLACK_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null || \
    aws secretsmanager create-secret \
        --name "$SLACK_SECRET_NAME" \
        --description "Slack integration secrets for incident management $ENVIRONMENT" \
        --secret-string "$SLACK_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null
    
    # Update PagerDuty secrets
    PAGERDUTY_SECRET_NAME="incident-management/pagerduty-config-$ENVIRONMENT"
    print_status "Updating PagerDuty secrets: $PAGERDUTY_SECRET_NAME"
    
    PAGERDUTY_SECRET_JSON=$(cat <<EOF
{
  "user_api_key": "${PAGERDUTY_USER_API_KEY:-}",
  "api_host": "${PAGERDUTY_API_HOST:-https://api.pagerduty.com}",
  "app_host": "${PAGERDUTY_APP_HOST:-https://app.pagerduty.com}",
  "auto_create_incidents": "${PAGERDUTY_AUTO_CREATE_INCIDENTS:-false}"
}
EOF
)
    
    aws secretsmanager update-secret \
        --secret-id "$PAGERDUTY_SECRET_NAME" \
        --secret-string "$PAGERDUTY_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null || \
    aws secretsmanager create-secret \
        --name "$PAGERDUTY_SECRET_NAME" \
        --description "PagerDuty integration secrets for incident management $ENVIRONMENT" \
        --secret-string "$PAGERDUTY_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null
    
    # Update App secrets
    APP_SECRET_NAME="incident-management/app-config-$ENVIRONMENT"
    print_status "Updating App secrets: $APP_SECRET_NAME"
    
    # Generate JWT secret if not provided
    if [[ -z "${JWT_SECRET:-}" ]]; then
        JWT_SECRET=$(openssl rand -base64 32)
        print_warning "Generated new JWT secret (save this for future deployments)"
    fi
    
    APP_SECRET_JSON=$(cat <<EOF
{
  "jwt_secret": "$JWT_SECRET"
}
EOF
)
    
    aws secretsmanager update-secret \
        --secret-id "$APP_SECRET_NAME" \
        --secret-string "$APP_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null || \
    aws secretsmanager create-secret \
        --name "$APP_SECRET_NAME" \
        --description "Application secrets for incident management $ENVIRONMENT" \
        --secret-string "$APP_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null
    
    # Create/Update Splunk secrets
    SPLUNK_SECRET_NAME="incident-management/splunk-config-$ENVIRONMENT"
    print_status "Updating Splunk secrets: $SPLUNK_SECRET_NAME"
    
    SPLUNK_SECRET_JSON=$(cat <<EOF
{
  "SplunkHost": "${SPLUNK_HOST:-}",
  "SplunkToken": "${SPLUNK_TOKEN:-}"
}
EOF
)
    
    aws secretsmanager update-secret \
        --secret-id "$SPLUNK_SECRET_NAME" \
        --secret-string "$SPLUNK_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null || \
    aws secretsmanager create-secret \
        --name "$SPLUNK_SECRET_NAME" \
        --description "Splunk integration secrets for incident management $ENVIRONMENT" \
        --secret-string "$SPLUNK_SECRET_JSON" \
        --region "$AWS_REGION" &> /dev/null
    
    cd infrastructure
    print_success "Secrets populated successfully from .env.dev"
    
    # Display secrets summary
    display_secrets_summary
}

# Function to validate secrets configuration
validate_secrets_configuration() {
    print_status "Validating secrets configuration..."
    
    local warnings=0
    
    # Check Slack configuration
    if [[ -z "${SLACK_BOT_TOKEN:-}" ]] || [[ "$SLACK_BOT_TOKEN" == "your-slack-bot-token" ]]; then
        print_warning "Slack bot token not configured - Slack integration will be disabled"
        ((warnings++))
    fi
    
    # Check PagerDuty configuration
    if [[ -z "${PAGERDUTY_USER_API_KEY:-}" ]] || [[ "$PAGERDUTY_USER_API_KEY" == "your-pagerduty-api-key" ]]; then
        print_warning "PagerDuty API key not configured - PagerDuty integration will be disabled"
        ((warnings++))
    fi
    
    # Check Splunk configuration
    if [[ -z "${SPLUNK_HOST:-}" ]] || [[ "$SPLUNK_HOST" == "your-splunk-host" ]]; then
        print_warning "Splunk host not configured - Splunk integration will be disabled"
        ((warnings++))
    fi
    
    if [[ -z "${SPLUNK_TOKEN:-}" ]] || [[ "$SPLUNK_TOKEN" == "your-splunk-token" ]]; then
        print_warning "Splunk token not configured - Splunk integration will be disabled"
        ((warnings++))
    fi
    
    if [[ $warnings -gt 0 ]]; then
        print_warning "Found $warnings configuration warnings. The system will deploy but some integrations may not work."
        print_status "Update .env.dev with your actual credentials and redeploy to enable all features."
    else
        print_success "All secrets configuration validated successfully"
    fi
}

# Function to display secrets summary
display_secrets_summary() {
    print_status "Secrets Summary for $ENVIRONMENT environment:"
    echo "  📧 Slack Config: incident-management/slack-config-$ENVIRONMENT"
    echo "  📟 PagerDuty Config: incident-management/pagerduty-config-$ENVIRONMENT"
    echo "  🔐 App Config: incident-management/app-config-$ENVIRONMENT"
    echo "  📊 Splunk Config: incident-management/splunk-config-$ENVIRONMENT"
    echo ""
    echo "  💡 To update secrets later, modify .env and run:"
    echo "     $0 -a $AWS_ACCOUNT_ID -r $AWS_REGION"
}

# Function to create minimal secrets if .env doesn't exist
create_minimal_secrets() {
    print_status "Creating minimal secrets for $ENVIRONMENT environment..."
    
    # Generate a secure JWT secret
    JWT_SECRET=$(openssl rand -base64 32)
    
    # Create App secrets
    APP_SECRET_NAME="incident-management/app-config-$ENVIRONMENT"
    aws secretsmanager create-secret \
        --name "$APP_SECRET_NAME" \
        --description "Application secrets for incident management $ENVIRONMENT" \
        --secret-string "{\"jwt_secret\":\"$JWT_SECRET\"}" \
        --region "$AWS_REGION" &> /dev/null || true
    
    # Create minimal Slack secrets
    SLACK_SECRET_NAME="incident-management/slack-config-$ENVIRONMENT"
    aws secretsmanager create-secret \
        --name "$SLACK_SECRET_NAME" \
        --description "Slack integration secrets for incident management $ENVIRONMENT" \
        --secret-string '{"webhook_url":"","bot_token":"","signing_secret":"","app_token":"","channel":"#incidents"}' \
        --region "$AWS_REGION" &> /dev/null || true
    
    # Create minimal PagerDuty secrets
    PAGERDUTY_SECRET_NAME="incident-management/pagerduty-config-$ENVIRONMENT"
    aws secretsmanager create-secret \
        --name "$PAGERDUTY_SECRET_NAME" \
        --description "PagerDuty integration secrets for incident management $ENVIRONMENT" \
        --secret-string '{"user_api_key":"","api_host":"https://api.pagerduty.com","app_host":"https://app.pagerduty.com","auto_create_incidents":"false"}' \
        --region "$AWS_REGION" &> /dev/null || true
    
    # Create minimal Splunk secrets
    SPLUNK_SECRET_NAME="incident-management/splunk-config-$ENVIRONMENT"
    aws secretsmanager create-secret \
        --name "$SPLUNK_SECRET_NAME" \
        --description "Splunk integration secrets for incident management $ENVIRONMENT" \
        --secret-string '{"SplunkHost":"","SplunkToken":""}' \
        --region "$AWS_REGION" &> /dev/null || true
    
    print_success "Minimal secrets created with secure defaults"
    
    # Create .env template
    create_env_template
}

# Function to create .env template
create_env_template() {
    print_status "Creating .env template..."
    
    cat > .env << EOF
# ===== INCIDENT MANAGEMENT SYSTEM CONFIGURATION =====
# Update these values with your actual credentials and settings

# ===== SLACK INTEGRATION =====
# Get these from your Slack app configuration
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_SIGNING_SECRET=your-slack-signing-secret
SLACK_APP_TOKEN=xapp-your-slack-app-token
SLACK_CHANNEL=#incidents

# ===== PAGERDUTY INTEGRATION =====
# Get these from your PagerDuty account
PAGERDUTY_USER_API_KEY=your-pagerduty-api-key
PAGERDUTY_API_HOST=https://api.pagerduty.com
PAGERDUTY_APP_HOST=https://app.pagerduty.com
PAGERDUTY_AUTO_CREATE_INCIDENTS=false

# ===== SPLUNK INTEGRATION =====
# Your Splunk instance details
SPLUNK_HOST=your-splunk-host.com
SPLUNK_TOKEN=your-splunk-token

# ===== APPLICATION SECURITY =====
# JWT secret for API authentication (auto-generated if empty)
JWT_SECRET=

# ===== DEPLOYMENT CONFIGURATION =====
# These are used by the deployment script
ENVIRONMENT=$ENVIRONMENT
AWS_REGION=$AWS_REGION
AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID

# ===== OPTIONAL SETTINGS =====
# API Configuration
API_PORT=8002
API_HOST=0.0.0.0

# Detection Configuration
DETECTION_INTERVAL=300
ENABLE_AI_ANALYSIS=true

# Logging Configuration
LOG_LEVEL=INFO
ENABLE_DEBUG_LOGGING=false

EOF
    
    print_warning "Created .env template file"
    print_warning "Please edit .env with your actual credentials before the next deployment"
    print_status "The system will deploy with minimal functionality until credentials are configured"
}

# Function to handle failed stack cleanup
cleanup_failed_stacks() {
    if [[ "$ACTION" != "deploy" ]]; then
        return
    fi
    
    local stack_name="$1"
    print_status "Checking for existing stack issues: $stack_name"
    
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name "$stack_name" --region "$AWS_REGION" --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")
    
    if [[ "$STACK_STATUS" == "ROLLBACK_COMPLETE" ]]; then
        print_warning "Stack is in ROLLBACK_COMPLETE state"
        print_status "Deleting failed stack to allow redeployment..."
        aws cloudformation delete-stack --stack-name "$stack_name" --region "$AWS_REGION"
        
        print_status "Waiting for stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$stack_name" --region "$AWS_REGION"
        print_success "Failed stack deleted successfully"
    elif [[ "$STACK_STATUS" == "DELETE_FAILED" ]]; then
        print_error "Stack is in DELETE_FAILED state. Manual cleanup required."
        print_error "Go to CloudFormation console and manually delete: $stack_name"
        exit 1
    elif [[ "$STACK_STATUS" != "DOES_NOT_EXIST" ]]; then
        print_status "Stack exists with status: $STACK_STATUS"
    fi
}

# Run prerequisite checks
check_prerequisites

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install -r requirements.txt

# Bootstrap CDK if needed (only for deploy action)
if [[ "$ACTION" == "deploy" ]]; then
    print_status "Checking CDK bootstrap status..."
    if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region "$AWS_REGION" &> /dev/null; then
        print_warning "CDK not bootstrapped in this region"
        print_status "Bootstrapping CDK..."
        cdk bootstrap "aws://$AWS_ACCOUNT_ID/$AWS_REGION"
        print_success "CDK bootstrap completed"
    else
        print_status "CDK already bootstrapped"
    fi
fi

# Populate secrets before deployment
if [[ "$ACTION" == "deploy" ]]; then
    populate_secrets
    
    # Verify Docker can build for the correct architecture
    print_status "Verifying Docker architecture compatibility..."
    # Get the project root directory (where the Dockerfile should be)
    SCRIPT_DIR="$(dirname "$0")"
    
    # Try to find the project root
    if [[ -d "$SCRIPT_DIR/.." ]]; then
        PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
        cd "$PROJECT_ROOT"
    else
        # If that fails, we're probably already in the right directory
        PROJECT_ROOT="$(pwd)"
        print_status "Using current directory as project root: $PROJECT_ROOT"
    fi
    
    # Check if Dockerfile exists, if not, look in api directory
    ORIGINAL_DIR="$(pwd)"
    if [[ ! -f "Dockerfile" ]] && [[ -f "api/Dockerfile" ]]; then
        print_status "Using Dockerfile from api directory"
        cd api
    elif [[ ! -f "Dockerfile" ]] && [[ ! -f "api/Dockerfile" ]]; then
        print_warning "No Dockerfile found, skipping Docker architecture verification"
        # Continue with deployment without Docker verification
    fi
    
    # Test build a small portion to verify architecture
    print_status "Testing Docker cross-platform build capability..."
    if docker buildx version &> /dev/null; then
        print_success "✅ Docker Buildx available for cross-platform builds"
        # Enable buildx for cross-platform builds
        docker buildx create --use --name incident-management-builder &> /dev/null || true
    else
        print_warning "⚠️ Docker Buildx not available, attempting standard build"
    fi
    
    # Test a simple cross-platform build
    if docker build --platform linux/amd64 -t incident-management-arch-test --target builder . &> /dev/null; then
        print_success "✅ Docker architecture verification passed (linux/amd64)"
        docker rmi incident-management-arch-test &> /dev/null || true
    else
        print_warning "⚠️ Cross-platform build test failed, but continuing deployment"
        print_status "CDK will handle the build process during deployment"
    fi
    
    # Change back to original directory after Docker verification
    cd "$ORIGINAL_DIR"
    
    # Go back to the infrastructure directory for CDK deployment
    # Since we know the script is in the infrastructure directory, just go there directly
    cd "$(dirname "$0")"
    print_status "Changed to infrastructure directory: $(pwd)"
    
    # Verify we have the app.py file
    if [[ ! -f "app.py" ]]; then
        print_error "app.py not found in $(pwd)"
        print_error "Expected to be in infrastructure directory"
        # Try to find the infrastructure directory
        if [[ -f "../infrastructure/app.py" ]]; then
            cd ../infrastructure
            print_status "Found infrastructure directory at: $(pwd)"
        elif [[ -f "infrastructure/app.py" ]]; then
            cd infrastructure
            print_status "Found infrastructure directory at: $(pwd)"
        else
            print_error "Cannot find infrastructure directory with app.py"
            exit 1
        fi
    fi
fi

# Function to execute CDK command for ECS stack
execute_ecs_stack() {
    local stack_full_name="SimpleIncidentManagementECSStack-${ENVIRONMENT}"
    
    cleanup_failed_stacks "$stack_full_name"
    
    print_status "Executing $ACTION for ECS stack: $stack_full_name"
    
    case "$ACTION" in
        deploy)
            cdk deploy "$stack_full_name" --require-approval never --app "python app.py"
            ;;
        destroy)
            print_warning "Destroying development environment. Are you sure? (y/N)"
            read -r confirmation
            if [[ ! "$confirmation" =~ ^[Yy]$ ]]; then
                print_status "Operation cancelled."
                exit 0
            fi
            cdk destroy "$stack_full_name" --force --app "python app.py"
            ;;
        diff)
            cdk diff "$stack_full_name" --app "python app.py"
            ;;
        synth)
            cdk synth "$stack_full_name" --app "python app.py"
            ;;
    esac
}

# Execute ECS deployment
execute_ecs_stack

if [[ "$ACTION" == "deploy" ]]; then
    print_success "ECS Deployment completed successfully!"
    
    # Get deployment outputs
    print_status "Retrieving ECS deployment outputs..."
    
    ALB_DNS=$(aws cloudformation describe-stacks \
        --stack-name "SimpleIncidentManagementECSStack-$ENVIRONMENT" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerURL-'$ENVIRONMENT'`].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [[ -n "$ALB_DNS" ]]; then
        # Extract just the DNS name from the URL
        ALB_DNS=$(echo "$ALB_DNS" | sed 's|http://||')
        
        print_success "🚀 Incident Management Service deployed successfully!"
        echo ""
        print_status "📋 Application URLs:"
        echo "  • Main Application: http://$ALB_DNS"
        echo "  • Health Check: http://$ALB_DNS/health"
        echo "  • System Info: http://$ALB_DNS/system/info"
        echo "  • API Documentation: http://$ALB_DNS/docs"
        echo ""
        
        # Test health endpoint
        print_status "🔍 Testing health endpoint..."
        sleep 10  # Brief wait for service to be ready
        if curl -f "http://$ALB_DNS/health" &> /dev/null; then
            print_success "✅ Health check passed!"
            print_success "🎉 Service is running and ready to receive incidents!"
        else
            print_warning "⚠️ Health check failed - service may still be starting"
            print_status "Check logs: aws logs tail /ecs/incident-management-$ENVIRONMENT --follow --region $AWS_REGION"
        fi
    else
        print_warning "Could not retrieve load balancer URL from stack outputs"
    fi
    
    echo ""
    print_status "🛠️ Useful ECS Management Commands:"
    echo "  # View ECS service status:"
    echo "  aws ecs describe-services --cluster incident-management-$ENVIRONMENT --services incident-management-$ENVIRONMENT --region $AWS_REGION"
    echo ""
    echo "  # View real-time logs:"
    echo "  aws logs tail /ecs/incident-management-$ENVIRONMENT --follow --region $AWS_REGION"
    echo ""
    echo "  # Force new deployment (redeploy with latest image):"
    echo "  aws ecs update-service --cluster incident-management-$ENVIRONMENT --service incident-management-$ENVIRONMENT --force-new-deployment --region $AWS_REGION"
    echo ""
    echo "  # Scale service (increase/decrease containers):"
    echo "  aws ecs update-service --cluster incident-management-$ENVIRONMENT --service incident-management-$ENVIRONMENT --desired-count 2 --region $AWS_REGION"
    
    echo ""
    print_status "🔐 Secret Management:"
    echo "  # View configured secrets:"
    echo "  aws secretsmanager list-secrets --query 'SecretList[?contains(Name, \`incident-management\`) && contains(Name, \`$ENVIRONMENT\`)].Name' --region $AWS_REGION"
    echo ""
    echo "  # Update Slack webhook URL:"
    echo "  aws secretsmanager update-secret --secret-id incident-management/slack-config-$ENVIRONMENT --secret-string '{\"webhook_url\":\"YOUR_WEBHOOK_URL\",\"bot_token\":\"YOUR_BOT_TOKEN\",\"signing_secret\":\"YOUR_SIGNING_SECRET\"}' --region $AWS_REGION"
    
    echo ""
    print_status "🚨 Next Steps:"
    echo "  1. ✅ Secrets are configured from .env"
    echo "  2. 🔗 Test Slack integration by visiting: http://$ALB_DNS/test-slack"
    echo "  3. 🎭 Simulate an incident: http://$ALB_DNS/simulate-incident"
    echo "  4. 📊 Monitor the service via CloudWatch and ECS console"
fi

print_success "Operation completed successfully!"