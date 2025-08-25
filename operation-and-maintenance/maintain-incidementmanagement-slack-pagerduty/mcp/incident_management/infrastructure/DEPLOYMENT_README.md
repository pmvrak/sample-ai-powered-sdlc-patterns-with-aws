# AWS Deployment Guide

Deployment guide for the Incident Management System on AWS ECS Fargate.

## Quick Start

```bash
cd operation-and-maintenance/maintain-incidentmanagement/mcp/incident_management/infrastructure

# Deploy to development
./deploy.sh -e dev -a YOUR_ACCOUNT_ID

# Deploy to production  
./deploy.sh -e prod -a YOUR_ACCOUNT_ID -r us-west-2
```

## Prerequisites

- **AWS CLI** configured with appropriate credentials
- **Docker** installed and running
- **AWS CDK** installed (`npm install -g aws-cdk`)
- **Python 3.8+** with pip

## Architecture

The system deploys as a containerized FastAPI application on ECS Fargate with:

- **ECS Fargate** - Serverless container hosting
- **Application Load Balancer** - Traffic routing and health checks
- **AWS Secrets Manager** - Secure credential storage
- **CloudWatch Logs** - Centralized logging
- **Auto Scaling** - Based on CPU/memory utilization
- **In-Memory Storage** - Incident data with optional file persistence

### Security Note

⚠️ **Development/Demo Environment**: This deployment uses a simplified architecture suitable for development and demonstration purposes. For production deployments, consider adding:

- **AWS WAF v2** - Web Application Firewall with OWASP Top 10 rules
- **API Gateway** - Rate limiting, request validation, and API management
- **CloudFront** - DDoS protection and global content delivery
- **VPC Flow Logs** - Network traffic monitoring
- **Container Insights** - Enhanced monitoring and security visibility

Current security measures include:
- Non-root container execution with dropped capabilities
- ALB security groups restricting network access
- Secrets management via AWS Secrets Manager
- Application-level input validation and authentication

### Network Segmentation Note

⚠️ **Network Architecture**: This demo deployment uses basic network segmentation:

**Current Implementation:**
- **Default VPC** - Uses AWS default VPC for simplicity
- **Security Groups** - ALB and ECS service have separate security groups with least-privilege rules
- **Public Subnets** - ECS tasks run in public subnets with internet gateway access
- **Traffic Flow** - Internet → ALB (port 80) → ECS (port 8002)

**Production Recommendations:**
- **Custom VPC** - Dedicated VPC with public/private subnet architecture
- **Private Subnets** - ECS tasks in private subnets with NAT Gateway for outbound traffic
- **VPC Endpoints** - AWS service endpoints to reduce internet traffic
- **Network ACLs** - Additional network-level access controls
- **VPC Flow Logs** - Network traffic monitoring and analysis

**Current Security Groups:**
- ALB Security Group: Allows HTTP (80) from internet (0.0.0.0/0)
- ECS Security Group: Allows traffic from ALB security group on port 8002 only

### Storage Note

⚠️ **Demo Storage**: This deployment uses simplified in-memory storage:

**Current Implementation:**
- **Memory Storage** - All incident data stored in application memory
- **File Persistence** - Optional backup to `/tmp/*.json` files in container
- **Data Lifecycle** - Data persists only during container lifetime
- **Scalability** - Single container limitation (no shared storage)

**Production Recommendations:**
- **Database** - PostgreSQL RDS or DynamoDB for persistent storage (currently using in-memory + file storage)
- **Caching** - Redis or ElastiCache for performance
- **Backup Strategy** - Automated backups with point-in-time recovery for persistent storage
- **High Availability** - Multi-AZ deployment with data replication
- **HTTPS/TLS** - Enable HTTPS for secure communication (see HTTPS Configuration section below)

**Current Storage Files:**
- `/tmp/incident_cache.json` - Incident metadata cache
- `/tmp/processed_incidents.json` - List of processed incident IDs

## 🔒 HTTPS Configuration for Production

> **⚠️ Security Warning**: The current deployment uses HTTP (port 80) for demo purposes only. Production deployments must use HTTPS to ensure secure communication.

### Step-by-Step HTTPS Implementation

#### 1. **Use AWS Certificate Manager (ACM)**
```bash
# Create SSL certificate for your domain
aws acm request-certificate \
  --domain-name incident-management.your-domain.com \
  --validation-method DNS \
  --region us-east-1
```

#### 2. **Update ALB Configuration**
- **Change Protocol**: From HTTP port 80 to HTTPS port 443 with certificate
- **Add Certificate**: Include ACM certificate ARN in ALB listener
- **Modify Code**: Update `simple_ecs_stack.py` listener configuration

#### 3. **Add HTTP Redirect**
- **Set Redirect**: Configure HTTP to HTTPS redirect = `true`
- **Force HTTPS**: Ensure all traffic automatically upgrades to secure connection

#### 4. **Update Stack Outputs**
- **Change URL Output**: Use HTTPS protocol in stack outputs
- **Add Certificate ARN**: Include certificate ARN output for reference
- **Update Health Checks**: Modify health check URLs to use HTTPS

#### 5. **Add CDK Suppressions**
- **Certificate Validation**: Add CDK Nag suppressions for certificate validation
- **HTTP Listener**: Suppress warnings for HTTP listener (used only for redirect)

#### 6. **Environment Configuration**
```bash
# Add to .env file
ENABLE_HTTPS=true
CERTIFICATE_ARN=arn:aws:acm:us-east-1:YOUR_ACCOUNT_ID:certificate/YOUR_CERTIFICATE_ID
DOMAIN_NAME=incident-management.your-domain.com
```

#### 7. **Deploy with HTTPS**
```bash
# Deploy with HTTPS configuration
./deploy.sh -e prod --enable-https
```

### Code Changes Required

**File: `simple_ecs_stack.py`**
```python
# Add HTTPS listener
https_listener = alb.add_listener(
    "HttpsListener",
    port=443,
    protocol=elbv2.ApplicationProtocol.HTTPS,
    certificates=[elbv2.ListenerCertificate.from_arn(certificate_arn)],
    default_target_groups=[target_group]
)

# Add HTTP redirect
http_listener = alb.add_listener(
    "HttpListener", 
    port=80,
    protocol=elbv2.ApplicationProtocol.HTTP,
    default_action=elbv2.ListenerAction.redirect(
        protocol="HTTPS",
        port="443",
        permanent=True
    )
)
```

### Security Benefits
- ✅ **Data Encryption**: All API communications encrypted in transit
- ✅ **Authentication**: Server identity verified via SSL certificate  
- ✅ **Compliance**: Meets security requirements for production systems
- ✅ **Browser Trust**: Secure connection indicators in web browsers

## Usage

```bash
./deploy.sh [OPTIONS]

OPTIONS:
    -e, --environment ENV    Environment (dev, staging, prod) [default: dev]
    -r, --region REGION      AWS region [default: us-east-1]
    -a, --account ACCOUNT    AWS account ID (required)
    -c, --action ACTION      Action (deploy, destroy, diff, synth) [default: deploy]
    --skip-secrets          Skip populating secrets from .env
    -h, --help              Show help message
```

## Examples

```bash
# Standard deployment
./deploy.sh -e dev -a 123456789012

# Deploy to different region
./deploy.sh -e prod -a 123456789012 -r eu-west-1

# Show what would be deployed (diff)
./deploy.sh -e dev -a 123456789012 -c diff

# Deploy without updating secrets
./deploy.sh -e dev -a 123456789012 --skip-secrets

# Destroy environment
./deploy.sh -e dev -a 123456789012 -c destroy
```

## Post-Deployment

After successful deployment, you'll get:

- **Application URL**: `http://your-alb-dns-name`
- **Health Check**: `http://your-alb-dns-name/health`
- **API Docs**: `http://your-alb-dns-name/docs`
- **System Info**: `http://your-alb-dns-name/system/info`

## Secret Management

Secrets are automatically populated from `.env`:

- **Slack Integration**: `incident-management/slack-config-{env}`
- **PagerDuty Integration**: `incident-management/pagerduty-config-{env}`
- **Application Config**: `incident-management/app-config-{env}`
- **Splunk Config**: `incident-management/splunk-config-{env}`

## Troubleshooting

### Container Architecture Issues
If you see "Essential container exited with code 255":
- Ensure Docker is building for `linux/amd64`
- The deployment script verifies this automatically

### Health Check Failures
```bash
# View logs
aws logs tail /ecs/incident-management-dev --follow --region us-east-1

# Check service status
aws ecs describe-services --cluster incident-management-dev --services incident-management-dev --region us-east-1
```

### Failed Stack Cleanup
The script automatically detects and cleans up failed stacks in `ROLLBACK_COMPLETE` state.

## Support

For issues or questions:
1. Check the deployment logs
2. Verify prerequisites are met
3. Ensure `.env` is properly configured
4. Review AWS CloudFormation events in the console