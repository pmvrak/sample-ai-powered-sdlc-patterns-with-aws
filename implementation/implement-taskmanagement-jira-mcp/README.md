# JIRA MCP Server

## Introduction

A Model Context Protocol (MCP) server for JIRA integration with Amazon Q Developer. This solution enables seamless natural language interactions with JIRA through Amazon Q Developer, allowing users to manage JIRA projects, issues, and workflows using conversational AI.

### Key Features

- **Complete JIRA Integration**: Health check, list projects, create issues, search issues, and get issue details
- **OAuth 2.0 Security**: Enterprise-grade authentication with PKCE, token introspection, and automatic discovery
- **Amazon Q Compatible**: Works seamlessly with Amazon Q Developer for natural language JIRA operations
- **AWS Lambda Deployment**: Scalable serverless architecture with automatic scaling
- **Zero Configuration**: Automated OAuth client registration and endpoint discovery

### Available JIRA Tools

| Tool | Description | Usage |
|------|-------------|-------|
| `jira_health_check` | Test JIRA connection and server info | Health monitoring |
| `jira_list_projects` | List all accessible JIRA projects | Project discovery |
| `jira_create_issue` | Create new JIRA issues | Issue creation |
| `jira_search_issues` | Search issues using JQL | Issue discovery |
| `jira_get_issue` | Get detailed issue information | Issue details |
| `jira_add_comment` | Add comments to JIRA issues | Issue updates |

## Solution Architecture

The JIRA MCP Server implements a secure, scalable architecture using AWS serverless services:

```
Amazon Q ↔ Local MCP Proxy ↔ AWS API Gateway ↔ AWS Lambda ↔ JIRA Cloud
```

### Architecture Components

1. **Local MCP Proxy** (`proxy_jira_mcp.py`)
   - Handles Amazon Q Developer communication
   - Manages OAuth token lifecycle
   - Translates MCP protocol to HTTP requests

2. **AWS API Gateway** (REST API)
   - Secure HTTPS endpoints with rate limiting (100 req/sec, 200 burst)
   - CORS protection configured for Amazon Q domains
   - Request/response transformation and validation

3. **OAuth Server Lambda**
   - Implements RFC 8414, RFC 7591, RFC 7636 (PKCE), and RFC 9728
   - Dynamic client registration and token management
   - Secure token introspection and validation

4. **MCP Server Lambda**
   - Processes MCP protocol requests
   - Authenticates requests using OAuth Bearer tokens
   - Interfaces with JIRA Cloud REST API

5. **DynamoDB Table**
   - Stores OAuth client registrations and tokens
   - TTL-enabled for automatic token cleanup

6. **JIRA Cloud Integration**
   - Connects to JIRA Cloud via REST API
   - Uses JIRA API tokens for authentication
   - Supports all major JIRA operations

### Step-by-Step Flow

1. **Initial Setup**: User configures JIRA credentials and deploys AWS infrastructure
2. **OAuth Registration**: Local proxy registers as OAuth client with the OAuth server
3. **Token Exchange**: PKCE-based OAuth flow generates secure access tokens
4. **Amazon Q Integration**: User configures Amazon Q to use the local MCP proxy
5. **Request Processing**: 
   - User makes natural language request to Amazon Q
   - Amazon Q sends MCP request to local proxy
   - Proxy forwards authenticated request to AWS API Gateway
   - Lambda processes request and calls JIRA API
   - Response flows back through the chain to Amazon Q

## Prerequisites

Before deploying the JIRA MCP Server, ensure you have:

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

### JIRA Requirements
- **JIRA Cloud instance**: Active Atlassian Cloud account
- **JIRA API Token**: Generate from [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
- **Project Access**: Permissions to view/create issues in target projects

### Amazon Q Developer
- Amazon Q Developer access
- Local configuration file access (`~/.aws/amazonq/mcp.json`)

## Deployment Instructions

### Step 1: Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd jira-mcp-server

# Set up Python environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2: Configure JIRA Credentials

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your JIRA details
# Required variables:
# JIRA_URL=https://yourcompany.atlassian.net
# JIRA_USERNAME=your-email@company.com
# JIRA_API_TOKEN=your-jira-api-token
```

### Step 3: Set Deployment Environment Variables

```bash
# Export JIRA variables for deployment
export JIRA_URL="https://yourcompany.atlassian.net"
export JIRA_USERNAME="your-email@company.com"
export JIRA_API_TOKEN="your-jira-api-token"

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
    "jira-mcp-server": {
      "command": "python3",
      "args": [
        "/path/to/your/jira-mcp-server/proxy_jira_mcp.py"
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
# Replace with your actual API Gateway URL
curl https://hw2kv2wfm5.execute-api.us-east-1.amazonaws.com/dev/health
```

Expected response:
```json
{
  "status": "healthy",
  "message": "Fixed JIRA MCP Server is running",
  "health_check": {
    "status": "success",
    "server_info": {
      "baseUrl": "https://yourcompany.atlassian.net",
      "version": "1001.0.0-SNAPSHOT"
    }
  }
}
```

### OAuth Server Test

Test OAuth client registration:

```bash
curl -X POST https://m97dth7m56.execute-api.us-east-1.amazonaws.com/dev/register \
  -H "Content-Type: application/json" \
  -d '{"redirect_uris": ["https://example.com/callback"], "client_name": "Test Client"}'
```

### MCP Server Test

Test MCP server with authentication:

```bash
# First get a fresh token
./get_fresh_token.sh

# Test tools list
curl -X POST https://hw2kv2wfm5.execute-api.us-east-1.amazonaws.com/dev/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### Amazon Q Integration Test

Once configured, test with natural language commands:

```
"List my JIRA projects"
"Create a task in PROJECT-KEY called 'Fix login bug'"
"Search for issues in PROJECT-KEY"
"Show me issue PROJECT-123"
"Check JIRA server health"
```

### Get Deployed URLs

After deployment, retrieve your API Gateway URLs:

```bash
# Get OAuth server URL
aws cloudformation describe-stacks --stack-name JiraMcpOAuthStack-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`OAuthApiEndpoint`].OutputValue' --output text

# Get MCP server URL
aws cloudformation describe-stacks --stack-name JiraMcpServerStack-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`McpApiEndpoint`].OutputValue' --output text
```

### Monitoring

Monitor Lambda function logs:

```bash
# View MCP server logs
aws logs tail /aws/lambda/jira-mcp-server-dev --follow

# View OAuth server logs
aws logs tail /aws/lambda/jira-mcp-oauth-server-dev --follow
```

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
rm -f proxy_jira_mcp.py.bak
rm -f .env
```

### Verify Cleanup

```bash
# Verify stacks are deleted
aws cloudformation list-stacks --stack-status-filter DELETE_COMPLETE

# Check for remaining resources
aws lambda list-functions --query 'Functions[?contains(FunctionName, `jira-mcp`)]'
aws apigateway get-rest-apis --query 'items[?contains(name, `jira-mcp`)]'
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

**Important**: This solution stores JIRA API tokens in Lambda environment variables. For production deployments, consider using AWS Secrets Manager or AWS Systems Manager Parameter Store for enhanced security.

See [CONTRIBUTING](CONTRIBUTING.md) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.

## Disclaimer

The solution architecture sample code is provided without any guarantees, and you're not recommended to use it for production-grade workloads. The intention is to provide content to build and learn. Be sure of reading the licensing terms.

---

**Estimated Monthly Cost**: $1-10 for typical usage (AWS Free Tier eligible)

**Support**: For issues and questions, please refer to the troubleshooting section or create an issue in the repository.
