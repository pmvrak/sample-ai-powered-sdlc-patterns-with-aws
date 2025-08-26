# Amazon Q Business Requirements Analysis MCP Server

## 1. Introduction

A Model Context Protocol (MCP) server that provides secure access to Amazon Q Business for requirements analysis and content creation. Features enterprise-grade authentication with Cognito JWT tokens and SigV4 signing.

### Features

- **RETRIEVE Tool**: Query Amazon Q Business for information retrieval
- **CREATE Tool**: Generate requirements, user stories, and documentation using Q Business CREATOR_MODE
- **Enterprise Authentication**: Cognito User Pool with JWT tokens + SigV4 signing
- **Secure Architecture**: Lambda-based MCP server with proper IAM permissions
- **Production Ready**: CDK infrastructure with Docker containerization

## 2. Solution Architecture (with steps explanation)

![Architecture Diagram](image/qmcp.jpg)

The system uses a hybrid authentication approach:
1. Cognito provides JWT tokens for user authentication
2. SigV4 signing secures API Gateway requests
3. Lambda exchanges JWT for IDC context to access Q Business

## 3. Prerequisites

- **Amazon Q Business Requirements Analysis Pattern**: Deploy the base pattern first from [AWS Samples Repository](https://github.com/aws-samples/sample-ai-powered-sdlc-patterns-with-aws/tree/main/requirement-and-planning/amazon-q-business-requirements-analysis)
- AWS CLI configured with appropriate permissions
- Docker installed
- Python 3.9+
- CDK CLI installed

## 4. Deployment instructions

### 1. Configure Environment

Use the discovery script to automatically find your AWS resources and generate configuration:

```bash
# Run the resource discovery script
./get_deployment_values.sh
```

This script will:
- Find your Identity Center instance
- List your Amazon Q Business applications  
- Show your Cognito User Pools and clients
- Generate a `deployment_config.env` file with the discovered values

Alternatively, manually create your configuration:
```bash
# Copy and edit configuration
cp deployment_config.env.example deployment_config.env
# Edit deployment_config.env with your AWS account details
```

### 2. Get Cognito User Pool Details

You need an existing Cognito User Pool with a user account. Get your pool details using:

```bash
# List your Cognito User Pools
aws cognito-idp list-user-pools --max-items 10

# Get specific pool details (replace with your pool ID)
aws cognito-idp describe-user-pool --user-pool-id us-east-1_XXXXXXXXX

# List app clients for your pool
aws cognito-idp list-user-pool-clients --user-pool-id us-east-1_XXXXXXXXX

# Get app client details (replace with your client ID)
aws cognito-idp describe-user-pool-client --user-pool-id us-east-1_XXXXXXXXX --client-id your-client-id
```

Update your `deployment_config.env` with these values:
- `EXISTING_COGNITO_USER_POOL_ID` - Your User Pool ID
- `EXISTING_COGNITO_CLIENT_ID` - Your App Client ID

### 3. Deploy Infrastructure

```bash
cd cdk
./deploy.sh
```

### 4. Enable CREATE Tool (CRITICAL STEP)

To enable the CREATE tool functionality, you MUST enable CREATOR_MODE in your Q Business application:

```bash
# Load your configuration
source deployment_config.env

# Enable CREATOR_MODE for CREATE tool functionality
aws qbusiness update-chat-controls-configuration \
  --application-id $Q_BUSINESS_APP_ID \
  --creator-mode-configuration creatorModeControl=ENABLED
```

**Important**: Without enabling CREATOR_MODE, the CREATE tool will fail with a validation error. This step is required for content generation capabilities.

### 5. Complete Deployment

Your MCP server is now deployed and ready to use.

## 5. Test

### Testing the System

```bash
# Test both RETRIEVE and CREATE tools
python3 test_mcp_integrated_auth.py your-username your-password
```

## Authentication Requirements

To use the MCP server, you need:

1. **Valid JWT token** from your Cognito User Pool (configured in `deployment_config.env`)
2. **AWS SigV4 signed request** to the API Gateway endpoint

### Required Headers
- `Authorization`: AWS SigV4 signature
- `X-Amz-Date`: Request timestamp  
- `X-Cognito-JWT`: Your Cognito JWT token
- `Content-Type`: application/json

### Complete Request Example
```bash
curl -X POST https://your-api-id.execute-api.us-east-1.amazonaws.com/ \
  -H "Authorization: AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20231201/us-east-1/execute-api/aws4_request, SignedHeaders=host;x-amz-date;x-cognito-jwt, Signature=example-signature" \
  -H "X-Amz-Date: 20231201T120000Z" \
  -H "X-Cognito-JWT: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "mcp_amazon_q_business_retrieve",
      "arguments": {
        "message": "Your query here"
      }
    },
    "id": 1
  }'
```

## MCP Tools

### RETRIEVE Tool
The RETRIEVE tool queries your Amazon Q Business knowledge base to find and analyze existing information. It can search through your indexed documents (Confluence, SharePoint, etc.), extract requirements from documentation, summarize content, and answer questions about your existing data sources.

**Tool Call:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "mcp_amazon_q_business_retrieve",
    "arguments": {
      "message": "What are the authentication requirements in our documentation?"
    }
  },
  "id": 1
}
```

### CREATE Tool  
The CREATE tool uses Amazon Q Business AI capabilities to generate new content based on your knowledge base. It can create user stories, technical specifications, acceptance criteria, test cases, project plans, and other documentation by leveraging both AI and your organization's existing knowledge.

**Tool Call:**
```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "mcp_amazon_q_business_create",
    "arguments": {
      "message": "Create a user story for user login with acceptance criteria"
    }
  },
  "id": 2
}
```

## Configuration Files

- `deployment_config.env` - Main configuration file
- `cdk/stack.py` - CDK infrastructure definition
- `mcp_server/` - MCP server implementation folder
  - `lambda_handler.py` - Lambda entry point and MCP protocol handler
  - `amazon_q_jsonrpc_server.py` - MCP server implementation
  - `atlassian_integration.py` - Q Business integration logic
  - `requirements.txt` - Python dependencies
  - `Dockerfile` - Container definition

## Key Components

### Lambda Function
- Handles MCP protocol requests
- Integrates JWT authentication with Q Business
- Supports both RETRIEVE and CREATE operations

### CDK Stack
- API Gateway with JWT authorizer
- Lambda function with proper IAM roles
- Docker image building and deployment

### Authentication Scripts
- `get_cognito_jwt.sh` - Initial token acquisition
- `refresh_cognito_token.sh` - Token refresh
- `test_mcp_integrated_auth.py` - End-to-end testing

## Troubleshooting

### CREATE Tool Not Working
If you get "CREATOR_MODE not enabled" error:
```bash
# Check current configuration
aws qbusiness get-chat-controls-configuration --application-id $Q_BUSINESS_APP_ID

# Enable CREATOR_MODE
aws qbusiness update-chat-controls-configuration \
  --application-id $Q_BUSINESS_APP_ID \
  --creator-mode-configuration creatorModeControl=ENABLED
```

### JWT Token Expired
Get a new JWT token from your Cognito User Pool using your preferred method (AWS CLI, SDK, or application).

### RETRIEVE Tool Access Denied / No Results
If the RETRIEVE tool returns access denied errors or no results when you expect content to be available, this is likely due to ACL (Access Control Lists) being enabled in the Confluence data source:

**Problem**: The Amazon Q Business Requirements Analysis pattern deploys with `isCrawlAcl: true` by default, which restricts content access based on Confluence permissions.

**Solution**: You need to redeploy the base pattern with ACL disabled:
- **File**: `amazon-q-confluence-stack.ts` 
- **Line**: ~315 (in additionalProperties section)
- **Change**: Set `isCrawlAcl: false`
```typescript
additionalProperties: {
  isCrawlAcl: false,  // ← Change this from true to false
  // ... other settings
}
```

**Important**: This requires redeploying the entire Amazon Q Business Requirements Analysis pattern as data source configurations cannot be modified after deployment.

### Lambda Deployment Issues
```bash
# Rebuild and redeploy
cd cdk
./deploy.sh
```

## Security Features

- JWT token validation in Lambda
- SigV4 request signing for API Gateway
- IAM roles with least privilege access
- Secure token storage and refresh mechanisms

## Development

### Local Testing
```bash
# Activate virtual environment
source mcp-test-env/bin/activate

# Run tests
python3 test_mcp_integrated_auth.py your-username your-password
```

### Updating Lambda Code
```bash
# After code changes, redeploy
cd cdk
cdk deploy
```

## Production Considerations

- Monitor Lambda function logs in CloudWatch
- Set up proper alerting for authentication failures
- Consider implementing token caching for performance
- Review IAM permissions regularly
- Enable AWS CloudTrail for audit logging

## 6. Clean Up

To remove all deployed resources:

```bash
# Delete the CDK stack
cd cdk
cdk destroy

# Clean up any remaining S3 objects if needed
aws s3 rm s3://your-bucket-name --recursive
```

## 7. Security

See CONTRIBUTING for more information.

## 8. License

This library is licensed under the MIT-0 License. See the LICENSE file.

## 9. Disclaimer

The solution architecture sample code is provided without any guarantees, and you're not recommended to use it for production-grade workloads. The intention is to provide content to build and learn. Be sure of reading the licensing terms.
