const {
  decodeJWT,
  extractTokenFromEvent,
  createAuthErrorResponse,
  authenticateRequest
} = require('./auth-middleware');

// Mock JWT token for testing (this is a sample token structure, not a real token)
const mockJWTHeader = {
  alg: 'RS256',
  kid: 'test-key-id',
  typ: 'JWT'
};

const mockJWTPayload = {
  sub: 'test-user-id',
  'cognito:username': 'testuser',
  email: 'test@example.com',
  iss: 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST123',
  aud: 'test-client-id',
  token_use: 'access',
  exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour from now
  iat: Math.floor(Date.now() / 1000),
  scope: 'openid email profile'
};

// Create a mock JWT token (base64url encoded)
function createMockJWT(header = mockJWTHeader, payload = mockJWTPayload) {
  const headerB64 = Buffer.from(JSON.stringify(header)).toString('base64url');
  const payloadB64 = Buffer.from(JSON.stringify(payload)).toString('base64url');
  const signature = 'mock-signature'; // This would be a real signature in production
  
  return `${headerB64}.${payloadB64}.${signature}`;
}

describe('JWT Authentication Middleware', () => {
  describe('decodeJWT', () => {
    test('should decode valid JWT token', () => {
      const token = createMockJWT();
      const decoded = decodeJWT(token);
      
      expect(decoded.header).toEqual(mockJWTHeader);
      expect(decoded.payload).toEqual(mockJWTPayload);
      expect(decoded.signature).toBe('mock-signature');
    });

    test('should throw error for invalid JWT format', () => {
      expect(() => decodeJWT('invalid.token')).toThrow('Invalid JWT format');
      expect(() => decodeJWT('invalid')).toThrow('Invalid JWT format');
    });

    test('should throw error for malformed JWT parts', () => {
      expect(() => decodeJWT('invalid.invalid.invalid')).toThrow('Failed to decode JWT');
    });
  });

  describe('extractTokenFromEvent', () => {
    test('should extract token from Authorization header', () => {
      const event = {
        headers: {
          Authorization: 'Bearer test-token'
        }
      };
      
      expect(extractTokenFromEvent(event)).toBe('test-token');
    });

    test('should extract token from lowercase authorization header', () => {
      const event = {
        headers: {
          authorization: 'Bearer test-token'
        }
      };
      
      expect(extractTokenFromEvent(event)).toBe('test-token');
    });

    test('should extract token from query parameters', () => {
      const event = {
        queryStringParameters: {
          token: 'test-token'
        }
      };
      
      expect(extractTokenFromEvent(event)).toBe('test-token');
    });

    test('should return null when no token found', () => {
      const event = {
        headers: {}
      };
      
      expect(extractTokenFromEvent(event)).toBeNull();
    });

    test('should handle missing headers', () => {
      const event = {};
      
      expect(extractTokenFromEvent(event)).toBeNull();
    });
  });

  describe('createAuthErrorResponse', () => {
    test('should create default 401 error response', () => {
      const response = createAuthErrorResponse('Test error');
      
      expect(response.statusCode).toBe(401);
      expect(response.headers['Content-Type']).toBe('application/json');
      expect(response.headers['Access-Control-Allow-Origin']).toBe('*');
      
      const body = JSON.parse(response.body);
      expect(body.success).toBe(false);
      expect(body.error).toBe('Test error');
      expect(body.code).toBe('AUTHENTICATION_ERROR');
    });

    test('should create custom status code error response', () => {
      const response = createAuthErrorResponse('Forbidden', 403);
      
      expect(response.statusCode).toBe(403);
      
      const body = JSON.parse(response.body);
      expect(body.error).toBe('Forbidden');
    });
  });

  describe('authenticateRequest', () => {
    const mockConfig = {
      region: 'us-east-1',
      userPoolId: 'us-east-1_TEST123',
      clientId: 'test-client-id',
      required: true
    };

    test('should return error when token is required but missing', async () => {
      const event = { headers: {} };
      
      const result = await authenticateRequest(event, mockConfig);
      
      expect(result.success).toBe(false);
      expect(result.error.statusCode).toBe(401);
    });

    test('should return success when token is not required and missing', async () => {
      const event = { headers: {} };
      const config = { ...mockConfig, required: false };
      
      const result = await authenticateRequest(event, config);
      
      expect(result.success).toBe(true);
      expect(result.authenticated).toBe(false);
      expect(result.user).toBeNull();
    });

    test('should handle malformed tokens gracefully', async () => {
      const event = {
        headers: {
          Authorization: 'Bearer invalid-token'
        }
      };
      
      const result = await authenticateRequest(event, mockConfig);
      
      expect(result.success).toBe(false);
      expect(result.error.statusCode).toBe(401);
    });
  });
});

// Export test utilities for use in other test files
module.exports = {
  createMockJWT,
  mockJWTHeader,
  mockJWTPayload
};