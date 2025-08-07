import { config, isProduction, isDevelopment } from './environment.js';

/**
 * Validates that all required configuration is present and valid
 * @throws Error if configuration is invalid
 */
export function validateConfiguration(): void {
  console.log('Validating configuration...');
  
  // Validate AWS configuration
  validateAwsConfiguration();
  
  // Validate Lambda configuration
  validateLambdaConfiguration();
  
  // Validate MCP server configuration
  validateMcpConfiguration();
  
  // Validate authentication configuration
  validateAuthConfiguration();
  
  console.log('Configuration validation completed successfully');
}

/**
 * Validates AWS-specific configuration
 */
function validateAwsConfiguration(): void {
  if (!config.AWS_REGION) {
    throw new Error('AWS_REGION is required');
  }
  
  // BUCKET_NAME validation removed - Lambda functions now return responses directly
  
  // Validate AWS region format
  const regionRegex = /^[a-z]{2}-[a-z]+-\d{1}$/;
  if (!regionRegex.test(config.AWS_REGION)) {
    throw new Error(`Invalid AWS_REGION format: ${config.AWS_REGION}`);
  }
  
  if (!regionRegex.test(config.BEDROCK_REGION)) {
    throw new Error(`Invalid BEDROCK_REGION format: ${config.BEDROCK_REGION}`);
  }
  
  console.log(`✓ AWS configuration valid (Region: ${config.AWS_REGION})`);
}

/**
 * Validates Lambda function configuration
 */
function validateLambdaConfiguration(): void {
  if (isProduction()) {
    if (!config.DOMAIN_ANALYZER_LAMBDA_ARN) {
      throw new Error('DOMAIN_ANALYZER_LAMBDA_ARN is required in production');
    }
    
    if (!config.DOC_GENERATOR_LAMBDA_ARN) {
      throw new Error('DOC_GENERATOR_LAMBDA_ARN is required in production');
    }
    
    console.log('✓ Lambda ARNs configured for production');
  } else {
    console.log('✓ Lambda configuration valid for development');
  }
  
  // Validate timeout values
  if (config.LAMBDA_TIMEOUT < 1000 || config.LAMBDA_TIMEOUT > 900000) {
    throw new Error('LAMBDA_TIMEOUT must be between 1000ms and 900000ms (15 minutes)');
  }
  
  if (config.LAMBDA_RETRY_ATTEMPTS < 0 || config.LAMBDA_RETRY_ATTEMPTS > 10) {
    throw new Error('LAMBDA_RETRY_ATTEMPTS must be between 0 and 10');
  }
}

/**
 * Validates MCP server configuration
 */
function validateMcpConfiguration(): void {
  if (config.MCP_PORT < 1024 || config.MCP_PORT > 65535) {
    throw new Error('MCP_PORT must be between 1024 and 65535');
  }
  
  if (config.MCP_MAX_CONNECTIONS < 1 || config.MCP_MAX_CONNECTIONS > 10000) {
    throw new Error('MCP_MAX_CONNECTIONS must be between 1 and 10000');
  }
  
  if (config.MCP_CONNECTION_TIMEOUT < 1000 || config.MCP_CONNECTION_TIMEOUT > 300000) {
    throw new Error('MCP_CONNECTION_TIMEOUT must be between 1000ms and 300000ms (5 minutes)');
  }
  
  console.log(`✓ MCP server configuration valid (Port: ${config.MCP_PORT})`);
}

/**
 * Validates authentication configuration
 */
function validateAuthConfiguration(): void {
  if (config.COGNITO_USER_POOL_ID && config.COGNITO_CLIENT_ID) {
    // Validate Cognito User Pool ID format
    const userPoolIdRegex = /^[a-z0-9-]+_[a-zA-Z0-9]+$/;
    if (!userPoolIdRegex.test(config.COGNITO_USER_POOL_ID)) {
      throw new Error(`Invalid COGNITO_USER_POOL_ID format: ${config.COGNITO_USER_POOL_ID}`);
    }
    
    console.log('✓ Cognito authentication configured');
  } else if (config.COGNITO_USER_POOL_ID || config.COGNITO_CLIENT_ID) {
    console.warn('⚠ Partial Cognito configuration detected. Both COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID should be set');
  } else {
    console.log('✓ Authentication configuration valid (IAM only)');
  }
}

/**
 * Prints current configuration summary
 */
export function printConfigurationSummary(): void {
  console.log('\n=== Configuration Summary ===');
  console.log(`Environment: ${config.NODE_ENV}`);
  console.log(`Server Port: ${config.PORT}`);
  console.log(`MCP Port: ${config.MCP_PORT}`);
  console.log(`AWS Region: ${config.AWS_REGION}`);
  console.log(`Bedrock Region: ${config.BEDROCK_REGION}`);
  // S3 Bucket logging removed - Lambda functions now return responses directly
  console.log(`Log Level: ${config.LOG_LEVEL}`);
  console.log(`Health Checks: ${config.HEALTH_CHECK_ENABLED ? 'Enabled' : 'Disabled'}`);
  console.log(`Metrics: ${config.ENABLE_METRICS ? 'Enabled' : 'Disabled'}`);
  
  if (isDevelopment()) {
    console.log('Lambda ARNs: Using development/mock configuration');
  } else {
    console.log(`Domain Analyzer ARN: ${config.DOMAIN_ANALYZER_LAMBDA_ARN || 'Not configured'}`);
    console.log(`Doc Generator ARN: ${config.DOC_GENERATOR_LAMBDA_ARN || 'Not configured'}`);
  }
  
  console.log('==============================\n');
}