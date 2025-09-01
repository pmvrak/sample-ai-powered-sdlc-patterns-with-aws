# AI-Powered Software Development using AWS generative AI

## Introduction

A comprehensive AI-powered development platform with secure infrastructure, conversation management, and enterprise integrations built on AWS.

### Demo


https://github.com/user-attachments/assets/19b9121d-cabb-48e8-b386-8c32a4aa5df1



### Overview

This solution provides a complete full-stack application that combines:
- **Frontend**: React.js application with modern UI components
- **Backend**: FastAPI with MCP (Model Context Protocol) integration
- **Infrastructure**: AWS CDK with enterprise-grade security
- **AI Integration**: Claude models via AWS Bedrock
- **Authentication**: AWS Cognito with role-based access
- **Storage**: S3 with encryption and versioning

## Solution Architecture (with steps explanation)

![Platform Architecture](icode-architecture.png)

### Core Components
- **Frontend**: React.js application with modern UI
- **Backend**: FastAPI with streaming AI responses  
- **Infrastructure**: ECS Fargate with Application Load Balancer
- **AI Engine**: Claude 3.7 via AWS Bedrock for code generation
- **Storage**: S3 for projects, conversations, and generated code
- **Authentication**: Cognito with role-based access control

### Development Workflow
1. **Design** - Create architecture diagrams and specifications
2. **Build** - Generate code and APIs using AI assistance  
3. **Deploy** - Provision infrastructure with CloudFormation
4. **Monitor** - Track performance and optimize resources

The application deploys on AWS using:
- **ECS Fargate** for containerized application hosting
- **Application Load Balancer** with IP restrictions for secure access
- **VPC** with private subnets for network isolation
- **S3** for project storage with encryption
- **Cognito** for user authentication and authorization
- **Bedrock** for AI model access
- **CloudTrail** and **CloudWatch** for monitoring and compliance

## Prerequisites

### Required Tools
- AWS CLI configured with appropriate permissions
- Node.js (v18+) and npm
- Python (v3.9+) and pip
- AWS CDK (`npm install -g aws-cdk`)
- Docker for container builds

### AWS Configuration

**Configure your AWS credentials first:**

```bash
aws configure
```

### AWS Permissions
Your AWS account needs permissions for:
- CloudFormation, ECS, ECR, ALB
- S3, Cognito, Lambda
- Bedrock model access
- VPC and networking resources

### Bedrock Model Setup

**Important**: Enable Claude models in AWS Bedrock before deployment:

1. Go to **AWS Bedrock Console** → **Model access**
2. Request access for Claude models:
   - Claude 3.7 Sonnet: `anthropic.claude-3-7-sonnet-20250219-v1:0`
   - Claude 3.5 Sonnet: `anthropic.claude-3-5-sonnet-20241022-v2:0`
   - Claude 3 Haiku: `anthropic.claude-3-haiku-20240307-v1:0`
3. Wait for approval (usually instant)

**Find available models:**
```bash
# List foundation models
aws bedrock list-foundation-models --region us-east-1 --query 'modelSummaries[?contains(modelId, `claude`)].modelId'

# List inference profiles (recommended for better availability)
aws bedrock list-inference-profiles --region us-east-1 --query 'inferenceProfileSummaries[?contains(inferenceProfileId, `claude`)].inferenceProfileId'
```

## Deployment instructions

### SSL Certificate Setup (REQUIRED)

**Complete this step BEFORE running the Quick Start deployment.**

HTTPS is mandatory for security compliance. Choose one of the following options:

#### **Option 1: Production Certificate (Recommended)**

**For production use with a real domain:**

1. **Get a domain** from any registrar (Route 53, GoDaddy, Namecheap, Cloudflare, etc.)

2. **Request SSL certificate in AWS Certificate Manager:**
   - Go to AWS Console → Certificate Manager → Request Certificate
   - Enter your domain name (e.g., `myapp.example.com`)
   - Choose DNS validation
   - Add the provided CNAME record to your domain's DNS settings
   - Wait for validation (usually a few minutes)

3. **Import existing certificate** (if you already have one):
   ```bash
   aws acm import-certificate \
     --certificate fileb://certificate.crt \
     --private-key fileb://private.key \
     --certificate-chain fileb://chain.crt \
     --region us-east-1
   ```

4. **Get certificate ARN:**
   ```bash
   aws acm list-certificates --region us-east-1
   # Copy the ARN to your .env file
   ```

#### **Option 2: Self-Signed Certificate (Development Only)**

**For testing and development:**

```bash
# Generate self-signed certificate
openssl req -x509 -newkey rsa:2048 -keyout private.key -out certificate.crt -days 365 -nodes \
  -subj "/C=US/ST=State/L=City/O=Company/CN=localhost"

# Import to ACM
aws acm import-certificate \
  --certificate fileb://certificate.crt \
  --private-key fileb://private.key \
  --region us-east-1

# Get the certificate ARN
aws acm list-certificates --region us-east-1
# Copy the ARN to your .env file
```

**Note**: Self-signed certificates will show security warnings in browsers but work for development.

### Quick Start

**Prerequisites**: Complete SSL Certificate Setup above first.

```bash
# Clone and navigate to repository
git clone <repository-url>
cd implement-softwaredevelopment-ui

# Set up environment variables
cd cdk
cp .env.example .env
```
Edit the `.env` file and replace the required variables with your corresponding values:

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `CDK_DEFAULT_ACCOUNT` | ✅ | AWS Account ID | `123456789012` |
| `CDK_DEFAULT_REGION` | ✅ | AWS Region | `us-east-1` |
| `ALLOWED_IP_ADDRESS` | ✅ | Your IP for ALB access | `1.2.3.4/32` |
| `CERTIFICATE_ARN` | ✅ | ACM certificate ARN for HTTPS | `arn:aws:acm:region:account:certificate/cert-id` |
| `CLAUDE_MODEL_ID` | ✅ | Claude model identifier | `us.anthropic.claude-3-7-sonnet-20250219-v1:0` |
| `DOMAIN_NAME` | ❌ | Custom domain name | `myapp.example.com` |
| `MCP_SERVER_URLS` | ❌ | MCP server endpoints | `https://abc.lambda-url.us-east-1.on.aws/` |
| `BEDROCK_KNOWLEDGE_BASE_ID` | ❌ | Knowledge Base ID | `ABCD1234EF` |

```bash
# Deploy the stack
cd ..
./deploy.sh
```

The deployment script will:
1. Create ECR repository
2. Build and push Docker image
3. Deploy CDK infrastructure
4. Configure IAM permissions
5. Provide access URLs and credentials

### Next Steps: Enhance with Knowledge Base and MCP Capabilities

#### Knowledge Base Setup

For enhanced AI capabilities with document retrieval:

1. **Get your S3 bucket name:**
```bash
aws cloudformation describe-stacks --stack-name ICodeStack --query 'Stacks[0].Outputs[?OutputKey==`S3BucketName`].OutputValue' --output text
```

2. **Create Knowledge Base in AWS Bedrock Console:**
   - Go to **AWS Bedrock Console** → **Knowledge bases** → **Create knowledge base**
   - **Data source**: Choose S3, use your bucket name from step 1
   - **S3 prefix**: Set to `projects/` to use project documents
   - **Embeddings model**: Choose Titan Text Embeddings v2 or Cohere Embed
   - **Vector database**: Choose Amazon S3 (native vector support at scale)
   - **Note the Knowledge Base ID and Data Source ID** after creation

3. **Configure your application:**
```bash
./configure-kb.sh <KNOWLEDGE_BASE_ID> <DATA_SOURCE_ID>
```

#### MCP Server Integration

To add MCP (Model Context Protocol) servers for enhanced capabilities:

1. **Deploy MCP servers** using AWS samples:
   - [OpenAPI Documentation MCP](https://github.com/aws-samples/sample-ai-powered-sdlc-patterns-with-aws/tree/main/design-and-architecture/design-openapidocumentation-mcp)
   - [Architecture Design MCP](https://github.com/aws-samples/sample-ai-powered-sdlc-patterns-with-aws/tree/main/design-and-architecture/Architecture-designer)
   - [Other AI-Powered SDLC Patterns](https://github.com/aws-samples/sample-ai-powered-sdlc-patterns-with-aws)

2. **Configure mcp_servers.json** with your actual endpoints:

   After deploying the MCP servers above, update the `mcp_servers.json` file with your actual MCP server endpoints:

   ```bash
   # Edit mcp_servers.json and replace sample URLs with your actual endpoints:
   # - Replace "https://your-lambda-url.lambda-url.us-east-1.on.aws/" 
   # - Replace "https://your-domain-analysis-server.amazonaws.com/mcp"
   # - Replace "https://your-api-gateway.execute-api.us-east-1.amazonaws.com"
   ```

   Example configuration:
   ```json
   {
     "environments": {
       "production": {
         "servers": [
           {
             "server_id": "aws-architecture-design",
             "endpoint_url": "https://abc123.lambda-url.us-east-1.on.aws/",
             "capabilities": ["query_aws_knowledge", "generate_architecture_code"],
             "server_type": "architecture",
             "auth": {
               "type": "aws_sigv4",
               "region": "us-east-1",
               "service": "lambda"
             }
           }
         ]
       }
     }
   }
   ```

3. **Add to .env file** (optional, for additional servers):
   ```bash
   # Add this line to your cdk/.env file:
   MCP_SERVER_URLS=https://your-additional-mcp-server.lambda-url.us-east-1.on.aws/
   ```

   **Important**: Update the placeholder URLs in `mcp_servers.json` with your actual MCP server endpoints before deployment. The sample URLs are provided as templates and will not work without your actual AWS resources.



### 🚀 Getting Started - User Guide

After successful deployment, follow these steps to start using the AI-powered development platform:

#### Step 1: Sign Up and Login

1. **Navigate to your deployed application** using the ALB DNS URL from deployment output
2. **Click "Sign Up"** to create a new account
3. **Login** with your credentials

#### Step 2: Navigate to Projects

1. **Click "Projects"** in the top navigation bar
2. **Create a new project** or select an existing one
3. **Start your AI-powered development workflow**

#### Step 3: Try These Example Prompts

Copy and paste these prompts to experience the platform's capabilities:

##### 📋 Requirements Phase (30 seconds)
```
Extract information available from my confluence page and create epics with story points
```

```
Create acceptance criteria for each Book Catalog Management Epic using Given/When/Then format. Include all success and error scenarios.
```

##### 🎨 Design Phase (1-5 minutes)
```
generate design diagram for the Book Catalog Management Epic
```

```
generate open api spec code file for Book Catalog Management Epic
```

```
generate infrastructure code for Book Catalog Management Epic
```

```
do domain analysis of Book Catalog Management Epic
```

```
give architecture analysis of Book Catalog Management Epic
```

```
generate documentation for Book Catalog Management System using domain analysis tool
```

#### Expected Response Times
- **Requirements extraction**: ~30 seconds
- **Acceptance criteria generation**: ~30 seconds  
- **Design diagrams**: ~1 minute
- **Code generation**: 3-5 minutes
- **Domain analysis**: ~30 seconds
- **Architecture analysis**: ~30 seconds
- **Documentation generation**: ~1 minute


#### Troubleshooting
- If prompts don't work initially, ensure your MCP servers are properly configured
- Check that your Confluence integration is set up if using Confluence-related prompts
- Verify your AWS Bedrock model access is enabled
- Review CloudWatch logs for any errors

### Post-Deployment Setup

### Security Features

- **Network isolation** with VPC and private subnets
- **IP-restricted** Application Load Balancer
- **Encryption** at rest (S3) and in transit (HTTPS)
- **Audit logging** via CloudTrail
- **Role-based access** via Cognito
- **Security groups** with least privilege

See CONTRIBUTING for more information.

## Test

- **Application health**: `https://your-alb-dns/health`
- **Logs**: CloudWatch `/ecs/icode-fullstack`
- **Audit trail**: CloudWatch `/aws/cloudtrail/icode-audit`
- **VPC flow logs**: CloudWatch `/aws/vpc/flowlogs`

## Cleanup

```bash
# Remove all resources
./cleanup.sh

# Or manually
cd cdk
npx cdk destroy --force
aws ecr delete-repository --repository-name icode-fullstack --force
```

### Local Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py

# Frontend
cd frontend/icode-website
npm install
npm start
```


## 🔐 Security

See CONTRIBUTING for more information

## 📄 License

This library is licensed under the MIT-0 License. See the LICENSE file.

## Disclaimer

The solution architecture sample code is provided without any guarantees, and you're not recommended to use it for production-grade workloads. The intention is to provide content to build and learn. Be sure of reading the licensing terms."

---

Built with ❤️ using the AWS, MCP, Amazon Bedrock, and AI-powered SDLC.
