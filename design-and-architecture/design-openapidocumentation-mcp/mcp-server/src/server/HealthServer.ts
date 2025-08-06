import { createServer, IncomingMessage, ServerResponse } from 'http';
import { logger } from '../utils/logger';
import { EnvironmentConfig } from '../config/environment';
import { MCPServer } from './MCPServer';

export class HealthServer {
  private server: ReturnType<typeof createServer>;
  private config: EnvironmentConfig;
  private isReady = false;
  private mcpServer?: MCPServer;

  constructor(config: EnvironmentConfig) {
    this.config = config;
    this.server = createServer(this.handleRequest.bind(this));
  }

  setMCPServer(mcpServer: MCPServer): void {
    this.mcpServer = mcpServer;
  }

  private handleRequest(req: IncomingMessage, res: ServerResponse): void {
    const url = req.url;
    const method = req.method;
    
    // Enable CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (method === 'OPTIONS') {
      res.writeHead(200);
      res.end();
      return;
    }
    
    if (url === '/health') {
      this.handleHealthCheck(res);
    } else if (url === '/ready') {
      this.handleReadinessCheck(res);
    } else if (url === '/metrics') {
      this.handleMetrics(res);
    } else if (url === '/tools' && method === 'GET') {
      this.handleListTools(res);
    } else if (url?.startsWith('/tools/') && method === 'POST') {
      this.handleCallTool(req, res);
    } else {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Not found' }));
    }
  }

  private handleHealthCheck(res: ServerResponse): void {
    const healthStatus = {
      status: 'healthy',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      version: '1.0.0',
      environment: this.config.NODE_ENV
    };

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(healthStatus));
  }

  private handleReadinessCheck(res: ServerResponse): void {
    if (this.isReady) {
      const readinessStatus = {
        status: 'ready',
        timestamp: new Date().toISOString(),
        services: {
          mcpServer: 'ready',
          awsConnection: 'ready'
        }
      };

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(readinessStatus));
    } else {
      const readinessStatus = {
        status: 'not ready',
        timestamp: new Date().toISOString(),
        services: {
          mcpServer: 'initializing',
          awsConnection: 'pending'
        }
      };

      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(readinessStatus));
    }
  }

  private handleMetrics(res: ServerResponse): void {
    if (!this.config.ENABLE_METRICS) {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Metrics disabled' }));
      return;
    }

    const metrics = {
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      cpu: process.cpuUsage(),
      environment: this.config.NODE_ENV,
      nodeVersion: process.version
    };

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(metrics));
  }

  private handleListTools(res: ServerResponse): void {
    if (!this.mcpServer) {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'MCP Server not available' }));
      return;
    }

    try {
      const tools = this.mcpServer.getToolRegistry().getToolsForMCP();
      const response = {
        tools,
        count: tools.length,
        timestamp: new Date().toISOString()
      };

      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(response));
    } catch (error) {
      logger.error('Error listing tools:', error);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ 
        error: 'Failed to list tools',
        message: error instanceof Error ? error.message : 'Unknown error'
      }));
    }
  }

  private handleCallTool(req: IncomingMessage, res: ServerResponse): void {
    if (!this.mcpServer) {
      res.writeHead(503, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'MCP Server not available' }));
      return;
    }

    // Extract tool name from URL path
    const toolName = req.url?.split('/tools/')[1];
    if (!toolName) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Tool name required in URL path' }));
      return;
    }

    // Parse request body
    let body = '';
    req.on('data', (chunk) => {
      body += chunk.toString();
    });

    req.on('end', async () => {
      try {
        const requestData = JSON.parse(body);
        const args = requestData.arguments || requestData;

        logger.info(`HTTP tool call: ${toolName}`, { args });

        // Execute tool via MCP server (double-check it's still available)
        if (!this.mcpServer) {
          res.writeHead(503, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'MCP Server not available' }));
          return;
        }

        const result = await this.mcpServer.getToolRegistry().executeTool(
          toolName,
          args,
          {
            requestId: `http_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`,
            timestamp: new Date()
          }
        );

        const response = {
          tool: toolName,
          result,
          timestamp: new Date().toISOString(),
          success: !result.isError
        };

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(response, null, 2));

      } catch (error) {
        logger.error(`HTTP tool call failed: ${toolName}`, error);
        
        const errorResponse = {
          tool: toolName,
          error: error instanceof Error ? error.message : 'Unknown error',
          timestamp: new Date().toISOString(),
          success: false
        };

        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(errorResponse));
      }
    });

    req.on('error', (error) => {
      logger.error('HTTP request error:', error);
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'Invalid request' }));
    });
  }

  async start(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.server.listen(this.config.PORT, () => {
        logger.info(`Health server started on port ${this.config.PORT}`);
        resolve();
      });

      this.server.on('error', (error) => {
        logger.error('Health server error:', error);
        reject(error);
      });
    });
  }

  setReady(ready: boolean): void {
    this.isReady = ready;
    logger.info(`Service readiness set to: ${ready}`);
  }

  async shutdown(): Promise<void> {
    return new Promise((resolve) => {
      this.server.close(() => {
        logger.info('Health server shutdown complete');
        resolve();
      });
    });
  }
}