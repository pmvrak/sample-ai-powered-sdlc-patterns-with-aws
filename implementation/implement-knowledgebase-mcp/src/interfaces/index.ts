// Service Interfaces
export interface IAuthenticationService {
  authenticate(): Promise<string>;
  getAccessToken(): Promise<string>;
  refreshToken(): Promise<void>;
}

export interface IProjectService {
  listAvailableProjects(): Promise<import('../types.js').ProjectInfo[]>;
  setActiveProject(projectName: string): Promise<void>;
  getActiveProject(): Promise<import('../types.js').ProjectInfo | null>;
  validateProjectAccess(projectId: string): Promise<boolean>;
}

export interface ISearchService {
  searchProject(
    projectId: string, 
    query: string, 
    filters?: import('../types.js').SearchFilters
  ): Promise<import('../types.js').SearchResult[]>;
  searchAllProjects(
    query: string, 
    filters?: import('../types.js').SearchFilters
  ): Promise<import('../types.js').SearchResult[]>;
  getDocument(projectId: string, documentId: string): Promise<import('../types.js').KBDocument>;
}

export interface IDocumentService {
  getDocument(projectId: string, documentId: string): Promise<import('../types.js').KBDocument>;
  getDocumentMetadata(projectId: string, documentId: string): Promise<import('../types.js').DocumentMetadata>;
}

export interface IMCPServer {
  initialize(): Promise<void>;
  registerTools(): Promise<void>;
  handleToolCall(toolName: string, args: any): Promise<any>;
  shutdown(): Promise<void>;
}