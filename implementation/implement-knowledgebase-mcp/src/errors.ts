/**
 * Comprehensive error handling system for the Project KB MCP Server
 * 
 * This module provides:
 * - Error classification and standardized error types
 * - Retry logic for transient failures
 * - User-friendly error message formatting
 * - Graceful degradation utilities
 * - MCP-compliant error response formatting
 */

import { ErrorResponse } from './types.js';
import { log } from './secure-logger.js';
import { sanitize } from './sanitization.js';

/**
 * Base error class for all Project KB MCP Server errors
 */
export abstract class ProjectKBError extends Error {
  abstract readonly code: string;
  abstract readonly retryable: boolean;
  abstract readonly category: ErrorCategory;
  
  public readonly timestamp: Date;
  public readonly details?: any;

  constructor(message: string, details?: any) {
    super(message);
    this.name = this.constructor.name;
    this.timestamp = new Date();
    this.details = details;
  }

  /**
   * Convert error to MCP-compliant error response
   */
  toMCPError(): ErrorResponse {
    return {
      error: {
        code: this.code,
        message: this.getUserFriendlyMessage(),
        details: this.getSafeDetails(),
        retryable: this.retryable
      }
    };
  }

  /**
   * Get user-friendly error message
   */
  abstract getUserFriendlyMessage(): string;

  /**
   * Get safe details for client consumption (removes sensitive info)
   */
  protected getSafeDetails(): any {
    if (!this.details) return undefined;
    
    // Remove sensitive information from details
    const safeDetails = { ...this.details };
    delete safeDetails.password;
    delete safeDetails.token;
    delete safeDetails.credentials;
    delete safeDetails.accessToken;
    delete safeDetails.refreshToken;
    
    return safeDetails;
  }
}

/**
 * Error categories for classification
 */
export enum ErrorCategory {
  AUTHENTICATION = 'authentication',
  AUTHORIZATION = 'authorization',
  CONFIGURATION = 'configuration',
  NETWORK = 'network',
  SEARCH = 'search',
  PROJECT = 'project',
  DOCUMENT = 'document',
  VALIDATION = 'validation',
  SYSTEM = 'system'
}

/**
 * Authentication-related errors
 */
export class AuthenticationError extends ProjectKBError {
  readonly category = ErrorCategory.AUTHENTICATION;
  
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'INVALID_CREDENTIALS':
        return 'Invalid email or password. Please check your credentials and try again.';
      case 'USER_NOT_FOUND':
        return 'User not found. Please check your email address.';
      case 'TOO_MANY_REQUESTS':
        return 'Too many authentication attempts. Please wait a moment and try again.';
      case 'TOKEN_EXPIRED':
        return 'Your session has expired. Please authenticate again.';
      case 'TOKEN_REFRESH_FAILED':
        return 'Failed to refresh authentication token. Please sign in again.';
      case 'COGNITO_SERVICE_ERROR':
        return 'Authentication service is temporarily unavailable. Please try again later.';
      case 'MISSING_CREDENTIALS':
        return 'Authentication credentials are required. Please provide your email and password.';
      default:
        return `Authentication failed: ${this.message}`;
    }
  }
}

/**
 * Authorization-related errors
 */
export class AuthorizationError extends ProjectKBError {
  readonly category = ErrorCategory.AUTHORIZATION;
  readonly retryable = false;
  
  constructor(
    message: string,
    public readonly code: string,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'PROJECT_ACCESS_DENIED':
        return 'You do not have permission to access this project. Please contact your administrator.';
      case 'DOCUMENT_ACCESS_DENIED':
        return 'You do not have permission to access this document.';
      case 'INSUFFICIENT_PERMISSIONS':
        return 'Insufficient permissions to perform this operation.';
      default:
        return `Access denied: ${this.message}`;
    }
  }
}

/**
 * Configuration-related errors
 */
export class ConfigurationError extends ProjectKBError {
  readonly category = ErrorCategory.CONFIGURATION;
  readonly retryable = false;
  
  constructor(
    message: string,
    public readonly code: string,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'MISSING_CONFIG':
        return 'Required configuration is missing. Please check your environment variables.';
      case 'INVALID_CONFIG':
        return 'Configuration is invalid. Please check your settings.';
      case 'OPENSEARCH_CONFIG_ERROR':
        return 'OpenSearch configuration is invalid. Please check your connection settings.';
      case 'COGNITO_CONFIG_ERROR':
        return 'Cognito configuration is invalid. Please check your authentication settings.';
      default:
        return `Configuration error: ${this.message}`;
    }
  }
}

/**
 * Network-related errors
 */
export class NetworkError extends ProjectKBError {
  readonly category = ErrorCategory.NETWORK;
  readonly retryable = true;
  
  constructor(
    message: string,
    public readonly code: string,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'CONNECTION_TIMEOUT':
        return 'Connection timed out. Please check your network connection and try again.';
      case 'CONNECTION_REFUSED':
        return 'Unable to connect to the service. Please try again later.';
      case 'DNS_RESOLUTION_FAILED':
        return 'Unable to resolve service address. Please check your network configuration.';
      case 'NETWORK_UNREACHABLE':
        return 'Network is unreachable. Please check your internet connection.';
      case 'SSL_ERROR':
        return 'Secure connection failed. Please check your network security settings.';
      default:
        return `Network error: ${this.message}`;
    }
  }
}

/**
 * Search-related errors
 */
export class SearchError extends ProjectKBError {
  readonly category = ErrorCategory.SEARCH;
  
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = true,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'INVALID_QUERY':
        return 'Search query is invalid. Please check your search terms and try again.';
      case 'QUERY_TOO_LONG':
        return 'Search query is too long. Please shorten your query and try again.';
      case 'SEARCH_TIMEOUT':
        return 'Search timed out. Please try a more specific query or try again later.';
      case 'INDEX_NOT_FOUND':
        return 'Project index not found. The project may not be available or indexed yet.';
      case 'SEARCH_SERVICE_ERROR':
        return 'Search service is temporarily unavailable. Please try again later.';
      case 'NO_RESULTS':
        return 'No results found for your search query. Try different search terms.';
      default:
        return `Search failed: ${this.message}`;
    }
  }
}

/**
 * Project-related errors
 */
export class ProjectError extends ProjectKBError {
  readonly category = ErrorCategory.PROJECT;
  
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'PROJECT_NOT_FOUND':
        return 'Project not found. Please check the project name and try again.';
      case 'PROJECT_DISCOVERY_ERROR':
        return 'Unable to discover available projects. Please try again later.';
      case 'PROJECT_ACCESS_DENIED':
        return 'You do not have access to this project. Please contact your administrator.';
      case 'INVALID_PROJECT_ID':
        return 'Project identifier is invalid. Please provide a valid project name or ID.';
      case 'PROJECT_UNAVAILABLE':
        return 'Project is temporarily unavailable. Please try again later.';
      default:
        return `Project error: ${this.message}`;
    }
  }
}

/**
 * Document-related errors
 */
export class DocumentError extends ProjectKBError {
  readonly category = ErrorCategory.DOCUMENT;
  
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'DOCUMENT_NOT_FOUND':
        return 'Document not found. The document may have been moved or deleted.';
      case 'DOCUMENT_ACCESS_DENIED':
        return 'You do not have permission to access this document.';
      case 'DOCUMENT_CORRUPTED':
        return 'Document appears to be corrupted and cannot be retrieved.';
      case 'DOCUMENT_TOO_LARGE':
        return 'Document is too large to retrieve. Please contact your administrator.';
      case 'INVALID_DOCUMENT_ID':
        return 'Document identifier is invalid. Please provide a valid document ID.';
      default:
        return `Document error: ${this.message}`;
    }
  }
}

/**
 * Validation-related errors
 */
export class ValidationError extends ProjectKBError {
  readonly category = ErrorCategory.VALIDATION;
  readonly retryable = false;
  
  constructor(
    message: string,
    public readonly code: string,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'INVALID_INPUT':
        return 'Input is invalid. Please check your parameters and try again.';
      case 'MISSING_REQUIRED_FIELD':
        return 'Required field is missing. Please provide all required information.';
      case 'INVALID_FORMAT':
        return 'Input format is invalid. Please check the expected format and try again.';
      case 'VALUE_OUT_OF_RANGE':
        return 'Value is out of acceptable range. Please adjust your input.';
      default:
        return `Validation error: ${this.message}`;
    }
  }
}

/**
 * System-related errors
 */
export class SystemError extends ProjectKBError {
  readonly category = ErrorCategory.SYSTEM;
  readonly retryable = true;
  
  constructor(
    message: string,
    public readonly code: string,
    details?: any
  ) {
    super(message, details);
  }

  getUserFriendlyMessage(): string {
    switch (this.code) {
      case 'INTERNAL_ERROR':
        return 'An internal error occurred. Please try again later.';
      case 'SERVICE_UNAVAILABLE':
        return 'Service is temporarily unavailable. Please try again later.';
      case 'RESOURCE_EXHAUSTED':
        return 'System resources are temporarily exhausted. Please try again later.';
      case 'TIMEOUT':
        return 'Operation timed out. Please try again.';
      default:
        return `System error: ${this.message}`;
    }
  }
}

/**
 * Retry configuration for different error types
 */
export interface RetryConfig {
  maxAttempts: number;
  baseDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
  retryableErrors: string[];
}

/**
 * Default retry configurations by error category
 */
export const DEFAULT_RETRY_CONFIGS: Record<ErrorCategory, RetryConfig> = {
  [ErrorCategory.AUTHENTICATION]: {
    maxAttempts: 3,
    baseDelayMs: 1000,
    maxDelayMs: 5000,
    backoffMultiplier: 2,
    retryableErrors: ['TOKEN_EXPIRED', 'COGNITO_SERVICE_ERROR', 'TOO_MANY_REQUESTS']
  },
  [ErrorCategory.AUTHORIZATION]: {
    maxAttempts: 1,
    baseDelayMs: 0,
    maxDelayMs: 0,
    backoffMultiplier: 1,
    retryableErrors: []
  },
  [ErrorCategory.CONFIGURATION]: {
    maxAttempts: 1,
    baseDelayMs: 0,
    maxDelayMs: 0,
    backoffMultiplier: 1,
    retryableErrors: []
  },
  [ErrorCategory.NETWORK]: {
    maxAttempts: 3,
    baseDelayMs: 1000,
    maxDelayMs: 10000,
    backoffMultiplier: 2,
    retryableErrors: ['CONNECTION_TIMEOUT', 'CONNECTION_REFUSED', 'NETWORK_UNREACHABLE']
  },
  [ErrorCategory.SEARCH]: {
    maxAttempts: 2,
    baseDelayMs: 500,
    maxDelayMs: 2000,
    backoffMultiplier: 2,
    retryableErrors: ['SEARCH_TIMEOUT', 'SEARCH_SERVICE_ERROR']
  },
  [ErrorCategory.PROJECT]: {
    maxAttempts: 2,
    baseDelayMs: 1000,
    maxDelayMs: 3000,
    backoffMultiplier: 2,
    retryableErrors: ['PROJECT_DISCOVERY_ERROR', 'PROJECT_UNAVAILABLE']
  },
  [ErrorCategory.DOCUMENT]: {
    maxAttempts: 2,
    baseDelayMs: 500,
    maxDelayMs: 2000,
    backoffMultiplier: 2,
    retryableErrors: []
  },
  [ErrorCategory.VALIDATION]: {
    maxAttempts: 1,
    baseDelayMs: 0,
    maxDelayMs: 0,
    backoffMultiplier: 1,
    retryableErrors: []
  },
  [ErrorCategory.SYSTEM]: {
    maxAttempts: 3,
    baseDelayMs: 1000,
    maxDelayMs: 5000,
    backoffMultiplier: 2,
    retryableErrors: ['INTERNAL_ERROR', 'SERVICE_UNAVAILABLE', 'TIMEOUT']
  }
};

/**
 * Retry utility with exponential backoff
 */
export class RetryManager {
  private static instance: RetryManager;
  private retryConfigs: Record<ErrorCategory, RetryConfig>;

  private constructor() {
    this.retryConfigs = { ...DEFAULT_RETRY_CONFIGS };
  }

  static getInstance(): RetryManager {
    if (!RetryManager.instance) {
      RetryManager.instance = new RetryManager();
    }
    return RetryManager.instance;
  }

  /**
   * Execute operation with retry logic
   */
  async executeWithRetry<T>(
    operation: () => Promise<T>,
    category: ErrorCategory,
    context?: string
  ): Promise<T> {
    const config = this.retryConfigs[category];
    let lastError: Error;
    
    for (let attempt = 1; attempt <= config.maxAttempts; attempt++) {
      try {
        return await operation();
      } catch (error) {
        lastError = error as Error;
        
        // Check if error is retryable
        if (!this.isRetryableError(error as Error, config)) {
          throw error;
        }
        
        // Don't retry on last attempt
        if (attempt === config.maxAttempts) {
          break;
        }
        
        // Calculate delay with exponential backoff
        const delay = Math.min(
          config.baseDelayMs * Math.pow(config.backoffMultiplier, attempt - 1),
          config.maxDelayMs
        );
        
        // SECURITY: Use secure logging with sanitized data
        log.warn('Retry attempt', {
          attempt,
          maxAttempts: config.maxAttempts,
          context: context ? sanitize.searchQuery(context).sanitized : 'operation',
          delay,
          error: error instanceof Error ? error.message : String(error)
        });
        
        await this.sleep(delay);
      }
    }
    
    throw lastError!;
  }

  /**
   * Check if error is retryable based on configuration
   */
  private isRetryableError(error: Error, config: RetryConfig): boolean {
    // If it's a ProjectKB error, use its retryable property
    if (error instanceof ProjectKBError) {
      if (!error.retryable) return false;
      return config.retryableErrors.length === 0 || 
             config.retryableErrors.includes(error.code);
    }
    
    // For non-ProjectKB errors, classify them first
    const classifiedError = ErrorClassifier.classifyError(error);
    if (!classifiedError.retryable) return false;
    
    return config.retryableErrors.length === 0 || 
           config.retryableErrors.includes(classifiedError.code);
  }

  /**
   * Sleep utility for retry delays
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Update retry configuration for a category
   */
  updateRetryConfig(category: ErrorCategory, config: Partial<RetryConfig>): void {
    this.retryConfigs[category] = {
      ...this.retryConfigs[category],
      ...config
    };
  }

  /**
   * Get retry configuration for a category
   */
  getRetryConfig(category: ErrorCategory): RetryConfig {
    return { ...this.retryConfigs[category] };
  }
}

/**
 * Error classification utility
 */
export class ErrorClassifier {
  /**
   * Classify unknown errors into appropriate ProjectKB error types
   */
  static classifyError(error: any, context?: string): ProjectKBError {
    // If already a ProjectKB error, return as-is
    if (error instanceof ProjectKBError) {
      return error;
    }

    const message = error.message || error.toString();
    const errorName = error.name || '';
    const errorCode = error.code || '';

    // AWS Cognito errors
    if (errorName === 'NotAuthorizedException' || errorCode === 'NotAuthorizedException') {
      return new AuthenticationError(message, 'INVALID_CREDENTIALS', false, error);
    }
    if (errorName === 'UserNotFoundException' || errorCode === 'UserNotFoundException') {
      return new AuthenticationError(message, 'USER_NOT_FOUND', false, error);
    }
    if (errorName === 'TooManyRequestsException' || errorCode === 'TooManyRequestsException') {
      return new AuthenticationError(message, 'TOO_MANY_REQUESTS', true, error);
    }

    // Network errors
    if (errorCode === 'ECONNREFUSED' || message.includes('ECONNREFUSED')) {
      return new NetworkError(message, 'CONNECTION_REFUSED', error);
    }
    if (errorCode === 'ETIMEDOUT' || message.includes('timeout')) {
      return new NetworkError(message, 'CONNECTION_TIMEOUT', error);
    }
    if (errorCode === 'ENOTFOUND' || message.includes('ENOTFOUND')) {
      return new NetworkError(message, 'DNS_RESOLUTION_FAILED', error);
    }

    // OpenSearch errors
    if (message.includes('index_not_found_exception')) {
      return new SearchError(message, 'INDEX_NOT_FOUND', false, error);
    }
    if (message.includes('parsing_exception') || message.includes('query_shard_exception')) {
      return new SearchError(message, 'INVALID_QUERY', false, error);
    }

    // Default to system error
    return new SystemError(
      message || 'An unexpected error occurred',
      'INTERNAL_ERROR',
      error
    );
  }
}

/**
 * Graceful degradation utilities
 */
export class GracefulDegradation {
  /**
   * Execute operation with graceful degradation
   * Returns partial results even if some operations fail
   */
  static async executeWithDegradation<T>(
    operations: Array<() => Promise<T>>,
    context: string,
    minSuccessCount: number = 1
  ): Promise<{
    results: T[];
    errors: ProjectKBError[];
    success: boolean;
  }> {
    const results: T[] = [];
    const errors: ProjectKBError[] = [];

    await Promise.allSettled(
      operations.map(async (operation, index) => {
        try {
          const result = await operation();
          results.push(result);
        } catch (error) {
          const classifiedError = ErrorClassifier.classifyError(error, `${context}[${index}]`);
          errors.push(classifiedError);
          // SECURITY: Use secure logging with sanitized data
          log.warn('Operation failed', {
            operationIndex: index,
            context: sanitize.searchQuery(context).sanitized,
            errorCode: classifiedError.code,
            message: classifiedError.message
          });
        }
      })
    );

    const success = results.length >= minSuccessCount;

    if (!success && errors.length > 0) {
      // If we don't have enough successful results, throw the first error
      throw errors[0];
    }

    return { results, errors, success };
  }

  /**
   * Execute cross-project search with graceful degradation
   */
  static async executeCrossProjectSearch<T>(
    projectOperations: Array<{ projectId: string; operation: () => Promise<T[]> }>,
    context: string
  ): Promise<{
    results: T[];
    failedProjects: Array<{ projectId: string; error: ProjectKBError }>;
    successfulProjects: string[];
  }> {
    const allResults: T[] = [];
    const failedProjects: Array<{ projectId: string; error: ProjectKBError }> = [];
    const successfulProjects: string[] = [];

    await Promise.allSettled(
      projectOperations.map(async ({ projectId, operation }) => {
        try {
          const results = await operation();
          allResults.push(...results);
          successfulProjects.push(projectId);
        } catch (error) {
          const classifiedError = ErrorClassifier.classifyError(error, `${context}:${projectId}`);
          failedProjects.push({ projectId, error: classifiedError });
          // SECURITY: Use secure logging with sanitized data
          log.warn('Search failed for project', {
            projectId: sanitize.projectId(projectId),
            context: sanitize.searchQuery(context).sanitized,
            errorCode: classifiedError.code,
            message: classifiedError.message
          });
        }
      })
    );

    return {
      results: allResults,
      failedProjects,
      successfulProjects
    };
  }
}

/**
 * Error logging utility
 */
export class ErrorLogger {
  private static instance: ErrorLogger;
  
  private constructor() {}

  static getInstance(): ErrorLogger {
    if (!ErrorLogger.instance) {
      ErrorLogger.instance = new ErrorLogger();
    }
    return ErrorLogger.instance;
  }

  /**
   * Log error with appropriate level and context
   */
  logError(error: ProjectKBError, context?: string): void {
    const logData = {
      timestamp: error.timestamp.toISOString(),
      category: error.category,
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      context: context || 'unknown',
      details: error.details
    };

    // SECURITY: Use secure logging with sanitized data
    const sanitizedLogData = {
      timestamp: logData.timestamp,
      category: logData.category,
      code: logData.code,
      message: logData.message,
      retryable: logData.retryable,
      context: context ? sanitize.searchQuery(context).sanitized : 'unknown',
      // SECURITY: Sanitize details object to prevent log injection
      details: logData.details ? this.sanitizeLogDetails(logData.details) : undefined
    };

    // Log based on error severity
    if (error.category === ErrorCategory.SYSTEM || !error.retryable) {
      log.error('ProjectKB Error', sanitizedLogData);
    } else {
      log.warn('ProjectKB Warning', sanitizedLogData);
    }
  }

  /**
   * Log successful retry
   */
  logRetrySuccess(context: string, attempts: number): void {
    // SECURITY: Use secure logging with sanitized data
    log.info('Operation succeeded after retry', {
      attempts,
      context: sanitize.searchQuery(context).sanitized
    });
  }

  /**
   * Log retry failure
   */
  logRetryFailure(context: string, attempts: number, finalError: ProjectKBError): void {
    // SECURITY: Use secure logging with sanitized data
    log.error('Operation failed after retry attempts', {
      attempts,
      context: sanitize.searchQuery(context).sanitized,
      finalError: finalError.code,
      message: finalError.message
    });
  }

  /**
   * Sanitize log details object to prevent log injection
   */
  private sanitizeLogDetails(details: any): any {
    if (!details) return undefined;
    
    if (typeof details === 'string') {
      return sanitize.searchQuery(details).sanitized;
    }
    
    if (typeof details === 'object' && details !== null) {
      const sanitized: any = {};
      for (const [key, value] of Object.entries(details)) {
        if (typeof value === 'string') {
          sanitized[key] = sanitize.searchQuery(value).sanitized;
        } else if (typeof value === 'object' && value !== null) {
          sanitized[key] = this.sanitizeLogDetails(value);
        } else {
          sanitized[key] = value;
        }
      }
      return sanitized;
    }
    
    return details;
  }
}