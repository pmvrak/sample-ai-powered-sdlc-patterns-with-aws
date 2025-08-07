import { 
  CognitoIdentityProviderClient, 
  InitiateAuthCommand,
  AuthFlowType 
} from '@aws-sdk/client-cognito-identity-provider';
import {
  CognitoIdentityClient,
  GetIdCommand,
  GetCredentialsForIdentityCommand
} from '@aws-sdk/client-cognito-identity';
import { AwsCredentialIdentity } from '@aws-sdk/types';
import { createInterface } from 'readline';
import { CognitoConfig } from './types.js';
import { 
  AuthenticationError, 
  ErrorClassifier, 
  RetryManager, 
  ErrorCategory,
  ErrorLogger 
} from './errors.js';
import { log, secureLogger } from './secure-logger.js';
import { sanitize } from './sanitization.js';

/**
 * Rate limiting configuration for authentication attempts
 */
interface RateLimitEntry {
  count: number;
  resetTime: number;
  blocked: boolean;
}

/**
 * Rate limiter for authentication operations
 */
class AuthRateLimiter {
  private attempts = new Map<string, RateLimitEntry>();
  private readonly maxAttempts = 5;
  private readonly windowMs = 60000; // 1 minute
  private readonly blockDurationMs = 300000; // 5 minutes

  /**
   * Check if an identifier is rate limited
   */
  checkRateLimit(identifier: string): { allowed: boolean; retryAfter?: number } {
    const now = Date.now();
    const entry = this.attempts.get(identifier);

    // Clean up expired entries
    this.cleanup();

    if (!entry) {
      // First attempt
      this.attempts.set(identifier, {
        count: 1,
        resetTime: now + this.windowMs,
        blocked: false
      });
      return { allowed: true };
    }

    // Check if currently blocked
    if (entry.blocked && now < entry.resetTime) {
      return { 
        allowed: false, 
        retryAfter: Math.ceil((entry.resetTime - now) / 1000) 
      };
    }

    // Reset if window expired
    if (now > entry.resetTime) {
      entry.count = 1;
      entry.resetTime = now + this.windowMs;
      entry.blocked = false;
      return { allowed: true };
    }

    // Increment attempt count
    entry.count++;

    // Block if exceeded max attempts
    if (entry.count > this.maxAttempts) {
      entry.blocked = true;
      entry.resetTime = now + this.blockDurationMs;
      
      log.securityViolation('rate_limit_exceeded', {
        userId: sanitize.username(identifier),
        metadata: {
          attempts: entry.count,
          blockDuration: this.blockDurationMs / 1000
        }
      });

      return { 
        allowed: false, 
        retryAfter: Math.ceil(this.blockDurationMs / 1000) 
      };
    }

    return { allowed: true };
  }

  /**
   * Reset rate limit for an identifier (used after successful auth)
   */
  resetRateLimit(identifier: string): void {
    this.attempts.delete(identifier);
  }

  /**
   * Clean up expired entries
   */
  private cleanup(): void {
    const now = Date.now();
    for (const [key, entry] of this.attempts.entries()) {
      if (now > entry.resetTime && !entry.blocked) {
        this.attempts.delete(key);
      }
    }
  }
}

export interface AuthCredentials {
  username: string;
  password: string;
}

export interface AWSCredentials extends AwsCredentialIdentity {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken?: string;
  expiration?: Date;
}

export class CognitoAuth {
  private client: CognitoIdentityProviderClient;
  private identityClient: CognitoIdentityClient;
  private config: CognitoConfig;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private refreshTokenExpiry: Date | null = null;
  private idToken: string | null = null;
  private tokenExpiry: Date | null = null;
  private credentials: AuthCredentials | null = null;
  private awsCredentials: AWSCredentials | null = null;
  private awsCredentialsExpiry: Date | null = null;
  private identityId: string | null = null;
  private retryManager: RetryManager;
  private errorLogger: ErrorLogger;
  private rateLimiter: AuthRateLimiter;

  constructor(config: CognitoConfig) {
    this.config = config;
    this.client = new CognitoIdentityProviderClient({ 
      region: config.region 
    });
    this.identityClient = new CognitoIdentityClient({
      region: config.region
    });
    this.retryManager = RetryManager.getInstance();
    this.errorLogger = ErrorLogger.getInstance();
    this.rateLimiter = new AuthRateLimiter();
  }

  /**
   * Get a valid access token, handling automatic authentication and refresh
   */
  async getAccessToken(): Promise<string> {
    return await secureLogger.measurePerformance('auth.getAccessToken', async () => {
      return await this.retryManager.executeWithRetry(
        async () => {
          // Return cached token if still valid
          if (this.accessToken && this.tokenExpiry && new Date() < this.tokenExpiry) {
            log.debug('Using cached access token');
            return this.accessToken;
          }

          // Try to refresh token if we have a valid refresh token
          if (this.refreshToken && this.isRefreshTokenValid()) {
            try {
              log.debug('Attempting to refresh access token');
              await this.refreshAccessToken();
              return this.accessToken!;
            } catch (error) {
              const classifiedError = ErrorClassifier.classifyError(error, 'token_refresh');
              this.errorLogger.logError(classifiedError, 'getAccessToken:refresh');
              
              // Check if this is an invalid refresh token error
              if (error instanceof Error && (
                error.message.includes('Invalid Refresh Token') ||
                error.message.includes('NotAuthorizedException') ||
                error.message.includes('TOKEN_REFRESH_FAILED')
              )) {
                log.warn('Refresh token is invalid or expired, clearing tokens and re-authenticating', { 
                  error: classifiedError.message,
                  refreshTokenExpiry: this.refreshTokenExpiry?.toISOString()
                });
                this.clearInvalidRefreshToken();
                this.clearTokens();
              } else if (error instanceof Error && (
                error.message.includes('ENOTFOUND') ||
                error.message.includes('DNS_RESOLUTION_FAILED') ||
                error.message.includes('getaddrinfo')
              )) {
                log.warn('Network connectivity issue during token refresh, will retry on next attempt', { 
                  error: classifiedError.message 
                });
                // Don't clear tokens for network errors - they might be temporary
                throw classifiedError; // Re-throw to trigger retry logic
              } else {
                log.warn('Token refresh failed with retryable error, will re-authenticate', { error: classifiedError.message });
                this.clearTokens();
              }
            }
          } else if (this.refreshToken && !this.isRefreshTokenValid()) {
            log.warn('Refresh token has expired, clearing tokens and re-authenticating', {
              refreshTokenExpiry: this.refreshTokenExpiry?.toISOString()
            });
            this.clearTokens();
          }

          // Authenticate (either first time or after refresh failure)
          log.debug('Performing authentication');
          await this.authenticate();
          return this.accessToken!;
        },
        ErrorCategory.AUTHENTICATION,
        'getAccessToken'
      );
    });
  }

  /**
   * Authenticate using environment variables or interactive console prompts
   */
  async authenticate(): Promise<void> {
    return await secureLogger.measurePerformance('auth.authenticate', async () => {
      try {
        log.info('Starting authentication process');
        
        // Get credentials from environment variables or prompt user
        const credentials = await this.getCredentials();
        
        // Check rate limiting
        const rateLimitCheck = this.rateLimiter.checkRateLimit(credentials.username);
        if (!rateLimitCheck.allowed) {
          const error = new AuthenticationError(
            `Authentication rate limit exceeded. Please try again in ${rateLimitCheck.retryAfter} seconds.`,
            'RATE_LIMIT_EXCEEDED',
            false
          );
          
          log.securityViolation('authentication_rate_limit_exceeded', {
            userId: sanitize.username(credentials.username),
            metadata: {
              retryAfter: rateLimitCheck.retryAfter
            }
          });
          
          throw error;
        }
        
        log.debug('Sending authentication request to Cognito', {
          username: sanitize.username(credentials.username),
          clientId: this.config.clientId,
          region: this.config.region
        });
        
        const command = new InitiateAuthCommand({
          AuthFlow: AuthFlowType.USER_PASSWORD_AUTH,
          ClientId: this.config.clientId,
          AuthParameters: {
            USERNAME: credentials.username,
            PASSWORD: credentials.password,
          },
        });

        const response = await this.client.send(command);
        
        if (!response.AuthenticationResult?.AccessToken) {
          const error = new AuthenticationError(
            'Authentication failed - no access token received',
            'AUTHENTICATION_FAILED',
            false
          );
          
          log.auth('login', false, {
            userId: sanitize.username(credentials.username),
            reason: 'no_access_token'
          });
          
          throw error;
        }

        // Store tokens
        this.accessToken = response.AuthenticationResult.AccessToken;
        this.refreshToken = response.AuthenticationResult.RefreshToken || null;
        this.idToken = response.AuthenticationResult.IdToken || null;
        
        // Set expiry time (default to 1 hour if not provided, refresh 1 min early)
        const expiresIn = response.AuthenticationResult.ExpiresIn || 3600;
        this.tokenExpiry = new Date(Date.now() + (expiresIn - 60) * 1000);
        
        // Set refresh token expiry (typically 30 days, but we'll be conservative and assume 7 days)
        if (this.refreshToken) {
          this.refreshTokenExpiry = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000); // 7 days
        }
        
        // Store credentials for potential retry
        this.credentials = credentials;
        
        log.info('Successfully authenticated with AWS Cognito', {
          username: sanitize.username(credentials.username),
          expiresIn,
          hasRefreshToken: !!this.refreshToken
        });
        
        log.auth('login', true, {
          userId: sanitize.username(credentials.username),
          metadata: { 
            method: 'cognito_user_pool',
            expiresIn,
            hasRefreshToken: !!this.refreshToken
          }
        });
        
        // Reset rate limit on successful authentication
        this.rateLimiter.resetRateLimit(credentials.username);
        
        // SECURITY: Use secure logging for authentication success
        log.info('Successfully authenticated with AWS Cognito', {
          username: sanitize.username(credentials.username),
          authMethod: 'cognito'
        });
        
      } catch (error: any) {
        this.clearAllCredentials();
        
        log.error('Authentication failed', {
          error: error.message,
          errorCode: error.code || 'UNKNOWN',
          stack: error.stack
        });
        
        log.auth('login', false, {
          userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          reason: error.message,
          metadata: { 
            errorCode: error.code || 'UNKNOWN'
          }
        });
        
        // Classify and throw appropriate error
        const classifiedError = ErrorClassifier.classifyError(error, 'authenticate');
        this.errorLogger.logError(classifiedError, 'authenticate');
        throw classifiedError;
      }
    });
  }

  /**
   * Refresh the access token using the refresh token
   */
  private async refreshAccessToken(): Promise<void> {
    return await secureLogger.measurePerformance('auth.refreshToken', async () => {
      if (!this.refreshToken) {
        const error = new AuthenticationError(
          'No refresh token available',
          'NO_REFRESH_TOKEN',
          false
        );
        
        log.auth('token_refresh', false, {
          userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          reason: 'no_refresh_token'
        });
        
        throw error;
      }

      try {
        log.debug('Refreshing access token');
        
        const command = new InitiateAuthCommand({
          AuthFlow: AuthFlowType.REFRESH_TOKEN_AUTH,
          ClientId: this.config.clientId,
          AuthParameters: {
            REFRESH_TOKEN: this.refreshToken,
          },
        });

        const response = await this.client.send(command);
        
        if (!response.AuthenticationResult?.AccessToken) {
          const error = new AuthenticationError(
            'Token refresh failed - no access token received',
            'TOKEN_REFRESH_FAILED',
            false
          );
          
          log.auth('token_refresh', false, {
            userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
            reason: 'no_access_token'
          });
          
          throw error;
        }

        this.accessToken = response.AuthenticationResult.AccessToken;
        
        // Update expiry time
        const expiresIn = response.AuthenticationResult.ExpiresIn || 3600;
        this.tokenExpiry = new Date(Date.now() + (expiresIn - 60) * 1000);
        
        log.info('Successfully refreshed authentication token', {
          username: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          expiresIn
        });
        
        log.auth('token_refresh', true, {
          userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          metadata: { expiresIn }
        });
        
        // SECURITY: Use secure logging for token refresh success
        log.info('Successfully refreshed authentication token', {
          username: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          expiresIn
        });
        
      } catch (error: any) {
        log.error('Token refresh failed', {
          error: error.message,
          errorCode: error.code || 'UNKNOWN',
          username: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined
        });
        
        log.auth('token_refresh', false, {
          userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          reason: error.message,
          metadata: { 
            errorCode: error.code || 'UNKNOWN'
          }
        });
        
        const classifiedError = ErrorClassifier.classifyError(error, 'refreshAccessToken');
        this.errorLogger.logError(classifiedError, 'refreshAccessToken');
        throw classifiedError;
      }
    });
  }

  /**
   * Get credentials from environment variables or prompt user interactively
   */
  private async getCredentials(): Promise<AuthCredentials> {
    // First try environment variables
    const envUsername = process.env.COGNITO_USERNAME || this.config.username;
    const envPassword = process.env.COGNITO_PASSWORD || this.config.password;
    
    if (envUsername && envPassword) {
      // SECURITY: Use secure logging for credential source
      log.info('Using credentials from environment variables', {
        credentialSource: 'environment'
      });
      return {
        username: envUsername,
        password: envPassword
      };
    }

    // For MCP servers, we should have credentials in environment
    // Interactive prompts don't work well in MCP context
    if (process.env.NODE_ENV === 'production' || process.env.MCP_SERVER === 'true') {
      throw new AuthenticationError(
        'Credentials must be provided via environment variables (COGNITO_USERNAME and COGNITO_PASSWORD) for MCP server operation',
        'MISSING_CREDENTIALS',
        false
      );
    }

    // Fall back to interactive console prompts (development only)
    // SECURITY: Use secure logging for credential prompt
    log.info('Credentials not found in environment variables, prompting for input', {
      credentialSource: 'interactive_prompt'
    });
    try {
      return await this.promptForCredentials();
    } catch (error) {
      throw new AuthenticationError(
        'Failed to obtain credentials',
        'MISSING_CREDENTIALS',
        false,
        error
      );
    }
  }

  /**
   * Prompt user for credentials via console input
   */
  private async promptForCredentials(): Promise<AuthCredentials> {
    const rl = createInterface({
      input: process.stdin,
      output: process.stdout
    });

    try {
      const username = await this.question(rl, 'Enter your email: ');
      if (!username.trim()) {
        throw new AuthenticationError(
          'Email is required',
          'MISSING_CREDENTIALS',
          false
        );
      }

      const password = await this.questionHidden(rl, 'Enter your password: ');
      if (!password.trim()) {
        throw new AuthenticationError(
          'Password is required',
          'MISSING_CREDENTIALS',
          false
        );
      }

      return {
        username: username.trim(),
        password: password.trim()
      };
    } finally {
      rl.close();
    }
  }

  /**
   * Prompt for input with readline
   */
  private question(rl: any, prompt: string): Promise<string> {
    return new Promise((resolve) => {
      rl.question(prompt, (answer: string) => {
        resolve(answer);
      });
    });
  }

  /**
   * Prompt for hidden input (password)
   */
  private questionHidden(rl: any, prompt: string): Promise<string> {
    return new Promise((resolve) => {
      // Disable echo for password input
      process.stdout.write(prompt);
      process.stdin.setRawMode(true);
      
      let password = '';
      const onData = (char: Buffer) => {
        const c = char.toString();
        
        if (c === '\r' || c === '\n') {
          // Enter pressed
          process.stdin.setRawMode(false);
          process.stdin.removeListener('data', onData);
          process.stdout.write('\n');
          resolve(password);
        } else if (c === '\u0003') {
          // Ctrl+C pressed
          process.stdin.setRawMode(false);
          process.stdin.removeListener('data', onData);
          process.stdout.write('\n');
          process.exit(1);
        } else if (c === '\u007f' || c === '\b') {
          // Backspace pressed
          if (password.length > 0) {
            password = password.slice(0, -1);
            process.stdout.write('\b \b');
          }
        } else if (c >= ' ' && c <= '~') {
          // Printable character
          password += c;
          process.stdout.write('*');
        }
      };
      
      process.stdin.on('data', onData);
    });
  }

  /**
   * Clear stored tokens and credentials
   */
  private clearTokens(): void {
    // SECURITY: Log token clearing for audit purposes
    log.info('Clearing authentication tokens', {
      hadAccessToken: !!this.accessToken,
      hadRefreshToken: !!this.refreshToken,
      hadIdToken: !!this.idToken,
      username: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined
    });
    
    this.accessToken = null;
    this.refreshToken = null;
    this.refreshTokenExpiry = null;
    this.idToken = null;
    this.tokenExpiry = null;
    
    // SECURITY: Log security event for token clearing
    log.auth('logout', true, {
      userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
      reason: 'manual_clear'
    });
  }

  /**
   * Check if currently authenticated
   */
  isAuthenticated(): boolean {
    return this.accessToken !== null && 
           this.tokenExpiry !== null && 
           new Date() < this.tokenExpiry;
  }

  /**
   * Check if token is close to expiring (within 5 minutes)
   */
  isTokenNearExpiry(): boolean {
    if (!this.tokenExpiry) return false;
    const fiveMinutesFromNow = new Date(Date.now() + 5 * 60 * 1000);
    return this.tokenExpiry < fiveMinutesFromNow;
  }

  /**
   * Check if refresh token is still valid
   */
  isRefreshTokenValid(): boolean {
    return this.refreshToken !== null && 
           this.refreshTokenExpiry !== null && 
           new Date() < this.refreshTokenExpiry;
  }

  /**
   * Check if refresh token is close to expiring (within 1 day)
   */
  isRefreshTokenNearExpiry(): boolean {
    if (!this.refreshTokenExpiry) return false;
    const oneDayFromNow = new Date(Date.now() + 24 * 60 * 60 * 1000);
    return this.refreshTokenExpiry < oneDayFromNow;
  }

  /**
   * Proactively refresh token if it's close to expiring
   */
  async ensureValidToken(): Promise<string> {
    // If token is expired or close to expiring, get a fresh one
    if (!this.isAuthenticated() || this.isTokenNearExpiry()) {
      log.debug('Token expired or near expiry, refreshing proactively');
      return await this.getAccessToken();
    }
    
    // Token is still valid and not close to expiring
    return this.accessToken!;
  }

  /**
   * Get current token expiry time
   */
  getTokenExpiry(): Date | null {
    return this.tokenExpiry;
  }

  /**
   * Get AWS credentials from Cognito Identity Pool using the access token
   */
  async getAWSCredentials(): Promise<AWSCredentials> {
    return await secureLogger.measurePerformance('auth.getAWSCredentials', async () => {
      return await this.retryManager.executeWithRetry(
        async () => {
          // Return cached AWS credentials if still valid
          if (this.awsCredentials && this.awsCredentialsExpiry && new Date() < this.awsCredentialsExpiry) {
            log.debug('Using cached AWS credentials');
            return this.awsCredentials;
          }

          // Ensure we have a valid access token first
          const accessToken = await this.getAccessToken();

          // Get or refresh AWS credentials from Identity Pool
          await this.refreshAWSCredentials(accessToken);
          
          if (!this.awsCredentials) {
            throw new AuthenticationError(
              'Failed to obtain AWS credentials from Identity Pool',
              'AWS_CREDENTIALS_FAILED',
              true
            );
          }

          return this.awsCredentials;
        },
        ErrorCategory.AUTHENTICATION,
        'getAWSCredentials'
      );
    });
  }

  /**
   * Refresh AWS credentials from Cognito Identity Pool
   */
  private async refreshAWSCredentials(accessToken: string): Promise<void> {
    return await secureLogger.measurePerformance('auth.refreshAWSCredentials', async () => {
      try {
        log.debug('Getting AWS credentials from Cognito Identity Pool');

        // Step 1: Get Identity ID if we don't have one
        if (!this.identityId) {
          await this.getIdentityId(accessToken);
        }

        // Step 2: Get AWS credentials for the identity
        const credentialsCommand = new GetCredentialsForIdentityCommand({
          IdentityId: this.identityId!,
          Logins: {
            [`cognito-idp.${this.config.region}.amazonaws.com/${this.config.userPoolId}`]: this.idToken || accessToken
          }
        });

        const credentialsResponse = await this.identityClient.send(credentialsCommand);
        
        if (!credentialsResponse.Credentials) {
          throw new AuthenticationError(
            'No AWS credentials returned from Identity Pool',
            'NO_AWS_CREDENTIALS',
            true
          );
        }

        const creds = credentialsResponse.Credentials;
        
        // Store AWS credentials
        this.awsCredentials = {
          accessKeyId: creds.AccessKeyId!,
          secretAccessKey: creds.SecretKey!,
          sessionToken: creds.SessionToken,
          expiration: creds.Expiration
        };

        // Set expiry time (refresh 5 minutes early)
        this.awsCredentialsExpiry = creds.Expiration ? 
          new Date(creds.Expiration.getTime() - 5 * 60 * 1000) : 
          new Date(Date.now() + 55 * 60 * 1000); // Default 55 minutes

        log.info('Successfully obtained AWS credentials from Identity Pool', {
          identityId: this.identityId,
          expiresAt: this.awsCredentialsExpiry.toISOString(),
          hasSessionToken: !!this.awsCredentials.sessionToken
        });

        log.auth('login', true, {
          userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          metadata: { 
            identityId: this.identityId,
            expiresAt: this.awsCredentialsExpiry.toISOString(),
            credentialType: 'aws_identity_pool'
          }
        });

        // SECURITY: Use secure logging for AWS credential success
        log.info('Successfully obtained AWS credentials from Identity Pool', {
          identityPoolId: this.config.identityPoolId,
          credentialType: 'identity_pool'
        });

      } catch (error: any) {
        log.error('Failed to get AWS credentials from Identity Pool', {
          error: error.message,
          errorCode: error.code || 'UNKNOWN',
          identityId: this.identityId
        });

        log.auth('login', false, {
          userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
          reason: error.message,
          metadata: { 
            errorCode: error.code || 'UNKNOWN',
            credentialType: 'aws_identity_pool'
          }
        });

        const classifiedError = ErrorClassifier.classifyError(error, 'refreshAWSCredentials');
        this.errorLogger.logError(classifiedError, 'refreshAWSCredentials');
        throw classifiedError;
      }
    });
  }

  /**
   * Get Identity ID from Cognito Identity Pool
   */
  private async getIdentityId(accessToken: string): Promise<void> {
    try {
      log.debug('Getting Identity ID from Cognito Identity Pool');

      const identityCommand = new GetIdCommand({
        IdentityPoolId: this.config.identityPoolId!,
        Logins: {
          [`cognito-idp.${this.config.region}.amazonaws.com/${this.config.userPoolId}`]: this.idToken || accessToken
        }
      });

      const identityResponse = await this.identityClient.send(identityCommand);
      
      if (!identityResponse.IdentityId) {
        throw new AuthenticationError(
          'No Identity ID returned from Identity Pool',
          'NO_IDENTITY_ID',
          true
        );
      }

      this.identityId = identityResponse.IdentityId;
      
      log.debug('Successfully obtained Identity ID', {
        identityId: this.identityId
      });

    } catch (error: any) {
      log.error('Failed to get Identity ID from Identity Pool', {
        error: error.message,
        errorCode: error.code || 'UNKNOWN'
      });

      const classifiedError = ErrorClassifier.classifyError(error, 'getIdentityId');
      this.errorLogger.logError(classifiedError, 'getIdentityId');
      throw classifiedError;
    }
  }

  /**
   * Clear all stored credentials and tokens
   */
  private clearAllCredentials(): void {
    // SECURITY: Log comprehensive credential clearing for audit purposes
    log.warn('Clearing all authentication credentials', {
      hadAccessToken: !!this.accessToken,
      hadRefreshToken: !!this.refreshToken,
      hadAWSCredentials: !!this.awsCredentials,
      hadIdentityId: !!this.identityId,
      username: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined
    });
    
    this.clearTokens();
    this.awsCredentials = null;
    this.awsCredentialsExpiry = null;
    this.identityId = null;
    
    // SECURITY: Log critical security event for complete credential clearing
    log.auth('logout', true, {
      userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
      reason: 'authentication_failure_or_reset'
    });
  }

  /**
   * Check if AWS credentials are available and valid
   */
  hasValidAWSCredentials(): boolean {
    return this.awsCredentials !== null && 
           this.awsCredentialsExpiry !== null && 
           new Date() < this.awsCredentialsExpiry;
  }

  /**
   * Check if AWS credentials are close to expiring (within 10 minutes)
   */
  areAWSCredentialsNearExpiry(): boolean {
    if (!this.awsCredentialsExpiry) return false;
    const tenMinutesFromNow = new Date(Date.now() + 10 * 60 * 1000);
    return this.awsCredentialsExpiry < tenMinutesFromNow;
  }

  /**
   * Proactively refresh AWS credentials if they're close to expiring
   */
  async ensureValidAWSCredentials(): Promise<AWSCredentials> {
    // If credentials are expired or close to expiring, get fresh ones
    if (!this.hasValidAWSCredentials() || this.areAWSCredentialsNearExpiry()) {
      log.debug('AWS credentials expired or near expiry, refreshing proactively');
      return await this.getAWSCredentials();
    }
    
    // Credentials are still valid and not close to expiring
    return this.awsCredentials!;
  }

  /**
   * Get AWS credentials expiry time
   */
  getAWSCredentialsExpiry(): Date | null {
    return this.awsCredentialsExpiry;
  }

  /**
   * Force clear invalid refresh tokens (useful when they consistently fail)
   */
  clearInvalidRefreshToken(): void {
    if (this.refreshToken) {
      log.info('Clearing invalid refresh token', {
        refreshTokenExpiry: this.refreshTokenExpiry?.toISOString(),
        username: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined
      });
      this.refreshToken = null;
      this.refreshTokenExpiry = null;
      
      log.auth('logout', true, {
        userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
        reason: 'invalid_refresh_token'
      });
    } else {
      // SECURITY: Log when token clearing is attempted but no token exists
      log.info('Attempted to clear invalid refresh token but no token exists', {
        username: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
        hasCredentials: !!this.credentials
      });
      
      log.auth('logout', false, {
        userId: this.credentials?.username ? sanitize.username(this.credentials.username) : undefined,
        reason: 'no_refresh_token_to_clear'
      });
    }
  }

  /**
   * Get comprehensive authentication status for health monitoring
   */
  getAuthenticationStatus(): {
    authenticated: boolean;
    tokenExpiry: Date | null;
    tokenNearExpiry: boolean;
    refreshTokenValid: boolean;
    refreshTokenExpiry: Date | null;
    refreshTokenNearExpiry: boolean;
    awsCredentialsValid: boolean;
    awsCredentialsExpiry: Date | null;
    awsCredentialsNearExpiry: boolean;
    username: string | null;
  } {
    return {
      authenticated: this.isAuthenticated(),
      tokenExpiry: this.tokenExpiry,
      tokenNearExpiry: this.isTokenNearExpiry(),
      refreshTokenValid: this.isRefreshTokenValid(),
      refreshTokenExpiry: this.refreshTokenExpiry,
      refreshTokenNearExpiry: this.isRefreshTokenNearExpiry(),
      awsCredentialsValid: this.hasValidAWSCredentials(),
      awsCredentialsExpiry: this.awsCredentialsExpiry,
      awsCredentialsNearExpiry: this.areAWSCredentialsNearExpiry(),
      username: this.credentials?.username || null
    };
  }
}