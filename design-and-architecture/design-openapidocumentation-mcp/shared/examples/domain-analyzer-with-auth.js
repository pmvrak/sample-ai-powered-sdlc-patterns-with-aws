/**
 * Example: Domain Analyzer Lambda with JWT Authentication
 * This shows how to integrate the JWT validation middleware with the existing domain-analyzer Lambda
 */

const { authenticateRequest } = require('../auth-middleware');
const { S3Client, PutObjectCommand, GetObjectCommand } = require('@aws-sdk/client-s3');
const { BedrockRuntimeClient, InvokeModelCommand } = require('@aws-sdk/client-bedrock-runtime');

// Original domain analyzer logic (simplified for example)
async function analyzeDomain(s3Client, bedrockClient, inputText, user) {
  // Your existing domain analysis logic here
  // Now you can include user context in the analysis
  
  const analysis = `Domain analysis for user: ${user.username}\n\n${inputText}`;
  
  // Save analysis with user context
  const analysisFileName = `domain-analysis-${user.username}-${Date.now()}.txt`;
  
  await s3Client.send(new PutObjectCommand({
    Bucket: process.env.BUCKET_NAME,
    Key: analysisFileName,
    Body: analysis,
    ContentType: 'text/plain',
    Metadata: {
      'analyzed-by': user.username,
      'user-id': user.sub
    }
  }));

  return {
    analysisS3Key: analysisFileName,
    domainAnalysis: analysis,
    analyzedBy: user.username
  };
}

exports.handler = async (event, context) => {
  try {
    // Authentication configuration
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

    const user = authResult.user;
    console.log(`Domain analysis request from user: ${user.username}`);

    // Initialize AWS clients
    const s3Client = new S3Client({ region: process.env.AWS_REGION });
    const bedrockClient = new BedrockRuntimeClient({ 
      region: process.env.BEDROCK_REGION || process.env.AWS_REGION 
    });

    // Parse request body
    let body;
    if (event.body) {
      body = JSON.parse(event.body);
    } else {
      body = event;
    }

    const { imageBase64, imageKey, prompt, businessContext, analysisType } = body;

    // Your existing domain analysis logic here
    // Pass user context to analysis functions
    const result = await analyzeDomain(s3Client, bedrockClient, prompt, user);

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
      },
      body: JSON.stringify({
        success: true,
        user: user.username,
        ...result
      })
    };

  } catch (error) {
    console.error('Domain analysis error:', error);
    
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
};