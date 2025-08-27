import { OpenSearchClient, OpenSearchError } from './opensearch.js';
import { ProjectService, ProjectServiceError } from './project.js';
import { 
  SearchResult, 
  SearchFilters, 
  KBDocument, 
  DocumentType, 
  ProjectInfo 
} from './types.js';
import { ISearchService } from './interfaces/index.js';
import { 
  SearchError, 
  ValidationError,
  ErrorClassifier, 
  RetryManager, 
  ErrorCategory,
  ErrorLogger,
  GracefulDegradation 
} from './errors.js';
import { log, secureLogger, AuditEventType } from './secure-logger.js';
import { sanitize } from './sanitization.js';

/**
 * Search service error class (legacy - kept for backward compatibility)
 */
export class SearchServiceError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    public readonly details?: any
  ) {
    super(message);
    this.name = 'SearchServiceError';
  }
}

/**
 * Search result ranking configuration
 */
interface RankingConfig {
  titleBoost: number;
  contentBoost: number;
  metadataBoost: number;
  recentnessBoost: number;
  documentTypeWeights: Record<DocumentType, number>;
}

/**
 * Search service for project-specific and cross-project search operations
 */
export class SearchService implements ISearchService {
  private openSearchClient: OpenSearchClient;
  private projectService: ProjectService;
  private rankingConfig: RankingConfig;
  private retryManager: RetryManager;
  private errorLogger: ErrorLogger;

  constructor(openSearchClient: OpenSearchClient, projectService: ProjectService) {
    this.openSearchClient = openSearchClient;
    this.projectService = projectService;
    this.retryManager = RetryManager.getInstance();
    this.errorLogger = ErrorLogger.getInstance();
    
    // Default ranking configuration
    this.rankingConfig = {
      titleBoost: 3.0,
      contentBoost: 2.0,
      metadataBoost: 2.0,
      recentnessBoost: 1.2,
      documentTypeWeights: {
        [DocumentType.BRD]: 1.5,
        [DocumentType.ARCHITECTURE]: 1.4,
        [DocumentType.API_SPEC]: 1.3,
        [DocumentType.TECHNICAL_DOC]: 1.2,
        [DocumentType.USER_GUIDE]: 1.1,
        [DocumentType.OTHER]: 1.0
      }
    };
  }

  /**
   * Search within a specific project's knowledge base
   */
  async searchProject(
    projectId: string, 
    query: string, 
    filters?: SearchFilters
  ): Promise<SearchResult[]> {
    return await secureLogger.measurePerformance('search.searchProject', async () => {
      try {
        // SECURITY: Sanitize data before logging
        log.debug('Starting project search', { 
          projectId: sanitize.projectId(projectId), 
          query: sanitize.searchQuery(query).sanitized, 
          filters 
        });
        
        // Validate inputs
        this.validateSearchInputs(query, projectId);

        // Validate project access
        const hasAccess = await this.projectService.validateProjectAccess(projectId);
        if (!hasAccess) {
          const error = new SearchServiceError(
            `Access denied to project: ${projectId}`,
            'PROJECT_ACCESS_DENIED',
            false
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'project_search', 'failure', 'medium', {
            userId: undefined, // Will be filled by audit system
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Project search access denied',
            data: { 
              reason: 'access_denied', 
              query: sanitize.searchQuery(query).sanitized,
              projectId: sanitize.projectId(projectId)
            }
          });
          
          throw error;
        }

        // Get project information for context
        const projectInfo = await this.projectService.getProject(projectId);
        if (!projectInfo) {
          const error = new SearchServiceError(
            `Project not found: ${projectId}`,
            'PROJECT_NOT_FOUND',
            false
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'project_search', 'failure', 'low', {
            userId: undefined, // Will be filled by audit system
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Project not found during search',
            data: { 
              reason: 'project_not_found', 
              query: sanitize.searchQuery(query).sanitized,
              projectId: sanitize.projectId(projectId)
            }
          });
          
          throw error;
        }

        // Prepare search filters with project constraint
        const searchFilters: SearchFilters = {
          ...filters,
          projectId: projectId,
          limit: filters?.limit || 20
        };

        // Execute search with optimized query
        const optimizedQuery = this.optimizeQuery(query);
        const searchOptions = {
          query: optimizedQuery,
          filters: searchFilters,
          highlight: true,
          size: searchFilters.limit,
          from: searchFilters.offset || 0
        };

        // SECURITY: Sanitize data before logging
        log.debug('Executing OpenSearch query', { 
          projectId: sanitize.projectId(projectId), 
          optimizedQuery: sanitize.searchQuery(optimizedQuery).sanitized, 
          searchOptions: {
            ...searchOptions,
            query: sanitize.searchQuery(searchOptions.query).sanitized
          }
        });

        const results = await this.openSearchClient.search(searchOptions);

        // SECURITY: Sanitize data before logging
        log.info('Project search completed', {
          projectId: sanitize.projectId(projectId),
          query: sanitize.searchQuery(query).sanitized,
          resultCount: results.length,
          filters: {
            ...searchFilters,
            projectId: sanitize.projectId(searchFilters.projectId || '')
          }
        });

        // Enhance results with project context and ranking
        const enhancedResults = this.enhanceSearchResults(results, projectInfo, query);

        // Apply custom ranking and sorting
        const rankedResults = this.rankSearchResults(enhancedResults, query);

        // Format results for Kiro display
        const formattedResults = this.formatResultsForKiro(rankedResults);

        // SECURITY: Use secure audit logging with sanitized data
        log.audit(AuditEventType.DATA_ACCESS, 'project_search', 'success', 'low', {
          userId: undefined, // Will be filled by audit system
          resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
          message: 'Project search completed successfully',
          data: { 
            query: sanitize.searchQuery(query).sanitized, 
            resultCount: formattedResults.length,
            projectId: sanitize.projectId(projectId),
            filters: {
              ...searchFilters,
              projectId: sanitize.projectId(searchFilters.projectId || '')
            }
          }
        });

        return formattedResults;

      } catch (error) {
        // SECURITY: Sanitize data before logging
        log.error('Project search failed', {
          projectId: sanitize.projectId(projectId),
          query: sanitize.searchQuery(query).sanitized,
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined
        });

        if (error instanceof SearchServiceError) {
          throw error;
        }

        if (error instanceof OpenSearchError) {
          const searchError = new SearchServiceError(
            `Search failed: ${error.message}`,
            'SEARCH_EXECUTION_ERROR',
            error.retryable,
            error
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'project_search', 'failure', 'medium', {
            userId: undefined,
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Project search failed with OpenSearch error',
            data: { 
              query: sanitize.searchQuery(query).sanitized, 
              projectId: sanitize.projectId(projectId),
              error: error.message,
              errorCode: error.code
            }
          });
          
          throw searchError;
        }

        if (error instanceof ProjectServiceError) {
          const searchError = new SearchServiceError(
            `Project validation failed: ${error.message}`,
            'PROJECT_VALIDATION_ERROR',
            error.retryable,
            error
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'project_search', 'failure', 'medium', {
            userId: undefined,
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Project search failed with project validation error',
            data: { 
              query: sanitize.searchQuery(query).sanitized, 
              projectId: sanitize.projectId(projectId),
              error: error.message,
              errorCode: error.code
            }
          });
          
          throw searchError;
        }

        const searchError = new SearchServiceError(
          'Search operation failed',
          'SEARCH_ERROR',
          true,
          error
        );
        
        // SECURITY: Use secure audit logging with sanitized data
        log.audit(AuditEventType.DATA_ACCESS, 'project_search', 'failure', 'medium', {
          userId: undefined, // Will be filled by audit system
          resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
          message: 'Project search failed',
          data: { 
            query: sanitize.searchQuery(query).sanitized, 
            projectId: sanitize.projectId(projectId),
            error: error instanceof Error ? error.message : String(error)
          }
        });
        
        throw searchError;
      }
    }, { projectId });
  }

  /**
   * Search across all accessible projects with graceful degradation
   */
  async searchAllProjects(query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    return await secureLogger.measurePerformance('search.searchAllProjects', async () => {
      return await this.retryManager.executeWithRetry(
        async () => {
          // SECURITY: Sanitize query before logging
          const sanitizedQuery = sanitize.searchQuery(query);
          log.debug('Starting cross-project search', { 
            query: sanitizedQuery.sanitized,
            originalQueryBlocked: sanitizedQuery.blocked,
            sanitizationWarnings: sanitizedQuery.warnings.length > 0 ? sanitizedQuery.warnings : undefined,
            filters 
          });
          
          // Validate inputs
          this.validateSearchInputs(query);

          // Get all available projects
          const availableProjects = await this.projectService.listAvailableProjects();
          
          // SECURITY: Sanitize data before logging
          log.info('Cross-project search initiated', {
            query: sanitize.searchQuery(query).sanitized,
            projectCount: availableProjects.length,
            filters
          });
          
          if (availableProjects.length === 0) {
            log.warn('No accessible projects found for cross-project search');
            return [];
          }

          // Prepare search filters for cross-project search
          const searchFilters: SearchFilters = {
            ...filters,
            limit: filters?.limit || 50 // Higher default limit for cross-project search
          };

          // Create project operations for graceful degradation
          const projectOperations = availableProjects.map(project => ({
            projectId: project.id,
            operation: async () => {
              const projectResults = await this.searchProject(project.id, query, {
                ...searchFilters,
                limit: Math.ceil((searchFilters.limit || 50) / availableProjects.length)
              });

              // Add project identification to results
              return projectResults.map(result => ({
                ...result,
                projectId: project.id,
                projectName: project.name
              }));
            }
          }));

          // Execute with graceful degradation
          const { results: allResults, failedProjects } = await GracefulDegradation.executeCrossProjectSearch(
            projectOperations,
            'searchAllProjects'
          );

          // Log failed projects for monitoring
          if (failedProjects.length > 0) {
            log.warn('Cross-project search partial failures', {
              query: sanitize.searchQuery(query).sanitized,
              failedProjectCount: failedProjects.length,
              totalProjects: availableProjects.length,
              failedProjects: failedProjects.map(fp => ({
                projectId: fp.projectId,
                error: fp.error.message
              }))
            });
            
            console.warn(`Cross-project search: ${failedProjects.length} projects failed:`, 
              failedProjects.map(fp => `${fp.projectId}: ${fp.error.message}`));
          }

          // Apply cross-project ranking and sorting
          const rankedResults = this.rankCrossProjectResults(allResults, query);

          // Apply final limit to combined results
          const limitedResults = rankedResults.slice(0, searchFilters.limit || 50);

          // SECURITY: Sanitize data before logging
          log.info('Cross-project search completed', {
            query: sanitize.searchQuery(query).sanitized,
            totalResults: allResults.length,
            limitedResults: limitedResults.length,
            successfulProjects: availableProjects.length - failedProjects.length,
            failedProjects: failedProjects.length
          });

          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'cross_project_search', 'success', 'low', {
            userId: undefined,
            resource: 'all_accessible_projects',
            message: 'Cross-project search completed successfully',
            data: {
              query: sanitize.searchQuery(query).sanitized,
              projectCount: availableProjects.length,
              resultCount: limitedResults.length,
              failedProjectCount: failedProjects.length,
              filters: searchFilters
            }
          });

          return limitedResults;
        },
        ErrorCategory.SEARCH,
        'searchAllProjects'
      );
    });
  }

  /**
   * Get a specific document by ID
   */
  async getDocument(projectId: string, documentId: string): Promise<KBDocument> {
    return await secureLogger.measurePerformance('search.getDocument', async () => {
      try {
        // SECURITY: Sanitize IDs before logging
        log.debug('Retrieving document', { 
          projectId: sanitize.projectId(projectId), 
          documentId: sanitize.documentId(documentId) 
        });
        
        // Validate inputs
        if (!projectId?.trim()) {
          const error = new SearchServiceError(
            'Project ID is required',
            'INVALID_PROJECT_ID',
            false
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'document_access', 'failure', 'medium', {
            userId: undefined,
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Document access denied - invalid project ID',
            data: { 
              projectId: sanitize.projectId(projectId),
              documentId: sanitize.documentId(documentId),
              reason: 'invalid_project_id' 
            }
          });
          
          throw error;
        }

        if (!documentId?.trim()) {
          const error = new SearchServiceError(
            'Document ID is required',
            'INVALID_DOCUMENT_ID',
            false
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'document_access', 'failure', 'medium', {
            userId: undefined,
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Document access denied - invalid document ID',
            data: { 
              projectId: sanitize.projectId(projectId),
              documentId: sanitize.documentId(documentId),
              reason: 'invalid_document_id' 
            }
          });
          
          throw error;
        }

        // Validate project access
        const hasAccess = await this.projectService.validateProjectAccess(projectId);
        if (!hasAccess) {
          const error = new SearchServiceError(
            `Access denied to project: ${projectId}`,
            'PROJECT_ACCESS_DENIED',
            false
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'document_access', 'failure', 'medium', {
            userId: undefined,
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Document access denied',
            data: { 
              projectId: sanitize.projectId(projectId),
              documentId: sanitize.documentId(documentId),
              reason: 'access_denied' 
            }
          });
          
          throw error;
        }

        // Retrieve document from OpenSearch
        const document = await this.openSearchClient.getDocument(projectId, documentId);

        // SECURITY: Sanitize data before logging
        log.info('Document retrieved successfully', {
          projectId: sanitize.projectId(projectId),
          documentId: sanitize.documentId(documentId),
          documentType: document.documentType,
          title: document.title
        });

        // SECURITY: Use secure audit logging with sanitized data
        log.audit(AuditEventType.DATA_ACCESS, 'document_access', 'success', 'low', {
          userId: undefined,
          resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
          message: 'Document retrieved successfully',
          data: { 
            projectId: sanitize.projectId(projectId),
            documentId: sanitize.documentId(documentId),
            documentType: document.documentType,
            title: document.title
          }
        });

        return document;

      } catch (error) {
        // SECURITY: Sanitize data before logging
        log.error('Document retrieval failed', {
          projectId: sanitize.projectId(projectId),
          documentId: sanitize.documentId(documentId),
          error: error instanceof Error ? error.message : String(error),
          stack: error instanceof Error ? error.stack : undefined
        });

        if (error instanceof SearchServiceError) {
          throw error;
        }

        if (error instanceof OpenSearchError) {
          if (error.code === 'DOCUMENT_NOT_FOUND') {
            const searchError = new SearchServiceError(
              `Document not found: ${documentId} in project ${projectId}`,
              'DOCUMENT_NOT_FOUND',
              false,
              error
            );
            
            // SECURITY: Use secure audit logging with sanitized data
            log.audit(AuditEventType.DATA_ACCESS, 'document_access', 'failure', 'low', {
              userId: undefined,
              resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
              message: 'Document access failed - document not found',
              data: { 
                projectId: sanitize.projectId(projectId),
                documentId: sanitize.documentId(documentId),
                reason: 'document_not_found',
                error: error.message
              }
            });
            
            throw searchError;
          }

          const searchError = new SearchServiceError(
            `Document retrieval failed: ${error.message}`,
            'DOCUMENT_RETRIEVAL_ERROR',
            error.retryable,
            error
          );
          
          // SECURITY: Use secure audit logging with sanitized data
          log.audit(AuditEventType.DATA_ACCESS, 'document_access', 'failure', 'medium', {
            userId: undefined,
            resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
            message: 'Document access failed with project service error',
            data: { 
              projectId: sanitize.projectId(projectId),
              documentId: sanitize.documentId(documentId),
              error: error.message,
              errorCode: error.code
            }
          });
          
          throw searchError;
        }

        const searchError = new SearchServiceError(
          'Document retrieval failed',
          'DOCUMENT_ERROR',
          true,
          error
        );
        
        // SECURITY: Use secure audit logging with sanitized data
        log.audit(AuditEventType.DATA_ACCESS, 'document_access', 'failure', 'high', {
          userId: undefined,
          resource: `project_knowledge_base/${sanitize.projectId(projectId)}`,
          message: 'Document access failed with unexpected error',
          data: { 
            projectId: sanitize.projectId(projectId),
            documentId: sanitize.documentId(documentId),
            error: error instanceof Error ? error.message : String(error)
          }
        });
        
        throw searchError;
      }
    }, { projectId });
  }

  /**
   * Validate search inputs
   */
  private validateSearchInputs(query: string, projectId?: string): void {
    if (!query?.trim()) {
      throw new ValidationError(
        'Search query cannot be empty',
        'INVALID_INPUT'
      );
    }

    if (query.length > 1000) {
      throw new ValidationError(
        'Search query is too long (max 1000 characters)',
        'VALUE_OUT_OF_RANGE'
      );
    }

    if (projectId && !projectId.trim()) {
      throw new ValidationError(
        'Project ID cannot be empty',
        'INVALID_INPUT'
      );
    }
  }

  /**
   * Optimize search query for better results
   */
  private optimizeQuery(query: string): string {
    // Clean and normalize the query
    let optimizedQuery = query.trim();

    // Handle quoted phrases
    const quotedPhrases = optimizedQuery.match(/"[^"]+"/g) || [];
    
    // Remove special characters that might interfere with search
    optimizedQuery = optimizedQuery.replace(/[^\w\s".-]/g, ' ');
    
    // Normalize whitespace
    optimizedQuery = optimizedQuery.replace(/\s+/g, ' ').trim();

    // If query is very short, don't apply fuzzy matching
    if (optimizedQuery.length <= 3) {
      return optimizedQuery;
    }

    // For longer queries, we can add query expansion logic here
    // This is a placeholder for more sophisticated query optimization
    
    return optimizedQuery;
  }

  /**
   * Enhance search results with project context
   */
  private enhanceSearchResults(
    results: SearchResult[], 
    projectInfo: ProjectInfo, 
    originalQuery: string
  ): SearchResult[] {
    return results.map(result => ({
      ...result,
      projectName: projectInfo.name,
      // Add query relevance context
      metadata: {
        ...result.metadata,
        searchContext: {
          originalQuery,
          projectContext: projectInfo.name,
          searchTimestamp: new Date().toISOString()
        }
      }
    }));
  }

  /**
   * Apply custom ranking to search results
   */
  private rankSearchResults(results: SearchResult[], query: string): SearchResult[] {
    const queryTerms = query.toLowerCase().split(/\s+/).filter(term => term.length > 2);
    
    return results
      .map(result => ({
        ...result,
        score: this.calculateCustomScore(result, queryTerms)
      }))
      .sort((a, b) => b.score - a.score);
  }

  /**
   * Apply cross-project ranking to search results
   */
  private rankCrossProjectResults(results: SearchResult[], query: string): SearchResult[] {
    const queryTerms = query.toLowerCase().split(/\s+/).filter(term => term.length > 2);
    
    return results
      .map(result => ({
        ...result,
        score: this.calculateCrossProjectScore(result, queryTerms)
      }))
      .sort((a, b) => b.score - a.score);
  }

  /**
   * Calculate custom relevance score
   */
  private calculateCustomScore(result: SearchResult, queryTerms: string[]): number {
    let score = result.score || 0;

    // Apply document type weighting
    const typeWeight = this.rankingConfig.documentTypeWeights[result.documentType] || 1.0;
    score *= typeWeight;

    // Boost for title matches
    const titleLower = result.title.toLowerCase();
    const titleMatches = queryTerms.filter(term => titleLower.includes(term)).length;
    if (titleMatches > 0) {
      score *= (1 + (titleMatches / queryTerms.length) * this.rankingConfig.titleBoost);
    }

    // Boost for content matches in highlights
    if (result.highlights && result.highlights.length > 0) {
      const highlightText = result.highlights.join(' ').toLowerCase();
      const highlightMatches = queryTerms.filter(term => highlightText.includes(term)).length;
      if (highlightMatches > 0) {
        score *= (1 + (highlightMatches / queryTerms.length) * this.rankingConfig.contentBoost);
      }
    }

    // Boost for metadata matches (tags, category)
    if (result.metadata.tags) {
      const tagMatches = result.metadata.tags.filter(tag => 
        queryTerms.some(term => tag.toLowerCase().includes(term))
      ).length;
      if (tagMatches > 0) {
        score *= (1 + (tagMatches / result.metadata.tags.length) * this.rankingConfig.metadataBoost);
      }
    }

    // Apply recency boost for recent documents
    if (result.metadata.lastModified && result.metadata.lastModified instanceof Date) {
      const daysSinceModified = (Date.now() - result.metadata.lastModified.getTime()) / (1000 * 60 * 60 * 24);
      if (daysSinceModified < 30) { // Boost documents modified in last 30 days
        const recencyFactor = Math.max(0.1, 1 - (daysSinceModified / 30));
        score *= (1 + recencyFactor * (this.rankingConfig.recentnessBoost - 1));
      }
    }

    return score;
  }

  /**
   * Calculate cross-project relevance score
   */
  private calculateCrossProjectScore(result: SearchResult, queryTerms: string[]): number {
    // Start with the base score calculation
    let score = this.calculateCustomScore(result, queryTerms);

    // Additional cross-project specific adjustments
    
    // Slight boost for results from projects with more specific names matching query
    if (result.projectName) {
      const projectNameLower = result.projectName.toLowerCase();
      const projectMatches = queryTerms.filter(term => projectNameLower.includes(term)).length;
      if (projectMatches > 0) {
        score *= (1 + (projectMatches / queryTerms.length) * 0.1); // Small boost for project name relevance
      }
    }

    // Normalize scores across projects to ensure fair ranking
    // This helps prevent one project from dominating results due to different scoring scales
    score = Math.min(score, 100); // Cap maximum score

    return score;
  }

  /**
   * Format search results for optimal Kiro display
   */
  private formatResultsForKiro(results: SearchResult[]): SearchResult[] {
    return results.map(result => ({
      ...result,
      // Ensure content is properly truncated and formatted
      content: this.formatContentForDisplay(result.content, result.highlights),
      // Clean up highlights for better display
      highlights: this.cleanHighlights(result.highlights),
      // Format metadata for display
      metadata: this.formatMetadataForDisplay(result.metadata)
    }));
  }

  /**
   * Format content for optimal display in Kiro
   */
  private formatContentForDisplay(content: string, highlights?: string[]): string {
    // If we have highlights, use them as they're more relevant
    if (highlights && highlights.length > 0) {
      return highlights.join(' ... ');
    }

    // Otherwise, return a clean excerpt
    const maxLength = 300;
    if (content.length <= maxLength) {
      return content;
    }

    // Find a good breaking point near the limit
    const truncated = content.substring(0, maxLength);
    const lastSpace = truncated.lastIndexOf(' ');
    const lastSentence = truncated.lastIndexOf('.');
    
    // Break at sentence end if it's reasonably close to the limit
    if (lastSentence > maxLength * 0.8) {
      return content.substring(0, lastSentence + 1);
    }
    
    // Otherwise break at word boundary
    if (lastSpace > maxLength * 0.8) {
      return content.substring(0, lastSpace) + '...';
    }
    
    return truncated + '...';
  }

  /**
   * Clean and optimize highlights for display
   */
  private cleanHighlights(highlights?: string[]): string[] {
    if (!highlights) return [];

    return highlights
      .map(highlight => highlight.trim())
      .filter(highlight => highlight.length > 0)
      .slice(0, 3); // Limit to 3 highlights for clean display
  }

  /**
   * Format metadata for display in Kiro
   */
  private formatMetadataForDisplay(metadata: any): any {
    return {
      ...metadata,
      // Format dates for display
      lastModified: metadata.lastModified ? 
        metadata.lastModified.toLocaleDateString() : undefined,
      // Limit tags for display
      tags: metadata.tags ? metadata.tags.slice(0, 5) : undefined,
      // Clean up any internal metadata
      searchContext: undefined // Remove internal search context from display
    };
  }

  /**
   * Get search suggestions based on query and project context
   */
  async getSearchSuggestions(projectId: string, partialQuery: string): Promise<string[]> {
    // This is a placeholder for future enhancement
    // Could implement query completion based on document content, tags, etc.
    return [];
  }

  /**
   * Get search statistics for a project
   */
  async getSearchStats(projectId: string): Promise<{
    totalDocuments: number;
    documentTypes: Record<DocumentType, number>;
    lastIndexed: Date | null;
  }> {
    try {
      const stats = await this.openSearchClient.getIndexStats(projectId);
      
      // This is a simplified version - could be enhanced with more detailed stats
      return {
        totalDocuments: stats.documentCount,
        documentTypes: {
          [DocumentType.BRD]: 0,
          [DocumentType.ARCHITECTURE]: 0,
          [DocumentType.API_SPEC]: 0,
          [DocumentType.TECHNICAL_DOC]: 0,
          [DocumentType.USER_GUIDE]: 0,
          [DocumentType.OTHER]: 0
        },
        lastIndexed: null
      };
    } catch (error) {
      throw new SearchServiceError(
        `Failed to get search statistics for project ${projectId}`,
        'STATS_ERROR',
        true,
        error
      );
    }
  }

  /**
   * Update ranking configuration
   */
  updateRankingConfig(config: Partial<RankingConfig>): void {
    this.rankingConfig = {
      ...this.rankingConfig,
      ...config
    };
  }

  /**
   * Get current ranking configuration
   */
  getRankingConfig(): RankingConfig {
    return { ...this.rankingConfig };
  }
}