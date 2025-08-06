# MCP Server Deployment Guide

This guide explains how to deploy and manage the MCP server for OpenAPI documentation generation.

## Prerequisites

- AWS CLI configured with appropriate permissions
- Docker installed locally
- Node.js and npm installed

## Deployment Scripts

### 1. Full Deployment

The `deploy-mcp-server-full.sh` script handles the complete deployment process:

1. Builds and pushes the Docker image to ECR
2. Deploys the CDK stack with all required resources
3. Updates the ECS service to start running tasks
4. Waits for the service to be stable

```bash
# Deploy with your current IP allowed to access the ALB
./deploy-mcp-server-full.sh --my-ip

# Deploy with specific IP restrictions
./deploy-mcp-server-full.sh --allowed-ips "192.168.1.1/32,10.0.0.0/24"

# Deploy with HTTPS using an existing certificate
./deploy-mcp-server-full.sh --my-ip --certificate-arn "arn:aws:acm:region:account:certificate/certificate-id"

# Deploy with a new certificate (requires DNS validation)
./deploy-mcp-server-full.sh --my-ip --create-certificate --domain-name "mcp.example.com"

# Skip Docker image build/push (if already done)
./deploy-mcp-server-full.sh --my-ip --skip-image-push

# Deploy with multiple ECS tasks
./deploy-mcp-server-full.sh --my-ip --desired-count 2

# Specify a different platform (default is linux/amd64)
./deploy-mcp-server-full.sh --my-ip --platform linux/amd64
```

### 2. Docker Image Build and Push

The `push-to-ecr.sh` script builds and pushes the Docker image to ECR using Podman:

```bash
# Basic usage
./push-to-ecr.sh

# Specify platform (default is linux/amd64)
./push-to-ecr.sh --platform linux/amd64

# Force rebuild without cache
./push-to-ecr.sh --force-build
```

### 3. Stack Update

The `update-stack.sh` script updates the CDK stack without rebuilding the Docker image:

```bash
./update-stack.sh
```

## Cleanup Scripts

### 1. Complete Resource Cleanup

The `cleanup-all-resources.sh` script removes all AWS resources created for the MCP server:

```bash
# Show cleanup options
./cleanup-all-resources.sh --help

# Remove all resources (with confirmation prompt)
./cleanup-all-resources.sh

# Remove all resources without confirmation
./cleanup-all-resources.sh --confirm

# Also delete all ECR images
./cleanup-all-resources.sh --confirm --delete-ecr-images

# Also empty S3 buckets before removal
./cleanup-all-resources.sh --confirm --delete-s3-content
```

### 2. Unused Files Cleanup

The `cleanup-unused-files.sh` script removes unnecessary files from the project:

```bash
./cleanup-unused-files.sh
```

### 3. Project Structure Cleanup

The `cleanup-for-mcp.sh` script optimizes the project structure for MCP server deployment:

```bash
./cleanup-for-mcp.sh
```

## Docker Image Building

The deployment process uses Podman to build Docker images with the following characteristics:

- **Container Engine**: Podman (instead of Docker)
- **Target Architecture**: x86_64/amd64 (specified with `--platform linux/amd64`)
- **Base Image**: Node.js Alpine (as defined in the Dockerfile)
- **Repository**: Amazon ECR (Elastic Container Registry)

This ensures compatibility with AWS ECS Fargate, which runs on x86_64 architecture.

## Deployment Architecture

The MCP server deployment consists of:

1. **ECS Fargate Service**: Runs the MCP server container
2. **Application Load Balancer**: Routes traffic to the ECS service
3. **VPC with Private Subnets**: Secure networking for the ECS service
4. **VPC Endpoints**: Allow private connectivity to AWS services
5. **Lambda Functions**: Domain analyzer and documentation generator
6. **S3 Bucket**: Stores domain analysis results and generated documentation

## Accessing the MCP Server

After deployment, the MCP server URL will be displayed in the deployment summary and saved to the `.env` file. You can access the server at:

- HTTP: `http://<load-balancer-dns>/`
- HTTPS: `https://<load-balancer-dns>/` (if certificate was provided)

The health endpoint is available at `/health`.

## Troubleshooting

### Common Issues

1. **ALB Access Denied**: Ensure your IP is included in the allowed IPs
2. **ECS Service Not Starting**: Check CloudWatch Logs for container errors
3. **Certificate Validation**: Ensure DNS records are created for certificate validation

### Logs

- ECS container logs: CloudWatch Logs group `/ecs/mcp-server`
- ALB access logs: S3 bucket `mcp-server-alb-logs-<account-id>-<region>`

### AWS Console

You can also check the status of resources in the AWS Console:

- ECS: https://console.aws.amazon.com/ecs/
- CloudFormation: https://console.aws.amazon.com/cloudformation/
- CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/