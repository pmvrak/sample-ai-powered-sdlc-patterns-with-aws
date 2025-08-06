import { 
  BedrockAgentRuntimeClient, 
  InvokeAgentCommand 
} from '@aws-sdk/client-bedrock-agent-runtime';
import { NodeHttpHandler } from "@smithy/node-http-handler";
import { v4 as uuidv4 } from 'uuid';
import { awsConfig } from '../config/environment';
import { logger } from '../utils/logger';

/**
 * Bedrock Agent Service
 * Handles invocation of AWS Bedrock agents for OpenAPI spec generation
 * Mimics the behavior of the backend Lambda's openapi-generator service
 */
export class BedrockAgentService {
  private client: BedrockAgentRuntimeClient;
  private agentId: string;
  private agentAliasId: string;

  constructor() {
    this.client = new BedrockAgentRuntimeClient({
      region: awsConfig.region,
      requestHandler: new NodeHttpHandler({
        connectionTimeout: 60000,
        socketTimeout: 300000
      })
    });

    // Get Bedrock agent configuration from environment
    this.agentId = process.env['BEDROCK_AGENT_ID'] || '';
    this.agentAliasId = process.env['BEDROCK_AGENT_ALIAS_ID'] || '';

    if (!this.agentId || !this.agentAliasId) {
      logger.warn('Bedrock agent configuration missing', {
        hasAgentId: !!this.agentId,
        hasAgentAliasId: !!this.agentAliasId
      });
    }
  }

  /**
   * Generate OpenAPI specification using Bedrock agent
   * @param prompt - Description of the API to generate
   * @returns Generated OpenAPI specification
   */
  async generateOpenAPI(prompt: string): Promise<any> {
    try {
      if (!this.agentId || !this.agentAliasId) {
        throw new Error('Bedrock agent configuration is missing. Please configure BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS_ID');
      }

      logger.info('Invoking Bedrock agent for OpenAPI generation', {
        agentId: this.agentId,
        agentAliasId: this.agentAliasId,
        promptLength: prompt.length,
        promptPreview: prompt.substring(0, 200) + (prompt.length > 200 ? '...' : '')
      });

      const sessionId = uuidv4();
      const command = new InvokeAgentCommand({
        agentId: this.agentId,
        agentAliasId: this.agentAliasId,
        sessionId: sessionId,
        inputText: prompt,
        enableTrace: true // Optional: for debugging
      });

      // Handle streaming response
      let aggregatedResponse = '';
      const response = await this.client.send(command);

      // Check if response is async iterable (streaming)
      if (response.completion && Symbol.asyncIterator in response.completion) {
        logger.debug("Processing streaming response from Bedrock agent");
        
        for await (const chunk of response.completion) {
          if (chunk.chunk?.bytes) {
            const decodedChunk = Buffer.from(chunk.chunk.bytes).toString('utf-8');
            logger.debug(`Received chunk: ${decodedChunk.substring(0, 50)}...`);
            aggregatedResponse += decodedChunk;
          }
        }
      } else {
        // Handle non-streaming response (fallback)
        logger.debug("Received non-streaming response from Bedrock agent");
        aggregatedResponse = response.completion || '';
      }

      // Process the complete response
      const result = this.processCompletionContent(aggregatedResponse);
      
      logger.info('Bedrock agent OpenAPI generation completed', {
        responseLength: aggregatedResponse.length,
        hasOpenApiSpec: !!result.openapi || !!result.openApiSpec,
        sessionId: sessionId
      });

      return result;

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      
      logger.error('Error generating OpenAPI spec with Bedrock agent', {
        error: errorMessage,
        agentId: this.agentId,
        agentAliasId: this.agentAliasId,
        errorType: error instanceof Error ? error.constructor.name : typeof error
      });

      // Check for common Bedrock agent errors
      if (errorMessage.includes('Internal Server Exception') || 
          errorMessage.includes('ServiceException') ||
          errorMessage.includes('ThrottlingException')) {
        throw new Error(`Bedrock agent error (possibly response too large or timeout): ${errorMessage}`);
      }

      throw error;
    }
  }

  /**
   * Process the completion content from Bedrock agent
   * Mimics the processCompletionContent function from backend Lambda
   */
  private processCompletionContent(completionContent: string): any {
    logger.debug(`Processing completion content, length: ${completionContent.length}`);
    
    if (completionContent) {
      logger.debug(`First 200 chars: ${completionContent.substring(0, 200)}...`);
    }

    // Process the response content
    if (completionContent.trim()) {
      // First, check if it's a JSON response
      try {
        const responseBody = JSON.parse(completionContent);
        
        if (responseBody.openApiSpec) {
          logger.debug('Found openApiSpec in response');
          return responseBody.openApiSpec;
        } else if (responseBody.raw_response) {
          // Process raw_response which might contain YAML
          logger.debug('Found raw_response, extracting YAML/JSON');
          const yamlContent = this.extractYamlOrJson(responseBody.raw_response);
          if (yamlContent) {
            const result = this.yamlToJson(yamlContent);
            return result;
          }
          return responseBody;
        } else {
          // If we have JSON but no openApiSpec, return the whole response
          logger.debug('No openApiSpec found in response, returning full response');
          return responseBody;
        }
      } catch (error) {
        logger.debug('Failed to parse as JSON, trying to extract YAML or JSON from text');
        
        // Not valid JSON, check for YAML content
        const yamlContent = this.extractYamlOrJson(completionContent);
        
        if (yamlContent) {
          const result = this.yamlToJson(yamlContent);
          return result;
        }
        
        // Look for JSON-like patterns
        const jsonPattern = /\{[\s\S]*\}/;
        const match = completionContent.match(jsonPattern);
        if (match) {
          try {
            const potentialJson = match[0];
            const responseBody = JSON.parse(potentialJson);
            logger.debug("Found embedded JSON");
            return responseBody;
          } catch (error) {
            logger.error("Error parsing embedded JSON:", error);
          }
        }
        
        // If all else fails, return the raw content
        logger.debug('Returning raw content');
        return { raw_response: completionContent };
      }
    } else {
      logger.warn('Empty completion content from Bedrock agent');
      return { error: 'Empty response from Bedrock agent' };
    }
  }

  /**
   * Extract YAML or JSON content from markdown code blocks or plain text
   * Mimics the extractYamlOrJson function from backend Lambda
   */
  private extractYamlOrJson(content: string): string | null {
    // Try to extract content from markdown code blocks with backticks
    const codeBlockRegex = /```(?:yaml|json)?\n([\s\S]*?)\n```/;
    const codeBlockMatch = content.match(codeBlockRegex);
    
    if (codeBlockMatch && codeBlockMatch[1]) {
      return codeBlockMatch[1];
    }
    
    // Try to extract content from blocks with triple single quotes
    const singleQuoteRegex = /'''(?:yaml|json)?([^']*?)'''/;
    const singleQuoteMatch = content.match(singleQuoteRegex);
    
    if (singleQuoteMatch && singleQuoteMatch[1]) {
      return singleQuoteMatch[1];
    }
    
    // If no code blocks, look for OpenAPI-specific content
    if (content.trim().startsWith('openapi:')) {
      return content;
    }
    
    // Look for JSON content
    if (content.trim().startsWith('{')) {
      try {
        // Simple JSON extraction
        let braceCount = 0;
        let start = content.indexOf('{');
        
        if (start >= 0) {
          for (let i = start; i < content.length; i++) {
            if (content[i] === '{') {
              braceCount++;
            } else if (content[i] === '}') {
              braceCount--;
              if (braceCount === 0) {
                // Found complete JSON object
                return content.substring(start, i + 1);
              }
            }
          }
        }
      } catch (error) {
        logger.error('Error extracting JSON:', error);
      }
    }
    
    // Look for OpenAPI-like structure without explicit markers
    const openapiRegex = /(?:^|\n)\s*openapi:\s*[0-9.]+\s*(?:\n|$)/;
    const openapiMatch = content.match(openapiRegex);
    
    if (openapiMatch) {
      const start = openapiMatch.index || 0;
      return content.substring(start);
    }
    
    return null;
  }

  /**
   * Convert YAML content to JSON
   * Mimics the yamlToJson function from backend Lambda
   */
  private yamlToJson(yamlContent: string): any {
    try {
      // For now, we'll use a simple YAML parser
      // In production, you might want to use the 'js-yaml' library
      const yaml = require('js-yaml');
      return yaml.load(yamlContent);
    } catch (error) {
      logger.error('Error converting YAML to JSON:', error);
      
      // If parsing fails, return a minimal valid OpenAPI spec
      return {
        openapi: '3.0.0',
        info: { title: 'Generated API', version: '1.0.0' },
        paths: {},
        _raw_yaml: yamlContent // Keep the raw content for debugging
      };
    }
  }

  /**
   * Check if Bedrock agent is properly configured
   */
  public isConfigured(): boolean {
    return !!(this.agentId && this.agentAliasId);
  }

  /**
   * Get configuration status
   */
  public getConfigurationStatus(): {
    configured: boolean;
    agentId: string;
    agentAliasId: string;
    region: string;
  } {
    return {
      configured: this.isConfigured(),
      agentId: this.agentId ? 'configured' : 'missing',
      agentAliasId: this.agentAliasId ? 'configured' : 'missing',
      region: awsConfig.region
    };
  }
}