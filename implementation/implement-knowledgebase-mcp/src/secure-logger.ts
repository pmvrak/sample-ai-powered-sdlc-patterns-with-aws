/**
 * Secure logging utility with built-in sanitization
 * 
 * This module provides:
 * - Sanitized logging to prevent injection attacks
 * - Structured logging with consistent format
 * - Security-aware log level management
 * - Performance monitoring integration
 * - Audit trail capabilities
 */

import { globalSanitizer } from './sanitization.js';

/**
 * Log levels with security considerations
 */
export enum LogLevel {
  ERROR = 0,
  WARN = 1,
  INFO = 2,
  DEBUG = 3,
  TRACE = 4
}

/**
 * Security-focused log entry structure
 */
export interface SecureLogEntry {
  timestamp: string;
  level: string;
  message: string;
  context?: string;
  userId?: string;
  sessionId?: string;
  requestId?: string;
  data?: Record<string, any>;
  duration?: number;
  success?: boolean;
}

/**
 * Audit event types for security monitoring
 */
export enum AuditEventType {
  AUTHENTICATION = 'authentication',
  AUTHORIZATION = 'authorization',
  DATA_ACCESS = 'data_access',
  CONFIGURATION_CHANGE = 'configuration_change',
  SECURITY_VIOLATION = 'security_violation',
  SYSTEM_EVENT = 'system_event'
}

/**
 * Audit log entry structure
 */
export interface AuditLogEntry extends SecureLogEntry {
  eventType: AuditEventType;
  resource?: string;
  action?: string;
  outcome: 'success' | 'failure' | 'partial';
  riskLevel: 'low' | 'medium' | 'high' | 'critical';
  clientInfo?: {
    userAgent?: string;
    ipAddress?: string;
    location?: string;
  };
}

/**
 * Performance measurement context
 */
export interface PerformanceContext {
  operation: string;
  startTime: number;
  metadata?: Record<string, any>;
}

/**
 * Secure logger class with sanitization
 */
export class SecureLogger {
  private currentLogLevel: LogLevel;
  private performanceContexts: Map<string, PerformanceContext> = new Map();

  constructor(logLevel: LogLevel = LogLevel.INFO) {
    this.currentLogLevel = logLevel;
  }

  /**
   * Log error with sanitization
   */
  error(message: string, data?: Record<string, any>, context?: string): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      this.writeLog(LogLevel.ERROR, message, data, context);
    }
  }

  /**
   * Log warning with sanitization
   */
  warn(message: string, data?: Record<string, any>, context?: string): void {
    if (this.shouldLog(LogLevel.WARN)) {
      this.writeLog(LogLevel.WARN, message, data, context);
    }
  }

  /**
   * Log info with sanitization
   */
  info(message: string, data?: Record<string, any>, context?: string): void {
    if (this.shouldLog(LogLevel.INFO)) {
      this.writeLog(LogLevel.INFO, message, data, context);
    }
  }

  /**
   * Log debug with sanitization (only in development)
   */
  debug(message: string, data?: Record<string, any>, context?: string): void {
    if (this.shouldLog(LogLevel.DEBUG) && process.env.NODE_ENV !== 'production') {
      this.writeLog(LogLevel.DEBUG, message, data, context);
    }
  }

  /**
   * Log trace with sanitization (only in development)
   */
  trace(message: string, data?: Record<string, any>, context?: string): void {
    if (this.shouldLog(LogLevel.TRACE) && process.env.NODE_ENV !== 'production') {
      this.writeLog(LogLevel.TRACE, message, data, context);
    }
  }

  /**
   * Log security audit event
   */
  audit(
    eventType: AuditEventType,
    action: string,
    outcome: 'success' | 'failure' | 'partial',
    riskLevel: 'low' | 'medium' | 'high' | 'critical',
    details?: {
      userId?: string;
      resource?: string;
      message?: string;
      data?: Record<string, any>;
      clientInfo?: AuditLogEntry['clientInfo'];
    }
  ): void {
    const auditEntry: AuditLogEntry = {
      timestamp: new Date().toISOString(),
      level: 'AUDIT',
      message: details?.message || `${eventType} ${action}`,
      eventType,
      action,
      outcome,
      riskLevel,
      userId: details?.userId,
      resource: details?.resource,
      clientInfo: details?.clientInfo,
      success: outcome === 'success'
    };

    // Sanitize audit data
    if (details?.data) {
      const sanitized = globalSanitizer.sanitizeLogData(auditEntry.message, details.data);
      auditEntry.data = sanitized.data;
    }

    // Always log audit events regardless of log level
    this.writeAuditLog(auditEntry);
  }

  /**
   * Start performance measurement
   */
  startPerformanceMeasurement(operation: string, metadata?: Record<string, any>): string {
    const measurementId = `${operation}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    
    this.performanceContexts.set(measurementId, {
      operation,
      startTime: performance.now(),
      metadata
    });

    return measurementId;
  }

  /**
   * End performance measurement and log result
   */
  endPerformanceMeasurement(measurementId: string, additionalData?: Record<string, any>): number {
    const context = this.performanceContexts.get(measurementId);
    if (!context) {
      this.warn('Performance measurement context not found', { measurementId });
      return 0;
    }

    const duration = performance.now() - context.startTime;
    this.performanceContexts.delete(measurementId);

    // Log performance data
    this.info('Performance measurement completed', {
      operation: context.operation,
      duration: Math.round(duration * 100) / 100, // Round to 2 decimal places
      metadata: context.metadata,
      ...additionalData
    }, 'performance');

    return duration;
  }

  /**
   * Convenience method for measuring async operations
   */
  async measurePerformance<T>(
    operation: string,
    asyncOperation: () => Promise<T>,
    metadata?: Record<string, any>
  ): Promise<T> {
    const measurementId = this.startPerformanceMeasurement(operation, metadata);
    
    try {
      const result = await asyncOperation();
      this.endPerformanceMeasurement(measurementId, { success: true });
      return result;
    } catch (error) {
      this.endPerformanceMeasurement(measurementId, { 
        success: false, 
        error: error instanceof Error ? error.message : String(error)
      });
      throw error;
    }
  }

  /**
   * Log authentication events with security context
   */
  logAuthEvent(
    action: 'login' | 'logout' | 'token_refresh' | 'token_expired',
    success: boolean,
    details: {
      userId?: string;
      reason?: string;
      clientInfo?: AuditLogEntry['clientInfo'];
      metadata?: Record<string, any>;
    }
  ): void {
    this.audit(
      AuditEventType.AUTHENTICATION,
      action,
      success ? 'success' : 'failure',
      success ? 'low' : 'medium',
      {
        userId: details.userId,
        message: `Authentication ${action} ${success ? 'succeeded' : 'failed'}`,
        data: {
          reason: details.reason,
          ...details.metadata
        },
        clientInfo: details.clientInfo
      }
    );
  }

  /**
   * Log data access events
   */
  logDataAccess(
    action: 'search' | 'retrieve' | 'list',
    resource: string,
    success: boolean,
    details: {
      userId?: string;
      query?: string;
      resultCount?: number;
      duration?: number;
      documentId?: string;
      projectId?: string;
      originalQuery?: string;
      metadata?: Record<string, any>;
    }
  ): void {
    this.audit(
      AuditEventType.DATA_ACCESS,
      action,
      success ? 'success' : 'failure',
      'low',
      {
        userId: details.userId,
        resource,
        message: `Data access ${action} on ${resource}`,
        data: {
          query: details.query,
          resultCount: details.resultCount,
          duration: details.duration,
          documentId: details.documentId,
          projectId: details.projectId,
          originalQuery: details.originalQuery,
          ...details.metadata
        }
      }
    );
  }

  /**
   * Log security violations
   */
  logSecurityViolation(
    violation: string,
    details: {
      userId?: string;
      resource?: string;
      clientInfo?: AuditLogEntry['clientInfo'];
      metadata?: Record<string, any>;
    }
  ): void {
    this.audit(
      AuditEventType.SECURITY_VIOLATION,
      violation,
      'failure',
      'high',
      {
        userId: details.userId,
        resource: details.resource,
        message: `Security violation: ${violation}`,
        data: details.metadata,
        clientInfo: details.clientInfo
      }
    );
  }

  /**
   * Set log level
   */
  setLogLevel(level: LogLevel): void {
    this.currentLogLevel = level;
    this.info('Log level changed', { newLevel: LogLevel[level] }, 'configuration');
  }

  /**
   * Get current log level
   */
  getLogLevel(): LogLevel {
    return this.currentLogLevel;
  }

  /**
   * Check if should log at given level
   */
  private shouldLog(level: LogLevel): boolean {
    return level <= this.currentLogLevel;
  }

  /**
   * Write sanitized log entry
   */
  private writeLog(level: LogLevel, message: string, data?: Record<string, any>, context?: string): void {
    // Sanitize all log data
    const sanitized = globalSanitizer.sanitizeLogData(message, data);
    
    const logEntry: SecureLogEntry = {
      timestamp: new Date().toISOString(),
      level: LogLevel[level],
      message: sanitized.message,
      context,
      data: Object.keys(sanitized.data).length > 0 ? sanitized.data : undefined
    };

    // Output to console with proper formatting
    const logOutput = this.formatLogEntry(logEntry);
    
    // SECURITY: Additional sanitization for console output to prevent log injection
    const sanitizedOutput = this.sanitizeConsoleOutput(logOutput);
    
    switch (level) {
      case LogLevel.ERROR:
        console.error(sanitizedOutput);
        break;
      case LogLevel.WARN:
        console.warn(sanitizedOutput);
        break;
      default:
        console.log(sanitizedOutput);
        break;
    }

    // In production, you might want to send logs to a centralized logging service
    if (process.env.NODE_ENV === 'production') {
      this.sendToLogService(logEntry);
    }
  }

  /**
   * Write audit log entry
   */
  private writeAuditLog(auditEntry: AuditLogEntry): void {
    const logOutput = this.formatAuditEntry(auditEntry);
    
    // Always output audit logs to console
    // SECURITY: Additional sanitization for console output to prevent log injection
    const sanitizedOutput = this.sanitizeConsoleOutput(logOutput);
    console.log(`[AUDIT] ${sanitizedOutput}`);
    
    // In production, send to security monitoring service
    if (process.env.NODE_ENV === 'production') {
      this.sendToSecurityService(auditEntry);
    }
  }

  /**
   * Format log entry for output
   */
  private formatLogEntry(entry: SecureLogEntry): string {
    const parts = [
      entry.timestamp,
      `[${entry.level}]`,
      entry.context ? `[${entry.context}]` : '',
      entry.message
    ].filter(Boolean);

    let formatted = parts.join(' ');

    if (entry.data && Object.keys(entry.data).length > 0) {
      formatted += ` ${JSON.stringify(entry.data)}`;
    }

    return formatted;
  }

  /**
   * Format audit entry for output
   */
  private formatAuditEntry(entry: AuditLogEntry): string {
    const parts = [
      entry.timestamp,
      `[${entry.eventType.toUpperCase()}]`,
      `[${entry.riskLevel.toUpperCase()}]`,
      `[${entry.outcome.toUpperCase()}]`,
      entry.action,
      entry.resource ? `on ${entry.resource}` : '',
      entry.userId ? `by ${globalSanitizer.sanitizeUsername(entry.userId)}` : ''
    ].filter(Boolean);

    let formatted = parts.join(' ');

    if (entry.data && Object.keys(entry.data).length > 0) {
      formatted += ` ${JSON.stringify(entry.data)}`;
    }

    return formatted;
  }

  /**
   * Sanitize console output to prevent log injection attacks
   * This provides an additional layer of protection even for the secure logger
   */
  private sanitizeConsoleOutput(output: string): string {
    if (!output) return '';
    
    // Remove or escape characters that could be used for log injection
    return output
      // Remove ANSI escape sequences that could manipulate terminal output
      .replace(/\x1b\[[0-9;]*m/g, '')
      // Remove carriage returns and line feeds that could create fake log entries
      .replace(/[\r\n]/g, ' ')
      // Remove null bytes and other control characters
      .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '')
      // Limit length to prevent log flooding
      .substring(0, 2000)
      // Escape any remaining potentially dangerous characters
      .replace(/[<>&"']/g, (match) => {
        const escapes: { [key: string]: string } = {
          '<': '&lt;',
          '>': '&gt;',
          '&': '&amp;',
          '"': '&quot;',
          "'": '&#x27;'
        };
        return escapes[match] || match;
      });
  }

  /**
   * Send logs to centralized logging service (placeholder)
   */
  private sendToLogService(entry: SecureLogEntry): void {
    // Implement integration with your logging service (e.g., CloudWatch, ELK, etc.)
    // This is a placeholder for production logging integration
  }

  /**
   * Send audit logs to security monitoring service (placeholder)
   */
  private sendToSecurityService(entry: AuditLogEntry): void {
    // Implement integration with your security monitoring service
    // This is a placeholder for security monitoring integration
  }
}

/**
 * Global secure logger instance
 */
export const secureLogger = new SecureLogger(
  process.env.NODE_ENV === 'production' ? LogLevel.INFO : LogLevel.DEBUG
);

/**
 * Convenience functions for common logging patterns
 */
export const log = {
  error: (message: string, data?: Record<string, any>, context?: string) => 
    secureLogger.error(message, data, context),
  
  warn: (message: string, data?: Record<string, any>, context?: string) => 
    secureLogger.warn(message, data, context),
  
  info: (message: string, data?: Record<string, any>, context?: string) => 
    secureLogger.info(message, data, context),
  
  debug: (message: string, data?: Record<string, any>, context?: string) => 
    secureLogger.debug(message, data, context),
  
  audit: secureLogger.audit.bind(secureLogger),
  
  auth: secureLogger.logAuthEvent.bind(secureLogger),
  
  dataAccess: secureLogger.logDataAccess.bind(secureLogger),
  
  securityViolation: secureLogger.logSecurityViolation.bind(secureLogger),
  
  measurePerformance: secureLogger.measurePerformance.bind(secureLogger)
};