# Jenkins MCP Server

## Introduction

A Model Context Protocol (MCP) server for Jenkins integration with Amazon Q Developer. This solution enables seamless natural language interactions with Jenkins through Amazon Q Developer, allowing users to manage Jenkins jobs, builds, and workflows using conversational AI.

### Key Features

- **Complete Jenkins Integration**: Health check, list jobs, trigger builds, get build logs, create/abort jobs, and queue management
- **OAuth 2.0 Security**: Enterprise-grade authentication with PKCE, token introspection, and automatic discovery
- **Amazon Q Compatible**: Works seamlessly with Amazon Q Developer for natural language Jenkins operations
- **AWS Lambda Deployment**: Scalable serverless architecture with automatic scaling
- **Zero Configuration**: Automated OAuth client registration and endpoint discovery

### Available Jenkins Tools

| Tool | Description | Usage |
|------|-------------|-------|
| `jenkins_health_check` | Test Jenkins connection and server info | Health monitoring |
| `jenkins_list_jobs` | List all accessible Jenkins jobs | Job discovery |
| `jenkins_get_job_info` | Get detailed job information | Job inspection |
| `jenkins_trigger_build` | Trigger Jenkins builds with parameters | Build execution |
| `jenkins_get_build_info` | Get detailed build information | Build status |
| `jenkins_get_build_log` | Get console logs for builds | Debugging |
| `jenkins_list_builds` | List recent builds for a job | Build history |
| `jenkins_create_job` | Create new Jenkins jobs | Job creation |
| `jenkins_abort_build` | Abort running builds | Build management |
| `jenkins_get_queue_info` | Get current build queue status | Queue monitoring |
| `jenkins_get_nodes` | Get Jenkins agents/nodes information | Infrastructure monitoring |

## Solution Architecture

The Jenkins MCP Server implements a secure, scalable architecture using AWS serverless services:

```
Amazon Q ↔ Local MCP Proxy ↔ AWS API Gateway ↔ AWS Lambda ↔ Jenkins Server
```

### Architecture Components

1. **Local MCP Proxy** (`proxy_jenkins_mcp.py`)
   - Handles Amazon Q Developer communication
   - Manages OAuth token lifecycle
   - Translates MCP protocol to HTTP requests

2. **AWS API Gateway** (REST API)
   - Secure HTTPS endpoints with rate limiting (100 req/sec, 200 burst)
   - CORS protection configured for Amazon Q domains
   - Request/response transformation and validation

3. **OAuth Server Lambda** (`deployment/oauth_handler.py`)
   - Implements RFC 8414, RFC 7591, RFC 7636 (PKCE), and RFC 9728
   - Dynamic client registration and token management
   - Secure token introspection and validation

4. **MCP Server Lambda** (`deployment/lambda_handler.py` + `deployment/lambda_mcp_server.py`)
   - Processes MCP protocol requests
   - Authenticates requests using OAuth Bearer tokens
   - Interfaces with Jenkins REST API using `JenkinsClient`

5. **DynamoDB Table**
   - Stores OAuth client registrations and tokens
   - TTL-enabled for automatic token cleanup

6. **Jenkins Integration** (`src/jenkins_client/client.py`)
   - Connects to Jenkins via REST API
   - Uses Jenkins API tokens for authentication
   - Supports all 11 Jenkins operations

### Step-by-Step Flow

1. **Initial Setup**: User configures Jenkins credentials and deploys AWS infrastructure
2. **OAuth Registration**: Local proxy registers as OAuth client with the OAuth server
3. **Token Exchange**: PKCE-based OAuth flow generates secure access tokens
4. **Amazon Q Integration**: User configures Amazon Q to use the local MCP proxy
5. **Request Processing**: 
   - User makes natural language request to Amazon Q
   - Amazon Q sends MCP request to local proxy
   - Proxy forwards authenticated request to AWS API Gateway
   - Lambda processes request and calls Jenkins API
   - Response flows back through the chain to Amazon Q

### Implementation Notes

The Jenkins MCP Server uses a lightweight Lambda-optimized implementation (`deployment/lambda_mcp_server.py`) designed for AWS serverless deployment with all 11 Jenkins tools.

## Project Structure

```
deploy-buildautomation-jenkins-mcp/
├── src/                           # Core source code
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py           # Configuration management
│   └── jenkins_client/
│       ├── __init__.py
│       └── client.py             # Jenkins REST API client
├── deployment/                    # AWS deployment files
│   ├── cdk/                      # CDK infrastructure code
│   │   ├── lib/
│   │   │   ├── jenkins-mcp-oauth-stack.ts
│   │   │   └── jenkins-mcp-server-stack.ts
│   │   ├── app.ts
│   │   ├── cdk.json
│   │   └── package.json
│   ├── lambda_handler.py         # Main Lambda handler
│   ├── lambda_mcp_server.py      # MCP server implementation
│   ├── oauth_handler.py          # OAuth server implementation
│   ├── deploy_cdk.sh            # Deployment script
│   └── package_*.sh             # Lambda packaging scripts
├── proxy_jenkins_mcp.py          # Local MCP proxy for Amazon Q
├── token_config.py               # OAuth token management
├── get_fresh_token.sh           # Token refresh script
├── refresh_and_start.sh         # Complete setup script
├── test_jenkins_mcp.py          # Test script for all tools
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
└── README.md                    # This file
```

## Prerequisites

Before deploying the Jenkins MCP Server, ensure you have:

### Required Software
- **Python 3.11+**: For local MCP proxy and development
- **Node.js 18+**: For AWS CDK deployment
- **AWS CLI**: Configured with appropriate permissions
- **AWS CDK v2**: For infrastructure deployment
- **jq**: For JSON processing in scripts

### AWS Requirements
- AWS account with appropriate permissions
- AWS CLI configured with credentials
- CDK bootstrap completed in target region

### Jenkins Requirements
- **Jenkins Server**: Running Jenkins instance (on-premises or cloud)
- **Jenkins API Token**: Generate from Jenkins user configuration
- **Network Access**: Jenkins server accessible from AWS Lambda
- **Permissions**: User account with appropriate Jenkins permissions

### Amazon Q Developer
- Amazon Q Developer access
- Local configuration file access (`~/.aws/amazonq/mcp.json`)

## Deployment Instructions

### Step 1: Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd jenkins-mcp-server

# Set up Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Configure Jenkins Credentials

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your Jenkins details
# Required variables:
# JENKINS_URL=https://jenkins.yourcompany.com
# JENKINS_USERNAME=your-username
# JENKINS_API_TOKEN=your-jenkins-api-token
```

### Step 3: Set Deployment Environment Variables

```bash
# Export Jenkins variables for deployment
export JENKINS_URL="https://jenkins.yourcompany.com"
export JENKINS_USERNAME="your-username"
export JENKINS_API_TOKEN="your-jenkins-api-token"

# Or source the deployment script
source deployment/.env_var_export.sh
```

### Step 4: Deploy AWS Infrastructure

```bash
# Deploy using CDK
./deployment/deploy_cdk.sh dev

# The deployment creates:
# - 2 Lambda Functions (MCP server and OAuth server)
# - 2 API Gateway REST APIs (secure HTTP endpoints)
# - 1 DynamoDB Table (OAuth client and token storage)
# - IAM Roles (minimal required permissions)
# - CloudWatch Log Groups (monitoring and debugging)

# Update API Gateway URLs in configuration files
./update_urls.sh
```

### Step 5: Configure Amazon Q Integration

```bash
# Add to ~/.aws/amazonq/mcp.json
{
  "mcpServers": {
    "jenkins-mcp-server": {
      "command": "python3",
      "args": [
        "/path/to/your/jenkins-mcp-server/proxy_jenkins_mcp.py"
      ],
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

**Note**: Update the path to match your local installation directory.

### Step 6: Initialize OAuth Token

```bash
# Get fresh OAuth token
./get_fresh_token.sh

# Start Amazon Q
q chat
```

## Test

### Health Check

Test the MCP server health endpoint:

```bash
# Test the MCP server health endpoint
curl https://example-mcp-api-gateway-url.amazonaws.com/dev/health
```

Expected response:
```json
{
  "status": "healthy",
  "message": "Jenkins MCP Server is running",
  "health_check": {
    "status": "success",
    "server_info": {
      "version": "2.401.3",
      "user": {"fullName": "Your Name"},
      "url": "https://jenkins.yourcompany.com"
    }
  }
}
```

### OAuth Server Test

Test OAuth client registration:

```bash
curl -X POST https://example-oauth-api-gateway-url.amazonaws.com/dev/register \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris": ["https://example.com/callback"], "client_name": "Test Client"}'
```

### MCP Server Test

Test MCP server with authentication:

```bash
# First get a fresh token
./get_fresh_token.sh

# Test tools list
curl -X POST https://example-mcp-api-gateway-url.amazonaws.com/dev/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### Amazon Q Integration Test

Once configured, test with natural language commands:

```
"Check Jenkins server health"
"List all Jenkins jobs"
"Show me details for job my-app-build"
"Trigger a build for my-app-build"
"Get the console log for build #42 of my-app-build"
"Create a new job called test-job that runs npm test"
"Show me the current build queue"
"Get information about Jenkins nodes"
```

### Get Deployed URLs

After deployment, retrieve your API Gateway URLs:

```bash
# Get OAuth server URL
aws cloudformation describe-stacks --stack-name JenkinsMcpOAuthStack-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`OAuthApiEndpoint`].OutputValue' --output text

# Get MCP server URL
aws cloudformation describe-stacks --stack-name JenkinsMcpServerStack-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`McpApiEndpoint`].OutputValue' --output text
```

### Monitoring

Monitor Lambda function logs:

```bash
# View MCP server logs
aws logs tail /aws/lambda/jenkins-mcp-server-dev --follow

# View OAuth server logs
aws logs tail /aws/lambda/jenkins-mcp-oauth-server-dev --follow
```

## Jenkins Configuration

### API Token Generation

1. Log into your Jenkins instance
2. Go to **People** → **[Your Username]** → **Configure**
3. Scroll to **API Token** section
4. Click **Add new Token**
5. Give it a name (e.g., "MCP Server")
6. Click **Generate** and copy the token
7. Use this token as `JENKINS_API_TOKEN` in your configuration

### Required Permissions

Your Jenkins user should have the following permissions:
- **Overall/Read**: View Jenkins
- **Job/Build**: Trigger builds
- **Job/Read**: View job configurations
- **Job/Create**: Create new jobs (if using job creation features)

### Network Configuration

Ensure your Jenkins server is accessible from AWS Lambda:
- **Public Jenkins**: No additional configuration needed
- **Private Jenkins**: Configure VPC, security groups, or VPN as needed
- **Firewall**: Allow HTTPS traffic from AWS IP ranges

## Clean Up

To remove all AWS resources and clean up the deployment:

### Remove AWS Infrastructure

```bash
# Destroy CDK stacks
./deployment/destroy_cdk.sh

# Or manually destroy
cd deployment/cdk
npx cdk destroy --all --force
```

### Clean Local Environment

```bash
# Deactivate Python environment
deactivate

# Remove virtual environment (optional)
rm -rf venv

# Remove generated files
rm -f proxy_jenkins_mcp.py.bak
rm -f .env
rm -f ~/.jenkins_mcp_token.json
```

### Verify Cleanup

```bash
# Verify stacks are deleted
aws cloudformation list-stacks --stack-status-filter DELETE_COMPLETE

# Check for remaining resources
aws lambda list-functions --query 'Functions[?contains(FunctionName, `jenkins-mcp`)]'
aws apigateway get-rest-apis --query 'items[?contains(name, `jenkins-mcp`)]'
```

## Security

This solution implements multiple layers of security:

- **OAuth 2.0 with PKCE**: Prevents authorization code interception attacks
- **Token Introspection**: Real-time token validation and revocation support
- **Minimal IAM Permissions**: Least privilege access for all AWS resources
- **HTTPS Only**: All communication encrypted via API Gateway
- **Rate Limiting**: API Gateway throttling (100 req/sec, 200 burst)
- **CORS Protection**: Configured for secure cross-origin requests
- **Token Expiration**: Automatic token cleanup with 1-hour expiry

**Important**: This solution stores Jenkins API tokens in Lambda environment variables. For production deployments, consider using AWS Secrets Manager or AWS Systems Manager Parameter Store for enhanced security.

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check Jenkins URL and network connectivity
2. **Authentication Failed**: Verify Jenkins username and API token
3. **Permission Denied**: Ensure Jenkins user has required permissions
4. **Token Expired**: Run `./get_fresh_token.sh` to refresh OAuth token

### Debug Commands

```bash
# Test Jenkins connection directly
python3 -m src.jenkins_client.client

# Check OAuth token
python3 -c "from token_config import test_token_flow; import asyncio; asyncio.run(test_token_flow())"

# View Lambda logs
aws logs tail /aws/lambda/jenkins-mcp-server-dev --follow
```

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.

## Disclaimer

The solution architecture sample code is provided without any guarantees, and you're not recommended to use it for production-grade workloads. The intention is to provide content to build and learn. Be sure of reading the licensing terms.

---

**Estimated Monthly Cost**: $1-10 for typical usage (AWS Free Tier eligible)
