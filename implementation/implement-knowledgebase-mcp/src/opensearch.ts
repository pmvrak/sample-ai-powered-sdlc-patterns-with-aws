import { Client } from '@opensearch-project/opensearch';
import { AwsSigv4Signer } from '@opensearch-project/opensearch/aws';
import { defaultProvider } from '@aws-sdk/credential-provider-node';
import { OpenSearchConfig, SearchFilters, SearchResult, KBDocument, DocumentType, DocumentMetadata } from './types.js';
import {
  SearchError,
  NetworkError,
  DocumentError,
  SystemError,
  ErrorClassifier,
  RetryManager,
  ErrorCategory,
  ErrorLogger
} from './errors.js';
import { log, secureLogger } from './secure-logger.js';

/**
 * OpenSearch operation error class (legacy - kept for backward compatibility)
 */
export class OpenSearchError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly retryable: boolean = false,
    public readonly details?: any
  ) {
    super(message);
    this.name = 'OpenSearchError';
  }
}

/**
 * OpenSearch connection health status
 */
export interface HealthStatus {
  connected: boolean;
  cluster: {
    name: string;
    status: 'green' | 'yellow' | 'red';
    numberOfNodes: number;
  };
  version: string;
  responseTime: number;
}

/**
 * Search query builder options
 */
export interface QueryBuilderOptions {
  query: string;
  filters?: SearchFilters;
  highlight?: boolean;
  size?: number;
  from?: number;
}

/**
 * OpenSearch client wrapper with AWS authentication integration
 */
export class OpenSearchClient {
  private client: Client;
  private config: OpenSearchConfig;
  private credentials?: any;
  private isConnected: boolean = false;
  private retryManager: RetryManager;
  private errorLogger: ErrorLogger;

  constructor(config: OpenSearchConfig, credentials?: any) {
    this.config = config;
    this.retryManager = RetryManager.getInstance();
    this.errorLogger = ErrorLogger.getInstance();
    this.credentials = credentials;
    this.client = this.createClient();
  }

  /**
   * Create OpenSearch client with AWS Sigv4 authentication
   */
  private createClient(): Client {
    try {
      return new Client({
        ...AwsSigv4Signer({
          region: this.config.region,
          service: 'aoss', // Amazon OpenSearch Serverless
          getCredentials: () => {
            // Security: Only use provided credentials, never fall back to default AWS credentials
            if (!this.credentials) {
              throw new Error('OpenSearch client requires explicit credentials for security compliance');
            }
            return Promise.resolve(this.credentials);
          },
        }),
        node: this.config.endpoint,
        requestTimeout: 30000,
        pingTimeout: 10000,
      });
    } catch (error) {
      const classifiedError = ErrorClassifier.classifyError(error, 'createClient');
      this.errorLogger.logError(classifiedError, 'OpenSearchClient:createClient');
      throw classifiedError;
    }
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

  /**
   * Validate connection and perform health check
   * For OpenSearch Serverless, we use a simple index listing instead of cluster health
   */
  async validateConnection(): Promise<HealthStatus> {
    return await this.retryManager.executeWithRetry(
      async () => {
        const startTime = Date.now();

        try {
          // For OpenSearch Serverless, use cat.indices to validate connection
          // This is a lightweight operation that confirms connectivity
          const response = await this.client.cat.indices({
            format: 'json',
            h: 'index,status'
          });

          this.isConnected = true;

          return {
            connected: true,
            cluster: {
              name: this.config.collectionName,
              status: 'green', // Serverless collections are always green when accessible
              numberOfNodes: 1 // Serverless abstracts node management
            },
            version: '2.x', // OpenSearch Serverless version
            responseTime: Date.now() - startTime
          };
        } catch (error) {
          this.isConnected = false;

          // Log with sanitized error message
          log.error('OpenSearch connection validation failed', {
            error: this.sanitizeErrorMessage(error),
            endpoint: this.config.endpoint,
            region: this.config.region
          });

          const classifiedError = ErrorClassifier.classifyError(error, 'validateConnection');
          this.errorLogger.logError(classifiedError, 'OpenSearchClient:validateConnection');
          throw classifiedError;
        }
      },
      ErrorCategory.NETWORK,
      'validateConnection'
    );
  }

  /**
   * Check if client is connected
   */
  isHealthy(): boolean {
    return this.isConnected;
  }

  /**
   * Build search query for OpenSearch
   */
  buildSearchQuery(options: QueryBuilderOptions): any {
    const { query, filters, highlight = true, size = 10, from = 0 } = options;

    // SECURITY: Import and use sanitization for all user queries
    const { sanitize } = require('./sanitization.js');
    const sanitizedQuery = sanitize.searchQuery(query);

    if (sanitizedQuery.blocked) {
      throw new SearchError(
        `Invalid search query: ${sanitizedQuery.warnings.join(', ')}`,
        'INVALID_QUERY',
        false
      );
    }

    // SECURITY: Sanitize projectId from filters to prevent path traversal
    const sanitizedProjectId = filters?.projectId ? sanitize.projectId(filters.projectId) : undefined;

    // Base query structure
    const searchQuery: any = {
      index: this.getIndexPattern(sanitizedProjectId),
      body: {
        query: {
          bool: {
            must: [],
            filter: []
          }
        },
        size,
        from,
        _source: ['id', 'title', 'content', 'documentType', 'projectId', 'projectName', 'metadata', 'createdAt', 'updatedAt']
      }
    };

    // Add main search query with sanitized input
    if (sanitizedQuery.sanitized.trim()) {
      searchQuery.body.query.bool.must.push({
        multi_match: {
          query: sanitizedQuery.sanitized, // ← NOW USING SANITIZED INPUT
          fields: ['title^3', 'content^2', 'metadata.tags^2', 'metadata.category'],
          type: 'best_fields',
          fuzziness: 'AUTO',
          operator: 'or'
        }
      });
    } else {
      // If no query provided, match all documents
      searchQuery.body.query.bool.must.push({
        match_all: {}
      });
    }

    // Add filters
    if (filters) {
      this.addFiltersToQuery(searchQuery.body.query.bool.filter, filters);
    }

    // Add highlighting
    if (highlight) {
      searchQuery.body.highlight = {
        fields: {
          title: { fragment_size: 150, number_of_fragments: 1 },
          content: { fragment_size: 200, number_of_fragments: 3 }
        },
        pre_tags: ['<mark>'],
        post_tags: ['</mark>']
      };
    }

    // Add sorting by relevance score only
    // Note: createdAt field doesn't exist in the index mapping, so we only sort by score
    searchQuery.body.sort = [
      '_score'
    ];

    return searchQuery;
  }

  /**
   * Add filters to search query
   */
  private addFiltersToQuery(filterArray: any[], filters: SearchFilters): void {
    // Document type filter
    if (filters.documentType) {
      filterArray.push({
        term: { documentType: filters.documentType }
      });
    }

    // Project ID filter
    if (filters.projectId) {
      // SECURITY: Sanitize projectId to prevent injection attacks
      const { sanitize } = require('./sanitization.js');
      const sanitizedFilterProjectId = sanitize.projectId(filters.projectId);
      filterArray.push({
        term: { projectId: sanitizedFilterProjectId }
      });
    }

    // Date range filter
    if (filters.dateRange) {
      const dateFilter: any = { range: { createdAt: {} } };
      if (filters.dateRange.start) {
        dateFilter.range.createdAt.gte = filters.dateRange.start.toISOString();
      }
      if (filters.dateRange.end) {
        dateFilter.range.createdAt.lte = filters.dateRange.end.toISOString();
      }
      filterArray.push(dateFilter);
    }

    // Tags filter
    if (filters.tags && filters.tags.length > 0) {
      filterArray.push({
        terms: { 'metadata.tags': filters.tags }
      });
    }
  }

  /**
   * Get index pattern for search
   */
  private getIndexPattern(projectId?: string): string {
    if (projectId) {
      // SECURITY: Sanitize projectId to prevent path traversal attacks
      const { sanitize } = require('./sanitization.js');
      const sanitizedProjectId = sanitize.projectId(projectId);
      return `${this.config.indexPrefix}${sanitizedProjectId}`;
    }
    return `${this.config.indexPrefix}*`;
  }

  /**
   * Execute search query
   */
  async search(options: QueryBuilderOptions): Promise<SearchResult[]> {
    return await this.retryManager.executeWithRetry(
      async () => {
        if (!this.isConnected) {
          throw new NetworkError(
            'OpenSearch client is not connected',
            'NOT_CONNECTED'
          );
        }

        try {
          const searchQuery = this.buildSearchQuery(options);
          const response = await this.client.search(searchQuery);

          return this.parseSearchResults(response.body);
        } catch (error) {
          // SECURITY: Import sanitization for logging
          const { sanitize } = require('./sanitization.js');
          const sanitizedQuery = sanitize.searchQuery(options.query);

          // Log with sanitized error message and sanitized query
          log.error('OpenSearch search operation failed', {
            error: this.sanitizeErrorMessage(error),
            query: sanitizedQuery.sanitized, // ← NOW USING SANITIZED QUERY IN LOGS
            originalQueryBlocked: sanitizedQuery.blocked,
            sanitizationWarnings: sanitizedQuery.warnings.length > 0 ? sanitizedQuery.warnings : undefined,
            statusCode: (error as any).meta?.statusCode
          });

          // Handle specific OpenSearch errors
          const statusCode = (error as any).meta?.statusCode;

          if (statusCode === 404) {
            throw new SearchError(
              'Index not found',
              'INDEX_NOT_FOUND',
              false,
              error
            );
          }

          if (statusCode === 400) {
            throw new SearchError(
              'Invalid search query',
              'INVALID_QUERY',
              false,
              error
            );
          }

          if (statusCode === 408 || statusCode === 504) {
            throw new SearchError(
              'Search operation timed out',
              'SEARCH_TIMEOUT',
              true,
              error
            );
          }

          const classifiedError = ErrorClassifier.classifyError(error, 'search');
          this.errorLogger.logError(classifiedError, 'OpenSearchClient:search');
          throw classifiedError;
        }
      },
      ErrorCategory.SEARCH,
      'search'
    );
  }

  /**
   * Parse OpenSearch response into SearchResult objects
   */
  private parseSearchResults(response: any): SearchResult[] {
    if (!response.hits || !response.hits.hits) {
      return [];
    }

    return response.hits.hits.map((hit: any) => {
      const source = hit._source;
      const highlights = hit.highlight || {};

      return {
        id: source.id || hit._id,
        title: source.title || 'Untitled',
        content: this.extractContent(source.content, highlights.content),
        documentType: source.documentType || DocumentType.OTHER,
        projectId: source.projectId || '',
        projectName: source.projectName || source.projectId || '',
        score: hit._score || 0,
        highlights: this.extractHighlights(highlights),
        metadata: this.parseMetadata(source.metadata)
      };
    });
  }

  /**
   * Extract content with highlights
   */
  private extractContent(content: string, highlights?: string[]): string {
    if (highlights && highlights.length > 0) {
      return highlights.join(' ... ');
    }

    // Return first 300 characters if no highlights
    return content ? content.substring(0, 300) + (content.length > 300 ? '...' : '') : '';
  }

  /**
   * Extract highlights from response
   */
  private extractHighlights(highlights: any): string[] {
    const result: string[] = [];

    if (highlights.title) {
      result.push(...highlights.title);
    }

    if (highlights.content) {
      result.push(...highlights.content);
    }

    return result;
  }

  /**
   * Parse metadata from source
   */
  private parseMetadata(metadata: any): DocumentMetadata {
    if (!metadata) {
      return {};
    }

    return {
      ...metadata,
      author: metadata.author,
      version: metadata.version,
      tags: Array.isArray(metadata.tags) ? metadata.tags : [],
      category: metadata.category,
      lastModified: metadata.lastModified ? new Date(metadata.lastModified) : undefined,
      fileSize: metadata.fileSize
    };
  }

  /**
   * Get document by ID
   */
  async getDocument(projectId: string, documentId: string): Promise<KBDocument> {
    return await this.retryManager.executeWithRetry(
      async () => {
        if (!this.isConnected) {
          throw new NetworkError(
            'OpenSearch client is not connected',
            'NOT_CONNECTED'
          );
        }

        try {
          // SECURITY: Sanitize projectId to prevent path traversal attacks
          const { sanitize } = require('./sanitization.js');
          const sanitizedProjectId = sanitize.projectId(projectId);
          const indexName = `${this.config.indexPrefix}${sanitizedProjectId}`;
          const response = await this.client.get({
            index: indexName,
            id: documentId
          });

          const source = response.body._source;

          return {
            id: source.id || documentId,
            title: source.title || 'Untitled',
            content: source.content || '',
            documentType: source.documentType || DocumentType.OTHER,
            projectId: source.projectId || projectId,
            createdAt: source.createdAt ? new Date(source.createdAt) : new Date(),
            updatedAt: source.updatedAt ? new Date(source.updatedAt) : new Date(),
            metadata: this.parseMetadata(source.metadata)
          };
        } catch (error) {
          // Log with sanitized error message
          log.error('OpenSearch document retrieval failed', {
            error: this.sanitizeErrorMessage(error),
            documentId,
            projectId,
            statusCode: (error as any).meta?.statusCode
          });

          const statusCode = (error as any).meta?.statusCode;

          if (statusCode === 404) {
            throw new DocumentError(
              `Document not found: ${documentId}`,
              'DOCUMENT_NOT_FOUND',
              false,
              error
            );
          }

          const classifiedError = ErrorClassifier.classifyError(error, 'getDocument');
          this.errorLogger.logError(classifiedError, 'OpenSearchClient:getDocument');
          throw classifiedError;
        }
      },
      ErrorCategory.DOCUMENT,
      'getDocument'
    );
  }

  /**
   * List available indexes (projects)
   */
  async listIndexes(): Promise<string[]> {
    if (!this.isConnected) {
      throw new OpenSearchError(
        'OpenSearch client is not connected',
        'NOT_CONNECTED',
        true
      );
    }

    try {
      const response = await this.client.cat.indices({
        index: `${this.config.indexPrefix}*`,
        format: 'json'
      });

      return response.body
        .map((index: any) => index.index)
        .filter((indexName: string) => indexName.startsWith(this.config.indexPrefix))
        .map((indexName: string) => indexName.replace(this.config.indexPrefix, ''));
    } catch (error) {
      throw new OpenSearchError(
        'Failed to list indexes',
        'INDEX_LIST_ERROR',
        true,
        error
      );
    }
  }

  /**
   * Get index statistics
   */
  async getIndexStats(projectId: string): Promise<{ documentCount: number; indexSize: string }> {
    if (!this.isConnected) {
      throw new OpenSearchError(
        'OpenSearch client is not connected',
        'NOT_CONNECTED',
        true
      );
    }

    try {
      // SECURITY: Sanitize projectId to prevent path traversal attacks
      const { sanitize } = require('./sanitization.js');
      const sanitizedProjectId = sanitize.projectId(projectId);
      const indexName = `${this.config.indexPrefix}${sanitizedProjectId}`;
      const response = await this.client.indices.stats({
        index: indexName
      });

      const stats = response.body.indices[indexName];

      return {
        documentCount: stats.total.docs.count || 0,
        indexSize: this.formatBytes(stats.total.store.size_in_bytes || 0)
      };
    } catch (error) {
      if ((error as any).meta?.statusCode === 404) {
        throw new OpenSearchError(
          `Index not found: ${projectId}`,
          'INDEX_NOT_FOUND',
          false,
          error
        );
      }

      throw new OpenSearchError(
        'Failed to get index statistics',
        'INDEX_STATS_ERROR',
        true,
        error
      );
    }
  }

  /**
   * Format bytes to human readable string
   */
  private formatBytes(bytes: number): string {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  /**
   * Update AWS credentials and recreate client
   */
  updateCredentials(credentials: any): void {
    this.credentials = credentials;
    this.client = this.createClient();
    this.isConnected = false; // Force revalidation
  }

  /**
   * Close the client connection
   */
  async close(): Promise<void> {
    try {
      await this.client.close();
      this.isConnected = false;
    } catch (error) {
      throw new OpenSearchError(
        'Failed to close OpenSearch client',
        'CLOSE_ERROR',
        false,
        error
      );
    }
  }
}