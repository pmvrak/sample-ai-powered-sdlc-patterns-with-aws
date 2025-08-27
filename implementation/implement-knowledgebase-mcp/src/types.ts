// Core Data Models
export interface ProjectInfo {
  id: string;
  name: string;
  indexName: string;
  description?: string;
  lastAccessed?: Date;
  documentCount?: number;
  // Bedrock KB specific fields
  knowledgeBaseId?: string;
  projectType?: string;
  status?: string;
  createdAt?: Date;
  lastUpdated?: Date;
  metadata?: any;
}

export interface SearchResult {
  id: string;
  title: string;
  content: string;
  documentType: DocumentType;
  projectId: string;
  projectName: string;
  score: number;
  highlights?: string[];
  metadata: DocumentMetadata;
}

export interface KBDocument {
  id: string;
  title: string;
  content: string;
  documentType: DocumentType;
  projectId: string;
  createdAt: Date;
  updatedAt: Date;
  metadata: DocumentMetadata;
}

export interface DocumentMetadata {
  author?: string;
  version?: string;
  tags?: string[];
  category?: string;
  lastModified?: Date;
  fileSize?: number;
  [key: string]: any;
}

export enum DocumentType {
  BRD = 'brd',
  ARCHITECTURE = 'architecture',
  API_SPEC = 'api_spec',
  TECHNICAL_DOC = 'technical_doc',
  USER_GUIDE = 'user_guide',
  OTHER = 'other'
}

// Configuration Models
export interface ServerConfig {
  cognito: CognitoConfig;
  openSearch?: OpenSearchConfig;
  bedrock?: BedrockKBConfig;
  server: MCPServerConfig;
  defaultBackend: 'opensearch' | 'bedrock';
}

export interface BedrockKBConfig {
  knowledgeBaseId: string;
  region: string;
  credentials?: any;
}

export interface CognitoConfig {
  userPoolId: string;
  clientId: string;
  region: string;
  identityPoolId?: string;  // Optional for backward compatibility
  username?: string;
  password?: string;
}

export interface OpenSearchConfig {
  endpoint: string;
  region: string;
  collectionName: string;
  indexPrefix: string;
}

export interface MCPServerConfig {
  name: string;
  version: string;
}

// Search and Filter Types
export interface SearchFilters {
  documentType?: DocumentType;
  projectId?: string;
  dateRange?: {
    start?: Date;
    end?: Date;
  };
  tags?: string[];
  limit?: number;
  offset?: number;
  // Enhanced search options
  fullContent?: boolean;        // Return full content instead of truncated
  contentLength?: number;       // Custom content length (default: 800)
  query?: string;              // Original query for better highlight extraction
  enhancedHighlights?: boolean; // Use enhanced highlighting with more context
}

export interface FormattedDocument {
  id: string;
  title: string;
  content: string;
  summary?: string;
  metadata: DocumentMetadata;
}

// Error Handling
export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: any;
    retryable: boolean;
  };
}

// Legacy interfaces for backward compatibility
export interface AuthConfig extends CognitoConfig {
  username: string;
  password: string;
}