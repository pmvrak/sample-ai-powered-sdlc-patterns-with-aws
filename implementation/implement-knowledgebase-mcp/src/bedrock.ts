import { BedrockAgentRuntimeClient, RetrieveCommand } from '@aws-sdk/client-bedrock-agent-runtime';
import { ProjectInfo, SearchResult, KBDocument, SearchFilters, DocumentType } from './types.js';

/**
 * Bedrock Knowledge Base client for project-based knowledge retrieval
 */
export class BedrockKBClient {
  private client: BedrockAgentRuntimeClient;
  private knowledgeBaseId: string;
  private projectCache: Map<string, ProjectInfo> = new Map();
  private cacheExpiry: number = 5 * 60 * 1000; // 5 minutes
  private lastCacheUpdate: number = 0;

  constructor(config: BedrockConfig, credentials?: any) {
    // Security: Only use provided credentials, never fall back to default AWS credentials
    if (!credentials) {
      throw new Error('Bedrock client requires explicit credentials for security compliance');
    }
    
    this.client = new BedrockAgentRuntimeClient({
      region: config.region,
      credentials: credentials
    });
    this.knowledgeBaseId = config.knowledgeBaseId;
  }

  /**
   * Sanitize error messages to prevent credential exposure
   */
  private sanitizeErrorMessage(error: any): string {
    if (!error) return 'Unknown error occurred';
    
    let message = error.message || error.toString();
    
    // Remove potential credential information
    message = message.replace(/credentials?[^,\s]*/gi, '[CREDENTIALS_REDACTED]');
    message = message.replace(/password[^,\s]*/gi, '[PASSWORD_REDACTED]');
    message = message.replace(/token[^,\s]*/gi, '[TOKEN_REDACTED]');
    message = message.replace(/key[^,\s]*/gi, '[KEY_REDACTED]');
    message = message.replace(/secret[^,\s]*/gi, '[SECRET_REDACTED]');
    
    // Remove AWS access key patterns
    message = message.replace(/AKIA[0-9A-Z]{16}/g, '[AWS_ACCESS_KEY_REDACTED]');
    message = message.replace(/[A-Za-z0-9/+=]{40}/g, '[AWS_SECRET_REDACTED]');
    
    return message;
  }

  async listProjects(): Promise<ProjectInfo[]> {
    try {
      if (this.isCacheValid()) {
        return Array.from(this.projectCache.values());
      }

      // Use a more specific query that targets metadata.json files
      // Add retry logic for Bedrock API calls
      let lastError: any;
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          const response = await this.client.send(new RetrieveCommand({
            knowledgeBaseId: this.knowledgeBaseId,
            retrievalQuery: { text: 'metadata.json project_id name description' },
            retrievalConfiguration: {
              vectorSearchConfiguration: {
                numberOfResults: 20,
                overrideSearchType: 'SEMANTIC'
              }
            }
          }));

          const projects = new Map<string, ProjectInfo>();
          for (const result of response.retrievalResults || []) {
            const projectInfo = this.extractProjectFromResult(result);
            if (projectInfo) {
              projects.set(projectInfo.id, projectInfo);
              this.projectCache.set(projectInfo.id, projectInfo);
            }
          }

          this.lastCacheUpdate = Date.now();
          return Array.from(projects.values()).sort((a, b) => a.name.localeCompare(b.name));

        } catch (error: any) {
          lastError = error;
          
          // Import secure logger
          const { log } = await import('./secure-logger.js');
          log.warn('Bedrock listProjects attempt failed', {
            attempt,
            error: this.sanitizeErrorMessage(error),
            errorName: error.name
          });
          
          // If it's an InternalServerException, wait before retrying
          if (error.name === 'InternalServerException' && attempt < 3) {
            await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
            continue;
          }
          
          // If it's not retryable or we've exhausted attempts, break
          if (attempt === 3) {
            break;
          }
        }
      }

      // If all attempts failed, try fallback approach
      const { log } = await import('./secure-logger.js');
      log.warn('Primary project discovery failed, trying fallback approach', {
        error: this.sanitizeErrorMessage(lastError)
      });
      return await this.listProjectsFallback();

    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.error('Failed to list projects from Bedrock KB', {
        error: this.sanitizeErrorMessage(error)
      });
      throw new BedrockKBError('Failed to discover projects', 'PROJECT_DISCOVERY_ERROR', true, error);
    }
  }

  async searchProject(projectId: string, query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    try {
      // SECURITY: Sanitize user query before processing
      const { sanitize } = await import('./sanitization.js');
      const sanitizedQuery = sanitize.searchQuery(query);
      
      if (sanitizedQuery.blocked) {
        throw new BedrockKBError(
          `Invalid search query: ${sanitizedQuery.warnings.join(', ')}`,
          'INVALID_QUERY',
          false
        );
      }
      
      const projectQuery = await this.buildProjectQuery(projectId, sanitizedQuery.sanitized);
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: projectQuery },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: filters?.limit || 10,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));

      return this.formatSearchResults(response.retrievalResults || [], projectId, filters);
    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.error('Bedrock project search failed', {
        projectId,
        error: this.sanitizeErrorMessage(error)
      });
      throw new BedrockKBError(`Search failed for project ${projectId}`, 'SEARCH_ERROR', true, error);
    }
  }

  async searchAllProjects(query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    try {
      // DEBUG: Log the query being processed in Bedrock backend
      console.log(`[DEBUG] BedrockKB.searchAllProjects called with query: "${query}"`);
      
      // SECURITY: Sanitize user query before processing
      const { sanitize } = await import('./sanitization.js');
      const sanitizedQuery = sanitize.searchQuery(query);
      
      console.log(`[DEBUG] BedrockKB sanitization result:`, {
        original: sanitizedQuery.original,
        sanitized: sanitizedQuery.sanitized,
        blocked: sanitizedQuery.blocked,
        warnings: sanitizedQuery.warnings
      });
      
      if (sanitizedQuery.blocked) {
        console.log(`[DEBUG] BedrockKB blocking query due to: ${sanitizedQuery.warnings.join(', ')}`);
        throw new BedrockKBError(
          `Invalid search query: ${sanitizedQuery.warnings.join(', ')}`,
          'INVALID_QUERY',
          false
        );
      }
      
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: sanitizedQuery.sanitized }, // ← NOW USING SANITIZED INPUT
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: filters?.limit || 20,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));

      return this.formatSearchResults(response.retrievalResults || [], null, filters);
    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.error('Bedrock cross-project search failed', {
        error: this.sanitizeErrorMessage(error)
      });
      throw new BedrockKBError('Cross-project search failed', 'SEARCH_ALL_ERROR', true, error);
    }
  }

  async getDocument(projectId: string, documentId: string): Promise<KBDocument> {
    const { log } = await import('./secure-logger.js');
    const { sanitize } = await import('./sanitization.js');
    
    // SECURITY: Sanitize document ID to prevent NoSQL injection
    const sanitizedDocumentId = sanitize.documentId(documentId);
    const sanitizedProjectId = sanitize.projectId(projectId);
    
    try {
      
      log.debug('Attempting to retrieve document', { 
        documentId: sanitizedDocumentId, 
        projectId: sanitizedProjectId 
      });
      
      // Simplified approach: Use semantic search with the sanitized document ID
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: `"${sanitizedDocumentId}"` },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 10,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));

      const results = response.retrievalResults || [];
      
      if (results.length === 0) {
        throw new BedrockKBError(`Document not found: ${sanitizedDocumentId}`, 'DOCUMENT_NOT_FOUND', false);
      }

      // Look for exact chunk ID match first
      let bestMatch = results.find(result => {
        const chunkId = this.extractChunkIdFromMetadata(result);
        return chunkId === sanitizedDocumentId;
      });

      // If no exact match, use the most relevant result
      if (!bestMatch) {
        log.debug('No exact chunk match found, using most relevant result');
        bestMatch = results[0];
      } else {
        log.debug('Found exact chunk match');
      }

      return this.formatDocument(bestMatch, projectId);
      
    } catch (error) {
      if (error instanceof BedrockKBError) {
        throw error;
      }
      const { log } = await import('./secure-logger.js');
      log.error('Bedrock document retrieval failed', {
        documentId,
        projectId,
        error: this.sanitizeErrorMessage(error)
      });
      throw new BedrockKBError(`Failed to retrieve document ${sanitizedDocumentId}`, 'DOCUMENT_RETRIEVAL_ERROR', true, error);
    }
  }

  async validateConnection(): Promise<boolean> {
    try {
      await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: 'test' },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 1
          }
        }
      }));
      return true;
    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.error('Bedrock KB connection validation failed', {
        error: this.sanitizeErrorMessage(error)
      });
      return false;
    }
  }

  isHealthy(): boolean {
    return !!this.client && !!this.knowledgeBaseId;
  }

  clearCache(): void {
    this.projectCache.clear();
    this.lastCacheUpdate = 0;
  }

  /**
   * Update AWS credentials and recreate client
   */
  updateCredentials(credentials: any): void {
    this.client = new BedrockAgentRuntimeClient({
      region: this.client.config.region,
      credentials: credentials
    });
  }

  /**
   * Strategy 1: Try to retrieve document by exact chunk ID
   */
  private async getDocumentByChunkId(chunkId: string): Promise<any[]> {
    try {
      const { sanitize } = await import('./sanitization.js');
      
      // SECURITY: Sanitize chunk ID to prevent NoSQL injection
      const sanitizedChunkId = sanitize.documentId(chunkId);
      
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: `chunkId:${sanitizedChunkId}` },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 5,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));
      
      return response.retrievalResults || [];
    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.warn('Chunk ID retrieval failed', { 
        chunkId, 
        error: this.sanitizeErrorMessage(error) 
      });
      return [];
    }
  }

  /**
   * Strategy 2: Try to retrieve document using project and document query
   */
  private async getDocumentByQuery(projectId: string, documentId: string): Promise<any[]> {
    try {
      const documentQuery = await this.buildDocumentQuery(projectId, documentId);
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: documentQuery },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 5,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));
      
      return response.retrievalResults || [];
    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.warn('Document query retrieval failed', { 
        documentId, 
        error: this.sanitizeErrorMessage(error) 
      });
      return [];
    }
  }

  /**
   * Strategy 3: Try broader search using just the document ID
   */
  private async getDocumentByBroadSearch(documentId: string): Promise<any[]> {
    try {
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: documentId },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 10,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));
      
      return response.retrievalResults || [];
    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.warn('Broad search retrieval failed', { 
        documentId, 
        error: this.sanitizeErrorMessage(error) 
      });
      return [];
    }
  }

  /**
   * Find the best matching document from results
   */
  private async findBestDocumentMatch(results: any[], targetDocumentId: string): Promise<any> {
    // First, try to find exact chunk ID match
    for (const result of results) {
      const chunkId = result.metadata?.chunkId || result.metadata?.['chunkId'];
      if (chunkId === targetDocumentId) {
        const { log } = await import('./secure-logger.js');
        log.debug('Found exact chunk ID match', { chunkId });
        return result;
      }
    }
    
    // If no exact match, look for partial matches in metadata
    for (const result of results) {
      const sourceUri = result.metadata?.['x-amz-bedrock-kb-source-uri'] as string;
      if (sourceUri && typeof sourceUri === 'string' && sourceUri.includes(targetDocumentId)) {
        const { log } = await import('./secure-logger.js');
        log.debug('Found source URI match', { sourceUri: sourceUri.substring(0, 100) + '...' });
        return result;
      }
    }
    
    // If still no match, return the first result (highest relevance score)
    const { log } = await import('./secure-logger.js');
    log.debug('No exact match found, returning highest relevance result');
    return results[0];
  }

  /**
   * Fallback method to discover projects using search results
   */
  private async listProjectsFallback(): Promise<ProjectInfo[]> {
    try {
      // Use a broad search to find any project-related content
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: 'project' },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 50,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));

      const projects = new Map<string, ProjectInfo>();
      
      // Extract projects from source URIs
      for (const result of response.retrievalResults || []) {
        const sourceUri = result.metadata?.['x-amz-bedrock-kb-source-uri'] as string;
        if (sourceUri && typeof sourceUri === 'string' && sourceUri.includes('/projects/')) {
          const projectMatch = sourceUri.match(/\/projects\/([^\/]+)\//);
          if (projectMatch) {
            const projectId = projectMatch[1];
            if (!projects.has(projectId)) {
              const projectInfo: ProjectInfo = {
                id: projectId,
                name: this.formatProjectName(projectId),
                indexName: this.knowledgeBaseId,
                description: `Project: ${projectId}`,
                documentCount: undefined,
                lastAccessed: undefined,
                knowledgeBaseId: this.knowledgeBaseId,
                projectType: 'unknown',
                status: 'active',
                createdAt: undefined,
                lastUpdated: undefined,
                metadata: { project_id: projectId }
              };
              projects.set(projectId, projectInfo);
              this.projectCache.set(projectId, projectInfo);
            }
          }
        }
      }

      this.lastCacheUpdate = Date.now();
      return Array.from(projects.values()).sort((a, b) => a.name.localeCompare(b.name));

    } catch (error) {
      console.error('Fallback project discovery also failed:', error);
      throw new BedrockKBError('Failed to discover projects', 'PROJECT_DISCOVERY_ERROR', true, error);
    }
  }

  /**
   * Find exact chunk match using multiple strategies
   */
  private async findExactChunkMatch(documentId: string, projectId: string): Promise<any | null> {
    const { sanitize } = await import('./sanitization.js');
    
    // SECURITY: Sanitize document ID to prevent NoSQL injection
    const sanitizedDocumentId = sanitize.documentId(documentId);
    
    // Strategy 1: Direct chunk ID search with various field names
    const chunkQueries = [
      `"${sanitizedDocumentId}"`,  // Exact string match
      `chunkId:"${sanitizedDocumentId}"`,
      `chunk_id:"${sanitizedDocumentId}"`,
      `x-amz-bedrock-kb-chunk-id:"${sanitizedDocumentId}"`
    ];

    const { log } = await import('./secure-logger.js');
    
    for (const query of chunkQueries) {
      try {
        log.debug('Trying chunk query', { query });
        const response = await this.client.send(new RetrieveCommand({
          knowledgeBaseId: this.knowledgeBaseId,
          retrievalQuery: { text: query },
          retrievalConfiguration: {
            vectorSearchConfiguration: {
              numberOfResults: 10,
              overrideSearchType: 'SEMANTIC'
            }
          }
        }));

        const results = response.retrievalResults || [];
        
        // Look for exact chunk ID match in results
        for (const result of results) {
          const chunkId = this.extractChunkIdFromMetadata(result);
          if (chunkId === sanitizedDocumentId) {
            log.debug('Found exact match with query', { query });
            return result;
          }
        }
      } catch (error) {
        log.warn('Query failed', { 
          query, 
          error: this.sanitizeErrorMessage(error) 
        });
        continue;
      }
    }

    // Strategy 2: Search within project scope
    try {
      log.debug('Trying project-scoped search');
      // SECURITY: Use sanitized inputs for project query
      const sanitizedProjectId = sanitize.projectId(projectId);
      const projectQuery = `project:${sanitizedProjectId} "${sanitizedDocumentId}"`;
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: projectQuery },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 10,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));

      const results = response.retrievalResults || [];
      for (const result of results) {
        const chunkId = this.extractChunkIdFromMetadata(result);
        if (chunkId === sanitizedDocumentId) {
          log.debug('Found exact match in project scope');
          return result;
        }
      }
    } catch (error) {
      log.warn('Project-scoped search failed', { 
        error: this.sanitizeErrorMessage(error) 
      });
    }

    return null;
  }

  /**
   * Find best fallback match when exact chunk isn't found
   */
  private async findBestFallbackMatch(documentId: string, projectId: string): Promise<any | null> {
    try {
      const { sanitize } = await import('./sanitization.js');
      
      // SECURITY: Sanitize inputs to prevent NoSQL injection
      const sanitizedDocumentId = sanitize.documentId(documentId);
      const sanitizedProjectId = sanitize.projectId(projectId);
      
      // Use the sanitized document ID as a semantic search query
      const response = await this.client.send(new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: { text: `${sanitizedDocumentId} project:${sanitizedProjectId}` },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 1,
            overrideSearchType: 'SEMANTIC'
          }
        }
      }));

      const results = response.retrievalResults || [];
      return results.length > 0 ? results[0] : null;
    } catch (error) {
      const { log } = await import('./secure-logger.js');
      log.warn('Fallback search failed', { 
        error: this.sanitizeErrorMessage(error) 
      });
      return null;
    }
  }

  /**
   * Extract chunk ID from result metadata
   */
  private extractChunkIdFromMetadata(result: any): string | null {
    if (!result.metadata) return null;
    
    // Try various possible chunk ID fields
    return result.metadata['chunkId'] || 
           result.metadata['x-amz-bedrock-kb-chunk-id'] ||
           result.metadata['chunk_id'] ||
           null;
  }

  private extractProjectFromResult(result: any): ProjectInfo | null {
    try {
      const sourceUri = result.metadata?.['x-amz-bedrock-kb-source-uri'];
      if (!sourceUri || !sourceUri.includes('/metadata.json')) {
        return null;
      }

      const projectMatch = sourceUri.match(/\/projects\/([^\/]+)\/metadata\.json$/);
      if (!projectMatch) {
        return null;
      }

      const projectId = projectMatch[1];
      let projectData: any = {};
      try {
        projectData = JSON.parse(result.content?.text || '{}');
      } catch (parseError) {
        console.warn(`Failed to parse project metadata for ${projectId}:`, parseError);
      }

      return {
        id: projectId,
        name: projectData.name || this.formatProjectName(projectId),
        indexName: this.knowledgeBaseId,
        description: projectData.description || `Knowledge base for ${this.formatProjectName(projectId)} project`,
        documentCount: undefined,
        lastAccessed: undefined,
        knowledgeBaseId: this.knowledgeBaseId,
        projectType: projectData.project_type,
        status: projectData.status,
        createdAt: projectData.created_at ? new Date(projectData.created_at) : undefined,
        lastUpdated: projectData.last_updated ? new Date(projectData.last_updated) : undefined,
        metadata: projectData
      };
    } catch (error) {
      console.warn('Failed to extract project info from result:', error);
      return null;
    }
  }

  private async buildProjectQuery(projectId: string, query: string): Promise<string> {
    const { sanitize } = await import('./sanitization.js');
    // SECURITY: Sanitize inputs to prevent NoSQL injection
    const sanitizedProjectId = sanitize.projectId(projectId);
    const sanitizedQuery = sanitize.searchQuery(query).sanitized;
    return `${sanitizedQuery} project:${sanitizedProjectId} OR path:projects/${sanitizedProjectId}`;
  }

  private async buildDocumentQuery(projectId: string, documentId: string): Promise<string> {
    const { sanitize } = await import('./sanitization.js');
    // SECURITY: Sanitize inputs to prevent NoSQL injection
    const sanitizedProjectId = sanitize.projectId(projectId);
    const sanitizedDocumentId = sanitize.documentId(documentId);
    return `project:${sanitizedProjectId} document:${sanitizedDocumentId} OR filename:${sanitizedDocumentId}`;
  }

  private formatSearchResults(results: any[], projectId: string | null, filters?: SearchFilters): SearchResult[] {
    return results
      .map(result => this.formatSearchResult(result, projectId, filters))
      .filter(result => result !== null) as SearchResult[];
  }

  private formatSearchResult(result: any, expectedProjectId: string | null, filters?: SearchFilters): SearchResult | null {
    try {
      const sourceUri = result.metadata?.['x-amz-bedrock-kb-source-uri'] || '';
      const content = result.content?.text || '';
      
      const projectMatch = sourceUri.match(/\/projects\/([^\/]+)\//);
      const projectId = projectMatch ? projectMatch[1] : 'unknown';
      
      if (expectedProjectId && projectId !== expectedProjectId) {
        return null;
      }

      const filenameMatch = sourceUri.match(/\/([^\/]+)$/);
      const filename = filenameMatch ? filenameMatch[1] : 'unknown';
      const documentType = this.determineDocumentType(filename, content);
      const documentId = result.metadata?.['x-amz-bedrock-kb-chunk-id'] || `${projectId}-${filename}`;

      // Enhanced content handling based on filters
      const contentLength = filters?.fullContent ? -1 : (filters?.contentLength || 800); // Increased default from 500 to 800
      const processedContent = contentLength === -1 ? content : this.truncateContent(content, contentLength);
      
      // Enhanced highlights with more context
      const highlights = filters?.enhancedHighlights ? 
        this.extractEnhancedHighlights(content, filters?.query || '') :
        this.extractHighlights(content);

      return {
        id: documentId,
        title: this.extractTitle(filename, content),
        content: processedContent,
        documentType,
        projectId,
        projectName: this.formatProjectName(projectId),
        score: result.score || 0,
        highlights,
        metadata: {
          sourceUri,
          filename,
          chunkId: result.metadata?.['x-amz-bedrock-kb-chunk-id'],
          dataSourceId: result.metadata?.['x-amz-bedrock-kb-data-source-id']
        }
      };
    } catch (error) {
      console.warn('Failed to format search result:', error);
      return null;
    }
  }

  private formatDocument(result: any, projectId: string): KBDocument {
    const sourceUri = result.metadata?.['x-amz-bedrock-kb-source-uri'] || '';
    const content = result.content?.text || '';
    const filenameMatch = sourceUri.match(/\/([^\/]+)$/);
    const filename = filenameMatch ? filenameMatch[1] : 'unknown';

    return {
      id: result.metadata?.['x-amz-bedrock-kb-chunk-id'] || `${projectId}-${filename}`,
      title: this.extractTitle(filename, content),
      content,
      documentType: this.determineDocumentType(filename, content),
      projectId,
      createdAt: new Date(),
      updatedAt: new Date(),
      metadata: {
        sourceUri,
        filename,
        chunkId: result.metadata?.['x-amz-bedrock-kb-chunk-id'],
        dataSourceId: result.metadata?.['x-amz-bedrock-kb-data-source-id']
      }
    };
  }

  private determineDocumentType(filename: string, content: string): DocumentType {
    const lowerFilename = filename.toLowerCase();
    
    if (lowerFilename.includes('brd') || content.includes('business requirements')) {
      return DocumentType.BRD;
    }
    if (lowerFilename.includes('architecture') || content.includes('architecture')) {
      return DocumentType.ARCHITECTURE;
    }
    if (lowerFilename.includes('api') || lowerFilename.includes('openapi') || content.includes('openapi')) {
      return DocumentType.API_SPEC;
    }
    if (lowerFilename.includes('guide') || lowerFilename.includes('manual')) {
      return DocumentType.USER_GUIDE;
    }
    if (lowerFilename.includes('tech') || lowerFilename.includes('technical')) {
      return DocumentType.TECHNICAL_DOC;
    }
    
    return DocumentType.OTHER;
  }

  private extractTitle(filename: string, content: string): string {
    try {
      const parsed = JSON.parse(content);
      if (parsed.name) return parsed.name;
      if (parsed.title) return parsed.title;
      if (parsed.project_name) return parsed.project_name;
    } catch {
      // Not JSON, continue with filename
    }

    return filename.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ');
  }

  private extractHighlights(content: string): string[] {
    const sentences = content.split(/[.!?]+/).filter(s => s.trim().length > 0);
    return sentences.slice(0, 3).map(s => s.trim());
  }

  /**
   * Enhanced highlights that provide more context around query matches
   */
  private extractEnhancedHighlights(content: string, query: string): string[] {
    if (!query.trim()) {
      return this.extractHighlights(content);
    }

    const highlights: string[] = [];
    const queryTerms = query.toLowerCase().split(/\s+/).filter(term => term.length > 2);
    
    // Split content into sentences
    const sentences = content.split(/[.!?]+/).filter(s => s.trim().length > 0);
    
    // Find sentences containing query terms
    const matchingSentences = sentences.filter(sentence => {
      const lowerSentence = sentence.toLowerCase();
      return queryTerms.some(term => lowerSentence.includes(term));
    });

    // If we have matching sentences, use them
    if (matchingSentences.length > 0) {
      highlights.push(...matchingSentences.slice(0, 3).map(s => s.trim()));
    }

    // If we need more highlights, add relevant sentences
    if (highlights.length < 3) {
      const remainingCount = 3 - highlights.length;
      const additionalSentences = sentences
        .filter(s => !highlights.includes(s.trim()))
        .slice(0, remainingCount);
      highlights.push(...additionalSentences.map(s => s.trim()));
    }

    return highlights.length > 0 ? highlights : this.extractHighlights(content);
  }

  private truncateContent(content: string, maxLength: number): string {
    if (content.length <= maxLength) return content;
    return content.substring(0, maxLength) + '...';
  }

  private formatProjectName(projectId: string): string {
    return projectId
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  private isCacheValid(): boolean {
    return (Date.now() - this.lastCacheUpdate) < this.cacheExpiry && this.projectCache.size > 0;
  }
}

export interface BedrockConfig {
  knowledgeBaseId: string;
  region: string;
  credentials?: any;
}

export class BedrockKBError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    public readonly details?: any
  ) {
    super(message);
    this.name = 'BedrockKBError';
  }
}