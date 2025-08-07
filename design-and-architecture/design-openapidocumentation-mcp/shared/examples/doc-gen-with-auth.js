/**
 * Example: Doc Generator Lambda with JWT Authentication
 * This shows how to integrate the JWT validation middleware with the existing doc-gen Lambda
 */

const { withAuthentication } = require('../auth-middleware');
const { BedrockRuntimeClient, InvokeModelCommand } = require('@aws-sdk/client-bedrock-runtime');

// Original doc-gen logic (simplified for example)
async function docGenHandler(event, context) {
  try {
    console.log("Authenticated doc generation request");
    
    // Access authenticated user info
    const user = event.auth.user;
    console.log(`Processing request for user: ${user.username}`);
    
    // Your existing doc generation logic here
    const openApiSpec = event;
    
    // Example: Add user context to generated documentation
    const result = {
      message: "Documentation generated successfully",
      generatedBy: user.username,
      generatedAt: new Date().toISOString(),
      // ... rest of your doc generation results
    };

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
      },
      body: JSON.stringify(result)
    };

  } catch (error) {
    console.error('Doc generation error:', error);
    
    return {
      statusCode: 500,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      },
      body: JSON.stringify({
        success: false,
        error: error.message
      })
    };
  }
}

// Authentication configuration
const authConfig = {
  region: process.env.AWS_REGION,
  userPoolId: process.env.COGNITO_USER_POOL_ID,
  clientId: process.env.COGNITO_CLIENT_ID,
  required: true
};

// Export the handler wrapped with authentication
exports.handler = withAuthentication(docGenHandler, authConfig);