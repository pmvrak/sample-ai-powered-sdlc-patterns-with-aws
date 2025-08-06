# OpenAPI Documentation MCP Server - CDK Deployment

This directory contains the AWS CDK infrastructure code for deploying the OpenAPI Documentation MCP Server.

## Environment Variables Configuration

The CDK stacks now support configuration through environment variables instead of hardcoded values. This makes the deployment more flexible and secure.

### Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file with your specific values:
   ```bash
   nano .env
   ```

### Available Environment Variables

#### AWS Configuration
- `CDK_DEFAULT_ACCOUNT`: Your AWS account ID
- `CDK_DEFAULT_REGION`: AWS region for deployment (default: us-east-1)

#### OpenSearch Configuration
- `OPENSEARCH_COLLECTION_NAME`: Name for the OpenSearch collection (default: openapi-kb)
- `OPENSEARCH_INDEX_NAME`: Name for the vector index (default: openapi-index)

#### IAM Configuration
- `CDK_IAM_USER_ARN`: IAM user ARN for OpenSearch access (optional, defaults to account root)

#### Bedrock Configuration
- `BEDROCK_REGION`: Region for Bedrock services (default: eu-west-1)
- `BEDROCK_FOUNDATION_MODEL`: Foundation model ID (default: eu.anthropic.claude-3-7-sonnet-20250219-v1:0)
- `BEDROCK_EMBEDDING_MODEL_ARN`: Embedding model ARN for knowledge base
- `BEDROCK_AGENT_ALIAS_ID`: Agent alias ID (default: TSTALIASID)

#### MCP Server Configuration
- `NODE_ENV`: Node.js environment (default: production)
- `PORT`: Health check port (default: 3000)
- `MCP_PORT`: MCP server port (default: 3001)
- `MODEL_ID`: Model ID for the MCP server
- `MCP_SERVER_NAME`: Name of the MCP server (default: openapi-documentation-mcp-prod)
- `MCP_SERVER_VERSION`: Version of the MCP server (default: 1.0.0)
- `LOG_LEVEL`: Logging level (default: info)
- `HEALTH_CHECK_ENABLED`: Enable health checks (default: true)
- `ENABLE_REQUEST_LOGGING`: Enable request logging (default: true)

### Deployment

The deployment script will automatically load environment variables from the `.env` file:

```bash
# Deploy all stacks
./deploy-all.sh

# Deploy with additional context parameters
./deploy-all.sh --domain-name your-domain.com --allowed-ips "1.2.3.4/32"
```

### CDK Context Parameters

Some parameters are still passed via CDK context (command line):
- `certificateArn`: ACM certificate ARN for HTTPS
- `domainName`: Domain name for certificate creation
- `allowedIps`: Comma-separated list of allowed IP addresses/CIDR blocks

Example:
```bash
cdk deploy McpServerStack \
  --context certificateArn=arn:aws:acm:us-east-1:123456789012:certificate/your-cert-id \
  --context domainName=your-domain.com \
  --context allowedIps="1.2.3.4/32,5.6.7.8/32"
```

### Security Best Practices

1. **Never commit the `.env` file** - it's already in `.gitignore`
2. **Use specific IAM user ARNs** instead of account root when possible
3. **Restrict allowed IPs** to only necessary addresses
4. **Use HTTPS** in production with proper certificates
5. **Regularly rotate credentials** and update environment variables

### Troubleshooting

If you encounter issues:

1. **Check environment variables**: Ensure all required variables are set in `.env`
2. **Verify AWS credentials**: Run `aws sts get-caller-identity`
3. **Check CDK bootstrap**: Run `cdk bootstrap` if needed
4. **Review stack outputs**: Check CloudFormation outputs for resource ARNs
5. **Check logs**: Review CloudWatch logs for ECS tasks and Lambda functions

### Manual Deployment

If you prefer to deploy individual stacks:

```bash
# Set environment variables
export $(grep -v '^#' .env | xargs)

# Deploy stacks in order
cdk deploy OpenSearchStack
cdk deploy StorageStack
cdk deploy BedrockStack
cdk deploy LambdaStack
cdk deploy McpServerStack --context allowedIps="YOUR_IP/32"
```