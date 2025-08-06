import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { Transport } from '@modelcontextprotocol/sdk/shared/transport.js';
import { 
  CallToolRequestSchema, 
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';
import { logger } from '../utils/logger';
import { EnvironmentConfig } from '../config/environment';
import { MCPToolRegistry } from './MCPToolRegistry';
import { MCPTool } from '../interfaces/MCPTool';

export interface MCPServerOptions {
  name: string;
  version: string;
  capabilities?: {
    tools?: any;
    resources?: any;
    prompts?: any;
  };
}

export class MCPServer {
  private server: Server;
  private config: EnvironmentConfig;
  private transport: Transport | null = null;
  private isInitialized: boolean = false;
  private isShuttingDown: boolean = false;
  private connectionCount: number = 0;
  private toolRegistry: MCPToolRegistry;

  constructor(config: EnvironmentConfig, options?: Partial<MCPServerOptions>) {
    this.config = config;
    
    const serverOptions: MCPServerOptions = {
      name: options?.name || 'openapi-mcp-server',
      version: options?.version || '1.0.0',
      capabilities: options?.capabilities || {
        tools: {},
        resources: {},
        prompts: {},
      }
    };

    this.server = new Server(
      {
        name: serverOptions.name,
        version: serverOptions.version,
      },
      {
        capabilities: {
          tools: {},
          resources: {},
          prompts: {},
        },
      }
    );

    // Initialize tool registry
    this.toolRegistry = new MCPToolRegistry();

    // Set up connection lifecycle handlers
    this.setupConnectionHandlers();
  }

  async initialize(): Promise<void> {
    if (this.isInitialized) {
      logger.warn('MCP Server already initialized');
      return;
    }

    if (this.isShuttingDown) {
      throw new Error('Cannot initialize server during shutdown');
    }

    logger.info('Initializing MCP Server...', { 
      environment: this.config.NODE_ENV,
      mcpPort: this.config.MCP_PORT 
    });
    
    try {
      // Set up request handlers
      this.setupToolHandlers();
      
      // Create and connect to transport
      this.transport = new StdioServerTransport();
      await this.handleConnection(this.transport);
      
      this.isInitialized = true;
      logger.info('MCP Server initialized successfully');
    } catch (error) {
      logger.error('Failed to initialize MCP Server', error);
      await this.cleanup();
      throw error;
    }
  }

  async handleConnection(transport: Transport): Promise<void> {
    if (this.isShuttingDown) {
      throw new Error('Server is shutting down, cannot accept new connections');
    }

    this.connectionCount++;
    const connectionId = this.connectionCount;
    
    logger.info(`Handling new MCP connection`, { connectionId });

    try {
      // Set up transport event handlers
      transport.onclose = () => {
        logger.info(`MCP connection closed`, { connectionId });
        this.connectionCount = Math.max(0, this.connectionCount - 1);
      };

      transport.onerror = (error) => {
        logger.error(`MCP transport error`, { connectionId, error });
      };

      // Connect the server to the transport
      await this.server.connect(transport);
      
      logger.info(`MCP connection established successfully`, { connectionId });
    } catch (error) {
      logger.error(`Failed to establish MCP connection`, { connectionId, error });
      this.connectionCount = Math.max(0, this.connectionCount - 1);
      throw error;
    }
  }

  private setupConnectionHandlers(): void {
    // Set up server-level connection event handlers
    logger.debug('Setting up connection lifecycle handlers');
    
    // Handle server errors
    process.on('uncaughtException', (error) => {
      logger.error('Uncaught exception in MCP Server', error);
      this.shutdown().catch((shutdownError) => {
        logger.error('Error during emergency shutdown', shutdownError);
      });
    });

    process.on('unhandledRejection', (reason, promise) => {
      logger.error('Unhandled rejection in MCP Server', { reason, promise });
    });

    // Handle graceful shutdown signals
    process.on('SIGTERM', () => {
      logger.info('Received SIGTERM, initiating graceful shutdown');
      this.shutdown().catch((error) => {
        logger.error('Error during SIGTERM shutdown', error);
        process.exit(1);
      });
    });

    process.on('SIGINT', () => {
      logger.info('Received SIGINT, initiating graceful shutdown');
      this.shutdown().catch((error) => {
        logger.error('Error during SIGINT shutdown', error);
        process.exit(1);
      });
    });
  }

  getConnectionCount(): number {
    return this.connectionCount;
  }

  isServerInitialized(): boolean {
    return this.isInitialized;
  }

  isServerShuttingDown(): boolean {
    return this.isShuttingDown;
  }

  private setupToolHandlers(): void {
    // List tools handler - returns all registered tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      const tools = this.toolRegistry.getToolsForMCP();
      logger.debug(`Listing ${tools.length} registered tools`);
      return { tools };
    });

    // Call tool handler - executes tools through the registry
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;
      
      logger.info(`Executing tool via registry: ${name}`, { 
        args: this.sanitizeArgsForLogging(args) 
      });
      
      try {
        // Create execution context
        const context = {
          requestId: this.generateRequestId(),
          timestamp: new Date()
        };

        // Execute tool through registry with validation and error handling
        const result = await this.toolRegistry.executeTool(name, args, context);
        
        logger.info(`Tool execution completed: ${name}`, { 
          resultType: result.content?.[0]?.type,
          isError: result.isError 
        });
        
        // Return in MCP SDK expected format
        return {
          content: result.content,
          isError: result.isError
        };
      } catch (error) {
        logger.error(`Tool execution failed: ${name}`, { 
          error: error instanceof Error ? error.message : error 
        });
        
        // Return error in MCP format
        return {
          content: [
            {
              type: 'text',
              text: `Tool execution failed: ${error instanceof Error ? error.message : 'Unknown error'}`
            }
          ],
          isError: true
        };
      }
    });
  }





  async shutdown(): Promise<void> {
    if (this.isShuttingDown) {
      logger.warn('MCP Server already shutting down');
      return;
    }

    this.isShuttingDown = true;
    logger.info('Shutting down MCP Server...', { connectionCount: this.connectionCount });

    try {
      await this.cleanup();
      logger.info('MCP Server shutdown complete');
    } catch (error) {
      logger.error('Error during MCP Server shutdown', error);
      throw error;
    }
  }

  private async cleanup(): Promise<void> {
    logger.debug('Starting MCP Server cleanup...');

    try {
      // Close transport connection if exists
      if (this.transport) {
        logger.debug('Closing transport connection...');
        // Note: The MCP SDK transport doesn't have a direct close method
        // Connection cleanup is handled by the transport's onclose handler
        this.transport = null;
      }

      // Clear tool registry
      this.toolRegistry.clear();

      // Reset connection state
      this.connectionCount = 0;
      this.isInitialized = false;

      logger.debug('MCP Server cleanup completed');
    } catch (error) {
      logger.error('Error during cleanup', error);
      throw error;
    }
  }

  /**
   * Register a new tool with the server
   */
  public registerTool(tool: MCPTool, category?: string): void {
    this.toolRegistry.registerTool(tool, category);
  }

  /**
   * Unregister a tool from the server
   */
  public unregisterTool(toolName: string): boolean {
    return this.toolRegistry.unregisterTool(toolName);
  }

  /**
   * Get tool registry for direct access
   */
  public getToolRegistry(): MCPToolRegistry {
    return this.toolRegistry;
  }



  /**
   * Generate a unique request ID
   */
  private generateRequestId(): string {
    return `req_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
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