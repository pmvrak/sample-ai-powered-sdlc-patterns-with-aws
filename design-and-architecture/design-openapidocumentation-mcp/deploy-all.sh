#!/bin/bash
# Merged deployment script for OpenAPI Documentation MCP Server
# This script deploys all required stacks in the correct order

set -e  # Exit on any error

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

# Load environment variables from .env file if it exists
if [ -f "$SCRIPT_DIR/cdk/.env" ]; then
    print_status "Loading environment variables from cdk/.env file..."
    export $(grep -v '^#' "$SCRIPT_DIR/cdk/.env" | xargs)
fi

# Parse command line arguments
CERTIFICATE_ARN=""
CREATE_CERTIFICATE=false
DOMAIN_NAME=""
REGION=${AWS_REGION:-${CDK_DEFAULT_REGION:-"us-east-1"}}
ALLOWED_IPS=""
SKIP_IMAGE_PUSH=false
WAIT_FOR_SERVICE=true
DESIRED_COUNT=1
PLATFORM="linux/amd64"  # Default to x86_64 architecture
DEPLOY_ALL=true

while [[ $# -gt 0 ]]; do
  case $1 in
    --certificate-arn)
      CERTIFICATE_ARN="$2"
      shift 2
      ;;
    --create-certificate)
      CREATE_CERTIFICATE=true
      shift
      ;;
    --domain-name)
      DOMAIN_NAME="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --allowed-ips)
      ALLOWED_IPS="$2"
      shift 2
      ;;
    --my-ip)
      # Get current public IP automatically
      CURRENT_IP=$(curl -s https://checkip.amazonaws.com)
      if [ -n "$CURRENT_IP" ]; then
        ALLOWED_IPS="$CURRENT_IP/32"
        print_status "Detected your public IP: $CURRENT_IP"
      else
        print_error "Failed to detect your public IP"
        exit 1
      fi
      shift
      ;;
    --skip-image-push)
      SKIP_IMAGE_PUSH=true
      shift
      ;;
    --no-wait)
      WAIT_FOR_SERVICE=false
      shift
      ;;
    --desired-count)
      DESIRED_COUNT="$2"
      shift 2
      ;;
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --mcp-server-only)
      DEPLOY_ALL=false
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --certificate-arn ARN    Use existing ACM certificate ARN"
      echo "  --create-certificate     Create a new ACM certificate"
      echo "  --domain-name DOMAIN     Domain name for certificate"
      echo "  --region REGION          AWS region (default: eu-west-1)"
      echo "  --allowed-ips IPS        Comma-separated list of IPs/CIDR blocks to allow access"
      echo "  --my-ip                  Automatically detect and allow your current public IP"
      echo "  --skip-image-push        Skip Docker image build and push step"
      echo "  --no-wait                Don't wait for ECS service to be stable"
      echo "  --desired-count COUNT    Number of ECS tasks to run (default: 1)"
      echo "  --platform PLATFORM      Target platform for Docker image (default: linux/amd64)"
      echo "  --mcp-server-only        Deploy only the MCP server stack (skip other stacks)"
      echo "  --help, -h               Show this help message"
      exit 0
      ;;
    *)
      shift
      ;;
  esac
done

# Get the absolute path to the script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CDK_DIR="$SCRIPT_DIR/cdk"

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check AWS CLI
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check Node.js
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed. Please install it first."
        exit 1
    fi
    
    # Check npm
    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed. Please install it first."
        exit 1
    fi
    
    # Check CDK
    if ! command -v cdk &> /dev/null; then
        print_error "AWS CDK is not installed. Please install it first: npm install -g aws-cdk"
        exit 1
    fi
    
    # Check Docker if we're not skipping image push
    if [ "$SKIP_IMAGE_PUSH" != true ]; then
        if ! command -v docker &> /dev/null; then
            print_error "Docker is not installed. Please install it first or use --skip-image-push."
            exit 1
        fi
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        print_error "AWS credentials are not configured. Please run 'aws configure' first."
        exit 1
    fi
    
    print_success "All prerequisites are met!"
}

# Function to create a certificate
create_certificate() {
    print_status "Creating certificate for domain: $DOMAIN_NAME"
    
    # Request a certificate
    print_status "Requesting certificate in region $REGION..."
    CERTIFICATE_ARN=$(aws acm request-certificate \
      --domain-name "$DOMAIN_NAME" \
      --validation-method DNS \
      --region "$REGION" \
      --output text \
      --query 'CertificateArn')
    
    if [ -z "$CERTIFICATE_ARN" ]; then
        print_error "Failed to request certificate"
        exit 1
    fi
    
    print_success "Certificate requested successfully!"
    print_status "Certificate ARN: $CERTIFICATE_ARN"
    
    # Get the DNS validation records
    print_status "Getting DNS validation records..."
    sleep 5  # Wait for the certificate to be created
    
    DNS_RECORDS=$(aws acm describe-certificate \
      --certificate-arn "$CERTIFICATE_ARN" \
      --region "$REGION" \
      --query 'Certificate.DomainValidationOptions[].ResourceRecord')
    
    if [ -z "$DNS_RECORDS" ] || [ "$DNS_RECORDS" == "null" ]; then
        print_warning "No DNS validation records found yet. Please wait a few seconds and try again."
        print_warning "You can check the certificate status with:"
        print_warning "aws acm describe-certificate --certificate-arn $CERTIFICATE_ARN --region $REGION"
    else
        print_success "DNS validation records retrieved!"
        print_status "Please create the following DNS records to validate your certificate:"
        echo "$DNS_RECORDS" | jq -r '.[] | "Name: \(.Name)\nType: \(.Type)\nValue: \(.Value)\n"'
    fi
    
    print_status "Once you've created the DNS records, the certificate will be validated automatically."
    print_status "This can take up to 30 minutes."
    
    # Save the certificate ARN to a file
    echo "$CERTIFICATE_ARN" > "$SCRIPT_DIR/certificate-arn.txt"
    print_status "Certificate ARN saved to certificate-arn.txt"
    
    # Ask user if they want to wait for validation
    read -p "Do you want to wait for certificate validation? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_status "Waiting for certificate validation..."
        while true; do
            STATUS=$(aws acm describe-certificate \
              --certificate-arn "$CERTIFICATE_ARN" \
              --region "$REGION" \
              --query 'Certificate.Status' \
              --output text)
            
            print_status "Certificate status: $STATUS"
            
            if [ "$STATUS" == "ISSUED" ]; then
                print_success "Certificate validated successfully!"
                break
            elif [ "$STATUS" == "FAILED" ]; then
                print_error "Certificate validation failed!"
                exit 1
            fi
            
            print_status "Waiting for validation to complete... (checking again in 30 seconds)"
            sleep 30
        done
    else
        print_warning "Proceeding without waiting for certificate validation."
        print_warning "The certificate must be validated before HTTPS will work."
        print_warning "You can check the status with:"
        print_warning "aws acm describe-certificate --certificate-arn $CERTIFICATE_ARN --region $REGION --query 'Certificate.Status'"
    fi
}

# Function to build and push Docker image
build_and_push_image() {
    print_status "Building and pushing Docker image for platform $PLATFORM..."
    
    # Check if push-to-ecr.sh exists
    if [ -f "$SCRIPT_DIR/push-to-ecr.sh" ]; then
        print_status "Running push-to-ecr.sh script..."
        chmod +x "$SCRIPT_DIR/push-to-ecr.sh"
        
        # Check if mcp-server-outputs.json exists and extract ECR URI
        if [ -f "$SCRIPT_DIR/mcp-server-outputs.json" ]; then
            ECR_URI=$(cat "$SCRIPT_DIR/mcp-server-outputs.json" | grep -o '"EcrRepositoryUri": "[^"]*"' | cut -d'"' -f4)
            
            if [ -n "$ECR_URI" ]; then
                print_status "Found ECR URI from deployment outputs: $ECR_URI"
                cd "$SCRIPT_DIR"
                ./push-to-ecr.sh --region "$REGION" --platform "$PLATFORM" --ecr-uri "$ECR_URI"
                cd - > /dev/null
                return
            fi
        fi
        
        # If we couldn't get the ECR URI from outputs, run without it
        # The push-to-ecr.sh script will try to find it itself
        cd "$SCRIPT_DIR"
        ./push-to-ecr.sh --region "$REGION" --platform "$PLATFORM"
        cd - > /dev/null
    else
        print_error "push-to-ecr.sh script not found!"
        print_error "Please build and push the Docker image manually."
        exit 1
    fi
}

# Function to bootstrap CDK environment
bootstrap_cdk() {
    print_status "Bootstrapping CDK environment..."
    
    # Navigate to CDK directory
    cd "$CDK_DIR"
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        print_status "Installing CDK dependencies..."
        npm install
    fi
    
    # Build the CDK project
    print_status "Building CDK project..."
    npm run build
    
    # Add cdk.json configuration for suppressions if it doesn't exist
    if [ ! -f "cdk.json" ] || ! grep -q "suppressNagWarnings" cdk.json; then
        print_status "Adding CDK Nag suppressions to cdk.json..."
        if [ -f "cdk.json" ]; then
            # Update existing cdk.json
            TMP_FILE=$(mktemp)
            jq '. + {"context": {"@aws-cdk/core:suppressNagWarnings": true}}' cdk.json > "$TMP_FILE" || \
            jq '.context += {"@aws-cdk/core:suppressNagWarnings": true}' cdk.json > "$TMP_FILE"
            mv "$TMP_FILE" cdk.json
        else
            # Create new cdk.json
            echo '{"context": {"@aws-cdk/core:suppressNagWarnings": true}}' > cdk.json
        fi
    fi
    
    # Run bootstrap command
    print_status "Running CDK bootstrap..."
    cdk bootstrap --no-validation
    
    # Navigate back to the original directory
    cd - > /dev/null
    
    print_success "CDK environment bootstrapped!"
}

# Function to deploy OpenSearch stack
deploy_opensearch_stack() {
    print_status "Deploying OpenSearch stack..."
    
    # Navigate to CDK directory
    cd "$CDK_DIR"
    
    # Deploy the stack with suppressions
    cdk deploy OpenSearchStack --require-approval never --context '@aws-cdk/core:suppressNagWarnings=true' --no-validation
    
    # Navigate back to the original directory
    cd - > /dev/null
    
    print_success "OpenSearch stack deployed!"
}

# Storage stack removed - S3 buckets no longer needed as Lambdas return responses directly

# Function to deploy Bedrock stack
deploy_bedrock_stack() {
    print_status "Deploying Bedrock stack..."
    
    # Navigate to CDK directory
    cd "$CDK_DIR"
    
    # Deploy the stack with suppressions
    cdk deploy BedrockStack --require-approval never --context '@aws-cdk/core:suppressNagWarnings=true' --no-validation
    
    # Navigate back to the original directory
    cd - > /dev/null
    
    print_success "Bedrock stack deployed!"
}

# Function to install Lambda dependencies
install_lambda_dependencies() {
    print_status "Installing Lambda function dependencies..."
    
    # Install domain analyzer Lambda dependencies
    if [ -d "$SCRIPT_DIR/domain-analyzer-lambda" ]; then
        print_status "Installing domain analyzer Lambda dependencies..."
        cd "$SCRIPT_DIR/domain-analyzer-lambda"
        npm install
        print_success "Domain analyzer dependencies installed!"
    fi
    
    # Install doc generator Lambda dependencies
    if [ -d "$SCRIPT_DIR/doc-gen-lambda" ]; then
        print_status "Installing doc generator Lambda dependencies..."
        cd "$SCRIPT_DIR/doc-gen-lambda"
        npm install
        print_success "Doc generator dependencies installed!"
    fi
    
    # Navigate back to the original directory
    cd - > /dev/null
}

# Function to deploy Lambda stack
deploy_lambda_stack() {
    print_status "Deploying Lambda API stack..."
    
    # Install Lambda dependencies first
    install_lambda_dependencies
    
    # Navigate to CDK directory
    cd "$CDK_DIR"
    
    # Deploy the stack with suppressions
    cdk deploy LambdaAPIStack --require-approval never --context '@aws-cdk/core:suppressNagWarnings=true' --no-validation
    
    # Navigate back to the original directory
    cd - > /dev/null
    
    print_success "Lambda API stack deployed!"
}

# Function to deploy MCP Server stack
deploy_mcp_server_stack() {
    print_status "Deploying MCP Server stack..."
    
    # Navigate to CDK directory
    cd "$CDK_DIR"
    
    # Build CDK context parameters
    CDK_CONTEXT=""
    
    # Add certificate ARN context if provided
    if [ -n "$CERTIFICATE_ARN" ]; then
        print_status "Using certificate ARN: $CERTIFICATE_ARN"
        CDK_CONTEXT="$CDK_CONTEXT --context certificateArn=$CERTIFICATE_ARN"
    else
        print_warning "No certificate ARN provided. Using HTTP listener only."
    fi
    
    # Add domain name context if provided
    if [ -n "$DOMAIN_NAME" ]; then
        print_status "Using domain name: $DOMAIN_NAME"
        CDK_CONTEXT="$CDK_CONTEXT --context domainName=$DOMAIN_NAME"
    fi
    
    # Add allowed IPs context if provided
    if [ -n "$ALLOWED_IPS" ]; then
        print_status "Restricting ALB access to IPs: $ALLOWED_IPS"
        CDK_CONTEXT="$CDK_CONTEXT --context allowedIps=$ALLOWED_IPS"
    else
        # Get current IP and suggest using it
        CURRENT_IP=$(curl -s https://checkip.amazonaws.com/ || curl -s https://ipinfo.io/ip || echo "unknown")
        if [ "$CURRENT_IP" != "unknown" ]; then
            print_warning "No IP restrictions specified. ALB will be inaccessible."
            print_warning "Your current IP is: $CURRENT_IP"
            print_warning "Consider rerunning with: --allowed-ips \"$CURRENT_IP/32\""
        else
            print_warning "No IP restrictions specified. ALB will be inaccessible."
            print_warning "Use --allowed-ips \"YOUR_IP/32\" to allow access from your IP."
        fi
    fi
    
    cdk deploy McpServerStack $CDK_CONTEXT --outputs-file "$SCRIPT_DIR/mcp-server-outputs.json" --require-approval never --context '@aws-cdk/core:suppressNagWarnings=true' --no-validation
    
    # Navigate back to the original directory
    cd - > /dev/null
    
    print_success "MCP Server stack deployed!"
}

# Function to update ECS service desired count
update_ecs_service() {
    print_status "Updating ECS service desired count to $DESIRED_COUNT..."
    
    # Extract cluster and service name from outputs
    CLUSTER_NAME=$(cat "$SCRIPT_DIR/mcp-server-outputs.json" | grep -o '"ClusterName": "[^"]*"' | cut -d'"' -f4)
    SERVICE_NAME=$(cat "$SCRIPT_DIR/mcp-server-outputs.json" | grep -o '"ServiceName": "[^"]*"' | cut -d'"' -f4)
    
    if [ -z "$CLUSTER_NAME" ] || [ -z "$SERVICE_NAME" ]; then
        print_error "Failed to extract cluster or service name from outputs"
        exit 1
    fi
    
    print_status "Cluster: $CLUSTER_NAME"
    print_status "Service: $SERVICE_NAME"
    
    # Update service desired count
    aws ecs update-service \
      --cluster "$CLUSTER_NAME" \
      --service "$SERVICE_NAME" \
      --desired-count "$DESIRED_COUNT" \
      --region "$REGION"
    
    print_success "ECS service updated to desired count: $DESIRED_COUNT"
    
    # Wait for service to be stable if requested
    if [ "$WAIT_FOR_SERVICE" = true ]; then
        print_status "Waiting for ECS service to be stable..."
        
        aws ecs wait services-stable \
          --cluster "$CLUSTER_NAME" \
          --services "$SERVICE_NAME" \
          --region "$REGION"
        
        print_success "ECS service is now stable!"
    fi
}

# Function to update environment variables
update_env_vars() {
    print_status "Updating environment variables..."
    
    # Extract values from outputs
    MCP_SERVER_URL=$(cat "$SCRIPT_DIR/mcp-server-outputs.json" | grep -o '"McpServerUrl": "[^"]*"' | cut -d'"' -f4)
    
    # Create/update .env file
    echo "MCP_SERVER_URL=$MCP_SERVER_URL" > "$SCRIPT_DIR/.env"
    
    print_success "Environment variables updated in .env file!"
}

# Function to display deployment summary
display_summary() {
    print_success "Deployment completed successfully!"
    
    MCP_SERVER_URL=$(cat "$SCRIPT_DIR/mcp-server-outputs.json" | grep -o '"McpServerUrl": "[^"]*"' | cut -d'"' -f4)
    
    echo ""
    echo "=========================================="
    echo "         DEPLOYMENT SUMMARY"
    echo "=========================================="
    echo "MCP Server URL:     $MCP_SERVER_URL"
    echo "ECS Desired Count:  $DESIRED_COUNT"
    echo "Region:             $REGION"
    echo "=========================================="
    echo ""
    echo "🎉 Your MCP server is now deployed and running!"
    echo "🚀 Test health endpoint: curl $MCP_SERVER_URL/health"
    echo ""
    
    # Get Bedrock Agent ID if available
    AGENT_ID=$(aws cloudformation describe-stacks --stack-name BedrockStack --query 'Stacks[0].Outputs[?OutputKey==`AgentId`].OutputValue' --output text 2>/dev/null || echo "N/A")
    if [ "$AGENT_ID" != "N/A" ]; then
        echo "Bedrock Agent ID:   $AGENT_ID"
    fi
    
    # Get Knowledge Base ID if available
    KB_ID=$(aws cloudformation describe-stacks --stack-name BedrockStack --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' --output text 2>/dev/null || echo "N/A")
    if [ "$KB_ID" != "N/A" ]; then
        echo "Knowledge Base ID:  $KB_ID"
    fi
    
    # Get Domain Analyzer Lambda ARN if available
    DOMAIN_ANALYZER_ARN=$(aws cloudformation describe-stacks --stack-name LambdaAPIStack --query 'Stacks[0].Outputs[?OutputKey==`DomainAnalyzerFunctionArn`].OutputValue' --output text 2>/dev/null || echo "N/A")
    if [ "$DOMAIN_ANALYZER_ARN" != "N/A" ]; then
        echo "Domain Analyzer:    $DOMAIN_ANALYZER_ARN"
    fi
}

# Function to upload documents to S3
upload_documents() {
    print_status "Uploading documents to S3..."
    
    local DOCS_DIR="./kb_docs"  # kb_docs is in the project directory
    
    # Get S3 bucket name from OpenSearch stack
    local BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name OpenSearchStack --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' --output text)
    
    if [ -d "$DOCS_DIR" ]; then
        aws s3 sync "$DOCS_DIR" "s3://$BUCKET_NAME/" --quiet
        print_success "Documents uploaded to S3!"
    else
        print_warning "No documents directory found at $DOCS_DIR. Skipping document upload."
    fi
}

# Function to start knowledge base ingestion
start_ingestion() {
    print_status "Starting knowledge base ingestion..."
    
    # Get knowledge base and data source IDs
    local KB_ID=$(aws cloudformation describe-stacks --stack-name BedrockStack --query 'Stacks[0].Outputs[?OutputKey==`KnowledgeBaseId`].OutputValue' --output text)
    
    if [ "$KB_ID" = "None" ] || [ -z "$KB_ID" ]; then
        print_warning "Knowledge Base ID not found. Skipping ingestion."
        return
    fi
    
    local DS_ID=$(aws bedrock-agent list-data-sources --knowledge-base-id "$KB_ID" --query 'dataSourceSummaries[0].dataSourceId' --output text)
    
    if [ "$DS_ID" = "None" ] || [ -z "$DS_ID" ]; then
        print_warning "Data Source ID not found. Skipping ingestion."
        return
    fi
    
    # Start ingestion job
    local INGESTION_JOB=$(aws bedrock-agent start-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --query 'ingestionJob.ingestionJobId' --output text)
    
    print_status "Ingestion job started: $INGESTION_JOB"
    print_status "Waiting for ingestion to complete..."
    
    # Wait for ingestion to complete (with timeout)
    local timeout=300  # 5 minutes timeout
    local elapsed=0
    
    while [ $elapsed -lt $timeout ]; do
        local STATUS=$(aws bedrock-agent get-ingestion-job --knowledge-base-id "$KB_ID" --data-source-id "$DS_ID" --ingestion-job-id "$INGESTION_JOB" --query 'ingestionJob.status' --output text)
        
        if [ "$STATUS" = "COMPLETE" ]; then
            print_success "Knowledge base ingestion completed successfully!"
            return
        elif [ "$STATUS" = "FAILED" ]; then
            print_error "Knowledge base ingestion failed!"
            # Don't exit - continue with deployment
            return
        else
            print_status "Ingestion status: $STATUS (${elapsed}s elapsed)"
            sleep 10
            elapsed=$((elapsed + 10))
        fi
    done
    
    print_warning "Ingestion timeout reached. Check AWS console for status."
}

# Main function
main() {
    echo "=========================================="
    echo "       OpenAPI Documentation MCP Server Deployment"
    echo "=========================================="
    echo ""
    
    # Check prerequisites
    check_prerequisites
    
    # Check for jq (needed for JSON manipulation)
    if ! command -v jq &> /dev/null; then
        print_warning "jq is not installed. JSON manipulation for cdk.json may not work correctly."
        print_warning "Consider installing jq for better JSON handling."
    fi
    
    # Bootstrap CDK environment first
    bootstrap_cdk
    
    # Create certificate if requested
    if [ "$CREATE_CERTIFICATE" = true ]; then
        if [ -z "$DOMAIN_NAME" ]; then
            print_error "Domain name is required when creating a certificate"
            print_error "Usage: $0 --create-certificate --domain-name example.com"
            exit 1
        fi
        
        create_certificate
    fi
    
    # Function to create vector index
    create_vector_index() {
        print_status "Creating vector index in OpenSearch..."
        
        # Navigate to CDK directory
        cd "$CDK_DIR"
        
        # Install required dependencies if not already installed
        if ! npm list @opensearch-project/opensearch &>/dev/null; then
            print_status "Installing OpenSearch dependencies..."
            npm install @opensearch-project/opensearch @aws-sdk/credential-provider-node
        fi
        
        # Set AWS_REGION environment variable for the index creation script
        export AWS_REGION="$REGION"
        
        # Use the JavaScript version
        node create-index.js
        
        if [ $? -eq 0 ]; then
            print_success "Vector index created!"
        else
            print_error "Failed to create vector index!"
            exit 1
        fi
        
        # Navigate back to the original directory
        cd - > /dev/null
    }
    
    # Deploy all stacks in correct dependency order
    if [ "$DEPLOY_ALL" = true ]; then
        deploy_opensearch_stack
        # Upload documents to S3 before creating vector index
        upload_documents
        # Create vector index after OpenSearch stack is deployed
        create_vector_index
        deploy_bedrock_stack
        deploy_lambda_stack
        # Start knowledge base ingestion after all stacks are deployed
        start_ingestion
    else
        print_warning "Deploying MCP server only. Make sure the following stacks are already deployed:"
        print_warning "  - OpenSearchStack"
        print_warning "  - BedrockStack"
        print_warning "  - LambdaAPIStack"
        print_warning "The MCP server depends on these stacks for proper functionality."
    fi
    
    # Deploy MCP Server stack after dependencies are ready
    deploy_mcp_server_stack
    
    # Build and push Docker image if not skipped
    if [ "$SKIP_IMAGE_PUSH" != true ]; then
        build_and_push_image
    else
        print_warning "Skipping Docker image build and push"
    fi
    
    # Update ECS service desired count
    update_ecs_service
    
    # Update environment variables
    update_env_vars
    
    # Display deployment summary
    display_summary
    
    print_success "All done! 🎉"
}

# Run main function
main "$@"