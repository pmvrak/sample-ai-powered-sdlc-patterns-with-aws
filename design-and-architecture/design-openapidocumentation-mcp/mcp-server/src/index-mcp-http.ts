import { MCPHTTPServer } from './server/MCPHTTPServer';
import { HealthServer } from './server/HealthServer';
import { logger } from './utils/logger';
import { config } from './config/environment';
import { DomainAnalysisTool } from './tools/DomainAnalysisTool';
import { DocumentationTool } from './tools/DocumentationTool';
import { OpenAPIGeneratorTool } from './tools/OpenAPIGeneratorTool';

async function main() {
  let mcpHttpServer: MCPHTTPServer | undefined;
  let healthServer: HealthServer | undefined;

  try {
    logger.info('Starting MCP-compliant HTTP Server with JSON-RPC 2.0...');
    
    // Start health server first for RunPod compatibility
    healthServer = new HealthServer(config);
    await healthServer.start();
    
    // Initialize MCP HTTP server with JSON-RPC 2.0 compliance
    mcpHttpServer = new MCPHTTPServer(config, {
      name: 'openapi-mcp-server-jsonrpc',
      version: '1.0.0',
      capabilities: [
        'domain_analysis',
        'generate_documentation', 
        'generate_openapi_spec'
      ]
    });
    
    await mcpHttpServer.initialize();
    
    // Register tools with their actual names
    logger.info('Registering MCP tools...');
    mcpHttpServer.registerTool(new DomainAnalysisTool(), 'analysis');
    mcpHttpServer.registerTool(new DocumentationTool(), 'documentation');
    mcpHttpServer.registerTool(new OpenAPIGeneratorTool(), 'generation');
    logger.info('MCP tools registered successfully');
    
    // Connect MCP HTTP server to health server for unified API
    healthServer.setMCPServer(mcpHttpServer as any); // Type compatibility
    
    // Mark service as ready
    healthServer.setReady(true);
    
    logger.info(`MCP HTTP Server (JSON-RPC 2.0) started on port ${config.MCP_PORT}`);
    logger.info(`Health server started on port ${config.PORT}`);
    logger.info('Available capabilities:', mcpHttpServer.getCapabilities());
    
    // Log available endpoints
    logger.info('Available endpoints:', {
      mcp: `http://localhost:${config.MCP_PORT}/mcp (JSON-RPC 2.0)`,
      info: `http://localhost:${config.MCP_PORT}/info`,
      health: `http://localhost:${config.PORT}/health`,
      ready: `http://localhost:${config.PORT}/ready`
    });
    
    // Log example JSON-RPC 2.0 requests
    logger.info('Example JSON-RPC 2.0 requests:');
    logger.info('Initialize:', {
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {},
        clientInfo: { name: 'test-client', version: '1.0.0' }
      }
    });
    logger.info('List Tools:', {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/list',
      params: {}
    });
    
    // Handle graceful shutdown
    const shutdown = async (signal: string) => {
      logger.info(`Received ${signal}, shutting down gracefully...`);
      
      if (healthServer) {
        healthServer.setReady(false);
        await healthServer.shutdown();
      }
      
      if (mcpHttpServer) {
        await mcpHttpServer.shutdown();
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
    if (mcpHttpServer) {
      await mcpHttpServer.shutdown();
    }
    
    process.exit(1);
  }
}

main().catch((error) => {
  logger.error('Unhandled error in main:', error);
  process.exit(1);
});