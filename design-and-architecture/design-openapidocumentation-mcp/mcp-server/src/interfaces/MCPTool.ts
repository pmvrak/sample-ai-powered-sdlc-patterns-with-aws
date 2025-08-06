import { JSONSchema7 } from 'json-schema';

/**
 * Base interface for MCP tools
 */
export interface MCPTool {
  /** Unique name identifier for the tool */
  name: string;

  /** Human-readable description of what the tool does */
  description: string;

  /** JSON Schema defining the expected input parameters */
  inputSchema: JSONSchema7;

  /**
   * Execute the tool with the provided arguments
   * @param args - Arguments matching the inputSchema
   * @returns Promise resolving to the tool execution result
   */
  execute(args: any): Promise<MCPToolResult>;

  /**
   * Validate input arguments against the tool's schema
   * @param args - Arguments to validate
   * @returns true if valid, throws error if invalid
   */
  validateInput(args: any): boolean;
}

/**
 * Result returned by MCP tool execution
 */
export interface MCPToolResult {
  content: MCPToolContent[];
  isError?: boolean;
}

/**
 * Content types that can be returned by MCP tools
 */
export interface MCPToolContent {
  type: 'text' | 'image' | 'resource';
  text?: string;
  data?: string;
  url?: string;
  mimeType?: string;
}

/**
 * Error information for tool execution failures
 */
export class MCPToolError extends Error {
  public code: number;
  public data?: any;

  constructor(message: string, code: number, data?: any) {
    super(message);
    this.name = 'MCPToolError';
    this.code = code;
    this.data = data;
  }
}

/**
 * Tool execution context containing request metadata
 */
export interface MCPToolContext {
  requestId?: string;
  userId?: string;
  sessionId?: string;
  timestamp: Date;
}