import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ErrorCode,
  ListToolsRequestSchema,
  McpError,
} from '@modelcontextprotocol/sdk/types.js';

import { CognitoAuth } from './auth.js';
import { OpenSearchClient } from './opensearch.js';
import { ProjectService } from './project.js';
import { SearchService } from './search.js';
import { MCP_TOOLS, ToolName } from './tools/index.js';
import {
  ServerConfig,
  DocumentType,
  SearchFilters,
  ErrorResponse
} from './types.js';
import { IMCPServer } from './interfaces/index.js';
import {
  ProjectKBError,
  ValidationError,
  ErrorClassifier,
  RetryManager,
  ErrorCategory,
  ErrorLogger
} from './errors.js';
import { log, secureLogger } from './secure-logger.js';
import { sanitize } from './sanitization.js';

/**
 * MCP Server error class (legacy - kept for backward compatibility)
 */
export class MCPServerError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    public readonly details?: Record<string, unknown> | Error
  ) {
    super(message);
    this.name = 'MCPServerError';
  }
}

/**
 * Main MCP Server implementation
 */
export class MCPServer implements IMCPServer {
  private server: Server;
  private config: ServerConfig;
  private authService: CognitoAuth;
  private openSearchClient: OpenSearchClient;
  private projectService: ProjectService;
  private searchService: SearchService;
  private isInitialized: boolean = false;
  private retryManager: RetryManager;
  private errorLogger: ErrorLogger;

  constructor(config: ServerConfig) {
    this.config = config;
    this.retryManager = RetryManager.getInstance();
    this.errorLogger = ErrorLogger.getInstance();

    this.server = new Server(
      {
        name: config.server.name,
        version: config.server.version,
      },
      {
        capabilities: {
          tools: {}
        }
      }
    );

    // Initialize auth service
    this.authService = new CognitoAuth(config.cognito);

    // Backend services will be initialized during initialize() after authentication
    this.openSearchClient = null as any;
    this.projectService = null as any;
    this.searchService = null as any;
  }

  /**
   * Initialize the MCP server and all services with comprehensive validation
   */
  async initialize(): Promise<void> {
    return await this.retryManager.executeWithRetry(
      async () => {
        try {
          log.info('Initializing MCP Server');

          // Step 1: Validate configuration
          log.info('Step 1: Validating server configuration');
          await this.validateConfiguration();

          // Step 2: Authenticate with Cognito and get AWS credentials
          log.info('Step 2: Authenticating with AWS Cognito');
          await this.authService.authenticate();
          log.info('Authentication successful');

          // Step 2.5: Get AWS credentials from Identity Pool (REQUIRED for security)
          log.info('Step 2.5: Obtaining AWS credentials from Identity Pool');
          const awsCredentials = await this.authService.getAWSCredentials();
          log.info('AWS credentials obtained from Identity Pool');

          // Step 2.6: Initialize backends with Identity Pool credentials
          // SECURITY: Use secure logging instead of console
          log.info('Initializing backends with secure credentials');
          await this.initializeBackends(awsCredentials);
          log.info('Backends initialized with Identity Pool credentials');

          // Step 3: Validate backend connection
          // SECURITY: Use secure logging with sanitized backend name
          log.info('Validating backend connection', { backend: sanitize.projectId(this.config.defaultBackend) });
          const backendInfo = this.projectService.getBackendInfo();
          if (!backendInfo.isHealthy) {
            throw new Error(`Backend is not healthy`);
          }
          log.info('Backend connection validated', { backend: sanitize.projectId(this.config.defaultBackend) });

          // Step 4: Initialize project service and validate access
          console.log('📁 Step 4: Initializing project service...');
          await this.validateProjectAccess();
          console.log('✅ Project access validated');

          // Step 5: Register MCP tools
          console.log('🛠️  Step 5: Registering MCP tools...');
          await this.registerTools();
          console.log('✅ MCP tools registered');

          // Step 6: Set up error handling (moved to lifecycle manager)
          console.log('🛡️  Step 6: Error handling configured');

          this.isInitialized = true;
          console.log('✅ MCP Server initialization completed successfully');

        } catch (error) {
          const classifiedError = ErrorClassifier.classifyError(error, 'initialize');
          this.errorLogger.logError(classifiedError, 'MCPServer:initialize');
          throw classifiedError;
        }
      },
      ErrorCategory.SYSTEM,
      'initialize'
    );
  }

  /**
   * Initialize backends with Identity Pool credentials
   */
  private async initializeBackends(awsCredentials: any): Promise<void> {
    try {
      console.log('🏗️  Initializing backends with Identity Pool credentials...');

      // Initialize backend based on default configuration
      if (this.config.defaultBackend === 'bedrock' && this.config.bedrock) {
        console.log('🤖 Initializing Bedrock backend...');
        this.projectService = new ProjectService({
          type: 'bedrock',
          bedrock: this.config.bedrock
        }, awsCredentials); // Pass credentials during construction

        // For Bedrock, we don't need OpenSearch client or SearchService
        this.openSearchClient = null as any;
        this.searchService = null as any;

      } else if (this.config.openSearch) {
        console.log('🔍 Initializing OpenSearch backend...');
        this.openSearchClient = new OpenSearchClient(this.config.openSearch, awsCredentials);
        this.projectService = new ProjectService({
          type: 'opensearch',
          opensearch: this.config.openSearch
        }, awsCredentials); // Pass credentials during construction

        this.searchService = new SearchService(this.openSearchClient, this.projectService);
      } else {
        throw new Error('No valid backend configuration provided');
      }

      console.log('✅ Backends initialized successfully');

    } catch (error) {
      console.error('❌ Failed to initialize backends:', error);
      throw new Error(`Failed to initialize backends: ${error instanceof Error ? error.message : error}`);
    }
  }

  /**
   * Update backend clients with Identity Pool credentials
   */
  async updateBackendCredentials(awsCredentials: any): Promise<void> {
    try {
      console.log('🔄 Updating backend clients with Identity Pool credentials...');

      // Update the project service backend with new credentials
      const backend = this.projectService.getBackend();
      if (backend && typeof backend.updateCredentials === 'function') {
        backend.updateCredentials(awsCredentials);
        console.log('✅ Backend credentials updated successfully');
      } else {
        console.warn('⚠️  Backend does not support credential updates');
      }

      // Update OpenSearch client if it exists
      if (this.openSearchClient && typeof this.openSearchClient.updateCredentials === 'function') {
        this.openSearchClient.updateCredentials(awsCredentials);
        console.log('✅ OpenSearch client credentials updated successfully');
      }

    } catch (error) {
      console.error('❌ Failed to update backend credentials:', error);
      throw new Error(`Failed to update backend credentials: ${error instanceof Error ? error.message : error}`);
    }
  }

  /**
   * Validate server configuration
   */
  private async validateConfiguration(): Promise<void> {
    try {
      // Validate Cognito configuration
      if (!this.config.cognito.userPoolId || !this.config.cognito.clientId || !this.config.cognito.region) {
        throw new ValidationError(
          'Missing required Cognito configuration (userPoolId, clientId, region)',
          'INVALID_COGNITO_CONFIG'
        );
      }

      // Validate backend configuration
      if (this.config.defaultBackend === 'opensearch') {
        if (!this.config.openSearch?.endpoint || !this.config.openSearch?.region) {
          throw new ValidationError(
            'Missing required OpenSearch configuration (endpoint, region)',
            'INVALID_OPENSEARCH_CONFIG'
          );
        }
      } else if (this.config.defaultBackend === 'bedrock') {
        if (!this.config.bedrock?.knowledgeBaseId || !this.config.bedrock?.region) {
          throw new ValidationError(
            'Missing required Bedrock configuration (knowledgeBaseId, region)',
            'INVALID_BEDROCK_CONFIG'
          );
        }
      } else {
        throw new ValidationError(
          'Invalid default backend. Must be "opensearch" or "bedrock"',
          'INVALID_DEFAULT_BACKEND'
        );
      }

      // Validate server configuration
      if (!this.config.server.name || !this.config.server.version) {
        throw new ValidationError(
          'Missing required server configuration (name, version)',
          'INVALID_SERVER_CONFIG'
        );
      }

      console.log('✅ Configuration validation passed');

    } catch (error) {
      throw new ValidationError(
        `Configuration validation failed: ${error instanceof Error ? error.message : error}`,
        'CONFIG_VALIDATION_ERROR'
      );
    }
  }

  /**
   * Validate project access and connectivity
   */
  private async validateProjectAccess(): Promise<void> {
    try {
      // Test project discovery
      const projects = await this.projectService.listAvailableProjects();
      console.log(`📊 Found ${projects.length} accessible projects`);

      if (projects.length === 0) {
        console.warn('⚠️  No projects found - this may indicate access issues or empty indexes');
      } else {
        // SECURITY: Use secure logging with sanitized project names
        log.info('Available projects found', {
          projectNames: projects.map(p => sanitize.projectId(p.name))
        });
      }

    } catch (error) {
      // Don't fail initialization if project discovery fails - log warning instead
      console.warn('⚠️  Project discovery failed during initialization:', error);
      console.warn('   This may indicate access issues but server will continue to start');
    }
  }

  /**
   * Register all MCP tools with the server
   */
  async registerTools(): Promise<void> {
    try {
      // Register list tools handler
      this.server.setRequestHandler(ListToolsRequestSchema, async () => {
        return {
          tools: Object.values(MCP_TOOLS).map(tool => ({
            name: tool.name,
            description: tool.description,
            inputSchema: tool.inputSchema,
          })),
        };
      });

      // Register call tool handler
      this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
        const { name, arguments: args } = request.params;

        try {
          return await this.handleToolCall(name as ToolName, args || {});
        } catch (error) {
          // Classify and log the error
          const classifiedError = ErrorClassifier.classifyError(error, `tool:${name}`);
          this.errorLogger.logError(classifiedError, `MCPServer:handleToolCall:${name}`);

          // Convert to MCP-compliant error
          if (classifiedError instanceof ProjectKBError) {
            throw new McpError(
              this.mapProjectKBErrorToMCP(classifiedError),
              classifiedError.getUserFriendlyMessage()
            );
          }

          throw new McpError(
            ErrorCode.InternalError,
            `Tool execution failed: ${error instanceof Error ? error.message : error}`
          );
        }
      });

      console.log(`📋 Registered ${Object.keys(MCP_TOOLS).length} MCP tools`);

    } catch (error) {
      throw new MCPServerError(
        `Tool registration failed: ${error instanceof Error ? error.message : error}`,
        'TOOL_REGISTRATION_ERROR',
        false,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Handle tool invocation and route to appropriate services
   */
  async handleToolCall(toolName: ToolName, args: any): Promise<any> {
    if (!this.isInitialized) {
      throw new MCPServerError(
        'Server not initialized',
        'SERVER_NOT_INITIALIZED',
        false
      );
    }

    try {
      // SECURITY: Use secure logging with sanitized tool name and args
      log.debug('Executing tool', {
        toolName: sanitize.searchQuery(toolName).sanitized,
        argsCount: Object.keys(args || {}).length
      });

      switch (toolName) {
        case 'list_projects':
          return await this.handleListProjects();

        case 'set_active_project':
          return await this.handleSetActiveProject(args);

        case 'search_all_projects':
          return await this.handleSearchAllProjects(args);

        case 'get_document':
          return await this.handleGetDocument(args);

        case 'search':
          return await this.handleSearch(args);

        case 'switch_backend':
          return await this.handleSwitchBackend(args);

        case 'get_backend_info':
          return await this.handleGetBackendInfo();

        default:
          throw new MCPServerError(
            `Unknown tool: ${toolName}`,
            'UNKNOWN_TOOL',
            false
          );
      }

    } catch (error) {
      // SECURITY: Use secure logging with sanitized error data
      log.error('Tool execution failed', {
        toolName: sanitize.projectId(toolName),
        error: error instanceof Error ? error.message : String(error),
        stack: error instanceof Error ? error.stack : undefined
      });

      if (error instanceof MCPServerError) {
        throw error;
      }

      throw new MCPServerError(
        `Tool execution failed: ${error instanceof Error ? error.message : error}`,
        'TOOL_EXECUTION_ERROR',
        true,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Handle list_projects tool
   */
  private async handleListProjects(): Promise<any> {
    try {
      const projects = await this.projectService.listAvailableProjects();

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              projects: projects.map(project => ({
                id: project.id,
                name: project.name,
                description: project.description,
                documentCount: project.documentCount,
                lastAccessed: project.lastAccessed?.toISOString()
              })),
              total: projects.length,
              timestamp: new Date().toISOString()
            }, null, 2)
          }
        ]
      };

    } catch (error) {
      throw new MCPServerError(
        `Failed to list projects: ${error instanceof Error ? error.message : error}`,
        'LIST_PROJECTS_ERROR',
        true,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Handle set_active_project tool
   */
  private async handleSetActiveProject(args: any): Promise<any> {
    const { projectName } = args;

    if (!projectName) {
      throw new MCPServerError(
        'Project name is required',
        'MISSING_PROJECT_NAME',
        false
      );
    }

    try {
      await this.projectService.setActiveProject(projectName);
      const activeProject = await this.projectService.getActiveProject();

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: true,
              message: `Active project set to: ${activeProject?.name}`,
              activeProject: activeProject ? {
                id: activeProject.id,
                name: activeProject.name,
                description: activeProject.description,
                documentCount: activeProject.documentCount
              } : null,
              timestamp: new Date().toISOString()
            }, null, 2)
          }
        ]
      };

    } catch (error) {
      throw new MCPServerError(
        `Failed to set active project: ${error instanceof Error ? error.message : error}`,
        'SET_ACTIVE_PROJECT_ERROR',
        false,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Handle search_project tool
   */
  private async handleSearchProject(args: any): Promise<any> {
    console.log(`[DEBUG] handleSearchProject called with args:`, args);

    const { query, documentType, limit: rawLimit = 10 } = args;
    
    // Validate and convert limit parameter
    const limit = this.validateLimit(rawLimit, 10);

    if (!query) {
      console.log(`[DEBUG] No query provided`);
      throw new ValidationError(
        'Search query is required',
        'MISSING_REQUIRED_FIELD'
      );
    }

    // SECURITY: Use secure logging with sanitized query
    log.debug('Search query received', {
      query: sanitize.searchQuery(query).sanitized
    });

    // Get active project
    const activeProject = await this.projectService.getActiveProject();
    if (!activeProject) {
      console.log(`[DEBUG] No active project set`);
      throw new ValidationError(
        'No active project set. Use set_active_project first.',
        'INVALID_INPUT'
      );
    }

    // SECURITY: Use secure logging with sanitized project data
    log.debug('Active project retrieved', {
      projectName: sanitize.projectId(activeProject.name),
      projectId: sanitize.projectId(activeProject.id)
    });

    // Prepare search filters
    const filters: SearchFilters = {
      limit: Math.min(limit, 50), // Cap at 50 results
    };

    if (documentType && this.isValidDocumentType(documentType)) {
      filters.documentType = documentType as DocumentType;
    }

    console.log(`[DEBUG] Search filters:`, filters);

    // Execute search
    console.log(`[DEBUG] Calling projectService.searchProject...`);
    const results = await this.projectService.searchProject(
      activeProject.id,
      query,
      filters
    );

    console.log(`[DEBUG] Search results:`, results.length, 'results found');

    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            query,
            projectId: activeProject.id,
            projectName: activeProject.name,
            results: results.map(result => ({
              id: result.id,
              title: result.title,
              content: result.content,
              documentType: result.documentType,
              score: result.score,
              highlights: result.highlights,
              metadata: {
                ...result.metadata,
                lastModified: result.metadata.lastModified?.toISOString()
              }
            })),
            total: results.length,
            timestamp: new Date().toISOString()
          }, null, 2)
        }
      ]
    };
  }

  /**
   * Handle search_all_projects tool
   */
  private async handleSearchAllProjects(args: any): Promise<any> {
    const { query, documentType, limit: rawLimit = 20 } = args;
    
    // Validate and convert limit parameter
    const limit = this.validateLimit(rawLimit, 20);

    if (!query) {
      throw new MCPServerError(
        'Search query is required',
        'MISSING_QUERY',
        false
      );
    }

    // Import sanitization at the top of the file
    const { sanitize } = await import('./sanitization.js');

    // Sanitize search query
    const sanitizedQuery = sanitize.searchQuery(query);
    if (sanitizedQuery.blocked) {
      throw new MCPServerError(
        `Invalid search query: ${sanitizedQuery.warnings.join(', ')}`,
        'INVALID_QUERY',
        false
      );
    }

    if (!sanitizedQuery.isValid) {
      throw new MCPServerError(
        `Query validation failed: ${sanitizedQuery.warnings.join(', ')}`,
        'QUERY_VALIDATION_ERROR',
        false
      );
    }

    try {
      // Prepare search filters
      const filters: SearchFilters = {
        limit: Math.min(limit, 100), // Cap at 100 results for cross-project search
      };

      if (documentType && this.isValidDocumentType(documentType)) {
        filters.documentType = documentType as DocumentType;
      }

      // Execute cross-project search with sanitized query
      const results = await this.projectService.searchAllProjects(sanitizedQuery.sanitized, filters);

      // Log data access for security monitoring
      const { log } = await import('./secure-logger.js');
      log.dataAccess('search', 'all_projects', true, {
        query: sanitizedQuery.sanitized,
        resultCount: results.length,
        originalQuery: query !== sanitizedQuery.sanitized ? query : undefined
      });

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              query: sanitizedQuery.sanitized,
              originalQuery: query !== sanitizedQuery.sanitized ? query : undefined,
              sanitizationWarnings: sanitizedQuery.warnings.length > 0 ? sanitizedQuery.warnings : undefined,
              searchType: 'cross-project',
              results: results.map(result => ({
                id: result.id,
                title: result.title,
                content: result.content,
                documentType: result.documentType,
                projectId: result.projectId,
                projectName: result.projectName,
                score: result.score,
                highlights: result.highlights,
                metadata: {
                  ...result.metadata,
                  lastModified: result.metadata.lastModified?.toISOString()
                }
              })),
              total: results.length,
              timestamp: new Date().toISOString()
            }, null, 2)
          }
        ]
      };

    } catch (error) {
      throw new MCPServerError(
        `Cross-project search failed: ${error instanceof Error ? error.message : error}`,
        'SEARCH_ALL_PROJECTS_ERROR',
        true,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Handle get_document tool
   */
  private async handleGetDocument(args: any): Promise<any> {
    const { documentId, projectId } = args;

    if (!documentId) {
      throw new MCPServerError(
        'Document ID is required',
        'MISSING_DOCUMENT_ID',
        false
      );
    }

    // Import sanitization
    const { sanitize } = await import('./sanitization.js');

    // Sanitize document ID
    let sanitizedDocumentId: string;
    try {
      sanitizedDocumentId = sanitize.documentId(documentId);
    } catch (error) {
      throw new MCPServerError(
        `Invalid document ID: ${error instanceof Error ? error.message : error}`,
        'INVALID_DOCUMENT_ID',
        false
      );
    }

    // Sanitize project ID if provided
    let sanitizedProjectId = projectId;
    if (projectId) {
      try {
        sanitizedProjectId = sanitize.projectId(projectId);
      } catch (error) {
        throw new MCPServerError(
          `Invalid project ID: ${error instanceof Error ? error.message : error}`,
          'INVALID_PROJECT_ID',
          false
        );
      }
    }

    try {
      let targetProjectId = sanitizedProjectId;

      // If no project ID provided, use active project
      if (!targetProjectId) {
        const activeProject = await this.projectService.getActiveProject();
        if (!activeProject) {
          throw new MCPServerError(
            'No project ID provided and no active project set. Use set_active_project first or provide projectId.',
            'NO_PROJECT_CONTEXT',
            false
          );
        }
        targetProjectId = activeProject.id;
      }

      // Retrieve document with sanitized IDs
      const document = await this.projectService.getDocument(targetProjectId, sanitizedDocumentId);

      // Log data access for security monitoring
      const { log } = await import('./secure-logger.js');
      log.dataAccess('retrieve', `${targetProjectId}/${sanitizedDocumentId}`, true, {
        documentId: sanitizedDocumentId,
        projectId: targetProjectId
      });

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              document: {
                id: document.id,
                title: document.title,
                content: document.content,
                documentType: document.documentType,
                projectId: document.projectId,
                createdAt: document.createdAt?.toISOString() || new Date().toISOString(),
                updatedAt: document.updatedAt?.toISOString() || new Date().toISOString(),
                metadata: {
                  ...document.metadata,
                  lastModified: document.metadata.lastModified?.toISOString()
                }
              },
              timestamp: new Date().toISOString()
            }, null, 2)
          }
        ]
      };

    } catch (error) {
      throw new MCPServerError(
        `Document retrieval failed: ${error instanceof Error ? error.message : error}`,
        'GET_DOCUMENT_ERROR',
        true,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Convert and validate limit parameter
   */
  private validateLimit(rawLimit: any, defaultValue: number): number {
    if (rawLimit === undefined || rawLimit === null) {
      return defaultValue;
    }
    
    let limit: number;
    if (typeof rawLimit === 'string') {
      const parsed = parseInt(rawLimit, 10);
      if (isNaN(parsed) || parsed < 1) {
        throw new MCPServerError(
          `Invalid limit value: "${rawLimit}". Must be a positive number.`,
          'INVALID_LIMIT',
          false
        );
      }
      limit = parsed;
    } else if (typeof rawLimit === 'number') {
      if (rawLimit < 1 || !Number.isInteger(rawLimit)) {
        throw new MCPServerError(
          `Invalid limit value: ${rawLimit}. Must be a positive integer.`,
          'INVALID_LIMIT',
          false
        );
      }
      limit = rawLimit;
    } else {
      throw new MCPServerError(
        `Invalid limit type: ${typeof rawLimit}. Must be a number or numeric string.`,
        'INVALID_LIMIT_TYPE',
        false
      );
    }
    
    // Cap at reasonable maximum
    return Math.min(limit, 100);
  }

  /**
   * Handle search tool
   */
  private async handleSearch(args: any): Promise<any> {
    const { query, projectId, limit: rawLimit = 5, enhancedHighlights = true } = args;
    
    // Validate and convert limit parameter
    const limit = this.validateLimit(rawLimit, 5);

    if (!query?.trim()) {
      throw new MCPServerError(
        'Search query is required',
        'MISSING_QUERY',
        false
      );
    }

    // Import sanitization
    const { sanitize } = await import('./sanitization.js');

    // Sanitize search query
    const sanitizedQuery = sanitize.searchQuery(query.trim());
    if (sanitizedQuery.blocked) {
      throw new MCPServerError(
        `Invalid search query: ${sanitizedQuery.warnings.join(', ')}`,
        'INVALID_QUERY',
        false
      );
    }

    if (!sanitizedQuery.isValid) {
      throw new MCPServerError(
        `Query validation failed: ${sanitizedQuery.warnings.join(', ')}`,
        'QUERY_VALIDATION_ERROR',
        false
      );
    }

    // Sanitize project ID if provided
    let sanitizedProjectId = projectId;
    if (projectId) {
      try {
        sanitizedProjectId = sanitize.projectId(projectId);
      } catch (error) {
        throw new MCPServerError(
          `Invalid project ID: ${error instanceof Error ? error.message : error}`,
          'INVALID_PROJECT_ID',
          false
        );
      }
    }

    try {
      let targetProjectId = projectId;

      // If no project ID provided, use active project
      if (!targetProjectId) {
        const activeProject = await this.projectService.getActiveProject();
        if (activeProject) {
          targetProjectId = activeProject.id;
        }
      }

      // Create enhanced search filters
      const filters = {
        limit,
        fullContent: true,
        enhancedHighlights,
        query: sanitizedQuery.sanitized
      };

      let results;
      if (targetProjectId) {
        results = await this.projectService.searchProject(targetProjectId, sanitizedQuery.sanitized, filters);
      } else {
        results = await this.projectService.searchAllProjects(sanitizedQuery.sanitized, filters);
      }

      // Log data access for security monitoring
      const { log } = await import('./secure-logger.js');
      log.dataAccess('search', targetProjectId || 'all_projects', true, {
        query: sanitizedQuery.sanitized,
        resultCount: results.length,
        projectId: targetProjectId,
        originalQuery: query !== sanitizedQuery.sanitized ? query : undefined
      });

      const searchType = targetProjectId ? 'project-specific' : 'cross-project';
      const projectName = targetProjectId ?
        (await this.projectService.getActiveProject())?.name || targetProjectId :
        'all projects';

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              query: sanitizedQuery.sanitized,
              originalQuery: query !== sanitizedQuery.sanitized ? query : undefined,
              sanitizationWarnings: sanitizedQuery.warnings.length > 0 ? sanitizedQuery.warnings : undefined,
              searchType,
              projectId: targetProjectId,
              projectName,
              results: results.map(result => ({
                id: result.id,
                title: result.title,
                content: result.content, // Full content, not truncated
                documentType: result.documentType,
                projectId: result.projectId,
                projectName: result.projectName,
                score: result.score,
                highlights: result.highlights,
                metadata: result.metadata
              })),
              total: results.length,
              timestamp: new Date().toISOString()
            }, null, 2)
          }
        ]
      };

    } catch (error) {
      throw new MCPServerError(
        `Full content search failed: ${error instanceof Error ? error.message : error}`,
        'SEARCH_FULL_CONTENT_ERROR',
        true,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Start the MCP server
   */
  async start(): Promise<void> {
    if (!this.isInitialized) {
      throw new MCPServerError(
        'Server must be initialized before starting',
        'SERVER_NOT_INITIALIZED',
        false
      );
    }

    try {
      const transport = new StdioServerTransport();
      await this.server.connect(transport);
      console.log('🌐 MCP Server started and listening for connections');

      // Keep the process alive to handle MCP requests
      // The server.connect() should handle this, but we'll add a safeguard
      process.stdin.resume();

    } catch (error) {
      throw new MCPServerError(
        `Failed to start server: ${error instanceof Error ? error.message : error}`,
        'SERVER_START_ERROR',
        false,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Shutdown the MCP server gracefully with comprehensive cleanup
   */
  async shutdown(): Promise<void> {
    try {
      console.log('🛑 Shutting down MCP Server...');

      // Step 1: Mark as shutting down
      this.isInitialized = false;

      // Step 2: Close server connection with timeout
      console.log('🔌 Closing server connection...');
      try {
        await Promise.race([
          this.server.close(),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Server close timeout')), 5000)
          )
        ]);
        console.log('✅ Server connection closed');
      } catch (error) {
        console.warn('⚠️  Server close warning:', error);
        // Continue with cleanup even if server close fails
      }

      // Step 3: Clear project cache and cleanup services
      console.log('🧹 Cleaning up services...');
      if (this.projectService) {
        this.projectService.clearCache();
        console.log('✅ Project cache cleared');
      }

      // Step 4: Cleanup auth tokens (if applicable)
      try {
        // Auth service cleanup would go here if needed
        console.log('✅ Authentication cleanup completed');
      } catch (error) {
        console.warn('⚠️  Authentication cleanup warning:', error);
      }

      console.log('✅ MCP Server shutdown completed successfully');

    } catch (error) {
      console.error('❌ Error during server shutdown:', error);
      throw new MCPServerError(
        `Server shutdown failed: ${error instanceof Error ? error.message : error}`,
        'SERVER_SHUTDOWN_ERROR',
        false,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Perform comprehensive health check
   */
  async performHealthCheck(): Promise<{
    status: 'healthy' | 'unhealthy';
    checks: {
      initialized: boolean;
      authenticated: boolean;
      opensearchConnected: boolean;
      projectsAccessible: boolean;
    };
    details: {
      activeProject: string | null;
      projectCount: number;
      lastError?: string;
    };
  }> {
    const checks = {
      initialized: this.isInitialized,
      authenticated: false,
      opensearchConnected: false,
      projectsAccessible: false
    };

    const details = {
      activeProject: null as string | null,
      projectCount: 0,
      lastError: undefined as string | undefined
    };

    try {
      // Check authentication
      checks.authenticated = this.authService.isAuthenticated();

      // Check OpenSearch connection
      try {
        await this.openSearchClient.validateConnection();
        checks.opensearchConnected = true;
      } catch (error) {
        details.lastError = `OpenSearch: ${error instanceof Error ? error.message : error}`;
      }

      // Check project access
      try {
        const projects = await this.projectService.listAvailableProjects();
        checks.projectsAccessible = true;
        details.projectCount = projects.length;

        const activeProject = await this.projectService.getActiveProject();
        details.activeProject = activeProject?.name || null;
      } catch (error) {
        details.lastError = `Projects: ${error instanceof Error ? error.message : error}`;
      }

    } catch (error) {
      details.lastError = `Health check: ${error instanceof Error ? error.message : error}`;
    }

    const isHealthy = checks.initialized &&
      checks.authenticated &&
      checks.opensearchConnected &&
      checks.projectsAccessible;

    return {
      status: isHealthy ? 'healthy' : 'unhealthy',
      checks,
      details
    };
  }



  /**
   * Handle switch_backend tool
   */
  private async handleSwitchBackend(args: any): Promise<any> {
    const { backendType, config } = args;

    if (!backendType) {
      throw new MCPServerError(
        'Backend type is required',
        'MISSING_BACKEND_TYPE',
        false
      );
    }

    if (!['opensearch', 'bedrock'].includes(backendType)) {
      throw new MCPServerError(
        'Invalid backend type. Must be "opensearch" or "bedrock"',
        'INVALID_BACKEND_TYPE',
        false
      );
    }

    try {
      let backendConfig;
      const currentBackendInfo = this.projectService.getBackendInfo();

      if (backendType === 'bedrock') {
        if (!config?.knowledgeBaseId || !config?.region) {
          throw new MCPServerError(
            'Bedrock backend requires knowledgeBaseId and region in config',
            'MISSING_BEDROCK_CONFIG',
            false
          );
        }

        backendConfig = {
          type: 'bedrock' as const,
          bedrock: {
            knowledgeBaseId: config.knowledgeBaseId,
            region: config.region,
            credentials: config.credentials
          }
        };
      } else {
        // OpenSearch backend
        if (!this.config.openSearch) {
          throw new MCPServerError(
            'OpenSearch backend is not configured. Please ensure OPENSEARCH_ENDPOINT and OPENSEARCH_COLLECTION_NAME environment variables are set.',
            'OPENSEARCH_NOT_CONFIGURED',
            false
          );
        }

        backendConfig = {
          type: 'opensearch' as const,
          opensearch: this.config.openSearch
        };
      }

      // Switch the backend
      await this.projectService.switchBackend(backendConfig);

      // Clear active project since it may not exist in the new backend
      const newBackendInfo = this.projectService.getBackendInfo();

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: true,
              message: `Successfully switched to ${backendType} backend`,
              previousBackend: currentBackendInfo.type,
              currentBackend: backendType,
              backendHealthy: newBackendInfo.isHealthy,
              note: 'Active project has been cleared. Use set_active_project to select a project.',
              timestamp: new Date().toISOString()
            }, null, 2)
          }
        ]
      };

    } catch (error) {
      // Provide more specific error messages based on the error type
      let errorMessage = `Failed to switch backend: ${error instanceof Error ? error.message : error}`;
      let userFriendlyMessage = errorMessage;

      if (error instanceof Error) {
        if (error.message.includes('Forbidden') || error.message.includes('403')) {
          userFriendlyMessage = `Failed to switch to ${backendType} backend: Access denied. Please check your AWS credentials and permissions for the ${backendType} service.`;
        } else if (error.message.includes('OPENSEARCH_NOT_CONFIGURED')) {
          userFriendlyMessage = error.message;
        } else if (error.message.includes('connection') || error.message.includes('timeout')) {
          userFriendlyMessage = `Failed to switch to ${backendType} backend: Connection failed. Please check your network connection and service availability.`;
        }
      }

      throw new MCPServerError(
        userFriendlyMessage,
        'SWITCH_BACKEND_ERROR',
        true,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Handle get_backend_info tool
   */
  private async handleGetBackendInfo(): Promise<any> {
    try {
      const backendInfo = this.projectService.getBackendInfo();
      const projectContext = this.projectService.getProjectContext();

      // Get health check info
      let connectionStatus = 'unknown';
      let projectCount = 0;

      try {
        const projects = await this.projectService.listAvailableProjects();
        projectCount = projects.length;
        connectionStatus = 'healthy';
      } catch (error) {
        connectionStatus = 'unhealthy';
      }

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              backend: {
                type: backendInfo.type,
                healthy: backendInfo.isHealthy,
                connectionStatus
              },
              projects: {
                total: projectCount,
                activeProject: projectContext.activeProject ? {
                  id: projectContext.activeProject.id,
                  name: projectContext.activeProject.name,
                  description: projectContext.activeProject.description
                } : null
              },
              capabilities: {
                projectSelection: true,
                crossProjectSearch: true,
                documentRetrieval: true,
                backendSwitching: true
              },
              supportedBackends: ['opensearch', 'bedrock'],
              timestamp: new Date().toISOString()
            }, null, 2)
          }
        ]
      };

    } catch (error) {
      throw new MCPServerError(
        `Failed to get backend info: ${error instanceof Error ? error.message : error}`,
        'GET_BACKEND_INFO_ERROR',
        true,
        error instanceof Error ? error : new Error(String(error))
      );
    }
  }

  /**
   * Validate document type
   */
  private isValidDocumentType(type: string): boolean {
    return Object.values(DocumentType).includes(type as DocumentType);
  }

  /**
   * Map ProjectKB errors to MCP error codes
   */
  private mapProjectKBErrorToMCP(error: ProjectKBError): ErrorCode {
    switch (error.category) {
      case 'validation':
        return ErrorCode.InvalidParams;

      case 'authorization':
        return ErrorCode.InvalidRequest;

      case 'authentication':
        return ErrorCode.InvalidRequest;

      case 'project':
      case 'document':
        if (error.code.includes('NOT_FOUND')) {
          return ErrorCode.InvalidRequest;
        }
        if (error.code.includes('ACCESS_DENIED')) {
          return ErrorCode.InvalidRequest;
        }
        return ErrorCode.InternalError;

      case 'search':
        if (error.code === 'INVALID_QUERY') {
          return ErrorCode.InvalidParams;
        }
        return ErrorCode.InternalError;

      case 'network':
      case 'system':
      default:
        return ErrorCode.InternalError;
    }
  }



  /**
   * Get comprehensive server status information
   */
  getStatus(): {
    initialized: boolean;
    authenticated: boolean;
    backend: string;
    activeProject: string | null;
    uptime: number;
    version: string;
    toolsRegistered: number;
    memoryUsage: NodeJS.MemoryUsage;
  } {
    return {
      initialized: this.isInitialized,
      authenticated: this.authService.isAuthenticated(),
      backend: this.config.defaultBackend,
      activeProject: this.projectService.getProjectContext()?.activeProject?.name || null,
      uptime: process.uptime(),
      version: this.config.server.version,
      toolsRegistered: Object.keys(MCP_TOOLS).length,
      memoryUsage: process.memoryUsage()
    };
  }

  /**
   * Get the authentication service for health checks and token refresh
   */
  getAuthService(): CognitoAuth {
    return this.authService;
  }

  /**
   * Clear invalid refresh tokens and force re-authentication
   */
  clearInvalidTokens(): void {
    log.info('Clearing invalid tokens and forcing re-authentication');
    this.authService.clearInvalidRefreshToken();
    console.log('🔄 Invalid tokens cleared, will re-authenticate on next request');
  }
}