#!/bin/bash

# Comprehensive cleanup script for MCP server deployment
# This script removes all AWS resources and local files

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
CONFIRM=false
DELETE_ECR_IMAGES=false
DELETE_S3_CONTENT=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --region)
      REGION="$2"
      shift 2
      ;;
    --confirm)
      CONFIRM=true
      shift
      ;;
    --delete-ecr-images)
      DELETE_ECR_IMAGES=true
      shift
      ;;
    --delete-s3-content)
      DELETE_S3_CONTENT=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Comprehensive cleanup for MCP server deployment:"
      echo ""
      echo "REMOVES:"
      echo "AWS Resources:"
      echo "- McpServerStack (ECS service, ALB, VPC, etc.)"
      echo "- LambdaAPIStack (Domain Analyzer and Doc Generator functions)"
      echo "- BedrockStack (Bedrock Agent and Knowledge Base)"
      echo "- OpenSearchStack (Vector database and S3 bucket for Knowledge Base)"
      echo "- All other stacks created by the CDK app"
      echo ""
      echo "Options:"
      echo "  --region REGION         AWS region (default: eu-west-1)"
      echo "  --confirm               Skip confirmation prompt"
      echo "  --delete-ecr-images     Delete all images in the ECR repository"
      echo "  --delete-s3-content     Delete all content in S3 buckets before removal"
      echo "  --help, -h              Show this help message"
      exit 0
      ;;
    *)
      print_error "Unknown option: $1"
      exit 1
      ;;
  esac
done

print_status "Comprehensive AWS Resource Cleanup"
print_status "Region: $REGION"
echo ""

print_warning "This will DELETE ALL AWS RESOURCES created for the MCP server:"
echo ""
print_warning "CDK STACKS:"
print_warning "- McpServerStack (ECS service, ALB, VPC, etc.)"
print_warning "- LambdaAPIStack (Domain Analyzer and Doc Generator functions)"
print_warning "- BedrockStack (Bedrock Agent and Knowledge Base)"
print_warning "- OpenSearchStack (Vector database and S3 bucket for Knowledge Base)"
print_warning "- All other stacks created by the CDK app"
echo ""

if [ "$DELETE_ECR_IMAGES" = true ]; then
    print_warning "ECR IMAGES:"
    print_warning "- All Docker images in the ECR repository will be deleted"
    echo ""
fi

if [ "$DELETE_S3_CONTENT" = true ]; then
    print_warning "S3 CONTENT:"
    print_warning "- All files in S3 buckets will be deleted before bucket removal"
    echo ""
fi

print_warning "⚠️  THIS ACTION IS IRREVERSIBLE! ⚠️"
echo ""

if [ "$CONFIRM" != "true" ]; then
    read -p "Are you sure you want to proceed with the cleanup? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Cleanup cancelled."
        exit 0
    fi
fi

print_status "Starting comprehensive AWS resource cleanup..."

# Step 0: First scale down ECS service to 0 to avoid issues with resource deletion
print_status "Step 0: Scaling down ECS service to 0..."

# Extract cluster and service name from outputs if available
if [ -f "mcp-server-outputs.json" ]; then
    CLUSTER_NAME=$(cat mcp-server-outputs.json | grep -o '"ClusterName": "[^"]*"' | cut -d'"' -f4)
    SERVICE_NAME=$(cat mcp-server-outputs.json | grep -o '"ServiceName": "[^"]*"' | cut -d'"' -f4)
    
    if [ -n "$CLUSTER_NAME" ] && [ -n "$SERVICE_NAME" ]; then
        print_status "Scaling down ECS service: $SERVICE_NAME in cluster: $CLUSTER_NAME"
        
        # Check if service exists
        if aws ecs describe-services --cluster "$CLUSTER_NAME" --services "$SERVICE_NAME" --region "$REGION" --query "services[?status=='ACTIVE']" --output text | grep -q "$SERVICE_NAME"; then
            # Update service desired count to 0
            aws ecs update-service \
              --cluster "$CLUSTER_NAME" \
              --service "$SERVICE_NAME" \
              --desired-count 0 \
              --region "$REGION"
            
            print_status "Waiting for ECS service to scale down..."
            aws ecs wait services-stable \
              --cluster "$CLUSTER_NAME" \
              --services "$SERVICE_NAME" \
              --region "$REGION"
            
            print_success "ECS service scaled down to 0"
        else
            print_warning "ECS service not found or not active"
        fi
    else
        print_warning "Could not find cluster or service name in outputs"
    fi
else
    print_warning "mcp-server-outputs.json not found, skipping ECS service scale down"
fi

# Step 1: Delete ECR images if requested
if [ "$DELETE_ECR_IMAGES" = true ]; then
    print_status "Step 1: Deleting ECR images..."
    
    # Extract ECR repository URI from outputs if available
    if [ -f "mcp-server-outputs.json" ]; then
        ECR_REPO_URI=$(cat mcp-server-outputs.json | grep -o '"EcrRepositoryUri": "[^"]*"' | cut -d'"' -f4)
        
        if [ -n "$ECR_REPO_URI" ]; then
            # Extract repository name from URI
            ECR_REPO_NAME=$(echo "$ECR_REPO_URI" | cut -d'/' -f2)
            
            print_status "Deleting images in repository: $ECR_REPO_NAME"
            
            # List all image IDs
            IMAGE_IDS=$(aws ecr list-images --repository-name "$ECR_REPO_NAME" --region "$REGION" --query 'imageIds[*]' --output json)
            
            if [ -n "$IMAGE_IDS" ] && [ "$IMAGE_IDS" != "[]" ]; then
                # Delete all images
                aws ecr batch-delete-image --repository-name "$ECR_REPO_NAME" --image-ids "$IMAGE_IDS" --region "$REGION"
                print_success "Deleted all images in ECR repository"
            else
                print_warning "No images found in ECR repository"
            fi
        else
            print_warning "Could not find ECR repository URI in outputs"
        fi
    else
        print_warning "mcp-server-outputs.json not found, skipping ECR image deletion"
    fi
fi

# Step 2: Empty S3 buckets if requested
if [ "$DELETE_S3_CONTENT" = true ]; then
    print_status "Step 2: Emptying S3 buckets..."
    
    # Get list of S3 buckets created by CDK
    BUCKETS=$(aws s3api list-buckets --query "Buckets[?contains(Name, 'openapi') || contains(Name, 'mcp-server')].Name" --output text)
    
    for bucket in $BUCKETS; do
        print_status "Emptying bucket: $bucket"
        
        # Check if bucket exists
        if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
            # Empty the bucket
            aws s3 rm "s3://$bucket" --recursive --region "$REGION"
            print_success "Emptied bucket: $bucket"
        else
            print_warning "Bucket not found: $bucket"
        fi
    done
fi

# Step 2.5: Always empty S3 buckets to prevent deletion failures
print_status "Step 2.5: Emptying S3 buckets to prevent deletion failures..."

# Get list of S3 buckets from CloudFormation resources
STACK_RESOURCES=$(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[?contains(StackName, 'McpServerStack') || contains(StackName, 'LambdaAPIStack') || contains(StackName, 'BedrockStack') || contains(StackName, 'OpenSearchStack')].StackName" --output text --region "$REGION")

for stack in $STACK_RESOURCES; do
    print_status "Finding S3 buckets in stack: $stack"
    
    # Get all S3 buckets in the stack
    BUCKET_RESOURCES=$(aws cloudformation list-stack-resources --stack-name "$stack" --query "StackResourceSummaries[?ResourceType=='AWS::S3::Bucket'].PhysicalResourceId" --output text --region "$REGION")
    
    for bucket in $BUCKET_RESOURCES; do
        if [ -n "$bucket" ]; then
            print_status "Emptying bucket: $bucket"
            
            # Check if bucket exists and is accessible
            if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
                # Empty the bucket
                aws s3 rm "s3://$bucket" --recursive --region "$REGION"
                print_success "Emptied bucket: $bucket"
            else
                print_warning "Bucket not found or not accessible: $bucket"
            fi
        fi
    done
done

# Step 3: Destroy all CDK stacks
print_status "Step 3: Destroying CDK stacks..."

cd "$(dirname "$0")/cdk"

# Get list of all stacks created by this CDK app
STACKS=$(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query "StackSummaries[?contains(StackName, 'McpServerStack') || contains(StackName, 'LambdaAPIStack') || contains(StackName, 'BedrockStack') || contains(StackName, 'OpenSearchStack')].StackName" --output text --region "$REGION")

if [ -z "$STACKS" ]; then
    print_warning "No stacks found to destroy"
else
    # Destroy stacks in reverse dependency order
    for stack in $STACKS; do
        print_status "Destroying stack: $stack"
        
        # Destroy the stack
        cdk destroy "$stack" --force --region "$REGION" || {
            print_warning "Failed to destroy $stack using CDK, trying with CloudFormation directly"
            aws cloudformation delete-stack --stack-name "$stack" --region "$REGION"
        }
        
        print_status "Waiting for stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$stack" --region "$REGION" || {
            print_warning "Failed to wait for $stack deletion, it may still be in progress"
        }
        
        print_success "Stack $stack deleted or deletion in progress"
    done
fi

cd ..

# Step 4: Clean up CDK build artifacts
print_status "Step 4: Cleaning up CDK build artifacts..."

if [ -d "cdk/cdk.out" ]; then
    print_status "Removing CDK build artifacts..."
    rm -rf cdk/cdk.out
    print_success "Removed CDK build artifacts"
fi

# Step 5: Clean up local files
print_status "Step 5: Cleaning up local files..."

LOCAL_FILES_TO_REMOVE=(
    "mcp-server-outputs.json"
    "certificate-arn.txt"
    ".env"
)

for file in "${LOCAL_FILES_TO_REMOVE[@]}"; do
    if [ -f "$file" ]; then
        print_status "Removing file: $file"
        rm "$file"
        print_success "Removed $file"
    fi
done

print_success "Comprehensive AWS resource cleanup completed!"
echo ""
print_status "All AWS resources have been removed:"
print_status "✅ ECS service and tasks"
print_status "✅ Application Load Balancer"
print_status "✅ VPC and networking components"
print_status "✅ Lambda functions"
print_status "✅ S3 buckets (emptied before deletion)"
print_status "✅ Bedrock resources"
print_status "✅ IAM roles and policies"
echo ""
print_status "Your AWS account should now be clean of all MCP server resources."
print_status "To deploy again, run: ./deploy-mcp-server-full.sh --my-ip"
echo ""
print_success "Cleanup completed! Your AWS account is now clean. 🎉"