# JWT Authentication Middleware

This module provides JWT validation middleware for AWS Lambda functions using AWS Cognito authentication.

## Features

- JWT token validation using Cognito public keys
- Automatic key caching for performance
- Support for both access and ID tokens
- Comprehensive error handling
- Easy integration with existing Lambda functions
- Support for optional authentication

## Installation

```bash
npm install
```

## Usage

### Basic Usage with Middleware Wrapper

```javascript
const { withAuthentication } = require('./shared/auth-middleware');

// Your original Lambda handler
async function myHandler(event, context) {
  // Access authenticated user info
  const user = event.auth.user;
  console.log('Authenticated user:', user.username);
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      message: 'Hello authenticated user!',
      user: user.username
    })
  };
}

// Wrap with authentication
const authConfig = {
  region: process.env.AWS_REGION,
  userPoolId: process.env.COGNITO_USER_POOL_ID,
  clientId: process.env.COGNITO_CLIENT_ID,
  required: true // Set to false for optional authentication
};

exports.handler = withAuthentication(myHandler, authConfig);
```

### Manual Authentication Check

```javascript
const { authenticateRequest } = require('./shared/auth-middleware');

exports.handler = async (event, context) => {
  const authConfig = {
    region: process.env.AWS_REGION,
    userPoolId: process.env.COGNITO_USER_POOL_ID,
    clientId: process.env.COGNITO_CLIENT_ID,
    required: true
  };

  // Perform authentication
  const authResult = await authenticateRequest(event, authConfig);

  if (!authResult.success) {
    return authResult.error;
  }

  // Continue with authenticated request
  const user = authResult.user;
  
  return {
    statusCode: 200,
    body: JSON.stringify({
      message: 'Authenticated successfully',
      user: user.username
    })
  };
};
```

### Optional Authentication

```javascript
const { authenticateRequest } = require('./shared/auth-middleware');

exports.handler = async (event, context) => {
  const authConfig = {
    region: process.env.AWS_REGION,
    userPoolId: process.env.COGNITO_USER_POOL_ID,
    clientId: process.env.COGNITO_CLIENT_ID,
    required: false // Authentication is optional
  };

  const authResult = await authenticateRequest(event, authConfig);

  if (!authResult.success) {
    return authResult.error;
  }

  if (authResult.authenticated) {
    // User is authenticated
    return {
      statusCode: 200,
      body: JSON.stringify({
        message: `Hello ${authResult.user.username}!`,
        authenticated: true
      })
    };
  } else {
    // User is not authenticated but that's okay
    return {
      statusCode: 200,
      body: JSON.stringify({
        message: 'Hello anonymous user!',
        authenticated: false
      })
    };
  }
};
```

## Configuration

The authentication middleware requires the following configuration:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `region` | string | Yes | AWS region where Cognito User Pool is located |
| `userPoolId` | string | Yes | Cognito User Pool ID |
| `clientId` | string | Yes | Cognito User Pool Client ID |
| `required` | boolean | No | Whether authentication is required (default: true) |

## Environment Variables

Set these environment variables in your Lambda function:

```bash
AWS_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID=your-client-id
```

## Token Sources

The middleware automatically extracts JWT tokens from:

1. **Authorization Header**: `Authorization: Bearer <token>`
2. **Query Parameters**: `?token=<token>`

## User Object

When authentication is successful, the user object contains:

```javascript
{
  sub: 'user-uuid',
  username: 'username',
  email: 'user@example.com',
  tokenUse: 'access', // or 'id'
  clientId: 'client-id',
  scope: 'openid email profile',
  groups: ['admin', 'users'] // Cognito groups
}
```

## Error Handling

The middleware handles various error scenarios:

- **Missing Token**: Returns 401 when token is required but missing
- **Invalid Token Format**: Returns 401 for malformed JWT tokens
- **Expired Token**: Returns 401 for expired tokens
- **Invalid Signature**: Returns 401 for tokens with invalid signatures
- **Wrong Issuer/Audience**: Returns 401 for tokens from wrong Cognito pool
- **Network Errors**: Returns 401 when unable to fetch Cognito keys

## Performance

- **Key Caching**: Cognito public keys are cached for 1 hour to reduce API calls
- **Efficient Verification**: Uses Node.js crypto module for fast signature verification
- **Minimal Dependencies**: No external dependencies beyond Node.js built-ins

## Testing

Run the test suite:

```bash
npm test
```

Run tests in watch mode:

```bash
npm run test:watch
```

## Security Considerations

- Always use HTTPS in production
- Validate token expiration times
- Implement proper CORS policies
- Use short-lived access tokens
- Implement rate limiting
- Log authentication failures for monitoring

## Troubleshooting

### Common Issues

1. **"Token key ID not found in JWKS"**
   - Verify the User Pool ID is correct
   - Check that the token was issued by the correct Cognito pool

2. **"Invalid token issuer"**
   - Ensure the region and User Pool ID match the token issuer

3. **"Invalid token audience"**
   - Verify the Client ID matches the token audience

4. **"Failed to fetch JWKS"**
   - Check network connectivity
   - Verify the region is correct
   - Ensure Lambda has internet access

### Debug Mode

Enable debug logging by setting the environment variable:

```bash
DEBUG=auth-middleware
```

## License

ISC