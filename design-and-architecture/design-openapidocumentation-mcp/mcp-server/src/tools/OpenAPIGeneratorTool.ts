import { JSONSchema7 } from 'json-schema';
import { BaseMCPTool } from '../interfaces/BaseMCPTool';
import { MCPToolResult, MCPToolContext } from '../interfaces/MCPTool';
import { BedrockRetrieveGenerateService } from '../services/BedrockRetrieveGenerateService';
import { logger } from '../utils/logger';

/**
 * OpenAPI Generation MCP Tool
 * Wraps the existing documentation generator Lambda function with MCP interface
 * Generates OpenAPI 3.1 specifications from domain analysis input
 */
export class OpenAPIGeneratorTool extends BaseMCPTool {
  public readonly name = 'generate_openapi_spec';
  public readonly description = 'Generate OpenAPI 3.1 specifications from domain analysis results or business requirements';

  public readonly inputSchema: JSONSchema7 = {
    type: 'object',
    properties: {
      // OpenAPI specification base properties
      info: {
        type: 'object',
        properties: {
          title: { type: 'string', description: 'API title' },
          version: { type: 'string', description: 'API version' },
          description: { type: 'string', description: 'API description' },
          contact: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              email: { type: 'string' },
              url: { type: 'string' }
            }
          },
          license: {
            type: 'object',
            properties: {
              name: { type: 'string' },
              url: { type: 'string' }
            }
          }
        },
        required: ['title', 'version'],
        additionalProperties: false
      },
      servers: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            url: { type: 'string' },
            description: { type: 'string' }
          },
          required: ['url']
        },
        description: 'Server configurations'
      },
      paths: {
        type: 'object',
        description: 'API paths and operations',
        additionalProperties: true
      },
      components: {
        type: 'object',
        description: 'Reusable components (schemas, parameters, etc.)',
        additionalProperties: true
      },
      // Domain analysis input
      domainAnalysis: {
        type: 'string',
        description: 'Domain analysis results to base the OpenAPI spec on'
      },
      businessContext: {
        type: 'string',
        description: 'Business context to inform API design'
      },
      // Generation options
      includeExamples: {
        type: 'boolean',
        description: 'Whether to include example values in the specification',
        default: true
      },
      includeValidation: {
        type: 'boolean',
        description: 'Whether to include validation rules and constraints',
        default: true
      },
      apiStyle: {
        type: 'string',
        enum: ['REST', 'GraphQL', 'RPC'],
        description: 'API architectural style',
        default: 'REST'
      },
      authenticationScheme: {
        type: 'string',
        enum: ['none', 'apiKey', 'bearer', 'oauth2', 'basic'],
        description: 'Authentication scheme to include',
        default: 'bearer'
      },
      // User context
      userEmail: {
        type: 'string',
        description: 'User email for authentication and data isolation'
      },
      sessionId: {
        type: 'string',
        description: 'Session identifier for tracking related operations'
      }
    },
    required: ['info'],
    additionalProperties: false
  };

  private bedrockService: BedrockRetrieveGenerateService;

  constructor(bedrockService?: BedrockRetrieveGenerateService) {
    super();
    this.bedrockService = bedrockService || new BedrockRetrieveGenerateService();
  }

  /**
   * Execute OpenAPI generation using Bedrock agent
   */
  public async execute(args: any, context?: MCPToolContext): Promise<MCPToolResult> {
    try {
      logger.info('Executing OpenAPI generation tool', {
        apiTitle: args.info?.title,
        apiVersion: args.info?.version,
        apiStyle: args.apiStyle || 'REST',
        hasDomainAnalysis: !!args.domainAnalysis,
        sessionId: args.sessionId || context?.sessionId,
        bedrockConfigured: this.bedrockService.isConfigured()
      });

      // Validate required information
      if (!args.info || !args.info.title || !args.info.version) {
        return this.createErrorResult(
          'OpenAPI generation requires info.title and info.version to be specified'
        );
      }

      // Validate API style if provided
      if (args.apiStyle && !['REST', 'GraphQL', 'RPC'].includes(args.apiStyle)) {
        return this.createErrorResult(
          'Invalid API style. Must be one of: REST, GraphQL, RPC'
        );
      }

      // Validate authentication scheme if provided
      if (args.authenticationScheme && !['none', 'apiKey', 'bearer', 'oauth2', 'basic'].includes(args.authenticationScheme)) {
        return this.createErrorResult(
          'Invalid authentication scheme. Must be one of: none, apiKey, bearer, oauth2, basic'
        );
      }

      // Check if Bedrock service is configured
      if (!this.bedrockService.isConfigured()) {
        const configStatus = this.bedrockService.getConfigurationStatus();
        return this.createErrorResult(
          `Bedrock retrieve and generate service not configured. Status: ${JSON.stringify(configStatus)}`
        );
      }

      // Prepare the prompt for Bedrock agent
      const prompt = this.buildOpenAPIPrompt(args);

      logger.info('Generated prompt for Bedrock agent', {
        promptLength: prompt.length,
        apiTitle: args.info.title,
        prompt: prompt.substring(0, 500) + (prompt.length > 500 ? '...' : '')
      });

      // Invoke Bedrock retrieve and generate
      const openApiSpec = await this.bedrockService.generateOpenAPI(prompt);

      // Validate the generated spec
      const validation = this.validateOpenAPISpec(openApiSpec);
      if (!validation.valid) {
        logger.warn('Generated OpenAPI spec has validation issues', {
          errors: validation.errors,
          apiTitle: args.info.title
        });
      }

      // Format the result for MCP
      const formattedResult = this.formatOpenAPIResult(openApiSpec, args, validation);

      logger.info('OpenAPI generation tool execution completed', {
        success: true,
        hasOpenApiSpec: !!openApiSpec.openapi,
        validationErrors: validation.errors.length,
        apiTitle: args.info?.title,
        sessionId: args.sessionId || context?.sessionId
      });

      return {
        content: [
          {
            type: 'text',
            text: formattedResult
          }
        ],
        isError: false
      };

    } catch (error) {
      logger.error('OpenAPI generation tool execution failed', {
        error: error instanceof Error ? error.message : error,
        args: this.sanitizeOpenAPIArgsForLogging(args)
      });

      return this.createErrorResult(
        `OpenAPI generation failed: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    }
  }

  /**
   * Sanitize arguments for logging (remove sensitive data specific to OpenAPI generation)
   */
  private sanitizeOpenAPIArgsForLogging(args: any): any {
    if (!args || typeof args !== 'object') {
      return args;
    }

    const sanitized = { ...args };

    // Remove common sensitive fields
    const sensitiveFields = ['password', 'token', 'secret', 'key', 'auth', 'apiKey'];

    for (const field of sensitiveFields) {
      if (field in sanitized) {
        sanitized[field] = '[REDACTED]';
      }
    }

    // Sanitize nested objects
    if (sanitized.components && typeof sanitized.components === 'object') {
      sanitized.components = this.sanitizeNestedObject(sanitized.components, sensitiveFields);
    }

    if (sanitized.paths && typeof sanitized.paths === 'object') {
      sanitized.paths = this.sanitizeNestedObject(sanitized.paths, sensitiveFields);
    }

    return sanitized;
  }

  /**
   * Recursively sanitize nested objects
   */
  private sanitizeNestedObject(obj: any, sensitiveFields: string[]): any {
    if (!obj || typeof obj !== 'object') {
      return obj;
    }

    const sanitized = { ...obj };

    for (const field of sensitiveFields) {
      if (field in sanitized) {
        sanitized[field] = '[REDACTED]';
      }
    }

    // Recursively sanitize nested objects
    for (const [key, value] of Object.entries(sanitized)) {
      if (value && typeof value === 'object') {
        sanitized[key] = this.sanitizeNestedObject(value, sensitiveFields);
      }
    }

    return sanitized;
  }

  /**
   * Get tool usage examples
   * @returns Array of example usage scenarios
   */
  public getExamples(): Array<{ description: string; args: any }> {
    return [
      {
        description: 'Generate basic REST API specification',
        args: {
          info: {
            title: 'E-commerce API',
            version: '1.0.0',
            description: 'API for managing e-commerce operations'
          },
          servers: [
            { url: 'https://api.example.com/v1', description: 'Production server' }
          ],
          apiStyle: 'REST',
          authenticationScheme: 'bearer',
          includeExamples: true
        }
      },
      {
        description: 'Generate API from domain analysis',
        args: {
          info: {
            title: 'Library Management API',
            version: '2.0.0',
            description: 'API for library management system'
          },
          domainAnalysis: 'Domain entities: Book, Member, Loan, Author. Relationships: Book has Author, Member borrows Book via Loan.',
          businessContext: 'Public library system with book lending and member management',
          apiStyle: 'REST',
          authenticationScheme: 'oauth2'
        }
      },
      {
        description: 'Generate GraphQL API specification',
        args: {
          info: {
            title: 'Social Media GraphQL API',
            version: '1.0.0',
            description: 'GraphQL API for social media platform'
          },
          apiStyle: 'GraphQL',
          authenticationScheme: 'bearer',
          includeValidation: true,
          businessContext: 'Social media platform with posts, users, and interactions'
        }
      }
    ];
  }

  /**
   * Get tool capabilities and limitations
   * @returns Object describing tool capabilities
   */
  public getCapabilities(): {
    supportedFormats: string[];
    apiStyles: string[];
    authenticationSchemes: string[];
    features: string[];
    limitations: string[];
  } {
    return {
      supportedFormats: [
        'OpenAPI 3.1.0 specification',
        'JSON format output',
        'YAML format support (via conversion)'
      ],
      apiStyles: [
        'REST - RESTful API design patterns',
        'GraphQL - GraphQL schema and operations',
        'RPC - Remote Procedure Call patterns'
      ],
      authenticationSchemes: [
        'none - No authentication',
        'apiKey - API key authentication',
        'bearer - Bearer token authentication',
        'oauth2 - OAuth 2.0 flows',
        'basic - Basic HTTP authentication'
      ],
      features: [
        'Domain analysis integration',
        'Business context awareness',
        'Example value generation',
        'Validation rule inclusion',
        'Component reusability',
        'Server configuration',
        'Security scheme definition'
      ],
      limitations: [
        'Requires valid OpenAPI info object',
        'Complex nested schemas may need manual refinement',
        'GraphQL support depends on Lambda function capabilities',
        'Authentication context required for data persistence',
        'Generated examples are basic and may need customization'
      ]
    };
  }

  /**
   * Build prompt for Bedrock agent based on input arguments
   * @param args - Input arguments for OpenAPI generation
   * @returns Formatted prompt string
   */
  private buildOpenAPIPrompt(args: any): string {
    const sections = [];

    // Basic API information
    sections.push(`Generate an OpenAPI 3.1 specification for the following API:`);
    sections.push(`Title: ${args.info.title}`);
    sections.push(`Version: ${args.info.version}`);

    if (args.info.description) {
      sections.push(`Description: ${args.info.description}`);
    }

    // API style and architecture
    sections.push(`API Style: ${args.apiStyle || 'REST'}`);
    sections.push(`Authentication Scheme: ${args.authenticationScheme || 'bearer'}`);

    // Domain analysis and business context
    if (args.domainAnalysis) {
      sections.push(`\nDomain Analysis:`);
      sections.push(args.domainAnalysis);
    }

    if (args.businessContext) {
      sections.push(`\nBusiness Context:`);
      sections.push(args.businessContext);
    }

    // Generation options
    sections.push(`\nGeneration Options:`);
    sections.push(`- Include Examples: ${args.includeExamples !== false ? 'Yes' : 'No'}`);
    sections.push(`- Include Validation: ${args.includeValidation !== false ? 'Yes' : 'No'}`);

    // Server configuration
    if (args.servers && args.servers.length > 0) {
      sections.push(`\nServers:`);
      args.servers.forEach((server: any, index: number) => {
        sections.push(`${index + 1}. ${server.url}${server.description ? ` - ${server.description}` : ''}`);
      });
    }

    // Additional requirements
    sections.push(`\nRequirements:`);
    sections.push(`- Generate a concise but complete OpenAPI 3.1 specification`);
    sections.push(`- Include key HTTP methods and status codes (focus on main operations)`);
    sections.push(`- Define essential request/response schemas`);
    sections.push(`- Include basic security definitions`);
    sections.push(`- Add appropriate tags and descriptions`);
    sections.push(`- Keep the specification focused and avoid excessive detail`);
    sections.push(`- Limit to core CRUD operations for main entities`);

    if (args.apiStyle === 'REST') {
      sections.push(`- Follow RESTful design principles`);
      sections.push(`- Use appropriate HTTP verbs (GET, POST, PUT, DELETE)`);
      sections.push(`- Include proper resource naming conventions`);
    }

    // Output format guidance
    sections.push(`\nOutput Format:`);
    sections.push(`- Provide the OpenAPI specification in YAML format`);
    sections.push(`- Keep responses concise to avoid length limits`);
    sections.push(`- Focus on essential endpoints and schemas`);
    sections.push(`- Use references ($ref) to avoid duplication`);

    return sections.join('\n');
  }

  /**
   * Format the OpenAPI generation result for MCP response
   * @param openApiSpec - Generated OpenAPI specification
   * @param args - Original input arguments
   * @param validation - Validation result
   * @returns Formatted result string
   */
  private formatOpenAPIResult(openApiSpec: any, args: any, validation: { valid: boolean; errors: string[] }): string {
    const sections = [];

    // Header
    sections.push(`# OpenAPI Specification Generated`);
    sections.push(`**API Title:** ${args.info.title}`);
    sections.push(`**API Version:** ${args.info.version}`);
    sections.push(`**API Style:** ${args.apiStyle || 'REST'}`);
    sections.push(`**Authentication:** ${args.authenticationScheme || 'bearer'}`);
    sections.push('');

    // Validation status
    if (validation.valid) {
      sections.push(`✅ **Validation:** Passed`);
    } else {
      sections.push(`⚠️ **Validation:** ${validation.errors.length} issues found`);
      validation.errors.forEach(error => {
        sections.push(`   - ${error}`);
      });
    }
    sections.push('');

    // OpenAPI specification content
    if (openApiSpec.openapi || openApiSpec.info) {
      sections.push(`## 📋 Generated OpenAPI Specification`);
      sections.push('');
      sections.push('```json');
      sections.push(JSON.stringify(openApiSpec, null, 2));
      sections.push('```');
      sections.push('');

      // Summary of generated content
      sections.push(`## 📊 Specification Summary`);

      if (openApiSpec.info) {
        sections.push(`**Title:** ${openApiSpec.info.title || 'N/A'}`);
        sections.push(`**Version:** ${openApiSpec.info.version || 'N/A'}`);
        if (openApiSpec.info.description) {
          sections.push(`**Description:** ${openApiSpec.info.description}`);
        }
      }

      if (openApiSpec.servers && openApiSpec.servers.length > 0) {
        sections.push(`**Servers:** ${openApiSpec.servers.length} configured`);
      }

      if (openApiSpec.paths) {
        const pathCount = Object.keys(openApiSpec.paths).length;
        sections.push(`**Paths:** ${pathCount} endpoints defined`);
      }

      if (openApiSpec.components) {
        const components = openApiSpec.components;
        const schemaCount = components.schemas ? Object.keys(components.schemas).length : 0;
        const securityCount = components.securitySchemes ? Object.keys(components.securitySchemes).length : 0;

        if (schemaCount > 0) {
          sections.push(`**Schemas:** ${schemaCount} defined`);
        }
        if (securityCount > 0) {
          sections.push(`**Security Schemes:** ${securityCount} defined`);
        }
      }

      if (openApiSpec.tags && openApiSpec.tags.length > 0) {
        sections.push(`**Tags:** ${openApiSpec.tags.length} defined`);
      }

    } else if (openApiSpec.raw_response) {
      sections.push(`## 📝 Raw Response from Bedrock Agent`);
      sections.push('');
      sections.push(openApiSpec.raw_response);
      sections.push('');
    } else {
      sections.push(`## ⚠️ Unexpected Response Format`);
      sections.push('');
      sections.push('```json');
      sections.push(JSON.stringify(openApiSpec, null, 2));
      sections.push('```');
      sections.push('');
    }

    // Usage instructions
    sections.push(`## 🚀 Usage Instructions`);
    sections.push('');
    sections.push('1. **Save the specification** to a `.json` file');
    sections.push('2. **Import into API tools** like Postman, Insomnia, or Swagger UI');
    sections.push('3. **Generate client SDKs** using OpenAPI generators');
    sections.push('4. **Validate endpoints** using the specification');
    sections.push('5. **Document your API** using the generated specification');

    return sections.join('\n');
  }

  /**
   * Validate OpenAPI specification structure
   * @param spec - OpenAPI specification object to validate
   * @returns Validation result with errors if any
   */
  public validateOpenAPISpec(spec: any): { valid: boolean; errors: string[] } {
    const errors: string[] = [];

    // Check required top-level properties
    if (!spec.info) {
      errors.push('Missing required "info" object');
    } else {
      if (!spec.info.title) {
        errors.push('Missing required "info.title"');
      }
      if (!spec.info.version) {
        errors.push('Missing required "info.version"');
      }
    }

    // Check OpenAPI version
    if (spec.openapi && !spec.openapi.startsWith('3.')) {
      errors.push('OpenAPI version must be 3.x');
    }

    // Validate servers if present
    if (spec.servers && Array.isArray(spec.servers)) {
      spec.servers.forEach((server: any, index: number) => {
        if (!server.url) {
          errors.push(`Server at index ${index} missing required "url" property`);
        }
      });
    }

    // Basic paths validation
    if (spec.paths && typeof spec.paths !== 'object') {
      errors.push('Paths must be an object');
    }

    // Basic components validation
    if (spec.components && typeof spec.components !== 'object') {
      errors.push('Components must be an object');
    }

    return {
      valid: errors.length === 0,
      errors
    };
  }
}