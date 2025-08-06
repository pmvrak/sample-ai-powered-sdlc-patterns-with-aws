import { JSONSchema7 } from 'json-schema';
import Ajv from 'ajv';
import { MCPTool, MCPToolResult, MCPToolError, MCPToolContext } from './MCPTool';
import { logger } from '../utils/logger';

/**
 * Abstract base class for MCP tools providing common functionality
 */
export abstract class BaseMCPTool implements MCPTool {
  public abstract readonly name: string;
  public abstract readonly description: string;
  public abstract readonly inputSchema: JSONSchema7;

  private ajv: Ajv;

  constructor() {
    this.ajv = new Ajv({ allErrors: false });
  }

  /**
   * Abstract method that must be implemented by concrete tool classes
   */
  public abstract execute(args: any, context?: MCPToolContext): Promise<MCPToolResult>;

  /**
   * Validate input arguments against the tool's JSON schema
   */
  public validateInput(args: any): boolean {
    const validate = this.ajv.compile(this.inputSchema as any);
    const valid = validate(args);
    
    if (!valid) {
      const errors = validate.errors?.map(err => 
        `${err.instancePath} ${err.message}`
      ).join(', ') || 'Unknown validation error';
      
      throw this.createToolError(
        -32602, 
        `Invalid parameters for tool ${this.name}: ${errors}`,
        { validationErrors: validate.errors }
      );
    }
    
    return true;
  }

  /**
   * Execute the tool with validation and error handling
   */
  public async executeWithValidation(args: any, context?: MCPToolContext): Promise<MCPToolResult> {
    const executionContext: MCPToolContext = {
      timestamp: new Date(),
      ...context
    };

    logger.info(`Executing tool: ${this.name}`, { 
      args: this.sanitizeArgsForLogging(args),
      context: executionContext 
    });

    try {
      // Validate input
      this.validateInput(args);
      
      // Execute the tool
      const result = await this.execute(args, executionContext);
      
      logger.info(`Tool execution completed: ${this.name}`, { 
        resultType: result.content?.[0]?.type,
        isError: result.isError 
      });
      
      return result;
    } catch (error) {
      logger.error(`Tool execution failed: ${this.name}`, { 
        error: error instanceof Error ? error.message : error,
        args: this.sanitizeArgsForLogging(args)
      });
      
      if (error instanceof MCPToolError) {
        throw error;
      }
      
      throw this.createToolError(
        -32603,
        `Internal error in tool ${this.name}: ${error instanceof Error ? error.message : 'Unknown error'}`,
        { originalError: error }
      );
    }
  }

  /**
   * Create a standardized MCP tool error
   */
  protected createToolError(code: number, message: string, data?: any): MCPToolError {
    return new MCPToolError(message, code, data);
  }

  /**
   * Create a successful text result
   */
  protected createTextResult(text: string): MCPToolResult {
    return {
      content: [
        {
          type: 'text',
          text
        }
      ]
    };
  }

  /**
   * Create an error result
   */
  protected createErrorResult(message: string): MCPToolResult {
    return {
      content: [
        {
          type: 'text',
          text: message
        }
      ],
      isError: true
    };
  }

  /**
   * Sanitize arguments for logging (remove sensitive data)
   */
  private sanitizeArgsForLogging(args: any): any {
    if (!args || typeof args !== 'object') {
      return args;
    }

    const sanitized = { ...args };
    
    // Remove common sensitive fields
    const sensitiveFields = ['password', 'token', 'secret', 'key', 'auth'];
    
    for (const field of sensitiveFields) {
      if (field in sanitized) {
        sanitized[field] = '[REDACTED]';
      }
    }
    
    return sanitized;
  }
}