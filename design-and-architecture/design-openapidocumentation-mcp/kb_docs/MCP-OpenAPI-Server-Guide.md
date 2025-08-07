# MCP OpenAPI Documentation Server Guide

## Overview

This MCP server provides AI-powered OpenAPI documentation generation capabilities through three main tools:

1. **domain_analysis** - Analyze business domains and generate domain models
2. **generate_documentation** - Generate comprehensive API documentation  
3. **generate_openapi_spec** - Generate OpenAPI 3.1 specifications using Bedrock agents

## Tool Capabilities

### Domain Analysis Tool
- **Purpose**: Analyze business requirements and extract domain entities
- **Input**: Business descriptions, domain contexts, analysis depth (basic/detailed/comprehensive)
- **Output**: Structured domain analysis with entities, relationships, and business insights
- **Use Cases**: 
  - Extract entities from business requirements
  - Identify relationships between domain objects
  - Generate business rules and constraints

### Documentation Generation Tool  
- **Purpose**: Generate comprehensive API documentation from domain models
- **Input**: Domain models, API types (REST/GraphQL/gRPC), security requirements
- **Output**: OpenAPI specifications with security definitions, governance policies, and examples
- **Features**:
  - Security scheme generation (OAuth2, JWT, API Keys)
  - Rate limiting and caching policies
  - Validation rules and constraints
  - Request/response examples

### OpenAPI Specification Generator
- **Purpose**: Generate standards-compliant OpenAPI 3.1 specifications
- **Input**: API information, domain analysis results, business context
- **Output**: Complete OpenAPI 3.1 specifications with proper structure
- **Features**:
  - RESTful API design patterns
  - Component reusability with $ref
  - Security definitions
  - Server configurations
  - Comprehensive schemas and examples

## Best Practices for OpenAPI Generation

### API Design Principles
1. **RESTful Design**: Use appropriate HTTP verbs (GET, POST, PUT, DELETE)
2. **Resource Naming**: Use nouns for resources, not verbs
3. **Consistent Patterns**: Maintain consistent URL structures and response formats
4. **Proper Status Codes**: Use appropriate HTTP status codes for different scenarios

### OpenAPI Structure Guidelines
1. **Info Object**: Always include title, version, and description
2. **Servers**: Define production, staging, and development servers
3. **Paths**: Organize endpoints logically with proper operations
4. **Components**: Use reusable schemas, parameters, and responses
5. **Security**: Define authentication schemes and apply them consistently

### Schema Design
1. **Data Types**: Use appropriate OpenAPI data types (string, integer, boolean, array, object)
2. **Validation**: Include format, pattern, minimum/maximum constraints
3. **Examples**: Provide realistic example values
4. **Descriptions**: Add clear descriptions for all fields and operations

### Security Considerations
1. **Authentication**: Implement appropriate auth schemes (OAuth2, JWT, API Key)
2. **Authorization**: Define scopes and permissions clearly
3. **Rate Limiting**: Include rate limiting policies
4. **Input Validation**: Specify validation rules for all inputs

## Common API Patterns

### CRUD Operations
- **Create**: POST /resources
- **Read**: GET /resources/{id} and GET /resources
- **Update**: PUT /resources/{id} or PATCH /resources/{id}  
- **Delete**: DELETE /resources/{id}

### Pagination
- Use query parameters: `?page=1&limit=20`
- Include pagination metadata in responses
- Provide links to next/previous pages

### Error Handling
- Use consistent error response format
- Include error codes and descriptive messages
- Provide troubleshooting guidance

### Versioning
- Use URL versioning: `/v1/resources`
- Include version in headers: `Accept-Version: v1`
- Maintain backward compatibility

## Integration Examples

### Domain Analysis Example
```json
{
  "description": "E-commerce platform with products, customers, orders, and payments",
  "analysis_depth": "detailed"
}
```

### Documentation Generation Example  
```json
{
  "domain_model": "Entities: Product, Customer, Order, Payment. Relationships: Customer places Order, Order contains Products, Order has Payment",
  "api_type": "REST",
  "include_security": true,
  "include_examples": true
}
```

### OpenAPI Generation Example
```json
{
  "info": {
    "title": "E-commerce API",
    "version": "1.0.0",
    "description": "API for managing e-commerce operations"
  },
  "apiStyle": "REST",
  "authenticationScheme": "oauth2",
  "businessContext": "Online retail platform with product catalog and order management"
}
```

## Quality Guidelines

### OpenAPI Specification Quality
1. **Completeness**: Include all necessary endpoints and operations
2. **Accuracy**: Ensure schemas match actual data structures  
3. **Consistency**: Use consistent naming and patterns throughout
4. **Documentation**: Provide clear descriptions and examples
5. **Validation**: Ensure specification validates against OpenAPI 3.1 schema

### API Documentation Quality
1. **Clarity**: Use clear, concise language
2. **Examples**: Provide realistic request/response examples
3. **Error Cases**: Document error scenarios and responses
4. **Authentication**: Clearly explain authentication requirements
5. **Rate Limits**: Document any rate limiting policies

This guide helps ensure high-quality OpenAPI specifications and comprehensive API documentation generation through the MCP server tools.