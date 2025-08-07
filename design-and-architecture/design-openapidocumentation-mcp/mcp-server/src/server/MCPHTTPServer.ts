import { createServer, IncomingMessage, ServerResponse } from 'http';
import { logger } from '../utils/logger';
import { EnvironmentConfig } from '../config/environment';
import { MCPToolRegistry } from './MCPToolRegistry';
import { MCPTool } from '../interfaces/MCPTool';

/**
 * JSON-RPC 2.0 compliant MCP HTTP Server
 * Implements the Model Context Protocol over HTTP using proper JSON-RPC 2.0 messages
 */

interface JSONRPCRequest {
    jsonrpc: '2.0';
    id?: string | number | null;
    method: string;
    params?: any;
}

interface JSONRPCResponse {
    jsonrpc: '2.0';
    id?: string | number | null | undefined;
    result?: any;
    error?: {
        code: number;
        message: string;
        data?: any;
    };
}

interface JSONRPCError {
    code: number;
    message: string;
    data?: any;
}

// JSON-RPC 2.0 Error Codes
const JSONRPC_ERRORS = {
    PARSE_ERROR: { code: -32700, message: 'Parse error' },
    INVALID_REQUEST: { code: -32600, message: 'Invalid Request' },
    METHOD_NOT_FOUND: { code: -32601, message: 'Method not found' },
    INVALID_PARAMS: { code: -32602, message: 'Invalid params' },
    INTERNAL_ERROR: { code: -32603, message: 'Internal error' },
    SERVER_ERROR: { code: -32000, message: 'Server error' }
};

export interface MCPHTTPServerOptions {
    name: string;
    version: string;
    capabilities: string[];
}

export class MCPHTTPServer {
    private server: ReturnType<typeof createServer>;
    private config: EnvironmentConfig;
    private isInitialized: boolean = false;
    private isShuttingDown: boolean = false;
    private connectionCount: number = 0;
    private toolRegistry: MCPToolRegistry;
    private serverOptions: MCPHTTPServerOptions;

    constructor(config: EnvironmentConfig, options?: Partial<MCPHTTPServerOptions>) {
        this.config = config;

        this.serverOptions = {
            name: options?.name || 'openapi-mcp-server',
            version: options?.version || '1.0.0',
            capabilities: options?.capabilities || [
                'domain_analysis',
                'generate_documentation',
                'generate_openapi_spec'
            ]
        };

        // Initialize tool registry
        this.toolRegistry = new MCPToolRegistry();

        // Create HTTP server
        this.server = createServer(this.handleRequest.bind(this));
        this.setupServerHandlers();
    }

    private setupServerHandlers(): void {
        this.server.on('error', (error) => {
            logger.error('MCP HTTP Server error:', error);
        });

        this.server.on('connection', (socket) => {
            this.connectionCount++;
            logger.debug('New MCP connection established', { connectionCount: this.connectionCount });

            socket.on('close', () => {
                this.connectionCount = Math.max(0, this.connectionCount - 1);
                logger.debug('MCP connection closed', { connectionCount: this.connectionCount });
            });
        });
    }

    private handleRequest(req: IncomingMessage, res: ServerResponse): void {
        const url = req.url;
        const method = req.method;

        // Enable CORS
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

        if (method === 'OPTIONS') {
            res.writeHead(200);
            res.end();
            return;
        }

        try {
            // MCP over HTTP uses POST requests to a single endpoint
            if (url === '/mcp' && method === 'POST') {
                this.handleMCPRequest(req, res);
            } else if (url === '/health' && method === 'GET') {
                this.handleHealthCheck(res);
            } else if (url === '/ready' && method === 'GET') {
                this.handleReadinessCheck(res);
            } else if (url === '/info' && method === 'GET') {
                this.handleServerInfo(res);
            } else {
                this.handleNotFound(res);
            }
        } catch (error) {
            logger.error('Error handling HTTP request:', error);
            this.handleInternalError(res, error);
        }
    }

    private handleMCPRequest(req: IncomingMessage, res: ServerResponse): void {
        this.parseRequestBody(req, async (body) => {
            try {
                // Parse JSON-RPC 2.0 request
                let jsonrpcRequest: JSONRPCRequest;
                try {
                    jsonrpcRequest = JSON.parse(body);
                } catch (parseError) {
                    this.sendJSONRPCError(res, null, JSONRPC_ERRORS.PARSE_ERROR);
                    return;
                }

                // Validate JSON-RPC 2.0 format
                if (!this.isValidJSONRPCRequest(jsonrpcRequest)) {
                    this.sendJSONRPCError(res, (jsonrpcRequest as any)?.id || null, JSONRPC_ERRORS.INVALID_REQUEST);
                    return;
                }

                // Now jsonrpcRequest is properly typed as JSONRPCRequest
                const validRequest = jsonrpcRequest as JSONRPCRequest;

                logger.info(`MCP JSON-RPC request: ${validRequest.method}`, {
                    id: validRequest.id,
                    params: this.sanitizeArgsForLogging(validRequest.params)
                });

                // Route to appropriate MCP method handler
                const response = await this.handleMCPMethod(jsonrpcRequest);
                this.sendJSONRPCResponse(res, response);

            } catch (error) {
                logger.error('MCP request handling failed:', error);
                this.sendJSONRPCError(res, null, {
                    ...JSONRPC_ERRORS.INTERNAL_ERROR,
                    data: error instanceof Error ? error.message : 'Unknown error'
                });
            }
        });
    }

    private async handleMCPMethod(request: JSONRPCRequest): Promise<JSONRPCResponse> {
        const { method, params, id } = request;

        try {
            switch (method) {
                case 'initialize':
                    return this.handleInitialize(id, params);

                case 'tools/list':
                    return this.handleListTools(id, params);

                case 'tools/call':
                    return await this.handleCallTool(id, params);

                case 'resources/list':
                    return {
                        jsonrpc: '2.0',
                        id,
                        result: { resources: [] }
                    };

                case 'resources/read':
                    return {
                        jsonrpc: '2.0',
                        id,
                        error: JSONRPC_ERRORS.METHOD_NOT_FOUND
                    };

                case 'prompts/list':
                    return {
                        jsonrpc: '2.0',
                        id,
                        result: { prompts: [] }
                    };

                case 'prompts/get':
                    return {
                        jsonrpc: '2.0',
                        id,
                        error: JSONRPC_ERRORS.METHOD_NOT_FOUND
                    };

                default:
                    return {
                        jsonrpc: '2.0',
                        id,
                        error: JSONRPC_ERRORS.METHOD_NOT_FOUND
                    };
            }
        } catch (error) {
            logger.error(`MCP method ${method} failed:`, error);
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    ...JSONRPC_ERRORS.SERVER_ERROR,
                    data: error instanceof Error ? error.message : 'Unknown error'
                }
            };
        }
    }

    private handleInitialize(id: any, _params: any): JSONRPCResponse {
        return {
            jsonrpc: '2.0',
            id,
            result: {
                protocolVersion: '2024-11-05',
                capabilities: {
                    tools: {
                        listChanged: false
                    },
                    resources: {
                        subscribe: false,
                        listChanged: false
                    },
                    prompts: {
                        listChanged: false
                    }
                },
                serverInfo: {
                    name: this.serverOptions.name,
                    version: this.serverOptions.version
                },
                instructions: `This is an OpenAPI MCP server with capabilities: ${this.serverOptions.capabilities.join(', ')}`
            }
        };
    }

    private handleListTools(id: any, _params: any): JSONRPCResponse {
        try {
            const tools = this.toolRegistry.getToolsForMCP();
            return {
                jsonrpc: '2.0',
                id,
                result: {
                    tools: tools.map(tool => ({
                        name: tool.name,
                        description: tool.description,
                        inputSchema: tool.inputSchema
                    }))
                }
            };
        } catch (error) {
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    ...JSONRPC_ERRORS.SERVER_ERROR,
                    data: error instanceof Error ? error.message : 'Failed to list tools'
                }
            };
        }
    }

    private async handleCallTool(id: any, params: any): Promise<JSONRPCResponse> {
        if (!params || !params.name) {
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    ...JSONRPC_ERRORS.INVALID_PARAMS,
                    data: 'Tool name is required'
                }
            };
        }

        try {
            const { name, arguments: args } = params;

            // Create execution context
            const context = {
                requestId: this.generateRequestId(),
                timestamp: new Date()
            };

            // Execute tool via registry
            const result = await this.toolRegistry.executeTool(name, args || {}, context);

            return {
                jsonrpc: '2.0',
                id,
                result: {
                    content: result.content,
                    isError: result.isError
                }
            };
        } catch (error) {
            return {
                jsonrpc: '2.0',
                id,
                error: {
                    ...JSONRPC_ERRORS.SERVER_ERROR,
                    data: error instanceof Error ? error.message : 'Tool execution failed'
                }
            };
        }
    }



    private handleHealthCheck(res: ServerResponse): void {
        const healthStatus = {
            status: 'healthy',
            server: this.serverOptions.name,
            version: this.serverOptions.version,
            timestamp: new Date().toISOString(),
            uptime: process.uptime(),
            environment: this.config.NODE_ENV,
            capabilities: this.serverOptions.capabilities,
            connections: this.connectionCount,
            initialized: this.isInitialized,
            protocol: 'MCP over HTTP with JSON-RPC 2.0'
        };

        this.sendJSONResponse(res, 200, healthStatus);
    }

    private handleReadinessCheck(res: ServerResponse): void {
        if (this.isInitialized && !this.isShuttingDown) {
            const readinessStatus = {
                status: 'ready',
                timestamp: new Date().toISOString(),
                services: {
                    mcpServer: 'ready',
                    toolRegistry: 'ready',
                    awsConnection: 'ready'
                }
            };

            this.sendJSONResponse(res, 200, readinessStatus);
        } else {
            const readinessStatus = {
                status: 'not ready',
                timestamp: new Date().toISOString(),
                services: {
                    mcpServer: this.isShuttingDown ? 'shutting down' : 'initializing',
                    toolRegistry: 'pending',
                    awsConnection: 'pending'
                }
            };

            this.sendJSONResponse(res, 503, readinessStatus);
        }
    }

    private handleServerInfo(res: ServerResponse): void {
        const serverInfo = {
            name: this.serverOptions.name,
            version: this.serverOptions.version,
            capabilities: this.serverOptions.capabilities,
            protocol: 'MCP over HTTP with JSON-RPC 2.0',
            transport: 'http',
            endpoints: {
                mcp: '/mcp',
                health: '/health',
                ready: '/ready',
                info: '/info'
            },
            status: {
                initialized: this.isInitialized,
                shuttingDown: this.isShuttingDown,
                connections: this.connectionCount
            },
            timestamp: new Date().toISOString()
        };

        this.sendJSONResponse(res, 200, serverInfo);
    }

    private handleNotFound(res: ServerResponse): void {
        this.sendJSONResponse(res, 404, {
            error: 'Not found',
            message: 'This is an MCP server. Send JSON-RPC 2.0 requests to /mcp',
            availableEndpoints: [
                'POST /mcp - MCP JSON-RPC 2.0 endpoint',
                'GET /health - Health check',
                'GET /ready - Readiness check',
                'GET /info - Server information'
            ]
        });
    }

    private handleInternalError(res: ServerResponse, error: any): void {
        this.sendJSONResponse(res, 500, {
            error: 'Internal server error',
            message: error instanceof Error ? error.message : 'Unknown error',
            timestamp: new Date().toISOString()
        });
    }

    private isValidJSONRPCRequest(request: any): request is JSONRPCRequest {
        return (
            request &&
            typeof request === 'object' &&
            request.jsonrpc === '2.0' &&
            typeof request.method === 'string' &&
            request.method.length > 0 &&
            (request.id === undefined ||
                typeof request.id === 'string' ||
                typeof request.id === 'number' ||
                request.id === null)
        );
    }

    private sendJSONRPCResponse(res: ServerResponse, response: JSONRPCResponse): void {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(response));
    }

    private sendJSONRPCError(res: ServerResponse, id: any, error: JSONRPCError): void {
        const response: JSONRPCResponse = {
            jsonrpc: '2.0',
            id,
            error
        };
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(response));
    }

    private sendJSONResponse(res: ServerResponse, statusCode: number, data: any): void {
        res.writeHead(statusCode, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data, null, 2));
    }

    private parseRequestBody(req: IncomingMessage, callback: (body: string) => void): void {
        let body = '';
        req.on('data', (chunk) => {
            body += chunk.toString();
        });

        req.on('end', () => {
            callback(body);
        });

        req.on('error', (error) => {
            logger.error('HTTP request body parsing error:', error);
            throw error;
        });
    }

    private generateRequestId(): string {
        return `mcp_req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    }

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

    async initialize(): Promise<void> {
        if (this.isInitialized) {
            logger.warn('MCP HTTP Server already initialized');
            return;
        }

        if (this.isShuttingDown) {
            throw new Error('Cannot initialize server during shutdown');
        }

        logger.info('Initializing MCP HTTP Server with JSON-RPC 2.0...', {
            environment: this.config.NODE_ENV,
            port: this.config.MCP_PORT,
            capabilities: this.serverOptions.capabilities
        });

        try {
            await this.start();
            this.isInitialized = true;
            logger.info('MCP HTTP Server initialized successfully');
        } catch (error) {
            logger.error('Failed to initialize MCP HTTP Server', error);
            throw error;
        }
    }

    async start(): Promise<void> {
        return new Promise((resolve, reject) => {
            this.server.listen(this.config.MCP_PORT, () => {
                logger.info(`MCP HTTP Server started on port ${this.config.MCP_PORT}`);
                logger.info('Protocol: MCP over HTTP with JSON-RPC 2.0');
                logger.info('Endpoint: POST /mcp');
                resolve();
            });

            this.server.on('error', (error) => {
                logger.error('MCP HTTP Server startup error:', error);
                reject(error);
            });
        });
    }

    async shutdown(): Promise<void> {
        if (this.isShuttingDown) {
            logger.warn('MCP HTTP Server already shutting down');
            return;
        }

        this.isShuttingDown = true;
        logger.info('Shutting down MCP HTTP Server...', { connectionCount: this.connectionCount });

        try {
            await new Promise<void>((resolve) => {
                this.server.close(() => {
                    logger.info('MCP HTTP Server shutdown complete');
                    resolve();
                });
            });

            // Clear tool registry
            this.toolRegistry.clear();

            // Reset state
            this.connectionCount = 0;
            this.isInitialized = false;

        } catch (error) {
            logger.error('Error during MCP HTTP Server shutdown', error);
            throw error;
        }
    }

    // Registry management methods
    public registerTool(tool: MCPTool, category?: string): void {
        this.toolRegistry.registerTool(tool, category);
    }

    public unregisterTool(toolName: string): boolean {
        return this.toolRegistry.unregisterTool(toolName);
    }

    public getToolRegistry(): MCPToolRegistry {
        return this.toolRegistry;
    }



    public getConnectionCount(): number {
        return this.connectionCount;
    }

    public isServerInitialized(): boolean {
        return this.isInitialized;
    }

    public isServerShuttingDown(): boolean {
        return this.isShuttingDown;
    }

    public getCapabilities(): string[] {
        return [...this.serverOptions.capabilities];
    }

    public updateCapabilities(capabilities: string[]): void {
        this.serverOptions.capabilities = [...capabilities];
        logger.info('Server capabilities updated', { capabilities: this.serverOptions.capabilities });
    }
}