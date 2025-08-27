// MCP Tool Definitions
export const MCP_TOOLS = {
  list_projects: {
    name: 'list_projects',
    description: 'List all available project knowledge bases',
    inputSchema: {
      type: 'object',
      properties: {},
      required: []
    }
  },
  
  set_active_project: {
    name: 'set_active_project',
    description: 'Set the active project for subsequent searches',
    inputSchema: {
      type: 'object',
      properties: {
        projectName: { 
          type: 'string', 
          description: 'Name of the project to activate' 
        }
      },
      required: ['projectName']
    }
  },
  

  
  search_all_projects: {
    name: 'search_all_projects',
    description: 'Search across all accessible project knowledge bases',
    inputSchema: {
      type: 'object',
      properties: {
        query: { 
          type: 'string', 
          description: 'Search query' 
        },
        documentType: { 
          type: 'string', 
          description: 'Filter by document type (brd, architecture, api_spec, technical_doc, user_guide, other)' 
        },
        limit: { 
          type: 'number', 
          description: 'Maximum results to return (default: 20)' 
        }
      },
      required: ['query']
    }
  },
  
  get_document: {
    name: 'get_document',
    description: 'Retrieve full content of a specific document',
    inputSchema: {
      type: 'object',
      properties: {
        documentId: { 
          type: 'string', 
          description: 'Document identifier' 
        },
        projectId: { 
          type: 'string', 
          description: 'Project identifier (optional if active project set)' 
        }
      },
      required: ['documentId']
    }
  },

  search: {
    name: 'search',
    description: 'Search with full document content and enhanced features',
    inputSchema: {
      type: 'object',
      properties: {
        query: { 
          type: 'string', 
          description: 'Search query' 
        },
        projectId: { 
          type: 'string', 
          description: 'Project identifier (optional if active project set)' 
        },
        limit: { 
          type: 'number', 
          description: 'Maximum results to return (default: 5)' 
        },
        enhancedHighlights: {
          type: 'boolean',
          description: 'Use enhanced highlighting with query context (default: true)'
        }
      },
      required: ['query']
    }
  },

  switch_backend: {
    name: 'switch_backend',
    description: 'Switch between OpenSearch and Bedrock Knowledge Base backends',
    inputSchema: {
      type: 'object',
      properties: {
        backendType: { 
          type: 'string', 
          enum: ['opensearch', 'bedrock'],
          description: 'Backend type to switch to (opensearch or bedrock)' 
        },
        config: {
          type: 'object',
          description: 'Backend-specific configuration',
          properties: {
            knowledgeBaseId: {
              type: 'string',
              description: 'Bedrock Knowledge Base ID (required for bedrock backend)'
            },
            region: {
              type: 'string', 
              description: 'AWS region (required for bedrock backend)'
            }
          }
        }
      },
      required: ['backendType']
    }
  },

  get_backend_info: {
    name: 'get_backend_info',
    description: 'Get information about the current backend configuration and health',
    inputSchema: {
      type: 'object',
      properties: {},
      required: []
    }
  }
} as const;

export type ToolName = keyof typeof MCP_TOOLS;