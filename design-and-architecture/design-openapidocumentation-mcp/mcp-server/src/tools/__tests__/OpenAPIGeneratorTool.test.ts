import { OpenAPIGeneratorTool } from '../OpenAPIGeneratorTool';
import { LambdaWrapper } from '../../services/LambdaWrapper';
import { MCPToolError } from '../../interfaces/MCPTool';

// Mock the LambdaWrapper
jest.mock('../../services/LambdaWrapper');
jest.mock('../../utils/logger');

describe('OpenAPIGeneratorTool', () => {
  let tool: OpenAPIGeneratorTool;
  let mockLambdaWrapper: jest.Mocked<LambdaWrapper>;

  beforeEach(() => {
    mockLambdaWrapper = new LambdaWrapper() as jest.Mocked<LambdaWrapper>;
    tool = new OpenAPIGeneratorTool(mockLambdaWrapper);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Tool Configuration', () => {
    it('should have correct name and description', () => {
      expect(tool.name).toBe('generate_openapi_spec');
      expect(tool.description).toContain('Generate OpenAPI 3.1 specifications');
    });

    it('should have valid input schema', () => {
      expect(tool.inputSchema).toBeDefined();
      expect(tool.inputSchema.type).toBe('object');
      expect(tool.inputSchema.properties).toBeDefined();
      expect(tool.inputSchema.required).toContain('info');
    });
  });

  describe('Input Validation', () => {
    it('should validate valid basic OpenAPI input', () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should validate OpenAPI input with servers', () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0',
          description: 'A test API'
        },
        servers: [
          { url: 'https://api.example.com', description: 'Production' }
        ]
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should validate OpenAPI input with domain analysis', () => {
      const args = {
        info: {
          title: 'E-commerce API',
          version: '2.0.0'
        },
        domainAnalysis: 'Customer, Order, Product entities with relationships',
        businessContext: 'Online retail platform',
        apiStyle: 'REST'
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should reject input without required info object', () => {
      const args = {
        paths: {},
        components: {}
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });

    it('should reject invalid API style', () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        apiStyle: 'INVALID'
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });

    it('should reject invalid authentication scheme', () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        authenticationScheme: 'invalid'
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });
  });

  describe('Tool Execution', () => {
    it('should execute successfully with basic OpenAPI spec', async () => {
      const args = {
        info: {
          title: 'E-commerce API',
          version: '1.0.0',
          description: 'API for e-commerce operations'
        },
        servers: [
          { url: 'https://api.example.com/v1' }
        ],
        apiStyle: 'REST',
        authenticationScheme: 'bearer'
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          message: 'OpenAPI specification generated successfully',
          parsed_json: {
            openapi: '3.1.0',
            info: args.info,
            servers: args.servers,
            paths: {},
            components: {}
          },
          authenticated: true,
          user: { userId: 'test-user', username: 'test@example.com' }
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBeFalsy();
      expect(result.content).toBeDefined();
      expect(result.content.length).toBeGreaterThan(0);
      expect(result.content[0]?.type).toBe('text');
      expect(result.content[0]?.text).toContain('OpenAPI specification generated successfully');
    });

    it('should execute successfully with domain analysis', async () => {
      const args = {
        info: {
          title: 'Library API',
          version: '2.0.0'
        },
        domainAnalysis: 'Book, Member, Loan entities with borrowing relationships',
        businessContext: 'Public library management system',
        apiStyle: 'REST',
        sessionId: 'test-session'
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          message: 'OpenAPI specification generated from domain analysis',
          parsed_json: {
            openapi: '3.1.0',
            info: args.info,
            paths: {
              '/books': { get: {}, post: {} },
              '/members': { get: {}, post: {} },
              '/loans': { get: {}, post: {} }
            }
          },
          authenticated: false
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBeFalsy();
      expect(result.content).toBeDefined();
      expect(mockLambdaWrapper.invokeDocumentationGenerator).toHaveBeenCalledWith(
        expect.objectContaining({
          task: 'documentation',
          info: args.info,
          domainAnalysis: args.domainAnalysis,
          businessContext: args.businessContext,
          generationType: 'openapi',
          openapi: '3.1.0'
        }),
        expect.any(Object)
      );
    });

    it('should handle missing required info fields', async () => {
      const args = {
        info: {
          title: 'Test API'
          // Missing version
        }
      };

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('info.title and info.version');
    });

    it('should handle invalid API style', async () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        apiStyle: 'SOAP'
      };

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Invalid API style');
    });

    it('should handle invalid authentication scheme', async () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        authenticationScheme: 'custom'
      };

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Invalid authentication scheme');
    });

    it('should handle Lambda function errors', async () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };

      const mockLambdaResponse = {
        success: false,
        error: 'Documentation generation failed'
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Lambda invocation failed');
    });

    it('should handle Lambda wrapper exceptions', async () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockRejectedValue(new Error('Network error'));

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('OpenAPI generation failed');
    });

    it('should pass authentication context correctly', async () => {
      const args = {
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        userEmail: 'user@example.com',
        sessionId: 'session-123'
      };

      const context = {
        userId: 'user-123',
        sessionId: 'session-123',
        timestamp: new Date()
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          message: 'OpenAPI specification generated',
          parsed_json: { openapi: '3.1.0', info: args.info },
          authenticated: true
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockResolvedValue(mockLambdaResponse);

      await tool.execute(args, context);

      expect(mockLambdaWrapper.invokeDocumentationGenerator).toHaveBeenCalledWith(
        expect.objectContaining({
          task: 'documentation',
          info: args.info,
          generationType: 'openapi',
          openapi: '3.1.0'
        }),
        expect.objectContaining({
          userId: 'user-123',
          userEmail: 'user@example.com',
          sessionId: 'session-123'
        })
      );
    });
  });

  describe('Helper Methods', () => {
    it('should provide usage examples', () => {
      const examples = tool.getExamples();
      
      expect(examples).toBeDefined();
      expect(examples.length).toBeGreaterThan(0);
      expect(examples[0]).toHaveProperty('description');
      expect(examples[0]).toHaveProperty('args');
      expect(examples[0]?.args).toHaveProperty('info');
    });

    it('should provide capabilities information', () => {
      const capabilities = tool.getCapabilities();
      
      expect(capabilities).toBeDefined();
      expect(capabilities).toHaveProperty('supportedFormats');
      expect(capabilities).toHaveProperty('apiStyles');
      expect(capabilities).toHaveProperty('authenticationSchemes');
      expect(capabilities).toHaveProperty('features');
      expect(capabilities).toHaveProperty('limitations');
    });
  });

  describe('OpenAPI Spec Validation', () => {
    it('should validate valid OpenAPI spec', () => {
      const spec = {
        openapi: '3.1.0',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        paths: {}
      };

      const result = tool.validateOpenAPISpec(spec);
      
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should detect missing info object', () => {
      const spec = {
        openapi: '3.1.0',
        paths: {}
      };

      const result = tool.validateOpenAPISpec(spec);
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required "info" object');
    });

    it('should detect missing info.title', () => {
      const spec = {
        openapi: '3.1.0',
        info: {
          version: '1.0.0'
        },
        paths: {}
      };

      const result = tool.validateOpenAPISpec(spec);
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required "info.title"');
    });

    it('should detect missing info.version', () => {
      const spec = {
        openapi: '3.1.0',
        info: {
          title: 'Test API'
        },
        paths: {}
      };

      const result = tool.validateOpenAPISpec(spec);
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Missing required "info.version"');
    });

    it('should detect invalid OpenAPI version', () => {
      const spec = {
        openapi: '2.0',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        paths: {}
      };

      const result = tool.validateOpenAPISpec(spec);
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('OpenAPI version must be 3.x');
    });

    it('should detect invalid server configuration', () => {
      const spec = {
        openapi: '3.1.0',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        servers: [
          { description: 'Missing URL' }
        ],
        paths: {}
      };

      const result = tool.validateOpenAPISpec(spec);
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Server at index 0 missing required "url" property');
    });
  });
});