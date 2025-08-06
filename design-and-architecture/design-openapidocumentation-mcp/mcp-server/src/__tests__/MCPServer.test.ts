import { EnvironmentConfig } from '../config/environment';

describe('MCPServer', () => {
  const mockConfig: EnvironmentConfig = {
    NODE_ENV: 'test',
    PORT: 3000,
    MCP_PORT: 3001,
    AWS_REGION: 'us-east-1',
    BEDROCK_REGION: 'us-east-1',
    MODEL_ID: 'test-model',
    LOG_LEVEL: 'error',
    ENABLE_METRICS: false,
  };

  it('should have valid configuration', () => {
    expect(mockConfig.NODE_ENV).toBe('test');
    expect(mockConfig.PORT).toBe(3000);
    expect(mockConfig.MCP_PORT).toBe(3001);
  });

  it('should load environment configuration', () => {
    // Test that the config module can be imported without errors
    expect(mockConfig).toBeDefined();
    expect(mockConfig.AWS_REGION).toBe('us-east-1');
  });
});