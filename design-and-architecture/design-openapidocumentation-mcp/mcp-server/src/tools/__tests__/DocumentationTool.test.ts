import { DocumentationTool } from '../DocumentationTool';
import { LambdaWrapper } from '../../services/LambdaWrapper';
import { MCPToolError } from '../../interfaces/MCPTool';

// Mock the LambdaWrapper
jest.mock('../../services/LambdaWrapper');
jest.mock('../../utils/logger');

describe('DocumentationTool', () => {
  let tool: DocumentationTool;
  let mockLambdaWrapper: jest.Mocked<LambdaWrapper>;

  beforeEach(() => {
    mockLambdaWrapper = new LambdaWrapper() as jest.Mocked<LambdaWrapper>;
    tool = new DocumentationTool(mockLambdaWrapper);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Tool Configuration', () => {
    it('should have correct name and description', () => {
      expect(tool.name).toBe('generate_api_documentation');
      expect(tool.description).toContain('Generate comprehensive API documentation');
    });

    it('should have valid input schema', () => {
      expect(tool.inputSchema).toBeDefined();
      expect(tool.inputSchema.type).toBe('object');
      expect(tool.inputSchema.properties).toBeDefined();
      expect(tool.inputSchema.anyOf).toBeDefined();
    });
  });

  describe('Input Validation', () => {
    it('should validate documentation task input', () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should validate security task input', () => {
      const args = {
        task: 'security',
        info: {
          title: 'Banking API',
          version: '2.0.0'
        },
        securitySchemes: {
          bearerAuth: { type: 'http', scheme: 'bearer' }
        }
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should validate governance task input', () => {
      const args = {
        task: 'governance',
        info: {
          title: 'Healthcare API',
          version: '1.0.0'
        },
        governancePolicies: {
          dataRetention: '7 years',
          complianceStandards: ['HIPAA']
        }
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should validate versioning task input', () => {
      const args = {
        task: 'versioning',
        info: {
          title: 'Social API',
          version: '3.0.0'
        },
        versioningStrategy: {
          type: 'semantic',
          deprecationPolicy: '12 months'
        }
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should reject invalid task type', () => {
      const args = {
        task: 'invalid',
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });

    it('should reject invalid format', () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        format: 'invalid'
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });

    it('should reject invalid target audience', () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        targetAudience: 'invalid'
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });
  });

  describe('Tool Execution', () => {
    it('should execute successfully with documentation task', async () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'E-commerce API',
          version: '1.0.0',
          description: 'Complete e-commerce platform API'
        },
        format: 'markdown',
        targetAudience: 'developers',
        includeExamples: true
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          message: 'API documentation generated successfully',
          parsed_json: {
            documentation: 'Generated documentation content...',
            format: 'markdown',
            sections: ['overview', 'endpoints', 'schemas', 'examples']
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
      expect(result.content[0]?.text).toContain('API documentation generated successfully');
    });

    it('should execute successfully with security task', async () => {
      const args = {
        task: 'security',
        info: {
          title: 'Banking API',
          version: '2.0.0'
        },
        securitySchemes: {
          bearerAuth: { type: 'http', scheme: 'bearer' }
        },
        format: 'html'
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          message: 'Security documentation generated',
          parsed_json: {
            securityDefinitions: {
              authentication: 'Bearer token required',
              authorization: 'Role-based access control'
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
          task: 'security',
          info: args.info,
          securitySchemes: args.securitySchemes,
          generationType: 'documentation',
          format: 'html'
        }),
        expect.any(Object)
      );
    });

    it('should execute successfully with governance task and default policies', async () => {
      const args = {
        task: 'governance',
        info: {
          title: 'Healthcare API',
          version: '1.0.0'
        }
        // No governance policies provided - should use defaults
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          message: 'Governance documentation generated',
          parsed_json: {
            policies: {
              dataRetention: '30 days for logs, 7 years for business data',
              accessControl: 'Role-based access control (RBAC)'
            }
          },
          authenticated: false
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBeFalsy();
      expect(mockLambdaWrapper.invokeDocumentationGenerator).toHaveBeenCalledWith(
        expect.objectContaining({
          task: 'governance',
          governancePolicies: expect.objectContaining({
            dataRetention: '30 days for logs, 7 years for business data',
            accessControl: 'Role-based access control (RBAC)',
            auditLogging: true,
            complianceStandards: ['SOC2', 'ISO27001']
          })
        }),
        expect.any(Object)
      );
    });

    it('should execute successfully with versioning task and default strategy', async () => {
      const args = {
        task: 'versioning',
        info: {
          title: 'Social API',
          version: '3.0.0'
        }
        // No versioning strategy provided - should use defaults
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          message: 'Versioning documentation generated',
          parsed_json: {
            versioning: {
              strategy: 'semantic',
              deprecationPolicy: '6 months notice before deprecation'
            }
          },
          authenticated: false
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBeFalsy();
      expect(mockLambdaWrapper.invokeDocumentationGenerator).toHaveBeenCalledWith(
        expect.objectContaining({
          task: 'versioning',
          versioningStrategy: expect.objectContaining({
            type: 'semantic',
            deprecationPolicy: '6 months notice before deprecation',
            backwardCompatibility: true,
            migrationGuide: true
          })
        }),
        expect.any(Object)
      );
    });

    it('should handle invalid task type', async () => {
      const args = {
        task: 'invalid',
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Invalid task type');
    });

    it('should handle invalid format', async () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        format: 'invalid'
      };

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Invalid format');
    });

    it('should handle invalid target audience', async () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        targetAudience: 'invalid'
      };

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Invalid target audience');
    });

    it('should handle Lambda function errors', async () => {
      const args = {
        task: 'documentation',
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
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockRejectedValue(new Error('Network error'));

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Documentation generation failed');
    });

    it('should pass authentication context correctly', async () => {
      const args = {
        task: 'documentation',
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
          message: 'Documentation generated',
          parsed_json: { documentation: 'content' },
          authenticated: true
        }
      };

      mockLambdaWrapper.invokeDocumentationGenerator.mockResolvedValue(mockLambdaResponse);

      await tool.execute(args, context);

      expect(mockLambdaWrapper.invokeDocumentationGenerator).toHaveBeenCalledWith(
        expect.objectContaining({
          task: 'documentation',
          info: args.info,
          generationType: 'documentation'
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
      expect(examples[0]?.args).toHaveProperty('task');
    });

    it('should provide capabilities information', () => {
      const capabilities = tool.getCapabilities();
      
      expect(capabilities).toBeDefined();
      expect(capabilities).toHaveProperty('supportedTasks');
      expect(capabilities).toHaveProperty('outputFormats');
      expect(capabilities).toHaveProperty('targetAudiences');
      expect(capabilities).toHaveProperty('features');
      expect(capabilities).toHaveProperty('limitations');
    });

    it('should provide task-specific requirements', () => {
      const securityReqs = tool.getTaskRequirements('security');
      expect(securityReqs).toHaveProperty('required');
      expect(securityReqs).toHaveProperty('recommended');
      expect(securityReqs).toHaveProperty('optional');
      expect(securityReqs.recommended).toContain('securitySchemes');

      const governanceReqs = tool.getTaskRequirements('governance');
      expect(governanceReqs.recommended).toContain('governancePolicies');

      const versioningReqs = tool.getTaskRequirements('versioning');
      expect(versioningReqs.recommended).toContain('versioningStrategy');

      const docReqs = tool.getTaskRequirements('documentation');
      expect(docReqs.recommended).toContain('paths');
    });
  });

  describe('Documentation Request Validation', () => {
    it('should validate valid documentation request', () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        paths: {},
        components: {}
      };

      const result = tool.validateDocumentationRequest(args);
      
      expect(result.valid).toBe(true);
      expect(result.errors).toHaveLength(0);
    });

    it('should detect missing required fields', () => {
      const args = {
        // Missing both task and info
      };

      const result = tool.validateDocumentationRequest(args);
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('Either "info" object or "task" must be specified');
    });

    it('should detect incomplete info object', () => {
      const args = {
        info: {
          title: 'Test API'
          // Missing version
        }
      };

      const result = tool.validateDocumentationRequest(args);
      
      expect(result.valid).toBe(false);
      expect(result.errors).toContain('info.title and info.version are required when info is provided');
    });

    it('should provide warnings for missing recommended fields', () => {
      const args = {
        task: 'security',
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
        // Missing recommended securitySchemes
      };

      const result = tool.validateDocumentationRequest(args);
      
      expect(result.valid).toBe(true);
      expect(result.warnings.length).toBeGreaterThan(0);
      expect(result.warnings.some(w => w.includes('securitySchemes'))).toBe(true);
    });

    it('should provide suggestions for better documentation', () => {
      const args = {
        task: 'security',
        info: {
          title: 'Test API',
          version: '1.0.0'
        }
      };

      const result = tool.validateDocumentationRequest(args);
      
      expect(result.suggestions.length).toBeGreaterThan(0);
      expect(result.suggestions.some(s => s.includes('security schemes'))).toBe(true);
    });

    it('should warn about disabled examples for developer audience', () => {
      const args = {
        task: 'documentation',
        info: {
          title: 'Test API',
          version: '1.0.0'
        },
        targetAudience: 'developers',
        includeExamples: false
      };

      const result = tool.validateDocumentationRequest(args);
      
      expect(result.warnings.some(w => w.includes('examples'))).toBe(true);
    });
  });
});