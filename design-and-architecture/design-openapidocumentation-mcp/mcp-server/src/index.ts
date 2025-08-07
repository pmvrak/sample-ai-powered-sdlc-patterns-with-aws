import { MCPServer } from './server/MCPServer';
import { HealthServer } from './server/HealthServer';
import { logger } from './utils/logger';
import { config } from './config/environment';
import { DomainAnalysisTool } from './tools/DomainAnalysisTool';
import { DocumentationTool } from './tools/DocumentationTool';
import { OpenAPIGeneratorTool } from './tools/OpenAPIGeneratorTool';
import { ImageAnalysisTool } from './tools/ImageAnalysisTool';

async function main() {
  let mcpServer: MCPServer | undefined;
  let healthServer: HealthServer | undefined;

  try {
    logger.info('Starting OpenAPI MCP Server...');
    
    // Start health server first for RunPod compatibility
    healthServer = new HealthServer(config);
    await healthServer.start();
    
    // Initialize MCP server
    mcpServer = new MCPServer(config);
    await mcpServer.initialize();
    
    // Register tools
    logger.info('Registering MCP tools...');
    mcpServer.registerTool(new DomainAnalysisTool(), 'analysis');
    mcpServer.registerTool(new DocumentationTool(), 'documentation');
    mcpServer.registerTool(new OpenAPIGeneratorTool(), 'generation');
    mcpServer.registerTool(new ImageAnalysisTool(), 'analysis');
    logger.info('MCP tools registered successfully');
    
    // Connect MCP server to health server for HTTP API
    healthServer.setMCPServer(mcpServer);
    
    // Mark service as ready
    healthServer.setReady(true);
    
    logger.info(`MCP Server started on port ${config.MCP_PORT}`);
    logger.info(`Health server started on port ${config.PORT}`);
    
    // Handle graceful shutdown
    const shutdown = async (signal: string) => {
      logger.info(`Received ${signal}, shutting down gracefully...`);
      
      if (healthServer) {
        healthServer.setReady(false);
        await healthServer.shutdown();
      }
      
      if (mcpServer) {
        await mcpServer.shutdown();
      }
      
      process.exit(0);
    };
    
    process.on('SIGINT', () => shutdown('SIGINT'));
    process.on('SIGTERM', () => shutdown('SIGTERM'));
    
  } catch (error) {
    logger.error('Failed to start servers:', error);
    
    // Cleanup on error
    if (healthServer) {
      await healthServer.shutdown();
    }
    if (mcpServer) {
      await mcpServer.shutdown();
    }
    
    process.exit(1);
  }
}

main().catch((error) => {
  logger.error('Unhandled error in main:', error);
  process.exit(1);
});