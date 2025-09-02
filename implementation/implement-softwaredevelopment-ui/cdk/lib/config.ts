export interface ICodeConfig {
  // General configuration
  appName: string;
  env: {
    account: string;
    region: string;
  };

  // Network configuration
  allowedIpAddress: string;

  // SSL/HTTPS configuration - Optional for development
  certificateArn?: string; // Optional for HTTP-only deployment
  domainName?: string;

  // ECS configuration
  containerPort: number;
  cpu: number;
  memory: number;
  desiredCount: number;

  // ECR configuration
  repositoryName: string;
  imageTag: string;

  // Cognito configuration
  userPoolName: string;
  clientName: string;
  identityPoolName: string;



  // MCP Server configuration
  mcpServerUrls: string[];

  // Bedrock access
  bedrockModelArns: string[];
  knowledgeBaseId?: string;
}

export const config: ICodeConfig = {
  appName: 'icode',
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT || '',
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
  },

  // Network configuration - users must set their own IP
  allowedIpAddress: process.env.ALLOWED_IP_ADDRESS || '', // No default - users must specify

  // SSL/HTTPS configuration - Optional for development
  certificateArn: process.env.CERTIFICATE_ARN || undefined,
  domainName: process.env.DOMAIN_NAME || undefined,

  containerPort: 8000,
  cpu: 1024,       
  memory: 2048,
  desiredCount: 1,

  repositoryName: process.env.ECR_REPOSITORY_NAME || 'icode-fullstack',
  imageTag: process.env.IMAGE_TAG || 'latest',

  userPoolName: 'icode-user-pool',
  clientName: 'icode-client',
  identityPoolName: 'icode-identity-pool',



  // MCP Server URLs - Parse comma-separated list
  mcpServerUrls: process.env.MCP_SERVER_URLS ? 
    process.env.MCP_SERVER_URLS.split(',').map(url => url.trim()).filter(url => url.length > 0) : 
    [],

  // Bedrock model ARNs - Fully configurable via environment variables
  bedrockModelArns: (() => {
    if (!process.env.CLAUDE_MODEL_ID) {
      throw new Error('CLAUDE_MODEL_ID environment variable is required');
    }
    
    const region = process.env.CDK_DEFAULT_REGION || 'us-east-1';
    const account = process.env.CDK_DEFAULT_ACCOUNT;
    const modelId = process.env.CLAUDE_MODEL_ID;
    
    console.log(`🔍 Configuring Bedrock ARN for model: ${modelId}`);
    console.log(`🔍 Account: ${account}, Region: ${region}`);
    
    // Check if it's an inference profile (starts with region prefix like 'us.')
    if (modelId.startsWith('us.') || modelId.startsWith('eu.') || modelId.startsWith('ap.')) {
      // It's an inference profile
      const arn = `arn:aws:bedrock:${region}:${account}:inference-profile/${modelId}`;
      console.log(`✅ Using inference profile ARN: ${arn}`);
      return [arn];
    } else {
      // It's a foundation model
      const arn = `arn:aws:bedrock:${region}::foundation-model/${modelId}`;
      console.log(`✅ Using foundation model ARN: ${arn}`);
      return [arn];
    }
  })(),

  // Knowledge Base ID (optional - users set this after creating their KB)
  knowledgeBaseId: process.env.BEDROCK_KNOWLEDGE_BASE_ID || ''
};