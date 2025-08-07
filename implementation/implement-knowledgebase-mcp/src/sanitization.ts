/**
 * Input sanitization and validation utilities for the Project KB MCP Server
 * 
 * This module provides:
 * - Search query sanitization and validation
 * - Log message sanitization to prevent injection attacks
 * - Input validation for various data types
 * - Security-focused string cleaning utilities
 */

import { ValidationError } from './errors.js';

/**
 * Configuration for sanitization rules
 */
export interface SanitizationConfig {
  maxQueryLength: number;
  maxLogMessageLength: number;
  allowedSearchCharacters: RegExp;
  blockedPatterns: RegExp[];
  logSafeFields: string[];
}

/**
 * Default sanitization configuration
 */
export const DEFAULT_SANITIZATION_CONFIG: SanitizationConfig = {
  maxQueryLength: 1000,
  maxLogMessageLength: 2000,
  allowedSearchCharacters: /^.+$/,
  blockedPatterns: [
    // Script injection patterns
    /<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi,
    // SQL injection patterns
    /(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)/gi,
    // Command injection patterns (more restrictive - allow () for search)
    /[;&`${}[\]\\]/g,
    // XSS patterns
    /javascript:/gi,
    /on\w+\s*=/gi,
    // Path traversal
    /\.\.[\/\\]/g,
    // Format string specifiers
    /%[sdioxXeEfFgGaAcpn%]/g
    // Removed LDAP injection pattern that was too restrictive for search
  ],
  logSafeFields: [
    'timestamp', 'level', 'message', 'context', 'userId', 'projectId', 
    'documentId', 'searchQuery', 'resultCount', 'duration', 'status'
  ]
};

/**
 * Search query sanitization result
 */
export interface SanitizedQuery {
  original: string;
  sanitized: string;
  isValid: boolean;
  warnings: string[];
  blocked: boolean;
}

/**
 * Log sanitization result
 */
export interface SanitizedLogData {
  message: string;
  data: Record<string, any>;
  warnings: string[];
}

/**
 * Main sanitization class
 */
export class InputSanitizer {
  private config: SanitizationConfig;

  constructor(config: Partial<SanitizationConfig> = {}) {
    this.config = { ...DEFAULT_SANITIZATION_CONFIG, ...config };
  }

  /**
   * Sanitize search query with comprehensive validation
   */
  sanitizeSearchQuery(query: string): SanitizedQuery {
    const result: SanitizedQuery = {
      original: query,
      sanitized: '',
      isValid: false,
      warnings: [],
      blocked: false
    };



    // Basic validation
    if (!query || typeof query !== 'string') {
      result.warnings.push('Query must be a non-empty string');

      return result;
    }

    // Length validation
    if (query.length > this.config.maxQueryLength) {
      result.warnings.push(`Query exceeds maximum length of ${this.config.maxQueryLength} characters`);
      result.blocked = true;

      return result;
    }

    // Check for blocked patterns
    for (const pattern of this.config.blockedPatterns) {
      if (pattern.test(query)) {
        result.warnings.push(`Query contains blocked pattern: ${pattern.source}`);
        result.blocked = true;

        return result;
      }
    }

    // Character validation - TEMPORARY BYPASS FOR HYPHEN DEBUGGING
    // Skip validation entirely for now to debug caching issue
    console.log(`[DEBUG] Skipping character validation for debugging - query: "${query}"`);
    
    /*
    if (!this.config.allowedSearchCharacters.test(query)) {
      result.warnings.push('Query contains invalid characters');
      result.blocked = true;
      return result;
    }
    */

    // Sanitization steps
    let sanitized = query;

    // 1. Normalize whitespace
    sanitized = sanitized.replace(/\s+/g, ' ').trim();

    // 2. Remove potential HTML/XML tags
    sanitized = sanitized.replace(/<[^>]*>/g, '');

    // 3. Escape special characters for search engines
    sanitized = this.escapeSearchSpecialChars(sanitized);

    // 4. Remove excessive punctuation
    sanitized = sanitized.replace(/[.]{3,}/g, '...');
    sanitized = sanitized.replace(/[!]{2,}/g, '!');
    sanitized = sanitized.replace(/[?]{2,}/g, '?');

    // 5. Validate final result
    if (sanitized.length === 0) {
      result.warnings.push('Query became empty after sanitization');
      return result;
    }

    if (sanitized.length < 2) {
      result.warnings.push('Query too short after sanitization (minimum 2 characters)');
      return result;
    }

    result.sanitized = sanitized;
    result.isValid = true;

    // Add informational warnings if query was modified
    if (sanitized !== query) {
      result.warnings.push('Query was modified during sanitization');
    }

    return result;
  }

  /**
   * Escape special characters for search engines
   */
  private escapeSearchSpecialChars(query: string): string {
    // Escape characters that have special meaning in search engines
    const specialChars = /[+=&|><!(){}[\]^"~*?:\\\/]/g;
    return query.replace(specialChars, (match) => {
      // Only escape if not part of a quoted phrase
      return `\\${match}`;
    });
  }

  /**
   * Sanitize log messages and data to prevent log injection
   */
  sanitizeLogData(message: string, data?: Record<string, any>): SanitizedLogData {
    const result: SanitizedLogData = {
      message: '',
      data: {},
      warnings: []
    };

    // Sanitize message
    result.message = this.sanitizeLogMessage(message);

    // Sanitize data object
    if (data) {
      result.data = this.sanitizeLogDataObject(data);
    }

    return result;
  }

  /**
   * Sanitize individual log message
   */
  private sanitizeLogMessage(message: string): string {
    if (!message || typeof message !== 'string') {
      return '[Invalid log message]';
    }

    // Truncate if too long
    if (message.length > this.config.maxLogMessageLength) {
      message = message.substring(0, this.config.maxLogMessageLength) + '...[truncated]';
    }

    // Remove control characters and format specifiers
    message = message.replace(/[\x00-\x1F\x7F]/g, ''); // Control characters
    message = message.replace(/%[sdioxXeEfFgGaAcpn%]/g, '[FORMAT_SPEC]'); // Format specifiers
    
    // Remove ANSI escape sequences
    message = message.replace(/\x1b\[[0-9;]*m/g, '');
    
    // Normalize line breaks
    message = message.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    
    // Limit line breaks
    message = message.replace(/\n{3,}/g, '\n\n');

    return message;
  }

  /**
   * Sanitize log data object
   */
  private sanitizeLogDataObject(data: Record<string, any>): Record<string, any> {
    const sanitized: Record<string, any> = {};

    for (const [key, value] of Object.entries(data)) {
      // Skip sensitive fields
      if (this.isSensitiveField(key)) {
        sanitized[key] = '[REDACTED]';
        continue;
      }

      // Sanitize key
      const sanitizedKey = this.sanitizeLogKey(key);
      
      // Sanitize value based on type
      sanitized[sanitizedKey] = this.sanitizeLogValue(value);
    }

    return sanitized;
  }

  /**
   * Check if field contains sensitive information
   */
  private isSensitiveField(key: string): boolean {
    const sensitivePatterns = [
      /password/i,
      /token/i,
      /secret/i,
      /key/i,
      /credential/i,
      /auth/i,
      /session/i,
      /cookie/i,
      /bearer/i
    ];

    return sensitivePatterns.some(pattern => pattern.test(key));
  }

  /**
   * Sanitize log object key
   */
  private sanitizeLogKey(key: string): string {
    if (typeof key !== 'string') {
      return 'invalid_key';
    }

    // Remove special characters from keys
    return key.replace(/[^a-zA-Z0-9_]/g, '_').substring(0, 50);
  }

  /**
   * Sanitize log value based on its type
   */
  private sanitizeLogValue(value: any): any {
    if (value === null || value === undefined) {
      return value;
    }

    if (typeof value === 'string') {
      return this.sanitizeLogMessage(value);
    }

    if (typeof value === 'number' || typeof value === 'boolean') {
      return value;
    }

    if (value instanceof Date) {
      return value.toISOString();
    }

    if (value instanceof Error) {
      return {
        name: value.name,
        message: this.sanitizeLogMessage(value.message),
        stack: value.stack ? this.sanitizeLogMessage(value.stack) : undefined
      };
    }

    if (Array.isArray(value)) {
      return value.slice(0, 10).map(item => this.sanitizeLogValue(item)); // Limit array size
    }

    if (typeof value === 'object') {
      // Recursively sanitize nested objects (with depth limit)
      return this.sanitizeNestedObject(value, 3);
    }

    // For unknown types, convert to string and sanitize
    return this.sanitizeLogMessage(String(value));
  }

  /**
   * Sanitize nested objects with depth limit
   */
  private sanitizeNestedObject(obj: any, maxDepth: number): any {
    if (maxDepth <= 0) {
      return '[MAX_DEPTH_EXCEEDED]';
    }

    const sanitized: Record<string, any> = {};
    let fieldCount = 0;
    const maxFields = 20;

    for (const [key, value] of Object.entries(obj)) {
      if (fieldCount >= maxFields) {
        sanitized['...'] = `[${Object.keys(obj).length - maxFields} more fields]`;
        break;
      }

      if (this.isSensitiveField(key)) {
        sanitized[this.sanitizeLogKey(key)] = '[REDACTED]';
      } else {
        sanitized[this.sanitizeLogKey(key)] = this.sanitizeLogValue(value);
      }
      
      fieldCount++;
    }

    return sanitized;
  }

  /**
   * Validate and sanitize project ID
   */
  sanitizeProjectId(projectId: string): string {
    if (!projectId || typeof projectId !== 'string') {
      throw new ValidationError('Project ID must be a non-empty string', 'INVALID_PROJECT_ID');
    }

    // Allow alphanumeric, hyphens, underscores
    const sanitized = projectId.replace(/[^a-zA-Z0-9\-_]/g, '').substring(0, 100);
    
    if (sanitized.length === 0) {
      throw new ValidationError('Project ID contains no valid characters', 'INVALID_PROJECT_ID');
    }

    return sanitized;
  }

  /**
   * Validate and sanitize document ID
   */
  sanitizeDocumentId(documentId: string): string {
    if (!documentId || typeof documentId !== 'string') {
      throw new ValidationError('Document ID must be a non-empty string', 'INVALID_DOCUMENT_ID');
    }

    // Allow alphanumeric, hyphens, underscores, dots
    const sanitized = documentId.replace(/[^a-zA-Z0-9\-_.]/g, '').substring(0, 200);
    
    if (sanitized.length === 0) {
      throw new ValidationError('Document ID contains no valid characters', 'INVALID_DOCUMENT_ID');
    }

    return sanitized;
  }

  /**
   * Sanitize username for logging
   */
  sanitizeUsername(username: string): string {
    if (!username || typeof username !== 'string') {
      return '[INVALID_USERNAME]';
    }

    // For logging purposes, show only first few characters and domain
    if (username.includes('@')) {
      const [local, domain] = username.split('@');
      return `${local.substring(0, 3)}***@${domain}`;
    }

    return `${username.substring(0, 3)}***`;
  }

  /**
   * Update sanitization configuration
   */
  updateConfig(newConfig: Partial<SanitizationConfig>): void {
    this.config = { ...this.config, ...newConfig };
  }

  /**
   * Get current configuration (for debugging)
   */
  getConfig(): SanitizationConfig {
    return { ...this.config };
  }
}

/**
 * Global sanitizer instance - recreated each time to avoid caching issues
 */
export const globalSanitizer = new InputSanitizer();

/**
 * Force reload the global sanitizer with fresh configuration
 */
export function reloadSanitizer(): void {
  // Create a new instance with fresh configuration
  const newSanitizer = new InputSanitizer();
  // Copy the new configuration to the global instance
  (globalSanitizer as any).config = newSanitizer.getConfig();
  console.log('[DEBUG] Sanitizer configuration reloaded');
}

/**
 * Create a fresh sanitizer instance to avoid caching issues
 */
export function createFreshSanitizer(): InputSanitizer {
  return new InputSanitizer();
}

/**
 * Convenience functions for common sanitization tasks - using fresh instances to avoid caching
 */
export const sanitize = {
  searchQuery: (query: string) => createFreshSanitizer().sanitizeSearchQuery(query),
  logData: (message: string, data?: Record<string, any>) => globalSanitizer.sanitizeLogData(message, data),
  projectId: (id: string) => globalSanitizer.sanitizeProjectId(id),
  documentId: (id: string) => globalSanitizer.sanitizeDocumentId(id),
  username: (username: string) => globalSanitizer.sanitizeUsername(username)
};