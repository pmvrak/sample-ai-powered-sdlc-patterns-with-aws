#!/bin/bash

# Secure Deployment Script for Incident Management System
# This script handles secrets securely without storing them in files

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

show_usage() {
    cat << EOF
Secure Deployment Script for Incident Management System

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -r, --region REGION      AWS region [default: us-east-1]
    -a, --account ACCOUNT    AWS account ID (required)
    -e, --environment ENV    Environment (dev, prod) [default: dev]
    -c, --action ACTION      Action (deploy, destroy, diff, synth) [default: deploy]
    --interactive           Interactive mode for secret input
    -h, --help              Show this help message

SECURE SECRET MANAGEMENT:
    This script does NOT read secrets from .env files. Instead:
    
    1. Use environment variables:
       export SLACK_BOT_TOKEN="xoxb-your-token"
       export SPLUNK_TOKEN="your-token"
       
    2. Use AWS CLI to set secrets directly:
       aws secretsmanager put-secret-value --secret-id incident-management/slack-config-dev --secret-string '{"bot_token":"xoxb-your-token"}'
       
    3. Use interactive mode:
       $0 --interactive

EXAMPLES:
    # Deploy with environment variables
    export SLACK_BOT_TOKEN="xoxb-your-token"
    $0 -a 123456789012 -e dev
    
    # Interactive deployment
    $0 -a 123456789012 -e dev --interactive
    
    # Deploy without updating secrets
    $0 -a 123456789012 -e dev --skip-secrets

EOF
}

# Function to securely prompt for secrets
prompt_for_secrets() {
    print_status "🔐 Interactive Secret Configuration"
    echo "Enter your secrets (they will be hidden):"
    
    echo -n "Slack Bot Token (xoxb-...): "
    read -s SLACK_BOT_TOKEN
    echo
    
    echo -n "Slack Signing Secret: "
    read -s SLACK_SIGNING_SECRET
    echo
    
    echo -n "Slack Webhook URL: "
    read SLACK_WEBHOOK_URL
    
    echo -n "PagerDuty API Key: "
    read -s PAGERDUTY_USER_API_KEY
    echo
    
    echo -n "Splunk Host: "
    read SPLUNK_HOST
    
    echo -n "Splunk Token: "
    read -s SPLUNK_TOKEN
    echo
    
    print_success "✅ Secrets collected securely"
}

# Function to validate secrets are available
validate_secrets() {
    local missing_secrets=()
    
    if [[ -z "${SLACK_BOT_TOKEN:-}" ]]; then
        missing_secrets+=("SLACK_BOT_TOKEN")
    fi
    
    if [[ -z "${SLACK_SIGNING_SECRET:-}" ]]; then
        missing_secrets+=("SLACK_SIGNING_SECRET")
    fi
    
    if [[ -z "${SPLUNK_TOKEN:-}" ]]; then
        missing_secrets+=("SPLUNK_TOKEN")
    fi
    
    if [[ ${#missing_secrets[@]} -gt 0 ]]; then
        print_warning "Missing secrets: ${missing_secrets[*]}"
        print_status "You can:"
        print_status "1. Set environment variables: export SLACK_BOT_TOKEN='your-token'"
        print_status "2. Use --interactive mode"
        print_status "3. Set secrets directly in AWS Secrets Manager"
        return 1
    fi
    
    return 0
}

# Function to securely populate secrets
populate_secrets_securely() {
    print_status "🔐 Populating AWS Secrets Manager securely..."
    
    # Generate JWT secret if not provided
    if [[ -z "${JWT_SECRET:-}" ]]; then
        JWT_SECRET=$(openssl rand -base64 32)
        print_status "Generated new JWT secret"
    fi
    
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
    
    # Update Splunk secrets
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
    
    # Clear sensitive variables from memory
    unset SLACK_BOT_TOKEN SLACK_SIGNING_SECRET PAGERDUTY_USER_API_KEY SPLUNK_TOKEN JWT_SECRET
    
    print_success "✅ Secrets populated securely"
}

# Default values
ENVIRONMENT="dev"
ACTION="deploy"
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=""
INTERACTIVE_MODE=false
SKIP_SECRETS=false

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
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -c|--action)
            ACTION="$2"
            shift 2
            ;;
        --interactive)
            INTERACTIVE_MODE=true
            shift
            ;;
        --skip-secrets)
            SKIP_SECRETS=true
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

# Validate required parameters
if [[ -z "$AWS_ACCOUNT_ID" ]]; then
    print_error "AWS account ID is required. Use -a flag."
    exit 1
fi

# Export environment variables for CDK
export ENVIRONMENT="$ENVIRONMENT"
export CDK_DEFAULT_ACCOUNT="$AWS_ACCOUNT_ID"
export CDK_DEFAULT_REGION="$AWS_REGION"
export AWS_DEFAULT_REGION="$AWS_REGION"

print_status "🚀 Starting secure deployment with configuration:"
echo "  Environment: $ENVIRONMENT"
echo "  Region: $AWS_REGION"
echo "  Account: $AWS_ACCOUNT_ID"
echo "  Action: $ACTION"
echo "  Interactive Mode: $INTERACTIVE_MODE"
echo ""

# Handle secrets securely
if [[ "$ACTION" == "deploy" && "$SKIP_SECRETS" == "false" ]]; then
    if [[ "$INTERACTIVE_MODE" == "true" ]]; then
        prompt_for_secrets
        populate_secrets_securely
    elif validate_secrets; then
        populate_secrets_securely
    else
        print_error "Secrets validation failed. Use --interactive or set environment variables."
        exit 1
    fi
fi

# Continue with normal deployment
print_status "🏗️ Proceeding with CDK deployment..."

# Install dependencies
pip install -r requirements.txt

# Bootstrap CDK if needed
if [[ "$ACTION" == "deploy" ]]; then
    if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region "$AWS_REGION" &> /dev/null; then
        print_status "Bootstrapping CDK..."
        cdk bootstrap "aws://$AWS_ACCOUNT_ID/$AWS_REGION"
    fi
fi

# Execute CDK command
STACK_NAME="SimpleIncidentManagementECSStack-${ENVIRONMENT}"

case "$ACTION" in
    deploy)
        cdk deploy "$STACK_NAME" --require-approval never
        ;;
    destroy)
        print_warning "Destroying $ENVIRONMENT environment. Are you sure? (y/N)"
        read -r confirmation
        if [[ "$confirmation" =~ ^[Yy]$ ]]; then
            cdk destroy "$STACK_NAME" --force
        else
            print_status "Operation cancelled."
            exit 0
        fi
        ;;
    diff)
        cdk diff "$STACK_NAME"
        ;;
    synth)
        cdk synth "$STACK_NAME"
        ;;
esac

print_success "🎉 Secure deployment completed!"