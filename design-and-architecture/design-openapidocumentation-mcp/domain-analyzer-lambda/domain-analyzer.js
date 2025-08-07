// S3 operations removed - Lambda now returns responses directly
const { BedrockRuntimeClient, InvokeModelCommand } = require('@aws-sdk/client-bedrock-runtime');
const { v4: uuidv4 } = require('uuid');
const { withAuthentication } = require('./auth-middleware');
// s3Service removed - no longer using S3 for storage

// Configuration - these will come from environment variables in Lambda
// Validate required environment variables
const requiredEnvVars = ['MODEL_ID'];
const missingEnvVars = requiredEnvVars.filter(varName => !process.env[varName]);

if (missingEnvVars.length > 0) {
  throw new Error(`Missing required environment variables: ${missingEnvVars.join(', ')}`);
}

// Authentication configuration
const authConfig = {
  region: process.env.AWS_REGION,
  userPoolId: process.env.COGNITO_USER_POOL_ID,
  clientId: process.env.COGNITO_CLIENT_ID,
  required: process.env.AUTH_REQUIRED !== 'false' // Default to true, can be disabled with AUTH_REQUIRED=false
};

// BUCKET_NAME removed - Lambda now returns responses directly
const REGION = process.env.AWS_REGION; // AWS_REGION is automatically set by Lambda runtime
const BEDROCK_REGION = process.env.BEDROCK_REGION || process.env.AWS_REGION;
const MODEL_ID = process.env.MODEL_ID;

// Analysis types
const ANALYSIS_TYPES = {
  DOMAIN: 'domain',
  BUSINESS_CONTEXT: 'bounded',  // keeping 'bounded' for backward compatibility
  ASCII_DIAGRAM: 'ascii'
};

/**
 * Lambda handler function for domain model analysis
 * @param {Object} event - Lambda event object (with auth info added by middleware)
 * @param {Object} context - Lambda context
 * @returns {Object} - Response object
 */
async function domainAnalyzerHandler(event, context) {
  try {
    // Extract user context from authentication
    const userContext = event.auth?.user || null;
    const isAuthenticated = event.auth?.authenticated || false;
    
    console.log('Domain Analyzer - Authentication Status:', {
      authenticated: isAuthenticated,
      userId: userContext?.sub,
      username: userContext?.username
    });

    // Initialize Bedrock client
    const bedrockClient = new BedrockRuntimeClient({ region: BEDROCK_REGION });

    // Parse request body
    let body;
    if (event.body) {
      body = JSON.parse(event.body);
    } else {
      body = event;
    }

    // Extract image data and prompt
    let imageBase64 = body.imageBase64;
    const imageKey = body.imageKey;
    const prompt = body.prompt || '';
    const businessContext = body.businessContext || ''; // Added business context input
    const analysisType = body.analysisType || ANALYSIS_TYPES.DOMAIN; // 'domain', 'bounded', or 'ascii'
    
    // Extract project context (if provided by backend Lambda)
    const projectContext = body.context || {};
    const projectName = projectContext.projectName || 'default-project';
    
    console.log('Domain Analyzer - Project context:', {
      projectName: projectName,
      analysisType: analysisType
    });
    
    // NOTE: This Lambda no longer saves to S3 - it just returns analysis results
    // The backend Lambda will handle all S3 operations

    // Image handling simplified - only accept base64 data directly
    if (imageKey && !imageBase64) {
      return formatResponse(400, {
        success: false,
        error: 'Image key references are no longer supported. Please provide image data as base64.'
      });
    }

    if (!imageBase64 && !prompt && !businessContext) {
      return formatResponse(400, {
        success: false,
        error: 'Either image data, image key, prompt text, or business context is required'
      });
    }

    let result;
    let extractedText = '';
    let fileName = null;

    // If image is provided, extract text from it
    if (imageBase64) {
      // Process image data directly (no S3 upload needed)

      // NOTE: Image storage is now handled by the backend Lambda
      fileName = `domain-model-${Date.now()}.jpg`;

      // Extract text using Claude 3.7 vision
      extractedText = await extractTextFromImage(bedrockClient, imageBase64);
    }

    // Combine extracted text with any provided prompt
    const combinedInput = extractedText
      ? `${prompt}\n\nExtracted text from diagram:\n${extractedText}`
      : prompt;

    // Perform analysis based on type
    if (analysisType === ANALYSIS_TYPES.BUSINESS_CONTEXT) {
      result = await generateBusinessContexts(bedrockClient, combinedInput);
    } else if (analysisType === ANALYSIS_TYPES.ASCII_DIAGRAM) {
      // For ASCII diagram, use both the combined input and business context if available
      const diagramInput = businessContext
        ? `${combinedInput}\n\nBusiness Context Analysis:\n${businessContext}`
        : combinedInput;
      result = await generateAsciiDiagram(bedrockClient, diagramInput);
    } else {
      result = await analyzeDomainModel(bedrockClient, combinedInput);
    }

    return formatResponse(200, {
      success: true,
      // imageS3Key removed - no longer using S3
      user: isAuthenticated ? {
        userId: userContext.sub,
        username: userContext.username
      } : null,
      authenticated: isAuthenticated,
      ...result
    });

  } catch (error) {
    console.error('Domain Analyzer Error:', error);
    const userContext = event.auth?.user || null;
    const isAuthenticated = event.auth?.authenticated || false;
    
    return formatResponse(500, {
      success: false,
      error: error.message,
      authenticated: isAuthenticated,
      user: isAuthenticated ? {
        userId: userContext?.sub,
        username: userContext?.username
      } : null
    });
  }
}

// Export the handler wrapped with authentication middleware
exports.handler = withAuthentication(domainAnalyzerHandler, authConfig);

/**
 * Format Lambda response with proper headers
 * @param {number} statusCode - HTTP status code
 * @param {Object} body - Response body
 * @returns {Object} - Formatted response
 */
function formatResponse(statusCode, body) {
  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
      'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Session-ID,X-User-Email'
    },
    body: JSON.stringify(body)
  };
}

/**
 * Extract text from an image using Claude 3.7 vision
 * @param {BedrockRuntimeClient} bedrockClient - Bedrock client
 * @param {string} imageBase64 - Base64 encoded image
 * @returns {string} - Extracted text
 */
async function extractTextFromImage(bedrockClient, imageBase64) {
  const extractTextPrompt = {
    role: 'user',
    content: [
      {
        type: 'text',
        text: 'Extract all text content from this domain model image. Return only the text you can read from the image, including entity names, attributes, relationships, and any labels or annotations.'
      },
      {
        type: 'image',
        source: {
          type: 'base64',
          media_type: 'image/jpeg',
          data: imageBase64
        }
      }
    ]
  };

  const extractCommand = new InvokeModelCommand({
    modelId: MODEL_ID,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: 1500,
      messages: [extractTextPrompt]
    })
  });

  const extractResponse = await bedrockClient.send(extractCommand);
  const extractBody = JSON.parse(new TextDecoder().decode(extractResponse.body));
  return extractBody.content[0].text;
}

/**
 * Analyze domain model
 * @param {BedrockRuntimeClient} bedrockClient - Bedrock client
 * @param {string} inputText - Text to analyze
 * @returns {Object} - Analysis result
 */
async function analyzeDomainModel(bedrockClient, inputText) {
  if (!inputText) {
    throw new Error('No input text provided for analysis');
  }

  const analyzePrompt = {
    role: 'user',
    content: [
      {
        type: 'text',
        text: `Analyze this domain model text and identify key entities, attributes, and relationships.

CRITICAL: You MUST follow this EXACT format structure:

# Domain Model Analysis

## ENTITIES
- Entity1: Brief description
- Entity2: Brief description
- Entity3: Brief description

## ATTRIBUTES
### Entity1
- attribute1: type/description
- attribute2: type/description

### Entity2
- attribute1: type/description
- attribute2: type/description

## RELATIONSHIPS
- Entity1 -> Entity2: relationship type and description
- Entity2 -> Entity3: relationship type and description

## DOMAIN INSIGHTS
- Business Rule 1: description
- Business Rule 2: description
- Pattern 1: description
- Pattern 2: description

Rules:
- Use EXACTLY the headers shown above (with # and ##)
- Keep descriptions concise and clear
- Use bullet points consistently
- Do not add extra sections or change the format
- Do not use nested bullet points beyond what's shown

Domain Model Text:
${inputText}`
      }
    ]
  };

  const analyzeCommand = new InvokeModelCommand({
    modelId: MODEL_ID,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: 2000,
      messages: [analyzePrompt]
    })
  });

  const analyzeResponse = await bedrockClient.send(analyzeCommand);
  const analyzeBody = JSON.parse(new TextDecoder().decode(analyzeResponse.body));
  const domainAnalysis = analyzeBody.content[0].text;

  // NOTE: S3 storage is now handled by the backend Lambda
  return {
    domainAnalysis
  };
}

/**
 * Generate business contexts
 * @param {BedrockRuntimeClient} bedrockClient - Bedrock client
 * @param {string} domainAnalysisText - Domain analysis text
 * @returns {Object} - Business contexts result
 */
async function generateBusinessContexts(bedrockClient, domainAnalysisText) {
  if (!domainAnalysisText) {
    throw new Error('No domain analysis text provided');
  }

  const contextPrompt = {
    role: 'user',
    content: [{
      type: 'text',
      text: `Based on this domain analysis, identify business contexts and their communications.

CRITICAL: You MUST follow this EXACT format structure:

# Business Context Analysis

## BUSINESS CONTEXTS
- Context1: Brief description and responsibilities
- Context2: Brief description and responsibilities
- Context3: Brief description and responsibilities

## CONTEXT BOUNDARIES
### Context1
- Entities: entity1, entity2, entity3
- Services: service1, service2
- Data: data1, data2

### Context2
- Entities: entity1, entity2
- Services: service1, service2
- Data: data1, data2

## INTEGRATION PATTERNS
- Context1 <-> Context2: integration pattern and description
- Context2 <-> Context3: integration pattern and description

## DOMAIN EVENTS
- Event1: description and which contexts it affects
- Event2: description and which contexts it affects

## API CONTRACTS
- Context1 API: brief description of exposed interfaces
- Context2 API: brief description of exposed interfaces

Rules:
- Use EXACTLY the headers shown above (with # and ##)
- Keep descriptions concise and clear
- Use bullet points and lists consistently
- Do not add extra sections or change the format
- Do not use nested bullet points beyond what's shown

Domain Analysis:
${domainAnalysisText}`
    }]
  };

  const command = new InvokeModelCommand({
    modelId: MODEL_ID,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: 3000,
      messages: [contextPrompt]
    })
  });

  const response = await bedrockClient.send(command);
  const responseBody = JSON.parse(new TextDecoder().decode(response.body));
  const businessContextAnalysis = responseBody.content[0].text;

  // NOTE: S3 storage is now handled by the backend Lambda
  return {
    businessContextAnalysis
  };
}

/**
 * Generate ASCII diagram of business contexts and their interactions
 * @param {BedrockRuntimeClient} bedrockClient - Bedrock client
 * @param {string} inputText - Text to analyze (can include both domain model and business context)
 * @returns {Object} - ASCII diagram result
 */
async function generateAsciiDiagram(bedrockClient, inputText) {
  if (!inputText) {
    throw new Error('No input text provided for ASCII diagram generation');
  }

  // Debug log the input
  console.log('🔍 Lambda ASCII Generation Debug:', {
    inputTextLength: inputText.length,
    inputTextPreview: inputText.substring(0, 200) + '...',
    containsDomainAnalysis: inputText.includes('# Domain Model Analysis'),
    containsBusinessContext: inputText.includes('# Business Context Analysis')
  });

  const diagramPrompt = {
    role: 'user',
    content: [{
      type: 'text',
      text: `Based on this domain description and business context analysis, create an ASCII diagram showing business contexts and their interactions.

CRITICAL: You MUST follow this EXACT format structure:

# Business Context Diagram

## ASCII Diagram
\`\`\`
┌─────────────────┐    API Calls    ┌─────────────────┐
│   Context1      │ ──────────────> │   Context2      │
│                 │                 │                 │
│ - Entity1       │                 │ - Entity3       │
│ - Entity2       │                 │ - Entity4       │
└─────────────────┘                 └─────────────────┘
         │                                   │
         │ Events                            │ Data Sync
         ▼                                   ▼
┌─────────────────┐                 ┌─────────────────┐
│   Context3      │ <──────────────> │   Context4      │
│                 │   Shared Data    │                 │
│ - Entity5       │                 │ - Entity6       │
│ - Entity7       │                 │ - Entity8       │
└─────────────────┘                 └─────────────────┘
\`\`\`

## Legend
- ┌─┐ : Business Context boundaries
- ──> : API calls or direct communication
- <──> : Bidirectional communication
- ▼   : Event flow or data flow

## Context Descriptions
- Context1: Brief description of responsibilities
- Context2: Brief description of responsibilities
- Context3: Brief description of responsibilities
- Context4: Brief description of responsibilities

## Integration Patterns
- Context1 → Context2: Description of integration pattern
- Context3 ↔ Context4: Description of bidirectional integration

Rules:
- Use EXACTLY the format shown above
- Use box drawing characters: ┌ ┐ └ ┘ │ ─ ├ ┤ ┬ ┴ ┼
- Keep the diagram clean and readable
- Include entity names inside context boxes
- Label all arrows with interaction types
- Keep descriptions concise
- Do not add extra sections beyond what's shown

Domain Description and Business Context:
${inputText}`
    }]
  };

  const command = new InvokeModelCommand({
    modelId: MODEL_ID,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      max_tokens: 4000,
      messages: [diagramPrompt]
    })
  });

  const response = await bedrockClient.send(command);
  const responseBody = JSON.parse(new TextDecoder().decode(response.body));
  const asciiDiagram = responseBody.content[0].text;

  // Debug log the generated ASCII
  console.log('🎨 Lambda ASCII Generation Result:', {
    asciiDiagramLength: asciiDiagram.length,
    asciiDiagramPreview: asciiDiagram.substring(0, 200) + '...',
    containsAsciiChars: /[┌┐└┘│─├┤┬┴┼]/.test(asciiDiagram),
    containsPokemon: asciiDiagram.toLowerCase().includes('pokemon')
  });

  // NOTE: S3 storage is now handled by the backend Lambda
  return {
    asciiDiagram
  };
}