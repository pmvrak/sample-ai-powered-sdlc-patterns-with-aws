import { ProjectInfo, SearchResult, KBDocument, SearchFilters } from './types.js';
import { OpenSearchClient } from './opensearch.js';
import { BedrockKBClient, BedrockConfig } from './bedrock.js';
import { OpenSearchConfig } from './types.js';

/**
 * Abstract interface for knowledge base backends
 */
export interface KnowledgeBaseBackend {
  listProjects(): Promise<ProjectInfo[]>;
  searchProject(projectId: string, query: string, filters?: SearchFilters): Promise<SearchResult[]>;
  searchAllProjects(query: string, filters?: SearchFilters): Promise<SearchResult[]>;
  getDocument(projectId: string, documentId: string): Promise<KBDocument>;
  validateConnection(): Promise<boolean>;
  isHealthy(): boolean;
  clearCache(): void;
  updateCredentials?(credentials: any): void; // Optional method for credential updates
}

/**
 * OpenSearch backend implementation
 */
export class OpenSearchBackend implements KnowledgeBaseBackend {
  private client: OpenSearchClient;

  constructor(config: OpenSearchConfig, credentials?: any) {
    this.client = new OpenSearchClient(config, credentials);
  }

  async listProjects(): Promise<ProjectInfo[]> {
    const projectIds = await this.client.listIndexes();
    const projects: ProjectInfo[] = [];

    for (const projectId of projectIds) {
      try {
        const stats = await this.client.getIndexStats(projectId);
        projects.push({
          id: projectId,
          name: this.formatProjectName(projectId),
          indexName: projectId,
          description: `Knowledge base for ${this.formatProjectName(projectId)} project`,
          documentCount: stats.documentCount
        });
      } catch (error) {
        // Add basic project info even if stats fail
        projects.push({
          id: projectId,
          name: this.formatProjectName(projectId),
          indexName: projectId,
          description: 'Project information unavailable',
          documentCount: undefined
        });
      }
    }

    return projects.sort((a, b) => a.name.localeCompare(b.name));
  }

  async searchProject(projectId: string, query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    return await this.client.search({ 
      query, 
      filters: { ...filters, projectId },
      size: filters?.limit || 10 
    });
  }

  async searchAllProjects(query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    const projectIds = await this.client.listIndexes();
    const allResults: SearchResult[] = [];

    for (const projectId of projectIds) {
      try {
        const results = await this.client.search({ 
          query, 
          filters: { ...filters, projectId },
          size: filters?.limit || 10 
        });
        allResults.push(...results);
      } catch (error) {
        console.warn(`Failed to search project ${projectId}:`, error);
      }
    }

    // Sort by score descending
    return allResults.sort((a, b) => b.score - a.score);
  }

  async getDocument(projectId: string, documentId: string): Promise<KBDocument> {
    return await this.client.getDocument(projectId, documentId);
  }

  async validateConnection(): Promise<boolean> {
    const status = await this.client.validateConnection();
    return status.connected;
  }

  isHealthy(): boolean {
    return this.client.isHealthy();
  }

  clearCache(): void {
    // OpenSearch client doesn't have cache to clear
  }

  updateCredentials(credentials: any): void {
    this.client.updateCredentials(credentials);
  }

  private formatProjectName(projectId: string): string {
    // Remove common prefixes and suffixes
    let name = projectId.replace(/^project-/, '').replace(/-[a-f0-9]{8}$/, '');

    // Convert kebab-case to Title Case
    return name
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }
}

/**
 * Bedrock KB backend implementation
 */
export class BedrockBackend implements KnowledgeBaseBackend {
  private client: BedrockKBClient;

  constructor(config: BedrockConfig, credentials?: any) {
    this.client = new BedrockKBClient(config, credentials);
  }

  async listProjects(): Promise<ProjectInfo[]> {
    return await this.client.listProjects();
  }

  async searchProject(projectId: string, query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    return await this.client.searchProject(projectId, query, filters);
  }

  async searchAllProjects(query: string, filters?: SearchFilters): Promise<SearchResult[]> {
    return await this.client.searchAllProjects(query, filters);
  }

  async getDocument(projectId: string, documentId: string): Promise<KBDocument> {
    return await this.client.getDocument(projectId, documentId);
  }

  async validateConnection(): Promise<boolean> {
    return await this.client.validateConnection();
  }

  isHealthy(): boolean {
    return this.client.isHealthy();
  }

  clearCache(): void {
    this.client.clearCache();
  }

  updateCredentials(credentials: any): void {
    this.client.updateCredentials(credentials);
  }
}

/**
 * Backend configuration types
 */
export interface BackendConfig {
  type: 'opensearch' | 'bedrock';
  opensearch?: OpenSearchConfig;
  bedrock?: BedrockConfig;
}

/**
 * Factory for creating knowledge base backends
 */
export class BackendFactory {
  static create(config: BackendConfig, credentials?: any): KnowledgeBaseBackend {
    switch (config.type) {
      case 'opensearch':
        if (!config.opensearch) {
          throw new Error('OpenSearch configuration is required when type is "opensearch"');
        }
        return new OpenSearchBackend(config.opensearch, credentials);
      
      case 'bedrock':
        if (!config.bedrock) {
          throw new Error('Bedrock configuration is required when type is "bedrock"');
        }
        return new BedrockBackend(config.bedrock, credentials);
      
      default:
        throw new Error(`Unsupported backend type: ${config.type}`);
    }
  }
}