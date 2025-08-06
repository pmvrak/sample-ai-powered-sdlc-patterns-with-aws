import { MCPTool, MCPToolResult, MCPToolContext } from '../interfaces/MCPTool';
import { BaseMCPTool } from '../interfaces/BaseMCPTool';
import { logger } from '../utils/logger';

/**
 * Registry for managing MCP tools
 */
export class MCPToolRegistry {
  private tools: Map<string, MCPTool> = new Map();
  private toolCategories: Map<string, string[]> = new Map();

  /**
   * Register a new tool in the registry
   */
  public registerTool(tool: MCPTool, category?: string): void {
    if (this.tools.has(tool.name)) {
      throw new Error(`Tool with name '${tool.name}' is already registered`);
    }

    // Validate tool implementation
    this.validateTool(tool);

    this.tools.set(tool.name, tool);
    
    if (category) {
      if (!this.toolCategories.has(category)) {
        this.toolCategories.set(category, []);
      }
      this.toolCategories.get(category)!.push(tool.name);
    }

    logger.info(`Registered MCP tool: ${tool.name}`, { 
      category,
      description: tool.description 
    });
  }

  /**
   * Unregister a tool from the registry
   */
  public unregisterTool(toolName: string): boolean {
    const removed = this.tools.delete(toolName);
    
    if (removed) {
      // Remove from categories
      for (const [category, toolNames] of this.toolCategories.entries()) {
        const index = toolNames.indexOf(toolName);
        if (index > -1) {
          toolNames.splice(index, 1);
          if (toolNames.length === 0) {
            this.toolCategories.delete(category);
          }
        }
      }
      
      logger.info(`Unregistered MCP tool: ${toolName}`);
    }
    
    return removed;
  }

  /**
   * Get a tool by name
   */
  public getTool(toolName: string): MCPTool | undefined {
    return this.tools.get(toolName);
  }

  /**
   * Get all registered tools
   */
  public getAllTools(): MCPTool[] {
    return Array.from(this.tools.values());
  }

  /**
   * Get tools by category
   */
  public getToolsByCategory(category: string): MCPTool[] {
    const toolNames = this.toolCategories.get(category) || [];
    return toolNames.map(name => this.tools.get(name)!).filter(Boolean);
  }

  /**
   * Get all categories
   */
  public getCategories(): string[] {
    return Array.from(this.toolCategories.keys());
  }

  /**
   * Check if a tool is registered
   */
  public hasTool(toolName: string): boolean {
    return this.tools.has(toolName);
  }

  /**
   * Get the number of registered tools
   */
  public getToolCount(): number {
    return this.tools.size;
  }

  /**
   * Execute a tool by name with validation and error handling
   */
  public async executeTool(
    toolName: string, 
    args: any, 
    context?: MCPToolContext
  ): Promise<MCPToolResult> {
    const tool = this.getTool(toolName);
    
    if (!tool) {
      throw new Error(`Tool '${toolName}' not found in registry`);
    }

    // Use BaseMCPTool's validation if available, otherwise call execute directly
    if (tool instanceof BaseMCPTool) {
      return await tool.executeWithValidation(args, context);
    } else {
      // For tools not extending BaseMCPTool, validate manually
      tool.validateInput(args);
      return await tool.execute(args);
    }
  }

  /**
   * Get tool information for MCP protocol
   */
  public getToolsForMCP(): Array<{
    name: string;
    description: string;
    inputSchema: any;
  }> {
    return this.getAllTools().map(tool => ({
      name: tool.name,
      description: tool.description,
      inputSchema: tool.inputSchema
    }));
  }

  /**
   * Clear all registered tools
   */
  public clear(): void {
    const toolCount = this.tools.size;
    this.tools.clear();
    this.toolCategories.clear();
    
    logger.info(`Cleared all tools from registry`, { removedCount: toolCount });
  }

  /**
   * Validate that a tool implements the required interface correctly
   */
  private validateTool(tool: MCPTool): void {
    if (!tool.name || typeof tool.name !== 'string') {
      throw new Error('Tool must have a valid name');
    }

    if (!tool.description || typeof tool.description !== 'string') {
      throw new Error('Tool must have a valid description');
    }

    if (!tool.inputSchema || typeof tool.inputSchema !== 'object') {
      throw new Error('Tool must have a valid inputSchema');
    }

    if (typeof tool.execute !== 'function') {
      throw new Error('Tool must implement execute method');
    }

    if (typeof tool.validateInput !== 'function') {
      throw new Error('Tool must implement validateInput method');
    }
  }

  /**
   * Get registry statistics
   */
  public getStats(): {
    totalTools: number;
    categories: number;
    toolsByCategory: Record<string, number>;
  } {
    const toolsByCategory: Record<string, number> = {};
    
    for (const [category, tools] of this.toolCategories.entries()) {
      toolsByCategory[category] = tools.length;
    }

    return {
      totalTools: this.tools.size,
      categories: this.toolCategories.size,
      toolsByCategory
    };
  }
}