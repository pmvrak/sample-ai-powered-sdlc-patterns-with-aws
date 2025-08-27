import winston from 'winston';

// Performance metrics interface
export interface PerformanceMetrics {
  operation: string;
  duration: number;
  success: boolean;
  projectId?: string;
  resultCount?: number;
  errorCode?: string;
  timestamp: Date;
}

// Audit event interface
export interface AuditEvent {
  event: string;
  userId?: string;
  projectId?: string;
  resource?: string;
  action: string;
  success: boolean;
  timestamp: Date;
  details?: Record<string, any>;
}

// Logger configuration
const logLevel = process.env.LOG_LEVEL || 'info';
const logFormat = process.env.LOG_FORMAT || 'json';

// Create winston logger instance with fallback for testing
let logger: winston.Logger;

try {
  logger = winston.createLogger({
    level: logLevel,
    format: winston.format.combine(
      winston.format.timestamp(),
      winston.format.errors({ stack: true }),
      logFormat === 'json' 
        ? winston.format.json()
        : winston.format.combine(
            winston.format.colorize(),
            winston.format.simple()
          )
    ),
    defaultMeta: { service: 'project-kb-mcp-server' },
    transports: [
      new winston.transports.Console({
        handleExceptions: true,
        handleRejections: true
      })
    ]
  });
} catch (error) {
  // Fallback for testing environment
  logger = {
    info: () => {},
    debug: () => {},
    warn: () => {},
    error: () => {}
  } as any;
}

// Performance metrics collection
class PerformanceCollector {
  private metrics: PerformanceMetrics[] = [];
  private readonly maxMetrics = 1000; // Keep last 1000 metrics in memory

  recordMetric(metric: PerformanceMetrics): void {
    this.metrics.push(metric);
    
    // Keep only the most recent metrics
    if (this.metrics.length > this.maxMetrics) {
      this.metrics = this.metrics.slice(-this.maxMetrics);
    }

    // Log the performance metric
    logger.info('Performance metric recorded', {
      type: 'performance',
      ...metric
    });
  }

  getMetrics(operation?: string): PerformanceMetrics[] {
    if (operation) {
      return this.metrics.filter(m => m.operation === operation);
    }
    return [...this.metrics];
  }

  getAverageResponseTime(operation: string): number {
    const operationMetrics = this.getMetrics(operation);
    if (operationMetrics.length === 0) return 0;
    
    const total = operationMetrics.reduce((sum, metric) => sum + metric.duration, 0);
    return total / operationMetrics.length;
  }

  getSuccessRate(operation: string): number {
    const operationMetrics = this.getMetrics(operation);
    if (operationMetrics.length === 0) return 0;
    
    const successful = operationMetrics.filter(m => m.success).length;
    return successful / operationMetrics.length;
  }
}

// Audit logger
class AuditLogger {
  private events: AuditEvent[] = [];
  private readonly maxEvents = 1000; // Keep last 1000 events in memory

  logEvent(event: AuditEvent): void {
    this.events.push(event);
    
    // Keep only the most recent events
    if (this.events.length > this.maxEvents) {
      this.events = this.events.slice(-this.maxEvents);
    }

    // Log the audit event
    logger.info('Audit event logged', {
      type: 'audit',
      ...event
    });
  }

  getEvents(eventType?: string): AuditEvent[] {
    if (eventType) {
      return this.events.filter(e => e.event === eventType);
    }
    return [...this.events];
  }
}

// Create singleton instances
export const performanceCollector = new PerformanceCollector();
export const auditLogger = new AuditLogger();

// Utility function to measure operation performance
export async function measurePerformance<T>(
  operation: string,
  fn: () => Promise<T>,
  context?: { projectId?: string; userId?: string }
): Promise<T> {
  const startTime = Date.now();
  const timestamp = new Date();
  let success = true;
  let errorCode: string | undefined;
  let resultCount: number | undefined;

  try {
    logger.debug(`Starting operation: ${operation}`, { operation, ...context });
    
    const result = await fn();
    
    // Try to extract result count if result is an array
    if (Array.isArray(result)) {
      resultCount = result.length;
    }
    
    logger.debug(`Completed operation: ${operation}`, { 
      operation, 
      duration: Date.now() - startTime,
      resultCount,
      ...context 
    });
    
    return result;
  } catch (error) {
    success = false;
    errorCode = error instanceof Error ? error.constructor.name : 'UnknownError';
    
    logger.error(`Failed operation: ${operation}`, {
      operation,
      error: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
      duration: Date.now() - startTime,
      ...context
    });
    
    throw error;
  } finally {
    const duration = Date.now() - startTime;
    
    performanceCollector.recordMetric({
      operation,
      duration,
      success,
      projectId: context?.projectId,
      resultCount,
      errorCode,
      timestamp
    });
  }
}

// Utility function to log audit events
export function logAuditEvent(
  event: string,
  action: string,
  success: boolean,
  context?: {
    userId?: string;
    projectId?: string;
    resource?: string;
    details?: Record<string, any>;
  }
): void {
  auditLogger.logEvent({
    event,
    action,
    success,
    timestamp: new Date(),
    ...context
  });
}

// Export the main logger
export { logger };
export default logger;