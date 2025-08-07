import {
  BedrockRuntimeClient,
  InvokeModelCommand
} from '@aws-sdk/client-bedrock-runtime';
import {
  BedrockAgentRuntimeClient,
  RetrieveCommand
} from '@aws-sdk/client-bedrock-agent-runtime';
import { NodeHttpHandler } from "@smithy/node-http-handler";
import { awsConfig } from '../config/environment';
import { logger } from '../utils/logger';

/**
 * Fixed Bedrock Retrieve and Generate Service
 * Fixes JSON parsing issues with improved error handling and response processing
 */
export class BedrockRetrieveGenerateService {
  private client: BedrockAgentRuntimeClient;
  private runtimeClient: BedrockRuntimeClient;
  private knowledgeBaseId: string;
  private modelId: string;

  constructor() {
    this.client = new BedrockAgentRuntimeClient({
      region: awsConfig.region,
      requestHandler: new NodeHttpHandler({
        connectionTimeout: 60000,
        socketTimeout: 300000
      })
    });

    this.runtimeClient = new BedrockRuntimeClient({
      region: awsConfig.region,
      requestHandler: new NodeHttpHandler({
        connectionTimeout: 60000,
        socketTimeout: 300000
      })
    });

    // Get configuration from environment
    this.knowledgeBaseId = process.env['BEDROCK_KNOWLEDGE_BASE_ID'] || '';
    // Use the model ID from config, fallback to US inference profile
    this.modelId = awsConfig.modelId || 'us.anthropic.claude-3-7-sonnet-20250219-v1:0';

    if (!this.knowledgeBaseId) {
      logger.warn('Bedrock knowledge base configuration missing', {
        hasKnowledgeBaseId: !!this.knowledgeBaseId
      });
    }
  }

  /**
   * Check if the service is properly configured
   */
  isConfigured(): boolean {
    // Only require modelId - knowledge base is optional
    return !!this.modelId;
  }

  /**
   * Get configuration status for debugging
   */
  getConfigurationStatus() {
    return {
      hasKnowledgeBaseId: !!this.knowledgeBaseId,
      hasModelId: !!this.modelId,
      knowledgeBaseId: this.knowledgeBaseId,
      modelId: this.modelId
    };
  }

  /**
   * Generate OpenAPI specification using two-step approach with improved JSON parsing
   */
  async generateOpenAPI(prompt: string): Promise<any> {
    try {
      if (!this.isConfigured()) {
        throw new Error('Bedrock retrieve and generate service is not properly configured');
      }

      logger.info('Starting improved OpenAPI generation', {
        knowledgeBaseId: this.knowledgeBaseId,
        modelId: this.modelId,
        promptLength: prompt.length
      });

      // Step 1: Retrieve relevant documentation from knowledge base
      const retrievedContext = await this.retrieveRelevantDocumentation(prompt);

      // Step 2: Generate OpenAPI spec using direct Bedrock call with improved parsing
      const openApiSpec = await this.generateWithImprovedParsing(prompt, retrievedContext);

      logger.info('Improved OpenAPI generation completed successfully', {
        hasOpenAPI: !!openApiSpec.openapi,
        hasInfo: !!openApiSpec.info,
        pathCount: Object.keys(openApiSpec.paths || {}).length,
        hasComponents: !!openApiSpec.components
      });

      return openApiSpec;

    } catch (error) {
      logger.error('OpenAPI generation failed', {
        error: error instanceof Error ? error.message : error,
        knowledgeBaseId: this.knowledgeBaseId,
        modelId: this.modelId
      });
      throw error;
    }
  }

  /**
   * Step 1: Retrieve relevant documentation from the knowledge base
   */
  private async retrieveRelevantDocumentation(prompt: string): Promise<string> {
    // Skip knowledge base retrieval if not configured
    if (!this.knowledgeBaseId) {
      logger.info('Knowledge base not configured, skipping documentation retrieval');
      return 'No specific documentation found. Use general OpenAPI 3.1 best practices.';
    }

    logger.info('Step 1: Retrieving relevant documentation from knowledge base');

    try {
      const retrieveCommand = new RetrieveCommand({
        knowledgeBaseId: this.knowledgeBaseId,
        retrievalQuery: {
          text: `OpenAPI 3.1 specification examples, best practices, and schema definitions for: ${prompt.substring(0, 200)}`
        },
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 10 // Reduced to avoid too much context
          }
        }
      });

      const retrieveResponse = await this.client.send(retrieveCommand);

      if (!retrieveResponse.retrievalResults || retrieveResponse.retrievalResults.length === 0) {
        logger.warn('No relevant documentation retrieved from knowledge base');
        return 'No specific documentation found. Use general OpenAPI 3.1 best practices.';
      }

      // Combine retrieved content with size limits
      const retrievedContent = retrieveResponse.retrievalResults
        .slice(0, 5) // Limit to top 5 results
        .map((result, index) => {
          const content = result.content?.text || '';
          const source = result.location?.s3Location?.uri || `Document ${index + 1}`;
          return `--- Source: ${source} ---\n${content.substring(0, 500)}`; // Limit each result
        })
        .join('\n\n');

      logger.info('Retrieved documentation from knowledge base', {
        resultCount: retrieveResponse.retrievalResults.length,
        totalContentLength: retrievedContent.length
      });

      return retrievedContent;
    } catch (error) {
      logger.warn('Failed to retrieve from knowledge base, continuing without context', {
        error: error instanceof Error ? error.message : error
      });
      return 'No specific documentation found. Use general OpenAPI 3.1 best practices.';
    }
  }

  /**
   * Step 2: Generate OpenAPI spec with improved JSON parsing
   */
  private async generateWithImprovedParsing(prompt: string, retrievedContext: string): Promise<any> {
    logger.info('Step 2: Generating OpenAPI spec with improved parsing');

    const systemPrompt = `You are an AWS Solutions Architect specializing in API design and OpenAPI specification generation. Your task is to generate complete, well-structured OpenAPI 3.1 specifications based on the business requirements, domain analysis, and API details provided by the user. 

CRITICAL REQUIREMENTS:
1. Generate ONLY valid JSON - no markdown, no explanations, no code blocks
2. Use OpenAPI 3.1.0 specification format
3. Keep the specification complete and detailed but within tocken limit.
4. Add realistic examples for all request/response bodies
5. Include proper HTTP status codes and error responses
6. Add security schemes (Bearer token authentication)
7. Include input validation and constraints
8. Follow REST API best practices
9. Use $ref for schema reuse to save space
10. Keep examples short and realistic

${retrievedContext ? `CONTEXT:\n${retrievedContext.substring(0, 1000)}\n\n` : ''}

USER REQUIREMENTS:
${prompt.substring(0, 1000)}

Generate a complete but CONCISE OpenAPI 3.1 specification in valid JSON format:`;

    const requestBody = {
      anthropic_version: "bedrock-2023-05-31",
      max_tokens: 10000, // Claude 3.5 Sonnet max is 8192 tokens
      temperature: 0.1,
      messages: [
        {
          role: "user",
          content: systemPrompt
        }
      ]
    };

    const command = new InvokeModelCommand({
      modelId: this.modelId,
      body: JSON.stringify(requestBody),
      contentType: 'application/json',
      accept: 'application/json'
    });

    const response = await this.runtimeClient.send(command);

    if (!response.body) {
      throw new Error('No response body received from Bedrock model');
    }

    const responseBody = JSON.parse(new TextDecoder().decode(response.body));
    const generatedText = responseBody.content[0].text;

    logger.info('Received response from direct Bedrock call', {
      responseLength: generatedText.length
    });

    // Parse with improved strategies
    return this.parseWithMultipleStrategies(generatedText);
  }

  /**
   * Parse JSON with multiple improved strategies
   */
  private parseWithMultipleStrategies(generatedText: string): any {
    logger.info('Parsing response with multiple strategies');

    let openApiSpec;
    let cleanResponse = generatedText.trim();

    try {
      // Strategy 1: Direct parse
      openApiSpec = JSON.parse(cleanResponse);
      logger.info('Successfully parsed with direct strategy');
    } catch (directError) {
      try {
        // Strategy 2: Remove markdown and parse
        cleanResponse = cleanResponse.replace(/```json\s*/, '').replace(/```\s*$/, '');
        cleanResponse = cleanResponse.replace(/```\s*/, '');
        openApiSpec = JSON.parse(cleanResponse);
        logger.info('Successfully parsed with markdown removal strategy');
      } catch (markdownError) {
        try {
          // Strategy 3: Extract JSON object
          const jsonMatch = cleanResponse.match(/\{[\s\S]*\}/);
          if (jsonMatch) {
            cleanResponse = jsonMatch[0];
            openApiSpec = JSON.parse(cleanResponse);
            logger.info('Successfully parsed with JSON extraction strategy');
          } else {
            throw new Error('No JSON object found in response');
          }
        } catch (extractError) {
          try {
            // Strategy 4: Find complete JSON by brace matching
            const startIdx = cleanResponse.indexOf('{');
            if (startIdx === -1) throw new Error('No opening brace found');

            let braceCount = 0;
            let endIdx = -1;

            for (let i = startIdx; i < cleanResponse.length; i++) {
              if (cleanResponse[i] === '{') braceCount++;
              if (cleanResponse[i] === '}') braceCount--;
              if (braceCount === 0) {
                endIdx = i;
                break;
              }
            }

            if (endIdx !== -1) {
              const jsonStr = cleanResponse.substring(startIdx, endIdx + 1);
              openApiSpec = JSON.parse(jsonStr);
              logger.info('Successfully parsed with brace matching strategy');
            } else {
              throw new Error('No matching closing brace found');
            }
          } catch (braceError) {
            // Strategy 5: Truncation recovery
            try {
              openApiSpec = this.recoverFromTruncatedJSON(cleanResponse);
              logger.info('Successfully recovered from truncated JSON');
            } catch (recoveryError) {
              // All strategies failed - return structured error
              logger.warn('All JSON parsing strategies failed', {
                directError: directError instanceof Error ? directError.message : directError,
                markdownError: markdownError instanceof Error ? markdownError.message : markdownError,
                extractError: extractError instanceof Error ? extractError.message : extractError,
                braceError: braceError instanceof Error ? braceError.message : braceError,
                recoveryError: recoveryError instanceof Error ? recoveryError.message : recoveryError,
                responsePreview: generatedText.substring(0, 200),
                contentLength: generatedText.length
              });

              return {
                openapi: '3.1.0',
                info: {
                  title: 'Generated API (Parse Error)',
                  version: '1.0.0',
                  description: 'Raw generated content due to JSON parsing error'
                },
                'x-parse-error': directError instanceof Error ? directError.message : String(directError),
                'x-raw-generated-content': cleanResponse.substring(0, 2000), // Limit to prevent huge responses
                'x-original-response': generatedText.substring(0, 1000), // Even more limited
                'x-parsing-attempts': {
                  directError: directError instanceof Error ? directError.message : directError,
                  markdownError: markdownError instanceof Error ? markdownError.message : markdownError,
                  extractError: extractError instanceof Error ? extractError.message : extractError,
                  braceError: braceError instanceof Error ? braceError.message : braceError,
                  recoveryError: recoveryError instanceof Error ? recoveryError.message : recoveryError
                },
                paths: {}
              };
            }
          }
        }
      }
    }

    // Validate and fix basic OpenAPI structure
    return this.validateAndFixStructure(openApiSpec, generatedText);
  }

  /**
   * Recover from truncated JSON
   */
  private recoverFromTruncatedJSON(cleanResponse: string): any {
    const startIdx = cleanResponse.indexOf('{');
    if (startIdx === -1) throw new Error('No JSON start found');

    const partial = cleanResponse.substring(startIdx);

    // Count unclosed braces and brackets
    let openBraces = 0;
    let openBrackets = 0;
    let inString = false;
    let escapeNext = false;

    for (let i = 0; i < partial.length; i++) {
      const char = partial[i];

      if (escapeNext) {
        escapeNext = false;
        continue;
      }

      if (char === '\\') {
        escapeNext = true;
        continue;
      }

      if (char === '"') {
        inString = !inString;
        continue;
      }

      if (!inString) {
        if (char === '{') openBraces++;
        if (char === '}') openBraces--;
        if (char === '[') openBrackets++;
        if (char === ']') openBrackets--;
      }
    }

    // Try to close the JSON properly
    let fixed = partial;

    // Remove any trailing incomplete content
    const lastComma = fixed.lastIndexOf(',');
    const lastBrace = fixed.lastIndexOf('}');
    const lastBracket = fixed.lastIndexOf(']');

    if (lastComma > Math.max(lastBrace, lastBracket)) {
      // Remove trailing comma and everything after
      fixed = fixed.substring(0, lastComma);
    }

    // Close open brackets and braces
    for (let i = 0; i < openBrackets; i++) {
      fixed += ']';
    }
    for (let i = 0; i < openBraces; i++) {
      fixed += '}';
    }

    return JSON.parse(fixed);
  }

  /**
   * Validate and fix basic OpenAPI structure
   */
  private validateAndFixStructure(openApiSpec: any, originalResponse: string): any {
    // Validate basic OpenAPI structure
    if (!openApiSpec.openapi || !openApiSpec.info || !openApiSpec.paths) {
      logger.warn('Generated spec missing required fields, fixing structure', {
        hasOpenapi: !!openApiSpec.openapi,
        hasInfo: !!openApiSpec.info,
        hasPaths: !!openApiSpec.paths
      });

      // Add missing required fields
      if (!openApiSpec.openapi) openApiSpec.openapi = '3.1.0';
      if (!openApiSpec.info) {
        openApiSpec.info = {
          title: 'Generated API',
          version: '1.0.0',
          description: 'Generated API specification'
        };
      }
      if (!openApiSpec.paths) openApiSpec.paths = {};
    }

    logger.info('Successfully parsed and validated OpenAPI specification', {
      hasOpenapi: !!openApiSpec.openapi,
      hasInfo: !!openApiSpec.info,
      pathCount: Object.keys(openApiSpec.paths || {}).length,
      hasComponents: !!openApiSpec.components,
      responseLength: originalResponse.length
    });

    return openApiSpec;
  }
}