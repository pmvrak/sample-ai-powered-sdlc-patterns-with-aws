import { z } from 'zod';

// AWS ARN validation regex
const arnRegex = /^arn:aws:lambda:[a-z0-9-]+:\d{12}:function:[a-zA-Z0-9-_]+$/;

const environmentSchema = z.object({
  // Server configuration
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  PORT: z.string().transform(Number).default('3000'),
  MCP_PORT: z.string().transform(Number).default('3001'),
  
  // AWS configuration
  AWS_REGION: z.string().min(1, 'AWS_REGION is required'),
  BEDROCK_REGION: z.string().default('us-east-1'),
  MODEL_ID: z.string().default('anthropic.claude-3-5-sonnet-20241022-v2:0'),
  // BUCKET_NAME removed - Lambda functions now return responses directly
  
  // Lambda function ARNs - required for production
  DOMAIN_ANALYZER_LAMBDA_ARN: z.string()
    .regex(arnRegex, 'Invalid Lambda ARN format for DOMAIN_ANALYZER_LAMBDA_ARN')
    .optional()
    .refine((val) => process.env['NODE_ENV'] !== 'production' || val, {
      message: 'DOMAIN_ANALYZER_LAMBDA_ARN is required in production'
    }),
  DOC_GENERATOR_LAMBDA_ARN: z.string()
    .regex(arnRegex, 'Invalid Lambda ARN format for DOC_GENERATOR_LAMBDA_ARN')
    .optional()
    .refine((val) => process.env['NODE_ENV'] !== 'production' || val, {
      message: 'DOC_GENERATOR_LAMBDA_ARN is required in production'
    }),
  
  // Authentication
  COGNITO_USER_POOL_ID: z.string().optional(),
  COGNITO_CLIENT_ID: z.string().optional(),
  
  // MCP Server configuration
  MCP_SERVER_NAME: z.string().default('openapi-documentation-mcp'),
  MCP_SERVER_VERSION: z.string().default('1.0.0'),
  MCP_MAX_CONNECTIONS: z.string().transform(Number).default('100'),
  MCP_CONNECTION_TIMEOUT: z.string().transform(Number).default('30000'), // 30 seconds
  
  // Health check configuration
  HEALTH_CHECK_ENABLED: z.string().transform(Boolean).default('true'),
  HEALTH_CHECK_INTERVAL: z.string().transform(Number).default('30000'), // 30 seconds
  
  // Logging and monitoring
  LOG_LEVEL: z.enum(['error', 'warn', 'info', 'debug']).default('info'),
  ENABLE_METRICS: z.string().transform(Boolean).default('false'),
  ENABLE_REQUEST_LOGGING: z.string().transform(Boolean).default('true'),
  
  // Performance tuning
  LAMBDA_TIMEOUT: z.string().transform(Number).default('300000'), // 5 minutes
  LAMBDA_RETRY_ATTEMPTS: z.string().transform(Number).default('3'),
  LAMBDA_RETRY_DELAY: z.string().transform(Number).default('1000'), // 1 second
});

export type EnvironmentConfig = z.infer<typeof environmentSchema>;

/**
 * Validates and loads environment configuration
 * @returns Validated environment configuration
 * @throws Error if configuration is invalid
 */
function loadConfig(): EnvironmentConfig {
  try {
    const config = environmentSchema.parse(process.env);
    
    // Additional validation for production environment
    if (config.NODE_ENV === 'production') {
      validateProductionConfig(config);
    }
    
    return config;
  } catch (error) {
    if (error instanceof z.ZodError) {
      const errorMessages = error.errors.map(err => 
        `${err.path.join('.')}: ${err.message}`
      ).join('\n');
      console.error('Environment configuration validation failed:\n', errorMessages);
    } else {
      console.error('Failed to load environment configuration:', error);
    }
    throw new Error('Invalid environment configuration');
  }
}

/**
 * Additional validation for production environment
 * @param config - Environment configuration
 */
function validateProductionConfig(config: EnvironmentConfig): void {
  const requiredForProduction: (keyof EnvironmentConfig)[] = [
    'AWS_REGION',
    'DOMAIN_ANALYZER_LAMBDA_ARN',
    'DOC_GENERATOR_LAMBDA_ARN'
  ];
  
  const missing = requiredForProduction.filter(key => 
    !config[key] || (typeof config[key] === 'string' && (config[key] as string).trim() === '')
  );
  
  if (missing.length > 0) {
    throw new Error(
      `Missing required environment variables for production: ${missing.join(', ')}`
    );
  }
}

/**
 * Get configuration value with type safety
 * @param key - Configuration key
 * @returns Configuration value
 */
export function getConfigValue<K extends keyof EnvironmentConfig>(
  key: K
): EnvironmentConfig[K] {
  return config[key];
}

/**
 * Check if running in development mode
 */
export function isDevelopment(): boolean {
  return config.NODE_ENV === 'development';
}

/**
 * Check if running in production mode
 */
export function isProduction(): boolean {
  return config.NODE_ENV === 'production';
}

/**
 * Check if running in test mode
 */
export function isTest(): boolean {
  return config.NODE_ENV === 'test';
}

// Load and export configuration
export const config = loadConfig();

// Export individual configuration sections for convenience
export const serverConfig = {
  nodeEnv: config.NODE_ENV,
  port: config.PORT,
  mcpPort: config.MCP_PORT,
  healthCheckEnabled: config.HEALTH_CHECK_ENABLED,
  healthCheckInterval: config.HEALTH_CHECK_INTERVAL,
} as const;

export const awsConfig = {
  region: config.AWS_REGION,
  bedrockRegion: config.BEDROCK_REGION,
  modelId: config.MODEL_ID,
  // bucketName removed - Lambda functions now return responses directly
} as const;

export const lambdaConfig = {
  domainAnalyzerArn: config.DOMAIN_ANALYZER_LAMBDA_ARN,
  docGeneratorArn: config.DOC_GENERATOR_LAMBDA_ARN,
  timeout: config.LAMBDA_TIMEOUT,
  retryAttempts: config.LAMBDA_RETRY_ATTEMPTS,
  retryDelay: config.LAMBDA_RETRY_DELAY,
} as const;

export const mcpConfig = {
  serverName: config.MCP_SERVER_NAME,
  serverVersion: config.MCP_SERVER_VERSION,
  maxConnections: config.MCP_MAX_CONNECTIONS,
  connectionTimeout: config.MCP_CONNECTION_TIMEOUT,
} as const;

export const authConfig = {
  cognitoUserPoolId: config.COGNITO_USER_POOL_ID,
  cognitoClientId: config.COGNITO_CLIENT_ID,
} as const;

export const loggingConfig = {
  logLevel: config.LOG_LEVEL,
  enableMetrics: config.ENABLE_METRICS,
  enableRequestLogging: config.ENABLE_REQUEST_LOGGING,
} as const;