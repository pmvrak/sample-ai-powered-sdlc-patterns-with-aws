# OpenAPI MCP Server

A lightweight MCP (Model Context Protocol) server that wraps existing OpenAPI documentation Lambda functions.

## 📚 Related Documentation

- **[Main Project README](../README.md)** - Project overview and architecture
- **[CDK Infrastructure README](../cdk/README.md)** - AWS deployment and configuration
- **[Authentication README](../shared/README.md)** - JWT middleware for Lambda functions
- **[Deployment Guide](../DEPLOYMENT_GUIDE.md)** - Step-by-step deployment instructions

## Features

- MCP protocol compliance using TypeScript SDK
- Wraps existing AWS Lambda functions for domain analysis and documentation generation
- Lightweight containerized deployment on RunPod
- AWS IAM authentication support
- Comprehensive logging and monitoring

## Development

### Prerequisites

- Node.js 18+
- Docker
- AWS CLI configured

### Setup

1. Install dependencies:
```bash
npm install
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Build the project:
```bash
npm run build
```

4. Run in development mode:
```bash
npm run dev
```

### Testing

```bash
npm test
```

### Docker

Build the container:
```bash
docker build -t openapi-mcp-server .
```

Run the container locally:
```bash
docker run -p 3000:3000 -p 3001:3001 openapi-mcp-server
```

### RunPod Deployment

#### Automated Deployment

1. Set your container registry URL:
```bash
export REGISTRY_URL=your-registry.com
export TAG=latest
```

2. Run the deployment script:
```bash
./deploy-runpod.sh
```

#### Manual Deployment

1. Build and push to a container registry:
```bash
docker build -t your-registry/openapi-mcp-server:latest .
docker push your-registry/openapi-mcp-server:latest
```

2. Create a RunPod template:
   - Use the generated `runpod-template.json` file
   - Set the container image URL
   - Configure environment variables (see `.env.runpod` for reference)

3. Deploy on RunPod:
   - Create a new pod using your template
   - Expose ports 3000 (HTTP/health) and 3001 (MCP protocol)
   - Set AWS credentials as environment variables
   - Configure Lambda function ARNs
   - Optional: Mount volume for persistent logs at `/app/logs`

#### Environment Variables for RunPod

Required AWS credentials:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_REGION`

Required Lambda function ARNs:
- `DOMAIN_ANALYZER_LAMBDA_ARN`
- `DOC_GENERATOR_LAMBDA_ARN`

Optional configuration:
- `BUCKET_NAME` - S3 bucket for document storage
- `COGNITO_USER_POOL_ID` - For authentication
- `COGNITO_CLIENT_ID` - For authentication
- `LOG_LEVEL` - Logging verbosity (default: info)
- `ENABLE_METRICS` - Enable metrics endpoint (default: true)

#### Health Checks

- Health endpoint: `http://your-pod-url:3000/health`
- Readiness endpoint: `http://your-pod-url:3000/ready`
- Metrics endpoint: `http://your-pod-url:3000/metrics` (if enabled)

## Configuration

The server is configured via environment variables:

- `NODE_ENV`: Environment (development/production/test)
- `PORT`: HTTP server port (default: 3000)
- `MCP_PORT`: MCP protocol port (default: 3001)
- `AWS_REGION`: AWS region
- `BEDROCK_REGION`: Bedrock service region
- `MODEL_ID`: Bedrock model ID
- `LOG_LEVEL`: Logging level (error/warn/info/debug)

> **AWS Deployment**: For complete environment variable configuration when deploying to AWS, see the [CDK Infrastructure README](../cdk/README.md) which includes all available configuration options and deployment-specific settings.

## MCP Tools

The server exposes the following MCP tools:

1. `analyze_domain_model` - Analyze domain models and generate business insights
2. `generate_openapi_spec` - Generate OpenAPI 3.1 specifications
3. `generate_api_documentation` - Generate comprehensive API documentation

## Architecture

The server acts as a lightweight wrapper around existing AWS Lambda functions, providing MCP protocol interfaces while maintaining the current backend architecture.