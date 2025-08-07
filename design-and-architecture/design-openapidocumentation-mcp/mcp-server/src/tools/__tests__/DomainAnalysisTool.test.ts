import { DomainAnalysisTool } from '../DomainAnalysisTool';
import { LambdaWrapper } from '../../services/LambdaWrapper';
import { MCPToolError } from '../../interfaces/MCPTool';

// Mock the LambdaWrapper
jest.mock('../../services/LambdaWrapper');
jest.mock('../../utils/logger');

describe('DomainAnalysisTool', () => {
  let tool: DomainAnalysisTool;
  let mockLambdaWrapper: jest.Mocked<LambdaWrapper>;

  beforeEach(() => {
    mockLambdaWrapper = new LambdaWrapper() as jest.Mocked<LambdaWrapper>;
    tool = new DomainAnalysisTool(mockLambdaWrapper);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Tool Configuration', () => {
    it('should have correct name and description', () => {
      expect(tool.name).toBe('analyze_domain_model');
      expect(tool.description).toContain('Analyze domain models');
    });

    it('should have valid input schema', () => {
      expect(tool.inputSchema).toBeDefined();
      expect(tool.inputSchema.type).toBe('object');
      expect(tool.inputSchema.properties).toBeDefined();
      expect(tool.inputSchema.anyOf).toBeDefined();
    });
  });

  describe('Input Validation', () => {
    it('should validate valid text prompt input', () => {
      const args = {
        prompt: 'Analyze e-commerce domain',
        analysisType: 'domain'
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should validate valid image key input', () => {
      const args = {
        imageKey: 'user-uploads/diagram.png',
        analysisType: 'bounded'
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should validate valid base64 image input', () => {
      const args = {
        imageBase64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
        analysisType: 'ascii'
      };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should reject input without required fields', () => {
      const args = {
        analysisType: 'domain'
        // Missing prompt, imageBase64, or imageKey
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });

    it('should reject invalid analysis type', () => {
      const args = {
        prompt: 'Test prompt',
        analysisType: 'invalid'
      };
      
      expect(() => tool.validateInput(args)).toThrow(MCPToolError);
    });
  });

  describe('Tool Execution', () => {
    it('should execute successfully with text prompt', async () => {
      const args = {
        prompt: 'Analyze e-commerce domain with Customer, Order, Product entities',
        analysisType: 'domain',
        businessContext: 'Online retail platform'
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          success: true,
          domainAnalysis: 'Domain analysis results...',
          businessContextAnalysis: 'Business context insights...',
          authenticated: true,
          user: { userId: 'test-user', username: 'test@example.com' }
        }
      };

      mockLambdaWrapper.invokeDomainAnalyzer.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBeFalsy();
      expect(result.content).toBeDefined();
      expect(result.content.length).toBeGreaterThan(0);
      expect(result.content[0]?.type).toBe('text');
      expect(result.content[0]?.text).toContain('Domain Analysis Results');
    });

    it('should execute successfully with image key', async () => {
      const args = {
        imageKey: 'user-uploads/domain-diagram.png',
        analysisType: 'bounded',
        sessionId: 'test-session'
      };

      const mockLambdaResponse = {
        success: true,
        payload: {
          success: true,
          domainAnalysis: 'Bounded context analysis...',
          imageS3Key: 'processed/domain-diagram.png',
          authenticated: false
        }
      };

      mockLambdaWrapper.invokeDomainAnalyzer.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBeFalsy();
      expect(result.content).toBeDefined();
      expect(mockLambdaWrapper.invokeDomainAnalyzer).toHaveBeenCalledWith(
        expect.objectContaining({
          imageKey: 'user-uploads/domain-diagram.png',
          analysisType: 'bounded',
          sessionId: 'test-session'
        }),
        expect.any(Object)
      );
    });

    it('should handle Lambda function errors', async () => {
      const args = {
        prompt: 'Test prompt',
        analysisType: 'domain'
      };

      const mockLambdaResponse = {
        success: false,
        error: 'Lambda function failed'
      };

      mockLambdaWrapper.invokeDomainAnalyzer.mockResolvedValue(mockLambdaResponse);

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Lambda invocation failed');
    });

    it('should handle Lambda wrapper exceptions', async () => {
      const args = {
        prompt: 'Test prompt',
        analysisType: 'domain'
      };

      mockLambdaWrapper.invokeDomainAnalyzer.mockRejectedValue(new Error('Network error'));

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Domain analysis failed');
    });

    it('should validate base64 image data', async () => {
      const args = {
        imageBase64: 'invalid-base64-data',
        analysisType: 'domain'
      };

      const result = await tool.execute(args);

      expect(result.isError).toBe(true);
      expect(result.content[0]?.text).toContain('Invalid base64 image data');
    });

    it('should pass authentication context correctly', async () => {
      const args = {
        prompt: 'Test prompt',
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
          success: true,
          domainAnalysis: 'Analysis results...',
          authenticated: true
        }
      };

      mockLambdaWrapper.invokeDomainAnalyzer.mockResolvedValue(mockLambdaResponse);

      await tool.execute(args, context);

      expect(mockLambdaWrapper.invokeDomainAnalyzer).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: 'Test prompt',
          userEmail: 'user@example.com',
          sessionId: 'session-123'
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
    });

    it('should provide capabilities information', () => {
      const capabilities = tool.getCapabilities();
      
      expect(capabilities).toBeDefined();
      expect(capabilities).toHaveProperty('supportedInputs');
      expect(capabilities).toHaveProperty('analysisTypes');
      expect(capabilities).toHaveProperty('outputFormats');
      expect(capabilities).toHaveProperty('limitations');
    });
  });

  describe('Base64 Image Validation', () => {
    it('should accept valid PNG base64', () => {
      // Valid 1x1 PNG image
      const validPng = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==';
      const args = { imageBase64: validPng, analysisType: 'domain' };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });

    it('should accept valid JPEG base64', () => {
      // Valid minimal JPEG header
      const validJpeg = '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/2wBDAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAv/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwA/8A8A';
      const args = { imageBase64: validJpeg, analysisType: 'domain' };
      
      expect(() => tool.validateInput(args)).not.toThrow();
    });
  });
});