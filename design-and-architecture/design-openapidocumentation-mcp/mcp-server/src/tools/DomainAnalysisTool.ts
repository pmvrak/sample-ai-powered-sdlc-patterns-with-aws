import { BaseMCPTool } from '../interfaces/BaseMCPTool';
import { MCPToolResult } from '../interfaces/MCPTool';
import { LambdaClient, InvokeCommand } from '@aws-sdk/client-lambda';
import { awsConfig, lambdaConfig } from '../config/environment';
import { logger } from '../utils/logger';
import { JSONSchema7 } from 'json-schema';

export interface DomainAnalysisInput {
  domains?: string[];
  business_context?: string;
  description?: string;
  domain?: string;
  project_description?: string;
  analysis_depth?: 'basic' | 'detailed' | 'comprehensive';
}

export class DomainAnalysisTool extends BaseMCPTool {
  public readonly name = 'domain_analysis';
  public readonly description = 'Analyze business domains and generate domain models using AWS Lambda';
  public readonly inputSchema: JSONSchema7 = {
    type: 'object',
    properties: {
      domains: {
        type: 'array',
        items: { type: 'string' },
        description: 'List of business domains to analyze'
      },
      business_context: {
        type: 'string',
        description: 'Business context or industry description'
      },
      description: {
        type: 'string',
        description: 'Business description that will be analyzed to extract domains and context'
      },
      domain: {
        type: 'string',
        description: 'Business domain description (alias for description)'
      },
      project_description: {
        type: 'string',
        description: 'Project description (alias for description)'
      },
      analysis_depth: {
        type: 'string',
        enum: ['basic', 'detailed', 'comprehensive'],
        default: 'detailed',
        description: 'Depth of analysis to perform'
      }
    },
    anyOf: [
      { required: ['description'] },
      { required: ['domain'] },
      { required: ['project_description'] }
    ]
  };

  private lambdaClient: LambdaClient;

  constructor() {
    super();

    this.lambdaClient = new LambdaClient({
      region: awsConfig.region
    });
  }

  public async execute(input: DomainAnalysisInput): Promise<MCPToolResult> {
    try {
      // Handle domain parameter as alias for description
      const description = input.description || input.domain || input.project_description;

      if (!description) {
        throw new Error('No description provided for domain analysis');
      }

      logger.info('Starting domain analysis', {
        domains: input.domains,
        context: input.business_context,
        description: description,
        depth: input.analysis_depth || 'detailed',
        lambdaArn: lambdaConfig.domainAnalyzerArn ? 'configured' : 'not configured'
      });

      if (!lambdaConfig.domainAnalyzerArn) {
        // For development/testing, return a mock response instead of failing
        logger.warn('Domain analyzer Lambda ARN not configured, returning mock response');
        return this.getMockResponse(input);
      }

      // Handle flexible input - extract domains and context from description if needed
      let domains = input.domains;
      let businessContext = input.business_context;

      if (description && (!domains || !businessContext)) {
        // Extract domains and context from description
        const extracted = this.extractDomainsFromDescription(description);
        domains = domains || extracted.domains;
        businessContext = businessContext || extracted.businessContext;
      }

      // Prepare payload for Lambda function - using the format expected by the Lambda
      const payload = {
        prompt: description,
        businessContext: businessContext,
        analysisType: 'domain',
        domains: domains,
        analysisDepth: input.analysis_depth || 'detailed',
        requestId: this.generateRequestId(),
        timestamp: new Date().toISOString()
      };

      // Invoke Lambda function
      const command = new InvokeCommand({
        FunctionName: lambdaConfig.domainAnalyzerArn,
        Payload: JSON.stringify(payload),
        InvocationType: 'RequestResponse'
      });

      logger.debug('Invoking domain analyzer Lambda', {
        functionArn: lambdaConfig.domainAnalyzerArn,
        payloadSize: JSON.stringify(payload).length,
        payload: payload
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
      let analysisResult;
      if (responsePayload.statusCode && responsePayload.body) {
        // Lambda HTTP response format
        if (responsePayload.statusCode !== 200) {
          throw new Error(`Lambda returned status ${responsePayload.statusCode}: ${responsePayload.body}`);
        }
        
        // Parse the body (which is a JSON string)
        const bodyContent = typeof responsePayload.body === 'string'
          ? JSON.parse(responsePayload.body)
          : responsePayload.body;
          
        analysisResult = bodyContent;
      } else {
        // Direct response format (fallback)
        analysisResult = responsePayload;
      }

      logger.info('Domain analysis completed successfully', {
        statusCode: responsePayload.statusCode,
        success: analysisResult.success,
        entitiesFound: analysisResult.entities?.length || 0,
        relationshipsFound: analysisResult.relationships?.length || 0,
        insightsGenerated: analysisResult.insights?.length || 0,
        analysisResult: JSON.stringify(analysisResult, null, 2)
      });

      // Check if the Lambda response indicates success
      if (!analysisResult.success && analysisResult.error) {
        throw new Error(`Lambda analysis failed: ${analysisResult.error}`);
      }

      // Format the result for MCP
      const formattedResult = this.formatAnalysisResult(analysisResult, input);

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
      logger.error('Domain analysis failed', {
        error: error instanceof Error ? error.message : error,
        domains: input.domains,
        context: input.business_context
      });

      return {
        content: [
          {
            type: 'text',
            text: `Domain analysis failed: ${error instanceof Error ? error.message : 'Unknown error'}`
          }
        ],
        isError: true
      };
    }
  }

  private formatAnalysisResult(result: any, input: DomainAnalysisInput): string {
    const sections = [];

    // Extract the processed values from the payload that was sent to Lambda
    const description = input.description || input.domain || input.project_description;
    const extracted = description ? this.extractDomainsFromDescription(description) : { domains: [], businessContext: '' };
    const finalDomains = input.domains || extracted.domains;
    const finalBusinessContext = input.business_context || extracted.businessContext;

    // Header
    sections.push(`# Domain Analysis Results`);
    sections.push(`**Business Context:** ${finalBusinessContext || 'Not specified'}`);
    sections.push(`**Domains Analyzed:** ${finalDomains?.join(', ') || 'Auto-detected from description'}`);
    sections.push(`**Analysis Depth:** ${input.analysis_depth || 'detailed'}`);
    sections.push('');

    // Add the main Lambda analysis content
    if (result && result.domainAnalysis) {
      sections.push('## 🤖 Domain Analysis');
      sections.push('');
      sections.push(result.domainAnalysis);
      sections.push('');
    }

    // Add any additional analysis content
    if (result) {
      // If there's a specific analysis text field, include it
      if (result.analysis || result.analysisText || result.text) {
        const analysisText = result.analysis || result.analysisText || result.text;
        sections.push('## 📝 Additional Analysis');
        sections.push('');
        sections.push(analysisText);
        sections.push('');
      }
      
      // Include any other text fields that might contain analysis results
      if (result.summary) {
        sections.push('## 📋 Summary');
        sections.push('');
        sections.push(result.summary);
        sections.push('');
      }
      
      if (result.recommendations) {
        sections.push('## 💡 Recommendations');
        sections.push('');
        sections.push(result.recommendations);
        sections.push('');
      }
    }

    // Entities
    if (result.entities && result.entities.length > 0) {
      sections.push('## 🏗️ Domain Entities');
      result.entities.forEach((entity: any, index: number) => {
        sections.push(`### ${index + 1}. ${entity.name}`);
        sections.push(`**Type:** ${entity.type || 'Entity'}`);
        if (entity.attributes && entity.attributes.length > 0) {
          sections.push(`**Attributes:** ${entity.attributes.join(', ')}`);
        }
        if (entity.description) {
          sections.push(`**Description:** ${entity.description}`);
        }
        sections.push('');
      });
    }

    // Relationships
    if (result.relationships && result.relationships.length > 0) {
      sections.push('## 🔗 Entity Relationships');
      result.relationships.forEach((rel: any, index: number) => {
        sections.push(`${index + 1}. **${rel.from}** ${rel.type || 'relates to'} **${rel.to}**`);
        if (rel.description) {
          sections.push(`   - ${rel.description}`);
        }
      });
      sections.push('');
    }

    // Business Rules & Insights
    if (result.insights && result.insights.length > 0) {
      sections.push('## 💡 Business Insights');
      result.insights.forEach((insight: any, index: number) => {
        sections.push(`${index + 1}. **${insight.type || 'Insight'}:** ${insight.description}`);
      });
      sections.push('');
    }

    // Session Information
    if (result.sessionId) {
      sections.push('## 📋 Session Information');
      sections.push(`**Session ID:** ${result.sessionId}`);
      if (result.userId) {
        sections.push(`**User ID:** ${result.userId}`);
      }
    }

    // Add raw Lambda response for debugging (if needed)
    if (process.env['NODE_ENV'] === 'development' || process.env['LOG_LEVEL'] === 'debug') {
      sections.push('');
      sections.push('---');
      sections.push('## 🔍 Raw Lambda Response (Debug)');
      sections.push('```json');
      sections.push(JSON.stringify(result, null, 2));
      sections.push('```');
    }

    return sections.join('\n');
  }

  private extractDomainsFromDescription(description: string): { domains: string[], businessContext: string } {
    // Simple domain extraction logic - can be enhanced with AI/NLP later
    const lowerDesc = description.toLowerCase();
    const domains: string[] = [];

    // Common business domain patterns
    const domainPatterns = [
      { pattern: /user|account|login|auth|profile/i, domain: 'user-management' },
      { pattern: /book|catalog|inventory|product/i, domain: 'catalog-management' },
      { pattern: /order|purchase|buy|cart|checkout/i, domain: 'order-processing' },
      { pattern: /payment|billing|transaction/i, domain: 'payment-processing' },
      { pattern: /search|browse|filter|recommendation/i, domain: 'search-discovery' },
      { pattern: /review|rating|feedback/i, domain: 'review-management' },
      { pattern: /notification|email|alert/i, domain: 'notification-service' },
      { pattern: /report|analytics|dashboard/i, domain: 'reporting-analytics' }
    ];

    // Extract domains based on patterns
    domainPatterns.forEach(({ pattern, domain }) => {
      if (pattern.test(description) && !domains.includes(domain)) {
        domains.push(domain);
      }
    });

    // If no specific domains found, create generic ones
    if (domains.length === 0) {
      if (lowerDesc.includes('bookstore') || lowerDesc.includes('book')) {
        domains.push('catalog-management', 'order-processing');
      } else {
        domains.push('core-business', 'user-management');
      }
    }

    // Extract business context
    let businessContext = description;

    // Enhance context based on detected patterns
    if (lowerDesc.includes('bookstore') || lowerDesc.includes('book')) {
      businessContext = `Online bookstore platform: ${description}`;
    } else if (lowerDesc.includes('ecommerce') || lowerDesc.includes('e-commerce')) {
      businessContext = `E-commerce platform: ${description}`;
    } else {
      businessContext = `Business system: ${description}`;
    }

    return { domains, businessContext };
  }

  private generateRequestId(): string {
    return `domain_analysis_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }

  private getMockResponse(input: DomainAnalysisInput): MCPToolResult {
    // Create a mock analysis result
    const mockResult = {
      entities: [
        {
          name: 'User',
          type: 'Entity',
          attributes: ['id', 'username', 'email', 'password'],
          description: 'Represents a user in the system'
        },
        {
          name: 'Book',
          type: 'Entity', 
          attributes: ['id', 'title', 'author', 'isbn', 'price'],
          description: 'Represents a book in the catalog'
        },
        {
          name: 'Order',
          type: 'Entity',
          attributes: ['id', 'userId', 'items', 'total', 'status'],
          description: 'Represents a customer order'
        }
      ],
      relationships: [
        {
          from: 'User',
          to: 'Order',
          type: 'places',
          description: 'A user can place multiple orders'
        },
        {
          from: 'Order',
          to: 'Book',
          type: 'contains',
          description: 'An order contains one or more books'
        }
      ],
      insights: [
        {
          type: 'Business Rule',
          description: 'Users must be authenticated to place orders'
        },
        {
          type: 'Domain Insight',
          description: 'The system follows a typical e-commerce pattern with user management, catalog, and order processing'
        }
      ],
      sessionId: this.generateRequestId(),
      userId: 'mock-user'
    };

    const formattedResult = this.formatAnalysisResult(mockResult, input);
    
    return {
      content: [
        {
          type: 'text',
          text: `${formattedResult}\n\n---\n**Note:** This is a mock response as Lambda function is not configured. Configure DOMAIN_ANALYZER_LAMBDA_ARN to use actual AWS Lambda analysis.`
        }
      ],
      isError: false
    };
  }
}