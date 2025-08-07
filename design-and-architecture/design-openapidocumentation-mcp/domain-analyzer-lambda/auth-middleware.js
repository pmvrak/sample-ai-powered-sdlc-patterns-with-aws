const https = require('https');
const crypto = require('crypto');

/**
 * JWT validation middleware for Lambda functions
 * Validates JWT tokens using Cognito public keys
 */

/**
 * Cache for Cognito public keys to avoid repeated fetches
 */
let cognitoKeysCache = null;
let cacheExpiry = 0;
const CACHE_DURATION = 3600000; // 1 hour in milliseconds

/**
 * Fetch Cognito public keys from the JWKS endpoint
 * @param {string} region - AWS region
 * @param {string} userPoolId - Cognito User Pool ID
 * @returns {Promise<Object>} - JWKS keys
 */
async function fetchCognitoKeys(region, userPoolId) {
  const now = Date.now();
  
  // Return cached keys if still valid
  if (cognitoKeysCache && now < cacheExpiry) {
    return cognitoKeysCache;
  }

  const jwksUrl = `https://cognito-idp.${region}.amazonaws.com/${userPoolId}/.well-known/jwks.json`;
  
  return new Promise((resolve, reject) => {
    https.get(jwksUrl, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const jwks = JSON.parse(data);
          
          // Cache the keys
          cognitoKeysCache = jwks;
          cacheExpiry = now + CACHE_DURATION;
          
          resolve(jwks);
        } catch (error) {
          reject(new Error(`Failed to parse JWKS response: ${error.message}`));
        }
      });
    }).on('error', (error) => {
      reject(new Error(`Failed to fetch JWKS: ${error.message}`));
    });
  });
}

/**
 * Convert JWK to PEM format for verification
 * @param {Object} jwk - JSON Web Key
 * @returns {string} - PEM formatted key
 */
function jwkToPem(jwk) {
  if (jwk.kty !== 'RSA') {
    throw new Error('Only RSA keys are supported');
  }

  // Convert base64url to buffer
  const nBuffer = Buffer.from(jwk.n, 'base64url');
  const eBuffer = Buffer.from(jwk.e, 'base64url');

  // Create ASN.1 structure for RSA public key
  const modulus = Buffer.concat([Buffer.from([0x00]), nBuffer]);
  const exponent = eBuffer;

  const modulusLength = modulus.length;
  const exponentLength = exponent.length;

  const sequenceLength = modulusLength + exponentLength + 4;
  const bitStringLength = sequenceLength + 1;
  const totalLength = bitStringLength + 15;

  const der = Buffer.alloc(totalLength);
  let offset = 0;

  // SEQUENCE
  der[offset++] = 0x30;
  der[offset++] = totalLength - 2;

  // SEQUENCE
  der[offset++] = 0x30;
  der[offset++] = 0x0d;

  // OBJECT IDENTIFIER (rsaEncryption)
  der[offset++] = 0x06;
  der[offset++] = 0x09;
  der[offset++] = 0x2a;
  der[offset++] = 0x86;
  der[offset++] = 0x48;
  der[offset++] = 0x86;
  der[offset++] = 0xf7;
  der[offset++] = 0x0d;
  der[offset++] = 0x01;
  der[offset++] = 0x01;
  der[offset++] = 0x01;

  // NULL
  der[offset++] = 0x05;
  der[offset++] = 0x00;

  // BIT STRING
  der[offset++] = 0x03;
  der[offset++] = bitStringLength;
  der[offset++] = 0x00;

  // SEQUENCE
  der[offset++] = 0x30;
  der[offset++] = sequenceLength;

  // INTEGER (modulus)
  der[offset++] = 0x02;
  der[offset++] = modulusLength;
  modulus.copy(der, offset);
  offset += modulusLength;

  // INTEGER (exponent)
  der[offset++] = 0x02;
  der[offset++] = exponentLength;
  exponent.copy(der, offset);

  // Convert to PEM
  const base64 = der.toString('base64');
  const pem = `-----BEGIN PUBLIC KEY-----\n${base64.match(/.{1,64}/g).join('\n')}\n-----END PUBLIC KEY-----`;
  
  return pem;
}

/**
 * Decode JWT token without verification (for header inspection)
 * @param {string} token - JWT token
 * @returns {Object} - Decoded token parts
 */
function decodeJWT(token) {
  const parts = token.split('.');
  
  if (parts.length !== 3) {
    throw new Error('Invalid JWT format');
  }

  try {
    const header = JSON.parse(Buffer.from(parts[0], 'base64url').toString());
    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString());
    
    return {
      header,
      payload,
      signature: parts[2]
    };
  } catch (error) {
    throw new Error(`Failed to decode JWT: ${error.message}`);
  }
}

/**
 * Verify JWT signature using Cognito public keys
 * @param {string} token - JWT token
 * @param {string} region - AWS region
 * @param {string} userPoolId - Cognito User Pool ID
 * @param {string} clientId - Cognito User Pool Client ID
 * @returns {Promise<Object>} - Verified token payload
 */
async function verifyJWT(token, region, userPoolId, clientId) {
  try {
    // Decode token to get header and payload
    const decoded = decodeJWT(token);
    const { header, payload } = decoded;

    // Validate token structure
    if (!header.kid) {
      throw new Error('Token header missing key ID (kid)');
    }

    if (!header.alg || header.alg !== 'RS256') {
      throw new Error('Token must use RS256 algorithm');
    }

    // Validate token claims
    const now = Math.floor(Date.now() / 1000);
    
    if (payload.exp && payload.exp < now) {
      throw new Error('Token has expired');
    }

    if (payload.nbf && payload.nbf > now) {
      throw new Error('Token is not yet valid');
    }

    if (payload.iss !== `https://cognito-idp.${region}.amazonaws.com/${userPoolId}`) {
      throw new Error('Invalid token issuer');
    }

    if (payload.aud !== clientId && payload.client_id !== clientId) {
      throw new Error('Invalid token audience');
    }

    if (payload.token_use !== 'access' && payload.token_use !== 'id') {
      throw new Error('Invalid token use');
    }

    // Fetch Cognito public keys
    const jwks = await fetchCognitoKeys(region, userPoolId);
    
    // Find the key that matches the token's kid
    const key = jwks.keys.find(k => k.kid === header.kid);
    if (!key) {
      throw new Error('Token key ID not found in JWKS');
    }

    // Convert JWK to PEM
    const pem = jwkToPem(key);

    // Verify signature
    const [headerB64, payloadB64, signatureB64] = token.split('.');
    const signatureData = `${headerB64}.${payloadB64}`;
    const signature = Buffer.from(signatureB64, 'base64url');

    const verifier = crypto.createVerify('RSA-SHA256');
    verifier.update(signatureData);
    
    const isValid = verifier.verify(pem, signature);
    
    if (!isValid) {
      throw new Error('Invalid token signature');
    }

    return payload;
  } catch (error) {
    throw new Error(`JWT verification failed: ${error.message}`);
  }
}

/**
 * Extract JWT token from Lambda event
 * @param {Object} event - Lambda event object
 * @returns {string|null} - JWT token or null if not found
 */
function extractTokenFromEvent(event) {
  // Check Authorization header
  const headers = event.headers || {};
  const authHeader = headers.Authorization || headers.authorization;
  
  if (authHeader && authHeader.startsWith('Bearer ')) {
    return authHeader.substring(7);
  }

  // Check query parameters
  if (event.queryStringParameters && event.queryStringParameters.token) {
    return event.queryStringParameters.token;
  }

  // Check request context (for API Gateway)
  if (event.requestContext && event.requestContext.authorizer && event.requestContext.authorizer.jwt) {
    return event.requestContext.authorizer.jwt.token;
  }

  return null;
}

/**
 * Create authentication error response
 * @param {string} message - Error message
 * @param {number} statusCode - HTTP status code (default: 401)
 * @returns {Object} - Lambda response object
 */
function createAuthErrorResponse(message, statusCode = 401) {
  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
      'Access-Control-Allow-Headers': 'Content-Type,Authorization'
    },
    body: JSON.stringify({
      success: false,
      error: message,
      code: 'AUTHENTICATION_ERROR'
    })
  };
}

/**
 * Main authentication middleware function
 * @param {Object} event - Lambda event object
 * @param {Object} config - Configuration object
 * @param {string} config.region - AWS region
 * @param {string} config.userPoolId - Cognito User Pool ID
 * @param {string} config.clientId - Cognito User Pool Client ID
 * @param {boolean} config.required - Whether authentication is required (default: true)
 * @returns {Promise<Object>} - Authentication result
 */
async function authenticateRequest(event, config) {
  const { region, userPoolId, clientId, required = true } = config;

  try {
    // Extract token from event
    const token = extractTokenFromEvent(event);

    // If no token and authentication is not required, return success with no user
    if (!token && !required) {
      return {
        success: true,
        authenticated: false,
        user: null
      };
    }

    // If no token and authentication is required, return error
    if (!token && required) {
      return {
        success: false,
        error: createAuthErrorResponse('Missing authentication token')
      };
    }

    // Verify the token
    const payload = await verifyJWT(token, region, userPoolId, clientId);

    // Return successful authentication result
    return {
      success: true,
      authenticated: true,
      user: {
        sub: payload.sub,
        username: payload['cognito:username'] || payload.username,
        email: payload.email,
        tokenUse: payload.token_use,
        clientId: payload.client_id || payload.aud,
        scope: payload.scope,
        groups: payload['cognito:groups'] || []
      },
      token: payload
    };

  } catch (error) {
    console.error('Authentication error:', error.message);
    
    return {
      success: false,
      error: createAuthErrorResponse(error.message)
    };
  }
}

/**
 * Middleware wrapper for Lambda functions
 * @param {Function} handler - Original Lambda handler
 * @param {Object} authConfig - Authentication configuration
 * @returns {Function} - Wrapped handler with authentication
 */
function withAuthentication(handler, authConfig) {
  return async (event, context) => {
    // Perform authentication
    const authResult = await authenticateRequest(event, authConfig);

    // If authentication failed, return error response
    if (!authResult.success) {
      return authResult.error;
    }

    // Add authentication info to event
    event.auth = authResult;

    // Call original handler
    return handler(event, context);
  };
}

module.exports = {
  authenticateRequest,
  withAuthentication,
  verifyJWT,
  extractTokenFromEvent,
  createAuthErrorResponse,
  decodeJWT
};