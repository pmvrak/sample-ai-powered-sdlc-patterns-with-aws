const { BedrockRuntimeClient, InvokeModelCommand } = require('@aws-sdk/client-bedrock-runtime');
const { withAuthentication } = require('./auth-middleware');
const s3Service = require('./s3Service');

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

// Configuration
const BEDROCK_REGION = process.env.BEDROCK_REGION;
const MODEL_ID = process.env.MODEL_ID;

/**
 * Format Lambda response with proper headers and authentication info
 * @param {number} statusCode - HTTP status code
 * @param {Object} body - Response body
 * @param {boolean} isAuthenticated - Whether user is authenticated
 * @param {Object} userContext - User context from JWT
 * @returns {Object} - Formatted response
 */
function formatResponse(statusCode, body, isAuthenticated = false, userContext = null) {
  const responseBody = {
    ...body,
    authenticated: isAuthenticated,
    user: isAuthenticated && userContext ? {
      userId: userContext.sub,
      username: userContext.username
    } : null
  };

  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
      'Access-Control-Allow-Headers': 'Content-Type,Authorization'
    },
    body: JSON.stringify(responseBody, null, 2)
  };
}

/**
 * Clean and parse JSON response from Claude
 * @param {string} text - Raw text response
 * @returns {Object} - Parsed JSON object
 */
function cleanAndParseJson(text) {
  try {
    // Remove any text before the first { and after the last }
    const startIdx = text.indexOf('{');
    const endIdx = text.lastIndexOf('}');

    if (startIdx === -1 || endIdx === -1 || endIdx <= startIdx) {
      throw new Error("Could not find valid JSON object in the text");
    }

    let jsonText = text.substring(startIdx, endIdx + 1);

    // Try to parse as is first
    try {
      return JSON.parse(jsonText);
    } catch (parseError) {
      console.log(`Initial JSON parsing error: ${parseError.message}`);

      // Try to fix common JSON issues
      if (parseError.message.includes("Unterminated string")) {
        // Replace newlines inside strings with \n
        jsonText = jsonText.replace(/"([^"]*)\n/g, '"$1\\n');

        try {
          return JSON.parse(jsonText);
        } catch (fixError) {
          console.log(`Fixed JSON parsing failed: ${fixError.message}`);
        }
      }

      // If all fixes fail, return fallback response
      console.log(`All JSON parsing attempts failed. Raw text: ${text}`);
      return {
        error: `Failed to parse JSON: ${parseError.message}`,
        fallback: true,
        message: "Using fallback response due to parsing error"
      };
    }
  } catch (error) {
    console.log(`Error in cleanAndParseJson: ${error.message}`);
    console.log(`Raw text: ${text}`);

    return {
      error: `Failed to parse JSON: ${error.message}`,
      fallback: true,
      message: "Using fallback response due to parsing error"
    };
  }
}

/**
 * Generate security definitions based on domain access patterns
 * @param {Object} openApiSpec - OpenAPI specification
 * @returns {Object} - Security definitions
 */
async function generateSecurityDefinitions(openApiSpec) {
  const bedrockClient = new BedrockRuntimeClient({ region: BEDROCK_REGION });

  // Extract only the security-related parts of the spec
  const securitySpec = {
    info: openApiSpec.info || {},
    components: {
      securitySchemes: openApiSpec.components?.securitySchemes || {}
    },
    security: openApiSpec.security || []
  };

  // Add a sample of paths to provide context
  securitySpec.paths = {};
  const paths = openApiSpec.paths || {};
  const pathKeys = Object.keys(paths).slice(0, 5); // Take up to 5 paths
  pathKeys.forEach(key => {
    securitySpec.paths[key] = paths[key];
  });

  const prompt = `Generate security definitions based on domain access patterns for this API.

CRITICAL: You MUST return ONLY a valid JSON object with this EXACT structure:

{
  "securityDefinitions": {
    "schemes": [
      {
        "name": "string",
        "type": "string",
        "description": "string",
        "scheme": "string (optional)",
        "bearerFormat": "string (optional)",
        "in": "string (optional for apiKey)",
        "flows": {
          "authorizationCode": {
            "authorizationUrl": "string",
            "tokenUrl": "string",
            "scopes": {
              "scope_name": "scope_description"
            }
          }
        }
      }
    ],
    "recommendations": [
      {
        "category": "string",
        "recommendation": "string",
        "priority": "high|medium|low"
      }
    ],
    "roles": [
      {
        "name": "string",
        "permissions": ["string"],
        "description": "string"
      }
    ]
  }
}

Rules:
- Return ONLY valid JSON
- No markdown, no explanations, no additional text
- All string values must be actual strings, not objects
- Arrays must contain objects with the exact structure shown
- Do not include any nested objects that aren't in this structure

API Specification:
${JSON.stringify(securitySpec, null, 2)}`;

  const command = new InvokeModelCommand({
    modelId: MODEL_ID,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.1,
      max_tokens: 3000
    })
  });

  const response = await bedrockClient.send(command);
  const responseBody = JSON.parse(new TextDecoder().decode(response.body));
  const rawCompletion = responseBody.content[0].text;

  return cleanAndParseJson(rawCompletion);
}

/**
 * Create API governance policies aligned with domain rules
 * @param {Object} openApiSpec - OpenAPI specification
 * @returns {Object} - Governance policies
 */
async function generateApiGovernance(openApiSpec) {
  const bedrockClient = new BedrockRuntimeClient({ region: BEDROCK_REGION });

  // Extract only the parts needed for governance policies
  const governanceSpec = {
    info: openApiSpec.info || {},
    paths: {}
  };

  // Add a sample of paths
  const paths = openApiSpec.paths || {};
  const pathKeys = Object.keys(paths).slice(0, 10); // Take up to 10 paths
  pathKeys.forEach(key => {
    governanceSpec.paths[key] = paths[key];
  });

  const prompt = `Create API governance policies aligned with domain rules for this API.

CRITICAL: You MUST return ONLY a valid JSON object with this EXACT structure:

{
  "policies": {
    "rateLimiting": {
      "default": "string",
      "authenticated": "string",
      "premium": "string",
      "burst": "string",
      "period": "string"
    },
    "caching": {
      "GET": "string",
      "POST": "string",
      "PUT": "string",
      "DELETE": "string",
      "ttl": "string"
    },
    "validation": {
      "inputValidation": "string",
      "outputValidation": "string",
      "schemaValidation": "string"
    },
    "recommendations": [
      {
        "category": "string",
        "recommendation": "string",
        "priority": "high|medium|low"
      }
    ]
  }
}

Rules:
- Return ONLY valid JSON
- No markdown, no explanations, no additional text
- All string values must be actual strings, not objects
- Arrays must contain objects with the exact structure shown
- Do not include any nested objects that aren't in this structure

API Specification:
${JSON.stringify(governanceSpec, null, 2)}`;

  const command = new InvokeModelCommand({
    modelId: MODEL_ID,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.1,
      max_tokens: 3000
    })
  });

  const response = await bedrockClient.send(command);
  const responseBody = JSON.parse(new TextDecoder().decode(response.body));
  const rawCompletion = responseBody.content[0].text;

  return cleanAndParseJson(rawCompletion);
}

/**
 * Add API documentation with domain-specific examples and descriptions
 * @param {Object} openApiSpec - OpenAPI specification
 * @returns {Object} - API documentation
 */
function generateApiDocumentation(openApiSpec) {
  // Extract the paths from the OpenAPI spec
  const paths = openApiSpec.paths || {};

  // If there are no paths, return a simple message
  if (Object.keys(paths).length === 0) {
    return {
      documentation: {
        message: "No paths found in the OpenAPI specification.",
        recommendation: "Add paths to your OpenAPI specification to generate documentation."
      }
    };
  }

  // Create a simplified documentation structure directly from the OpenAPI spec
  const documentation = {};

  Object.entries(paths).forEach(([path, pathItem]) => {
    documentation[path] = {};

    // Process each HTTP method (get, post, put, etc.)
    Object.entries(pathItem).forEach(([method, operation]) => {
      if (['get', 'post', 'put', 'delete', 'patch', 'options', 'head'].includes(method)) {
        // Extract basic information from the operation
        const docEntry = {
          summary: operation.summary || "No summary provided",
          description: operation.description || "No description provided",
          operationId: operation.operationId || `${method}_${path.replace(/\//g, '_')}`
        };

        // Extract parameters
        if (operation.parameters) {
          docEntry.parameters = operation.parameters.map(param => ({
            name: param.name || "unnamed",
            in: param.in || "query",
            description: param.description || "No description",
            required: param.required || false
          }));
        }

        // Extract responses
        if (operation.responses) {
          docEntry.responses = {};
          Object.entries(operation.responses).forEach(([statusCode, response]) => {
            docEntry.responses[statusCode] = {
              description: response.description || "No description"
            };
          });
        }

        // Add to documentation
        documentation[path][method] = docEntry;
      }
    });
  });

  return { documentation };
}

/**
 * Generate API versioning strategy based on domain evolution patterns
 * @param {Object} openApiSpec - OpenAPI specification
 * @returns {Object} - Versioning strategy
 */
async function generateVersioningStrategy(openApiSpec) {
  const bedrockClient = new BedrockRuntimeClient({ region: BEDROCK_REGION });

  // Extract only the parts needed for versioning strategy
  const versionSpec = {
    info: openApiSpec.info || {},
    tags: openApiSpec.tags || []
  };

  const prompt = `Generate an API versioning strategy based on domain evolution patterns.

CRITICAL: You MUST return ONLY a valid JSON object with this EXACT structure:

{
  "versioning": {
    "recommendedApproach": "header|uri|query",
    "approach": {
      "name": "string",
      "format": "string",
      "example": "string"
    },
    "lifecycleManagement": {
      "versionRetention": "string",
      "releaseSchedule": {
        "major": "string",
        "minor": "string",
        "patch": "string"
      },
      "deprecationPolicy": {
        "noticeTime": "string",
        "supportDuration": "string",
        "migrationSupport": "string"
      },
      "supportPolicy": {
        "currentVersion": "string",
        "previousVersion": "string",
        "legacyVersions": "string"
      },
      "stages": [
        {
          "name": "string",
          "duration": "string",
          "support": "string",
          "purpose": "string"
        }
      ]
    },
    "backwardCompatibility": {
      "strategy": "string",
      "breakingChanges": "string",
      "migrationPath": "string"
    },
    "communication": {
      "changelog": "string",
      "notifications": "string",
      "documentation": "string"
    }
  }
}

Rules:
- Return ONLY valid JSON
- No markdown, no explanations, no additional text
- All string values must be actual strings, not objects
- Arrays must contain objects with the exact structure shown
- Do not include any nested objects that aren't in this structure

API Specification:
${JSON.stringify(versionSpec, null, 2)}`;

  const command = new InvokeModelCommand({
    modelId: MODEL_ID,
    contentType: 'application/json',
    accept: 'application/json',
    body: JSON.stringify({
      anthropic_version: 'bedrock-2023-05-31',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.1,
      max_tokens: 3000
    })
  });

  const response = await bedrockClient.send(command);
  const responseBody = JSON.parse(new TextDecoder().decode(response.body));
  const rawCompletion = responseBody.content[0].text;

  return cleanAndParseJson(rawCompletion);
}

/**
 * Lambda handler function for API documentation generation
 * @param {Object} event - Lambda event object (with auth info added by middleware)
 * @param {Object} context - Lambda context
 * @returns {Object} - Response object
 */
async function docGeneratorHandler(event, context) {
  try {
    // Extract user context from authentication
    const userContext = event.auth?.user || null;
    const isAuthenticated = event.auth?.authenticated || false;
    
    console.log('Doc Generator - Authentication Status:', {
      authenticated: isAuthenticated,
      userId: userContext?.sub,
      username: userContext?.username
    });

    console.log("Lambda handler received event:", JSON.stringify(event).substring(0, 200) + "...");

    // Handle new payload structure with context
    let openApiSpec;
    let projectContext = {};
    
    if (event.openApiSpec && event.context) {
      // New format with context
      openApiSpec = event.openApiSpec;
      projectContext = event.context;
      console.log('Doc Generator - Project Context:', {
        projectName: projectContext.projectName
      });
    } else {
      // Legacy format - event is the OpenAPI spec directly
      openApiSpec = event;
      console.log('Doc Generator - Using legacy format (no project context)');
    }
    
    // NOTE: This Lambda no longer saves to S3 - it just returns the documentation
    // The backend Lambda will handle all S3 operations

    // Check if a specific task is requested
    const task = (typeof event === 'object' && event.task) ? event.task : null;

    try {
      if (task === "security") {
        // Generate only security definitions
        const result = await generateSecurityDefinitions(openApiSpec);

        // Check if we got a fallback response due to parsing error
        if (result.fallback) {
          return formatResponse(200, {
            message: "Security definitions generated with fallback",
            result: {
              securityDefinitions: {
                schemes: [
                  {
                    type: "oauth2",
                    name: "OAuth2",
                    description: "OAuth2 authentication with authorization code flow"
                  },
                  {
                    type: "http",
                    scheme: "bearer",
                    bearerFormat: "JWT",
                    name: "JWT",
                    description: "JWT token-based authentication"
                  },
                  {
                    type: "apiKey",
                    name: "API Key",
                    in: "header",
                    description: "API key for service-to-service authentication"
                  }
                ],
                recommendations: [
                  "Implement token-based authentication with short-lived JWTs",
                  "Use HTTPS for all API endpoints",
                  "Implement rate limiting per user and IP address",
                  "Apply strict CORS policies for browser-based clients",
                  "Implement input validation for all endpoints"
                ],
                error: result.error || "Unknown parsing error"
              }
            }
          }, isAuthenticated, userContext);
        }

        return formatResponse(200, {
          message: "Security definitions generated successfully",
          result
        }, isAuthenticated, userContext);
      } else if (task === "governance") {
        // Generate only governance policies
        const result = await generateApiGovernance(openApiSpec);

        // Check if we got a fallback response due to parsing error
        if (result.fallback) {
          return formatResponse(200, {
            message: "API governance policies generated with fallback",
            result: {
              policies: {
                rateLimiting: {
                  default: "100 requests per minute",
                  authenticated: "300 requests per minute",
                  premium: "1000 requests per minute"
                },
                caching: {
                  GET: "Cache for 5 minutes",
                  POST: "No caching",
                  PUT: "No caching",
                  DELETE: "No caching"
                },
                validation: "Apply schema validation to all requests",
                error: result.error || "Unknown parsing error"
              }
            }
          }, isAuthenticated, userContext);
        }

        return formatResponse(200, {
          message: "API governance policies generated successfully",
          result
        }, isAuthenticated, userContext);
      } else if (task === "documentation") {
        // Generate only API documentation
        const result = generateApiDocumentation(openApiSpec);

        // Check if we got a fallback response due to parsing error
        if (result.fallback) {
          return formatResponse(200, {
            message: "API documentation generated with fallback",
            result: {
              documentation: {
                endpoints: "Documentation could not be generated due to parsing error",
                error: result.error || "Unknown parsing error"
              }
            }
          }, isAuthenticated, userContext);
        }

        return formatResponse(200, {
          message: "API documentation generated successfully",
          result
        }, isAuthenticated, userContext);
      } else if (task === "versioning") {
        // Generate only versioning strategy
        const result = await generateVersioningStrategy(openApiSpec);

        // Check if we got a fallback response due to parsing error
        if (result.fallback) {
          return formatResponse(200, {
            message: "API versioning strategy generated with fallback",
            result: {
              versioning: {
                recommendedApproach: "header",
                approach: {
                  name: "Accept-Version header",
                  format: "Accept-Version: v{major}"
                },
                error: result.error || "Unknown parsing error"
              }
            }
          }, isAuthenticated, userContext);
        }

        return formatResponse(200, {
          message: "API versioning strategy generated successfully",
          result
        }, isAuthenticated, userContext);
      } else {
        // Generate all components sequentially
        let securityResult, governanceResult, documentationResult, versioningResult;

        try {
          securityResult = await generateSecurityDefinitions(openApiSpec);
        } catch (secError) {
          console.log(`Error generating security definitions: ${secError.message}`);
          securityResult = { fallback: true, error: secError.message };
        }

        try {
          governanceResult = await generateApiGovernance(openApiSpec);
        } catch (govError) {
          console.log(`Error generating governance policies: ${govError.message}`);
          governanceResult = { fallback: true, error: govError.message };
        }

        try {
          documentationResult = generateApiDocumentation(openApiSpec);
        } catch (docError) {
          console.log(`Error generating API documentation: ${docError.message}`);
          documentationResult = { fallback: true, error: docError.message };
        }

        try {
          versioningResult = await generateVersioningStrategy(openApiSpec);
        } catch (verError) {
          console.log(`Error generating versioning strategy: ${verError.message}`);
          versioningResult = { fallback: true, error: verError.message };
        }

        // Combine all results
        const combinedResult = {
          securityDefinitions: securityResult.securityDefinitions || {},
          policies: governanceResult.policies || {},
          documentation: documentationResult.documentation || {},
          versioning: versioningResult.versioning || {}
        };

        // Add error information if any component failed
        const hasErrors = [securityResult, governanceResult, documentationResult, versioningResult]
          .some(result => result.fallback);

        if (hasErrors) {
          combinedResult.errors = {
            security: securityResult.fallback ? securityResult.error : null,
            governance: governanceResult.fallback ? governanceResult.error : null,
            documentation: documentationResult.fallback ? documentationResult.error : null,
            versioning: versioningResult.fallback ? versioningResult.error : null
          };
        }

        return formatResponse(200, {
          message: `Comprehensive API documentation generated${hasErrors ? ' with some fallbacks' : ' successfully'}`,
          parsed_json: combinedResult,
          has_errors: hasErrors
        }, isAuthenticated, userContext);
      }
    } catch (taskError) {
      console.log(`Error processing task ${task}: ${taskError.message}`);

      // Return a more helpful error with fallback data
      return formatResponse(200, {
        message: `Error processing ${task || 'documentation'} task`,
        error: taskError.message,
        type: taskError.constructor.name,
        fallback: true,
        parsed_json: {
          securityDefinitions: {
            schemes: [
              { type: "oauth2", name: "OAuth2", description: "OAuth2 authentication" },
              { type: "http", scheme: "bearer", name: "JWT", description: "JWT authentication" }
            ],
            recommendations: ["Use HTTPS", "Implement rate limiting"]
          },
          policies: {},
          documentation: {},
          versioning: { recommendedApproach: "header" }
        }
      }, isAuthenticated, userContext);
    }
  } catch (error) {
    console.log(`Lambda handler error: ${error.message}`);

    // Extract user context for error response
    const userContext = event.auth?.user || null;
    const isAuthenticated = event.auth?.authenticated || false;

    // Return a 200 with error information to avoid breaking the client
    return formatResponse(200, {
      success: false,
      error: error.message,
      type: error.constructor.name,
      fallback: true,
      parsed_json: {
        securityDefinitions: {
          schemes: [
            { type: "oauth2", name: "OAuth2", description: "OAuth2 authentication" },
            { type: "http", scheme: "bearer", name: "JWT", description: "JWT authentication" }
          ]
        },
        policies: {},
        documentation: {},
        versioning: { recommendedApproach: "header" }
      }
    }, isAuthenticated, userContext);
  }
}

// Export the handler wrapped with authentication middleware
exports.handler = withAuthentication(docGeneratorHandler, authConfig);