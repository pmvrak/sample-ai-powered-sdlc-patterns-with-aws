import { BaseMCPTool } from '../interfaces/BaseMCPTool';
import { MCPToolResult } from '../interfaces/MCPTool';
import { LambdaClient, InvokeCommand } from '@aws-sdk/client-lambda';
import { awsConfig, lambdaConfig } from '../config/environment';
import { logger } from '../utils/logger';
import { JSONSchema7 } from 'json-schema';

export interface DocumentationInput {
  domain_model: string;
  api_type?: 'REST' | 'GraphQL' | 'gRPC';
  include_security?: boolean;
  include_examples?: boolean;
  output_format?: 'openapi' | 'markdown' | 'both';
}

export class DocumentationTool extends BaseMCPTool {
  public readonly name = 'generate_documentation';
  public readonly description = 'Generate API documentation and OpenAPI specifications using AWS Lambda';
  public readonly inputSchema: JSONSchema7 = {
    type: 'object',
    properties: {
      domain_model: {
        type: 'string',
        description: 'Domain model or business context for documentation generation'
      },
      api_type: {
        type: 'string',
        enum: ['REST', 'GraphQL', 'gRPC'],
        default: 'REST',
        description: 'Type of API to generate documentation for'
      },
      include_security: {
        type: 'boolean',
        default: true,
        description: 'Include security specifications in the documentation'
      },
      include_examples: {
        type: 'boolean',
        default: true,
        description: 'Include request/response examples'
      },
      output_format: {
        type: 'string',
        enum: ['openapi', 'markdown', 'both'],
        default: 'openapi',
        description: 'Output format for the documentation'
      }
    },
    required: ['domain_model']
  };

  private lambdaClient: LambdaClient;

  constructor() {
    super();

    this.lambdaClient = new LambdaClient({
      region: awsConfig.region
    });
  }

  public async execute(input: DocumentationInput): Promise<MCPToolResult> {
    try {
      logger.info('Starting documentation generation', {
        apiType: input.api_type || 'REST',
        outputFormat: input.output_format || 'openapi',
        includeSecurity: input.include_security !== false,
        includeExamples: input.include_examples !== false
      });

      if (!lambdaConfig.docGeneratorArn) {
        throw new Error('Documentation generator Lambda ARN not configured');
      }

      // Prepare payload for Lambda function
      const payload = {
        domainModel: input.domain_model,
        apiType: input.api_type || 'REST',
        includeSecurity: input.include_security !== false,
        includeExamples: input.include_examples !== false,
        outputFormat: input.output_format || 'openapi',
        requestId: this.generateRequestId(),
        timestamp: new Date().toISOString()
      };

      // Invoke Lambda function
      const command = new InvokeCommand({
        FunctionName: lambdaConfig.docGeneratorArn,
        Payload: JSON.stringify(payload),
        InvocationType: 'RequestResponse'
      });

      logger.debug('Invoking documentation generator Lambda', {
        functionArn: lambdaConfig.docGeneratorArn,
        payloadSize: JSON.stringify(payload).length
      });

      const response = await this.lambdaClient.send(command);

      if (response.StatusCode !== 200) {
        throw new Error(`Lambda invocation failed with status: ${response.StatusCode}`);
      }

      if (!response.Payload) {
        throw new Error('No payload received from Lambda function');
      }

      // Parse Lambda response
      const responsePayload = JSON.parse(Buffer.from(response.Payload).toString());

      if (responsePayload.errorMessage) {
        throw new Error(`Lambda function error: ${responsePayload.errorMessage}`);
      }

      // Handle Lambda response format - Lambda returns {statusCode, headers, body}
      let documentationResult;
      if (responsePayload.statusCode && responsePayload.body) {
        // Lambda HTTP response format
        if (responsePayload.statusCode !== 200) {
          throw new Error(`Lambda returned status ${responsePayload.statusCode}: ${responsePayload.body}`);
        }
        
        // Parse the body (which is a JSON string)
        const bodyContent = typeof responsePayload.body === 'string'
          ? JSON.parse(responsePayload.body)
          : responsePayload.body;
          
        documentationResult = bodyContent;
      } else {
        // Direct response format (fallback)
        documentationResult = responsePayload;
      }

      // Debug: Log the actual response structure
      logger.debug('Lambda response structure', {
        responseKeys: Object.keys(documentationResult),
        responsePayload: JSON.stringify(documentationResult, null, 2)
      });

      logger.info('Documentation generation completed successfully', {
        outputFormat: input.output_format || 'openapi',
        hasOpenAPI: !!documentationResult.openapi,
        hasMarkdown: !!documentationResult.markdown,
        hasSpec: !!documentationResult.spec,
        hasDocumentation: !!documentationResult.documentation,
        responseKeys: Object.keys(documentationResult)
      });

      // Format the result for MCP
      const formattedResult = this.formatDocumentationResult(documentationResult, input);

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
      logger.error('Documentation generation failed', {
        error: error instanceof Error ? error.message : error,
        apiType: input.api_type,
        outputFormat: input.output_format
      });

      return {
        content: [
          {
            type: 'text',
            text: `Documentation generation failed: ${error instanceof Error ? error.message : 'Unknown error'}`
          }
        ],
        isError: true
      };
    }
  }

  private formatDocumentationResult(result: any, input: DocumentationInput): string {
    const sections = [];

    // Header
    sections.push(`# API Documentation Generated`);
    sections.push(`**API Type:** ${input.api_type || 'REST'}`);
    sections.push(`**Output Format:** ${input.output_format || 'openapi'}`);
    sections.push(`**Security Included:** ${input.include_security !== false ? 'Yes' : 'No'}`);
    sections.push(`**Examples Included:** ${input.include_examples !== false ? 'Yes' : 'No'}`);
    sections.push('');

    // Show Lambda response message if available
    if (result.message) {
      sections.push(`## 📋 Generated Documentation`);
      sections.push(`**Status:** ${result.message}`);
      sections.push('');
    }

    // Extract the actual content from parsed_json
    const content = result.parsed_json || result;

    // Security Definitions
    if (content.securityDefinitions) {
      sections.push('## 🔒 Security Features Included:');
      
      if (content.securityDefinitions.schemes) {
        sections.push('### Authentication & Authorization:');
        content.securityDefinitions.schemes.forEach((scheme: any) => {
          sections.push(`- **${scheme.name || scheme.type}** ${scheme.description ? `- ${scheme.description}` : ''}`);
        });
        sections.push('');
      }

      if (content.securityDefinitions.recommendations) {
        sections.push('### Security Best Practices:');
        content.securityDefinitions.recommendations.forEach((rec: any) => {
          if (typeof rec === 'string') {
            sections.push(`- ${rec}`);
          } else if (rec.recommendation) {
            sections.push(`- **${rec.category || 'General'}:** ${rec.recommendation}`);
          }
        });
        sections.push('');
      }

      if (content.securityDefinitions.roles) {
        sections.push('### Access Control:');
        content.securityDefinitions.roles.forEach((role: any) => {
          sections.push(`- **${role.name}**: ${role.description || 'No description'}`);
          if (role.permissions && role.permissions.length > 0) {
            sections.push(`  - Permissions: ${role.permissions.join(', ')}`);
          }
        });
        sections.push('');
      }
    }

    // API Governance Policies
    if (content.policies) {
      sections.push('## 📋 API Governance Policies:');
      
      if (content.policies.rateLimiting) {
        sections.push('### Rate Limiting:');
        Object.entries(content.policies.rateLimiting).forEach(([key, value]) => {
          sections.push(`- **${key}**: ${value}`);
        });
        sections.push('');
      }

      if (content.policies.caching) {
        sections.push('### Caching Strategy:');
        Object.entries(content.policies.caching).forEach(([key, value]) => {
          sections.push(`- **${key}**: ${value}`);
        });
        sections.push('');
      }

      if (content.policies.validation) {
        sections.push('### Validation Rules:');
        if (typeof content.policies.validation === 'string') {
          sections.push(`- ${content.policies.validation}`);
        } else {
          Object.entries(content.policies.validation).forEach(([key, value]) => {
            sections.push(`- **${key}**: ${value}`);
          });
        }
        sections.push('');
      }

      if (content.policies.recommendations) {
        sections.push('### Policy Recommendations:');
        content.policies.recommendations.forEach((rec: any) => {
          sections.push(`- **${rec.category || 'General'}** (${rec.priority || 'medium'}): ${rec.recommendation}`);
        });
        sections.push('');
      }
    }

    // API Documentation
    if (content.documentation) {
      sections.push('## 📖 API Documentation:');
      
      if (typeof content.documentation === 'object' && Object.keys(content.documentation).length > 0) {
        Object.entries(content.documentation).forEach(([path, pathInfo]: [string, any]) => {
          if (typeof pathInfo === 'object' && pathInfo !== null) {
            sections.push(`### ${path}`);
            Object.entries(pathInfo).forEach(([method, methodInfo]: [string, any]) => {
              if (typeof methodInfo === 'object' && methodInfo !== null) {
                sections.push(`- **${method.toUpperCase()}**: ${methodInfo.summary || 'No summary'}`);
                if (methodInfo.description && methodInfo.description !== methodInfo.summary) {
                  sections.push(`  - ${methodInfo.description}`);
                }
              }
            });
            sections.push('');
          }
        });
      } else if (typeof content.documentation === 'string') {
        sections.push(content.documentation);
        sections.push('');
      }
    }

    // Versioning Strategy
    if (content.versioning) {
      sections.push('## 🔄 API Versioning Strategy:');
      
      if (content.versioning.recommendedApproach) {
        sections.push(`**Recommended Approach:** ${content.versioning.recommendedApproach}`);
        sections.push('');
      }

      if (content.versioning.approach) {
        sections.push('### Implementation:');
        Object.entries(content.versioning.approach).forEach(([key, value]) => {
          sections.push(`- **${key}**: ${value}`);
        });
        sections.push('');
      }

      if (content.versioning.lifecycleManagement) {
        sections.push('### Lifecycle Management:');
        const lifecycle = content.versioning.lifecycleManagement;
        
        if (lifecycle.versionRetention) {
          sections.push(`- **Version Retention:** ${lifecycle.versionRetention}`);
        }
        
        if (lifecycle.deprecationPolicy) {
          sections.push('- **Deprecation Policy:**');
          Object.entries(lifecycle.deprecationPolicy).forEach(([key, value]) => {
            sections.push(`  - ${key}: ${value}`);
          });
        }
        sections.push('');
      }
    }

    // Error Information
    if (result.errors || result.has_errors) {
      sections.push('## ⚠️ Generation Notes:');
      if (result.errors) {
        Object.entries(result.errors).forEach(([component, error]) => {
          if (error) {
            sections.push(`- **${component}**: ${error}`);
          }
        });
      }
      if (result.has_errors) {
        sections.push('- Some components were generated with fallback data due to processing errors');
      }
      sections.push('');
    }

    // Usage Instructions
    sections.push('## 🚀 Usage Instructions:');
    sections.push('1. **Review the security recommendations** and implement appropriate authentication');
    sections.push('2. **Apply the governance policies** to your API gateway or middleware');
    sections.push('3. **Use the versioning strategy** for future API evolution');
    sections.push('4. **Implement the documentation structure** in your API specification');
    sections.push('');
    sections.push('This comprehensive documentation provides a solid foundation for building a secure, well-governed API.');

    return sections.join('\n');
  }

  private generateRequestId(): string {
    return `doc_generation_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`;
  }
}