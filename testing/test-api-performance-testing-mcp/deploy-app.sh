#!/bin/bash

set -e

echo "🚀 Deploy Application for Performance Testing"
echo "============================================="

# Configuration
REGION="${REGION:-us-west-2}"
export AWS_PROFILE=default
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CLUSTER_NAME="performance-testing-cluster"

echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo "ECS Cluster: $CLUSTER_NAME"
echo ""

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -a, --app-dir PATH          Path to application directory with Dockerfile"
    echo "  -n, --app-name NAME         Application name (used for ECR repo and ECS service)"
    echo "  -p, --port PORT             Application port (default: 8080)"
    echo "  -c, --cpu CPU               CPU units (default: 512)"
    echo "  -m, --memory MEMORY         Memory in MB (default: 1024)"
    echo "  -r, --replicas COUNT        Number of replicas (default: 2)"
    echo "  -e, --env KEY=VALUE         Environment variables (can be used multiple times)"
    echo "  -h, --help                  Show this help message"
    echo ""
    echo "Examples:"
    echo "  # Deploy a simple web app"
    echo "  $0 --app-dir ./my-web-app --app-name my-web-app --port 3000"
    echo ""
    echo "  # Deploy with custom resources and environment"
    echo "  $0 --app-dir ./api-service --app-name api-service \\"
    echo "     --cpu 1024 --memory 2048 --replicas 3 \\"
    echo "     --env DATABASE_URL=postgres://... --env API_KEY=secret"
    echo ""
    echo "  # Deploy the demo fake API"
    echo "  $0 --app-dir ./fake-api-service --app-name fake-api"
}

# Default values
APP_DIR=""
APP_NAME=""
APP_PORT="8080"
CPU="512"
MEMORY="1024"
REPLICAS="2"
ENV_VARS=()

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--app-dir)
            APP_DIR="$2"
            shift 2
            ;;
        -n|--app-name)
            APP_NAME="$2"
            shift 2
            ;;
        -p|--port)
            APP_PORT="$2"
            shift 2
            ;;
        -c|--cpu)
            CPU="$2"
            shift 2
            ;;
        -m|--memory)
            MEMORY="$2"
            shift 2
            ;;
        -r|--replicas)
            REPLICAS="$2"
            shift 2
            ;;
        -e|--env)
            ENV_VARS+=("$2")
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$APP_DIR" ]]; then
    echo "❌ Error: Application directory is required"
    show_usage
    exit 1
fi

if [[ -z "$APP_NAME" ]]; then
    echo "❌ Error: Application name is required"
    show_usage
    exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
    echo "❌ Error: Application directory '$APP_DIR' does not exist"
    exit 1
fi

if [[ ! -f "$APP_DIR/Dockerfile" ]]; then
    echo "❌ Error: Dockerfile not found in '$APP_DIR'"
    exit 1
fi

# Sanitize app name for AWS resources
APP_NAME_CLEAN=$(echo "$APP_NAME" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | sed 's/--*/-/g' | sed 's/^-\|-$//g')

echo "📋 Deployment Configuration:"
echo "  Application Directory: $APP_DIR"
echo "  Application Name: $APP_NAME_CLEAN"
echo "  Port: $APP_PORT"
echo "  CPU: $CPU"
echo "  Memory: $MEMORY MB"
echo "  Replicas: $REPLICAS"
if [[ ${#ENV_VARS[@]} -gt 0 ]]; then
    echo "  Environment Variables:"
    for env_var in "${ENV_VARS[@]}"; do
        echo "    $env_var"
    done
fi
echo ""

# Confirmation
read -p "🤔 Proceed with deployment? (y/n): " -r
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled."
    exit 1
fi

echo ""
echo "🚀 Starting deployment process..."

# Step 1: Create ECR repository
echo "📦 Step 1: Creating ECR repository..."
ECR_REPO_NAME="$APP_NAME_CLEAN"

if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "ECR repository '$ECR_REPO_NAME' already exists"
else
    echo "Creating ECR repository '$ECR_REPO_NAME'..."
    aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$REGION" >/dev/null
fi

ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO_NAME"
echo "✅ ECR repository ready: $ECR_URI"
echo ""

# Step 2: Build and push Docker image
echo "🐳 Step 2: Building and pushing Docker image..."

# ECR login
echo "Logging into ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Build image
echo "Building Docker image..."
# Use buildx for cross-platform builds (ARM64 Mac -> AMD64 ECS)
if command -v docker buildx >/dev/null 2>&1; then
    echo "Using Docker buildx for cross-platform build..."
    docker buildx build --platform linux/amd64 -t "$APP_NAME_CLEAN" --load "$APP_DIR"
else
    echo "Using regular Docker build..."
    docker build -t "$APP_NAME_CLEAN" "$APP_DIR"
fi

# Tag and push
echo "Tagging and pushing image..."
docker tag "$APP_NAME_CLEAN:latest" "$ECR_URI:latest"
docker push "$ECR_URI:latest"

echo "✅ Docker image pushed successfully!"
echo ""

# Step 3: Create ECS task definition
echo "🏗️  Step 3: Creating ECS task definition..."

# Build environment variables JSON
ENV_JSON="[]"
if [[ ${#ENV_VARS[@]} -gt 0 ]]; then
    ENV_JSON="["
    for i in "${!ENV_VARS[@]}"; do
        IFS='=' read -r key value <<< "${ENV_VARS[$i]}"
        ENV_JSON+="{\"name\":\"$key\",\"value\":\"$value\"}"
        if [[ $i -lt $((${#ENV_VARS[@]} - 1)) ]]; then
            ENV_JSON+=","
        fi
    done
    ENV_JSON+="]"
fi

# Create task definition JSON
TASK_DEF_JSON=$(cat <<EOF
{
  "family": "$APP_NAME_CLEAN",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "$CPU",
  "memory": "$MEMORY",
  "executionRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/PerformanceTestingStack-ECSTaskExecutionRole*",
  "taskRoleArn": "arn:aws:iam::$ACCOUNT_ID:role/PerformanceTestingStack-ECSTaskRole*",
  "containerDefinitions": [
    {
      "name": "$APP_NAME_CLEAN-container",
      "image": "$ECR_URI:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": $APP_PORT,
          "protocol": "tcp"
        }
      ],
      "environment": $ENV_JSON,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/$APP_NAME_CLEAN",
          "awslogs-region": "$REGION",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
EOF
)

# Create CloudWatch log group
echo "Creating CloudWatch log group..."
aws logs create-log-group --log-group-name "/ecs/$APP_NAME_CLEAN" --region "$REGION" >/dev/null 2>&1 || echo "Log group already exists"

# Register task definition
echo "Registering ECS task definition..."
echo "$TASK_DEF_JSON" > "/tmp/$APP_NAME_CLEAN-task-def.json"

# Get the actual role ARNs
EXECUTION_ROLE_ARN=$(aws iam list-roles --query "Roles[?contains(RoleName, 'PerformanceTestingStack') && contains(RoleName, 'ECSTaskExecutionRole')].Arn" --output text)
TASK_ROLE_ARN=$(aws iam list-roles --query "Roles[?contains(RoleName, 'PerformanceTestingStack') && contains(RoleName, 'ECSTaskRole')].Arn" --output text)

# Update task definition with actual ARNs
sed -i.bak "s|arn:aws:iam::$ACCOUNT_ID:role/PerformanceTestingStack-ECSTaskExecutionRole\\*|$EXECUTION_ROLE_ARN|g" "/tmp/$APP_NAME_CLEAN-task-def.json"
sed -i.bak "s|arn:aws:iam::$ACCOUNT_ID:role/PerformanceTestingStack-ECSTaskRole\\*|$TASK_ROLE_ARN|g" "/tmp/$APP_NAME_CLEAN-task-def.json"

aws ecs register-task-definition --cli-input-json "file:///tmp/$APP_NAME_CLEAN-task-def.json" >/dev/null

echo "✅ ECS task definition created!"
echo ""

# Step 4: Create ECS service with ALB integration
echo "🚀 Step 4: Creating ECS service with load balancer..."

# Get VPC and subnet information
VPC_ID=$(aws cloudformation describe-stacks --stack-name PerformanceTestingStack --query 'Stacks[0].Outputs[?OutputKey==`VPCId`].OutputValue' --output text)
SUBNETS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" "Name=tag:Name,Values=*Private*" --query 'Subnets[].SubnetId' --output text | tr '\t' ',')
SECURITY_GROUP=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=*ECSSecurityGroup*" --query 'SecurityGroups[0].GroupId' --output text)

# Get Internal ALB information
INTERNAL_ALB_DNS=$(aws cloudformation describe-stacks --stack-name PerformanceTestingStack --query 'Stacks[0].Outputs[?OutputKey==`InternalALBDNSName`].OutputValue' --output text)
ALB_FULL_ARN=$(aws elbv2 describe-load-balancers --query "LoadBalancers[?DNSName=='$INTERNAL_ALB_DNS'].LoadBalancerArn" --output text)

# Create target group for this application
echo "Creating target group for $APP_NAME_CLEAN..."
TIMESTAMP=$(date +%s)
TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
    --name "$APP_NAME_CLEAN-tg-$TIMESTAMP" \
    --protocol HTTP \
    --port "$APP_PORT" \
    --vpc-id "$VPC_ID" \
    --target-type ip \
    --health-check-path /health \
    --health-check-protocol HTTP \
    --health-check-interval-seconds 15 \
    --health-check-timeout-seconds 10 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --query 'TargetGroups[0].TargetGroupArn' --output text)

echo "✅ Target group created: $TARGET_GROUP_ARN"

# Update ALB listener to route to this target group
LISTENER_ARN=$(aws elbv2 describe-listeners --load-balancer-arn "$ALB_FULL_ARN" --query 'Listeners[0].ListenerArn' --output text)
aws elbv2 modify-listener \
    --listener-arn "$LISTENER_ARN" \
    --default-actions Type=forward,TargetGroupArn="$TARGET_GROUP_ARN" >/dev/null

echo "✅ Load balancer updated to route to $APP_NAME_CLEAN"

# Ensure ALB security group can reach ECS security group
ALB_SECURITY_GROUP=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=*ALBSecurityGroup*" --query 'SecurityGroups[0].GroupId' --output text)

# Add egress rule to ALB security group to reach ECS on the app port
aws ec2 authorize-security-group-egress \
    --group-id "$ALB_SECURITY_GROUP" \
    --protocol tcp \
    --port "$APP_PORT" \
    --source-group "$SECURITY_GROUP" 2>/dev/null || echo "ALB egress rule already exists"

# Add ingress rule to ECS security group to allow ALB traffic
aws ec2 authorize-security-group-ingress \
    --group-id "$SECURITY_GROUP" \
    --protocol tcp \
    --port "$APP_PORT" \
    --source-group "$ALB_SECURITY_GROUP" 2>/dev/null || echo "ECS ingress rule already exists"

echo "✅ Security groups configured for ALB ↔ ECS communication"

# Get service discovery namespace ID for internal communication
NAMESPACE_ID=$(aws servicediscovery list-namespaces --query "Namespaces[?Name=='performance-testing.local'].Id" --output text)

# Create ECS service with both ALB and service discovery
echo "Creating ECS service '$APP_NAME_CLEAN' with load balancer and service discovery..."

SERVICE_REGISTRY_CONFIG=""
if [[ -n "$NAMESPACE_ID" && "$NAMESPACE_ID" != "None" ]]; then
    # Create service discovery service
    SERVICE_ID=$(aws servicediscovery create-service \
        --name "$APP_NAME_CLEAN" \
        --namespace-id "$NAMESPACE_ID" \
        --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
        --health-check-grace-period-seconds 60 \
        --query 'Service.Id' --output text 2>/dev/null || echo "")
    
    if [[ -n "$SERVICE_ID" && "$SERVICE_ID" != "None" ]]; then
        SERVICE_REGISTRY_CONFIG="--service-registries registryArn=arn:aws:servicediscovery:$REGION:$ACCOUNT_ID:service/$SERVICE_ID,port=$APP_PORT"
        echo "Service discovery configured for $APP_NAME_CLEAN.performance-testing.local"
    fi
fi

aws ecs create-service \
    --cluster "$CLUSTER_NAME" \
    --service-name "$APP_NAME_CLEAN" \
    --task-definition "$APP_NAME_CLEAN" \
    --desired-count "$REPLICAS" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SECURITY_GROUP],assignPublicIp=DISABLED}" \
    --load-balancers targetGroupArn="$TARGET_GROUP_ARN",containerName="$APP_NAME_CLEAN-container",containerPort="$APP_PORT" \
    --health-check-grace-period-seconds 60 \
    $SERVICE_REGISTRY_CONFIG \
    >/dev/null

echo "✅ ECS service created!"
echo ""

# Step 5: Force new deployment to pull latest image
echo "🔄 Step 5: Forcing deployment to pull latest image..."
aws ecs update-service --cluster "$CLUSTER_NAME" --service "$APP_NAME_CLEAN" --force-new-deployment >/dev/null
echo "✅ New deployment triggered"
echo ""

# Step 6: Wait for service to become stable
echo "⏳ Step 6: Waiting for service to become healthy..."
echo "This may take 3-5 minutes..."

aws ecs wait services-stable --cluster "$CLUSTER_NAME" --services "$APP_NAME_CLEAN"

echo "✅ Service is healthy and running!"
echo ""

# Step 7: Get service information
echo "📋 Deployment Summary:"
echo "======================"
echo "• Application: $APP_NAME_CLEAN"
echo "• ECR Repository: $ECR_URI"
echo "• ECS Service: $APP_NAME_CLEAN"
echo "• Running Tasks: $REPLICAS"
echo "• Port: $APP_PORT"
echo ""

# Get service endpoint information
TASKS=$(aws ecs list-tasks --cluster "$CLUSTER_NAME" --service-name "$APP_NAME_CLEAN" --query 'taskArns[0]' --output text)
if [[ "$TASKS" != "None" ]]; then
    TASK_DETAIL=$(aws ecs describe-tasks --cluster "$CLUSTER_NAME" --tasks "$TASKS" --query 'tasks[0].attachments[0].details[?name==`privateIPv4Address`].value' --output text)
    echo "• Private IP: $TASK_DETAIL:$APP_PORT"
    echo "• Service Discovery: $APP_NAME_CLEAN.performance-testing.local:$APP_PORT"
fi

echo ""
echo "🎯 Application URLs:"
echo "Getting application URLs..."

# Get internal ALB URL (for VPC-only access)
INTERNAL_ALB_URL=$(aws cloudformation describe-stacks --stack-name PerformanceTestingStack --query 'Stacks[0].Outputs[?OutputKey==`InternalALBDNSName`].OutputValue' --output text)
INTERNAL_URL="$APP_NAME_CLEAN.performance-testing.local"

echo ""
echo "✅ Application is accessible at:"
echo "  • Internal ALB (VPC-only): http://$INTERNAL_ALB_URL"
echo "  • Service Discovery: $INTERNAL_URL:$APP_PORT"
echo ""
echo "🧪 Test the deployment (from within VPC):"
echo "  curl http://$INTERNAL_ALB_URL/health"
echo ""
echo "🎯 MCP Server Configuration Examples:"
echo "  # For load balancer testing (recommended for JMeter):"
echo "  execution_environment: {"
echo "    \"target_url\": \"$INTERNAL_ALB_URL\""
echo "  }"
echo ""
echo "  # For service discovery testing:"
echo "  execution_environment: {"
echo "    \"target_url\": \"$INTERNAL_URL:$APP_PORT\""
echo "  }"
echo ""
echo "🧹 To remove this application:"
echo "  aws ecs update-service --cluster $CLUSTER_NAME --service $APP_NAME_CLEAN --desired-count 0"
echo "  aws ecs delete-service --cluster $CLUSTER_NAME --service $APP_NAME_CLEAN"
echo "  aws ecr delete-repository --repository-name $ECR_REPO_NAME --force"
echo ""
echo "🎉 Application deployed successfully!"

# Cleanup temp files
rm -f "/tmp/$APP_NAME_CLEAN-task-def.json" "/tmp/$APP_NAME_CLEAN-task-def.json.bak"