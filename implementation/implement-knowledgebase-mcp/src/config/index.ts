import { ServerConfig, CognitoConfig, OpenSearchConfig, BedrockKBConfig, MCPServerConfig } from '../types.js';

/**
 * Configuration validation error class
 */
export class ConfigurationError extends Error {
  constructor(message: string, public readonly errors: string[]) {
    super(message);
    this.name = 'ConfigurationError';
  }
}

/**
 * Configuration defaults for optional parameters
 */
const CONFIG_DEFAULTS = {
  AWS_REGION: 'us-east-1',
  OPENSEARCH_INDEX_PREFIX: 'project-',
  MCP_SERVER_NAME: 'project-kb-mcp-server',
  MCP_SERVER_VERSION: '1.0.0'
} as const;

/**
 * Required environment variables (base requirements)
 */
const REQUIRED_BASE_ENV_VARS = [
  'COGNITO_USER_POOL_ID',
  'COGNITO_CLIENT_ID'
] as const;

/**
 * Optional environment variables with fallback handling
 */
const OPTIONAL_ENV_VARS = [
  'AWS_REGION',
  'OPENSEARCH_INDEX_PREFIX',
  'COGNITO_USERNAME',
  'COGNITO_PASSWORD'
] as const;

/**
 * Load configuration from environment variables with validation and fallbacks
 */
export function loadConfig(): ServerConfig {
  // Validate base required environment variables first
  const missingRequired = REQUIRED_BASE_ENV_VARS.filter(varName => !process.env[varName]);
  if (missingRequired.length > 0) {
    throw new ConfigurationError(
      'Missing required environment variables',
      missingRequired.map(varName => `${varName} environment variable is required`)
    );
  }

  // Determine the default backend
  const defaultBackend = (process.env.DEFAULT_BACKEND as 'opensearch' | 'bedrock') || 'opensearch';

  const cognito: CognitoConfig = {
    userPoolId: process.env.COGNITO_USER_POOL_ID!,
    clientId: process.env.COGNITO_CLIENT_ID!,
    region: process.env.AWS_REGION || CONFIG_DEFAULTS.AWS_REGION,
    identityPoolId: process.env.COGNITO_IDENTITY_POOL_ID,
    username: process.env.COGNITO_USERNAME,
    password: process.env.COGNITO_PASSWORD
  };

  const server: MCPServerConfig = {
    name: process.env.MCP_SERVER_NAME || CONFIG_DEFAULTS.MCP_SERVER_NAME,
    version: process.env.MCP_SERVER_VERSION || CONFIG_DEFAULTS.MCP_SERVER_VERSION
  };

  // Build configuration based on backend type
  const config: ServerConfig = {
    cognito,
    server,
    defaultBackend
  };

  // Add OpenSearch configuration if available
  if (process.env.OPENSEARCH_ENDPOINT && process.env.OPENSEARCH_COLLECTION_NAME) {
    config.openSearch = {
      endpoint: process.env.OPENSEARCH_ENDPOINT,
      region: process.env.AWS_REGION || CONFIG_DEFAULTS.AWS_REGION,
      collectionName: process.env.OPENSEARCH_COLLECTION_NAME,
      indexPrefix: process.env.OPENSEARCH_INDEX_PREFIX || CONFIG_DEFAULTS.OPENSEARCH_INDEX_PREFIX
    };
  }

  // Add Bedrock configuration if available
  if (process.env.BEDROCK_KNOWLEDGE_BASE_ID) {
    config.bedrock = {
      knowledgeBaseId: process.env.BEDROCK_KNOWLEDGE_BASE_ID,
      region: process.env.AWS_REGION || CONFIG_DEFAULTS.AWS_REGION
    };
  }

  // Validate the loaded configuration
  validateConfig(config);

  return config;
}

/**
 * Validate configuration parameters
 */
export function validateConfig(config: ServerConfig): void {
  const errors: string[] = [];

  // Validate Cognito configuration
  if (!config.cognito.userPoolId?.trim()) {
    errors.push('Cognito User Pool ID cannot be empty');
  }
  if (!config.cognito.clientId?.trim()) {
    errors.push('Cognito Client ID cannot be empty');
  }
  if (!config.cognito.region?.trim()) {
    errors.push('AWS region cannot be empty');
  }
  if (config.cognito.region && !isValidAwsRegion(config.cognito.region)) {
    errors.push(`Invalid AWS region: ${config.cognito.region}`);
  }

  // Validate backend configuration based on default backend
  if (config.defaultBackend === 'opensearch') {
    if (!config.openSearch) {
      errors.push('OpenSearch configuration is required when defaultBackend is opensearch');
    } else {
      if (!config.openSearch.endpoint?.trim()) {
        errors.push('OpenSearch endpoint cannot be empty');
      }
      if (config.openSearch.endpoint && !isValidUrl(config.openSearch.endpoint)) {
        errors.push(`Invalid OpenSearch endpoint URL: ${config.openSearch.endpoint}`);
      }
      if (!config.openSearch.collectionName?.trim()) {
        errors.push('OpenSearch collection name cannot be empty');
      }
      if (!config.openSearch.region?.trim()) {
        errors.push('OpenSearch region cannot be empty');
      }
      if (config.openSearch.region && !isValidAwsRegion(config.openSearch.region)) {
        errors.push(`Invalid OpenSearch region: ${config.openSearch.region}`);
      }
      if (!config.openSearch.indexPrefix?.trim()) {
        errors.push('OpenSearch index prefix cannot be empty');
      }
    }
  } else if (config.defaultBackend === 'bedrock') {
    if (!config.bedrock) {
      errors.push('Bedrock configuration is required when defaultBackend is bedrock');
    } else {
      if (!config.bedrock.knowledgeBaseId?.trim()) {
        errors.push('Bedrock Knowledge Base ID cannot be empty');
      }
      if (!config.bedrock.region?.trim()) {
        errors.push('Bedrock region cannot be empty');
      }
      if (config.bedrock.region && !isValidAwsRegion(config.bedrock.region)) {
        errors.push(`Invalid Bedrock region: ${config.bedrock.region}`);
      }
    }
  } else {
    errors.push('Invalid defaultBackend. Must be "opensearch" or "bedrock"');
  }

  // Validate server configuration
  if (!config.server.name?.trim()) {
    errors.push('Server name cannot be empty');
  }
  if (!config.server.version?.trim()) {
    errors.push('Server version cannot be empty');
  }
  if (config.server.version && !isValidVersion(config.server.version)) {
    errors.push(`Invalid server version format: ${config.server.version}`);
  }

  if (errors.length > 0) {
    throw new ConfigurationError(
      `Configuration validation failed`,
      errors
    );
  }
}

/**
 * Check if credentials are available in environment variables
 */
export function hasCredentialsInEnv(): boolean {
  return !!(process.env.COGNITO_USERNAME && process.env.COGNITO_PASSWORD);
}

/**
 * Get configuration summary for logging (without sensitive data)
 */
export function getConfigSummary(config: ServerConfig): Record<string, any> {
  return {
    cognito: {
      userPoolId: config.cognito.userPoolId,
      clientId: config.cognito.clientId,
      region: config.cognito.region,
      hasCredentials: !!(config.cognito.username && config.cognito.password)
    },
    openSearch: config.openSearch ? {
      endpoint: config.openSearch.endpoint,
      region: config.openSearch.region,
      collectionName: config.openSearch.collectionName,
      indexPrefix: config.openSearch.indexPrefix
    } : null,
    bedrock: config.bedrock ? {
      knowledgeBaseId: config.bedrock.knowledgeBaseId,
      region: config.bedrock.region
    } : null,
    defaultBackend: config.defaultBackend,
    server: {
      name: config.server.name,
      version: config.server.version
    }
  };
}

/**
 * Validate AWS region format
 */
function isValidAwsRegion(region: string): boolean {
  // AWS region format: us-east-1, eu-west-1, ap-southeast-2, etc.
  const regionPattern = /^[a-z]{2}-[a-z]+-\d+$/;
  return regionPattern.test(region);
}

/**
 * Validate URL format
 */
function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Validate semantic version format
 */
function isValidVersion(version: string): boolean {
  // Semantic version format: 1.0.0, 2.1.3-beta, etc.
  const versionPattern = /^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$/;
  return versionPattern.test(version);
}