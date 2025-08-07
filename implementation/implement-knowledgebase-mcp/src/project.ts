import { ProjectInfo, SearchResult, SearchFilters, KBDocument } from './types.js';
import { KnowledgeBaseBackend, BackendConfig, BackendFactory } from './backend-factory.js';
import { ErrorLogger } from './errors.js';
import { log } from './secure-logger.js';
import { sanitize } from './sanitization.js';

/**
 * Project service error class (legacy - kept for backward compatibility)
 */
export class ProjectServiceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    public readonly details?: any
  ) {
    super(message);
    this.name = 'ProjectServiceError';
  }
}

/**
 * Project service for managing project discovery and context
 */
export class ProjectService {
  private backend: KnowledgeBaseBackend;
  private backendType: 'opensearch' | 'bedrock';
  private activeProject: ProjectInfo | null = null;
  private projectCache: Map<string, ProjectInfo> = new Map();
  private cacheExpiry: number = 5 * 60 * 1000; // 5 minutes
  private lastCacheUpdate: number = 0;
  private errorLogger: ErrorLogger;

  constructor(config: BackendConfig, credentials?: any) {
    this.backend = BackendFactory.create(config, credentials);
    this.backendType = config.type;
    this.errorLogger = ErrorLogger.getInstance();
  }

  /**
   * Discover and list all available project indexes
   */
  async listAvailableProjects(): Promise<ProjectInfo[]> {
    try {
      // Check if cache is still valid
      if (this.isCacheValid()) {
        return Array.from(this.projectCache.values());
      }

      // Ensure backend is connected
      if (!this.backend.isHealthy()) {
        await this.backend.validateConnection();
      }

      // Get projects from backend
      const projects = await this.backend.listProjects();

      // Update cache
      this.projectCache.clear();
      for (const project of projects) {
        this.projectCache.set(project.id, project);
      }

      // Update cache timestamp
      this.lastCacheUpdate = Date.now();

      return projects;

    } catch (error) {
      throw new ProjectServiceError(
        'Project discovery failed',
        'PROJECT_DISCOVERY_ERROR',
        true,
        error
      );
    }
  }



  /**
   * Set the active project for subsequent operations
   */
  async setActiveProject(projectName: string): Promise<void> {
    try {
      // SECURITY: Use secure logging with sanitized project name
      log.debug('Setting active project', {
        projectName: sanitize.projectId(projectName)
      });

      let targetProject: ProjectInfo | null = null;

      // First, try to find project using the normal approach
      try {
        // SECURITY: Use secure logging
        log.debug('Looking for project by name');
        targetProject = await this.findProjectByName(projectName);

        if (!targetProject) {
          // SECURITY: Use secure logging
          log.debug('Not found by name, trying by ID');
          targetProject = await this.findProjectById(projectName);
        }
      } catch (listError) {
        console.warn(`[DEBUG] Project listing failed, using fallback approach:`, listError);

        // Fallback: Create a minimal project info and validate by attempting a search
        targetProject = await this.validateProjectBySearch(projectName);
      }

      if (!targetProject) {
        // SECURITY: Use secure logging with sanitized project name
        log.debug('Project not found', {
          projectName: sanitize.projectId(projectName)
        });
        throw new ProjectServiceError(
          `Project not found: ${projectName}. The project may not exist or you may not have access to it.`,
          'PROJECT_NOT_FOUND',
          false
        );
      }

      // SECURITY: Use secure logging with sanitized project data
      log.debug('Found project', {
        projectName: sanitize.projectId(targetProject.name),
        projectId: sanitize.projectId(targetProject.id)
      });

      // SECURITY: Use secure logging
      log.debug('Setting as active project');

      // Update last accessed time
      targetProject.lastAccessed = new Date();
      this.projectCache.set(targetProject.id, targetProject);

      // Set as active project
      this.activeProject = targetProject;

      // SECURITY: Use secure logging with sanitized project name
      log.info('Active project set successfully', {
        projectName: sanitize.projectId(targetProject.name),
        projectId: sanitize.projectId(targetProject.id)
      });

    } catch (error) {
      // SECURITY: Use secure logging for errors
      log.error('Error in setActiveProject', {
        error: error instanceof Error ? error.message : String(error)
      });

      if (error instanceof ProjectServiceError) {
        throw error;
      }

      throw new ProjectServiceError(
        `Failed to set active project: ${projectName}`,
        'SET_ACTIVE_PROJECT_ERROR',
        true,
        error
      );
    }
  }

  /**
   * Get the currently active project
   */
  async getActiveProject(): Promise<ProjectInfo | null> {
    return this.activeProject;
  }

  /**
   * Validate access to a specific project
   */
  async validateProjectAccess(projectId: string): Promise<boolean> {
    try {
      // Check if project exists in our cache first
      if (this.projectCache.has(projectId)) {
        return true;
      }

      // Try to list projects first
      try {
        const projects = await this.backend.listProjects();
        return projects.some(project => project.id === projectId);
      } catch (listError) {
        console.warn(`Project listing failed, using search-based validation:`, listError);

        // Fallback: Try to search within the project to validate access
        try {
          // SECURITY: Sanitize project ID to prevent NoSQL injection
          const sanitizedProjectId = sanitize.projectId(projectId);
          await this.backend.searchProject(sanitizedProjectId, 'test', { limit: 1 });
          return true; // If search succeeds, we have access
        } catch (searchError) {
          console.warn(`Search-based validation also failed:`, searchError);
          return false;
        }
      }
    } catch (error) {
      // If there's an error checking project access, log it but don't fail
      console.warn(`Error validating access to project ${projectId}:`, error);
      return false;
    }
  }

  /**
   * Validate project exists by attempting a search within it (fallback method)
   */
  private async validateProjectBySearch(projectName: string): Promise<ProjectInfo | null> {
    try {
      // SECURITY: Use secure logging with sanitized project name
      log.debug('Validating project by search', {
        projectName: sanitize.projectId(projectName)
      });

      // Try to search within the project to see if it exists
      // SECURITY: Sanitize project name to prevent NoSQL injection
      const sanitizedProjectName = sanitize.projectId(projectName);
      const searchResults = await this.backend.searchProject(sanitizedProjectName, 'test', { limit: 1 });

      if (searchResults && searchResults.length >= 0) {
        // Project exists, create a minimal ProjectInfo
        const projectId = sanitizedProjectName.toLowerCase().replace(/\s+/g, '-');
        return {
          id: projectId,
          name: projectName,
          indexName: projectId,
          description: `Project: ${projectName}`,
          documentCount: undefined,
          lastAccessed: new Date(),
          knowledgeBaseId: this.backend.constructor.name === 'BedrockBackend' ?
            (this.backend as any).knowledgeBaseId : undefined,
          projectType: 'unknown',
          status: 'active',
          createdAt: undefined,
          lastUpdated: undefined,
          metadata: { project_id: projectId, name: projectName }
        };
      }

      return null;
    } catch (error) {
      console.warn(`[DEBUG] Project validation by search failed:`, error);
      return null;
    }
  }

  /**
   * Find project by name (case-insensitive)
   */
  private async findProjectByName(projectName: string): Promise<ProjectInfo | null> {
    const projects = await this.listAvailableProjects();
    const normalizedName = projectName.toLowerCase().trim();

    return projects.find(project =>
      project.name.toLowerCase() === normalizedName
    ) || null;
  }

  /**
   * Find project by ID
   */
  private async findProjectById(projectId: string): Promise<ProjectInfo | null> {
    const projects = await this.listAvailableProjects();

    return projects.find(project =>
      project.id === projectId
    ) || null;
  }



  /**
   * Get the backend instance for credential updates
   */
  getBackend(): KnowledgeBaseBackend {
    return this.backend;
  }

  /**
   * Get backend information and health status
   */
  getBackendInfo(): any {
    return {
      type: this.backendType,
      isHealthy: this.backend.isHealthy(),
      connectionStatus: this.backend.isHealthy() ? 'healthy' : 'unhealthy'
    };
  }

  /**
   * Check if project cache is still valid
   */
  private isCacheValid(): boolean {
    return (Date.now() - this.lastCacheUpdate) < this.cacheExpiry && this.projectCache.size > 0;
  }

  /**
   * Clear project cache
   */
  clearCache(): void {
    this.projectCache.clear();
    this.lastCacheUpdate = 0;
  }

  /**
   * Get project by ID from cache or fetch if needed
   */
  async getProject(projectId: string): Promise<ProjectInfo | null> {
    // SECURITY: Sanitize project ID to prevent injection attacks
    const sanitizedProjectId = sanitize.projectId(projectId);

    // Check cache first
    if (this.projectCache.has(sanitizedProjectId)) {
      return this.projectCache.get(sanitizedProjectId) || null;
    }

    // Try to fetch from backend
    try {
      const projects = await this.backend.listProjects();
      const project = projects.find(p => p.id === sanitizedProjectId);
      if (project) {
        this.projectCache.set(sanitizedProjectId, project);
      }
      return project || null;
    } catch (error) {
      return null;
    }
  }

  /**
   * Refresh project information
   */
  async refreshProject(projectId: string): Promise<ProjectInfo | null> {
    try {
      // Clear cache and refetch
      this.projectCache.delete(projectId);
      return await this.getProject(projectId);
    } catch (error) {
      return null;
    }
  }

  /**
   * Get project context information for search operations
   */
  getProjectContext(): { activeProject: ProjectInfo | null; availableProjects: string[]; backendType: string } {
    return {
      activeProject: this.activeProject,
      availableProjects: Array.from(this.projectCache.keys()),
      backendType: this.backendType
    };
  }

  /**
   * Switch to a different backend
   */
  async switchBackend(config: BackendConfig): Promise<void> {
    const previousBackend = this.backendType;
    let newBackend: KnowledgeBaseBackend | null = null;

    try {
      // Create the new backend
      newBackend = BackendFactory.create(config);

      // Validate the new backend connection before switching
      // SECURITY: Use secure logging with sanitized backend type
      log.info('Validating connection to backend', {
        backendType: config.type
      });
      const isHealthy = await newBackend.validateConnection();
      if (!isHealthy) {
        throw new ProjectServiceError(
          `Failed to connect to ${config.type} backend - connection validation failed`,
          'BACKEND_CONNECTION_ERROR',
          true
        );
      }

      // If validation succeeds, switch to the new backend
      this.backend = newBackend;
      this.backendType = config.type;
      this.clearCache();

      // Clear active project since it may not exist in the new backend
      this.activeProject = null;

      // SECURITY: Use secure logging with sanitized backend types
      log.info('Successfully switched backend', {
        previousBackend,
        newBackend: config.type
      });

    } catch (error) {
      // If switching failed, ensure we don't leave the system in a broken state
      if (newBackend && this.backend !== newBackend) {
        // The switch failed, so we're still on the previous backend
        console.warn(`Backend switch from ${previousBackend} to ${config.type} failed, remaining on ${previousBackend}`);
      }

      // Provide more specific error messages
      let errorMessage = `Failed to switch to ${config.type} backend`;
      if (error instanceof Error) {
        if (error.message.includes('Forbidden') || error.message.includes('403')) {
          errorMessage += ': Access denied. Please check your AWS credentials and permissions.';
        } else if (error.message.includes('timeout') || error.message.includes('connection')) {
          errorMessage += ': Connection failed. Please check network connectivity and service availability.';
        } else {
          errorMessage += `: ${error.message}`;
        }
      }

      throw new ProjectServiceError(
        errorMessage,
        'BACKEND_SWITCH_ERROR',
        true,
        error
      );
    }
  }

  /**
   * Search within a specific project using the current backend
   */
  async searchProject(projectId: string, query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    try {
      // DEBUG: Log the query being processed in project service
      console.log(`[DEBUG] ProjectService.searchProject called with query: "${query}", projectId: "${projectId}"`);
      
      // SECURITY: Sanitize inputs to prevent NoSQL injection
      const sanitizedProjectId = sanitize.projectId(projectId);
      const sanitizedQuery = sanitize.searchQuery(query);
      
      console.log(`[DEBUG] ProjectService sanitization result:`, {
        original: sanitizedQuery.original,
        sanitized: sanitizedQuery.sanitized,
        blocked: sanitizedQuery.blocked,
        warnings: sanitizedQuery.warnings
      });

      if (sanitizedQuery.blocked) {
        console.log(`[DEBUG] ProjectService blocking query due to: ${sanitizedQuery.warnings.join(', ')}`);
        throw new ProjectServiceError(
          `Invalid search query: ${sanitizedQuery.warnings.join(', ')}`,
          'INVALID_QUERY',
          false
        );
      }

      return await this.backend.searchProject(sanitizedProjectId, sanitizedQuery.sanitized, filters);
    } catch (error) {
      throw new ProjectServiceError(
        `Search failed for project ${projectId}`,
        'PROJECT_SEARCH_ERROR',
        true,
        error
      );
    }
  }

  /**
   * Search across all projects using the current backend
   */
  async searchAllProjects(query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    try {
      // DEBUG: Log the query being processed in project service
      console.log(`[DEBUG] ProjectService.searchAllProjects called with query: "${query}"`);
      
      // SECURITY: Sanitize query to prevent NoSQL injection
      const sanitizedQuery = sanitize.searchQuery(query);
      
      console.log(`[DEBUG] ProjectService sanitization result:`, {
        original: sanitizedQuery.original,
        sanitized: sanitizedQuery.sanitized,
        blocked: sanitizedQuery.blocked,
        warnings: sanitizedQuery.warnings
      });

      if (sanitizedQuery.blocked) {
        console.log(`[DEBUG] ProjectService blocking query due to: ${sanitizedQuery.warnings.join(', ')}`);
        throw new ProjectServiceError(
          `Invalid search query: ${sanitizedQuery.warnings.join(', ')}`,
          'INVALID_QUERY',
          false
        );
      }

      return await this.backend.searchAllProjects(sanitizedQuery.sanitized, filters);
    } catch (error) {
      throw new ProjectServiceError(
        'Cross-project search failed',
        'SEARCH_ALL_ERROR',
        true,
        error
      );
    }
  }

  /**
   * Get a specific document using the current backend
   */
  async getDocument(projectId: string, documentId: string): Promise<KBDocument> {
    try {
      // SECURITY: Sanitize inputs to prevent NoSQL injection
      const sanitizedProjectId = sanitize.projectId(projectId);
      const sanitizedDocumentId = sanitize.documentId(documentId);

      return await this.backend.getDocument(sanitizedProjectId, sanitizedDocumentId);
    } catch (error) {
      throw new ProjectServiceError(
        `Failed to get document ${sanitize.documentId(documentId)}`,
        'GET_DOCUMENT_ERROR',
        true,
        error
      );
    }
  }



  /**
   * Get the current backend instance
   */
  getCurrentBackend(): KnowledgeBaseBackend {
    return this.backend;
  }
}