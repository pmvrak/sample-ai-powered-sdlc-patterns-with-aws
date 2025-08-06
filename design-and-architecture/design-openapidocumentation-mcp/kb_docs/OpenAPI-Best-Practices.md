# OpenAPI 3.1 Best Practices and Guidelines

## OpenAPI 3.1 Specification Structure

### Required Top-Level Fields
```yaml
openapi: 3.1.0
info:
  title: API Title
  version: 1.0.0
  description: API description
paths: {}
```

### Complete OpenAPI Structure
```yaml
openapi: 3.1.0
info:
  title: Example API
  version: 1.0.0
  description: Comprehensive API example
  contact:
    name: API Support
    email: support@example.com
  license:
    name: MIT
    url: https://opensource.org/licenses/MIT

servers:
  - url: https://api.example.com/v1
    description: Production server
  - url: https://staging-api.example.com/v1
    description: Staging server

paths:
  /users:
    get:
      summary: List users
      description: Retrieve a paginated list of users
      tags:
        - users
      parameters:
        - name: page
          in: query
          schema:
            type: integer
            minimum: 1
            default: 1
        - name: limit
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                type: object
                properties:
                  users:
                    type: array
                    items:
                      $ref: '#/components/schemas/User'
                  pagination:
                    $ref: '#/components/schemas/Pagination'
    post:
      summary: Create user
      description: Create a new user account
      tags:
        - users
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateUserRequest'
      responses:
        '201':
          description: User created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/User'
        '400':
          $ref: '#/components/responses/BadRequest'

components:
  schemas:
    User:
      type: object
      required:
        - id
        - email
        - name
      properties:
        id:
          type: string
          format: uuid
          description: Unique user identifier
        email:
          type: string
          format: email
          description: User email address
        name:
          type: string
          minLength: 1
          maxLength: 100
          description: User full name
        createdAt:
          type: string
          format: date-time
          description: Account creation timestamp
    
    CreateUserRequest:
      type: object
      required:
        - email
        - name
        - password
      properties:
        email:
          type: string
          format: email
        name:
          type: string
          minLength: 1
          maxLength: 100
        password:
          type: string
          minLength: 8
          description: Password must be at least 8 characters
    
    Pagination:
      type: object
      required:
        - page
        - limit
        - total
        - totalPages
      properties:
        page:
          type: integer
          minimum: 1
        limit:
          type: integer
          minimum: 1
        total:
          type: integer
          minimum: 0
        totalPages:
          type: integer
          minimum: 0
    
    Error:
      type: object
      required:
        - code
        - message
      properties:
        code:
          type: string
          description: Error code
        message:
          type: string
          description: Human-readable error message
        details:
          type: object
          description: Additional error details

  responses:
    BadRequest:
      description: Invalid request parameters
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    
    Unauthorized:
      description: Authentication required
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'
    
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/Error'

  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: JWT token authentication
    
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      description: API key authentication

security:
  - BearerAuth: []

tags:
  - name: users
    description: User management operations
```

## RESTful API Design Principles

### HTTP Methods Usage
- **GET**: Retrieve resources (idempotent, safe)
- **POST**: Create new resources or non-idempotent operations
- **PUT**: Update entire resource (idempotent)
- **PATCH**: Partial resource updates
- **DELETE**: Remove resources (idempotent)

### URL Design Patterns
```
# Good patterns
GET    /users              # List users
GET    /users/{id}         # Get specific user
POST   /users              # Create user
PUT    /users/{id}         # Update user
DELETE /users/{id}         # Delete user

# Nested resources
GET    /users/{id}/orders  # Get user's orders
POST   /users/{id}/orders  # Create order for user

# Avoid verbs in URLs
GET    /users/{id}         # Good
GET    /getUser/{id}       # Bad
```

### HTTP Status Codes
- **200 OK**: Successful GET, PUT, PATCH
- **201 Created**: Successful POST
- **204 No Content**: Successful DELETE
- **400 Bad Request**: Invalid request data
- **401 Unauthorized**: Authentication required
- **403 Forbidden**: Access denied
- **404 Not Found**: Resource not found
- **409 Conflict**: Resource conflict
- **422 Unprocessable Entity**: Validation errors
- **500 Internal Server Error**: Server error

## Schema Design Best Practices

### Data Types and Formats
```yaml
# String types with formats
email:
  type: string
  format: email
  
date:
  type: string
  format: date
  
datetime:
  type: string
  format: date-time
  
uuid:
  type: string
  format: uuid

# Numeric types with constraints
age:
  type: integer
  minimum: 0
  maximum: 150
  
price:
  type: number
  format: float
  minimum: 0
  multipleOf: 0.01

# String validation
username:
  type: string
  pattern: '^[a-zA-Z0-9_]{3,20}$'
  minLength: 3
  maxLength: 20
```

### Enum Definitions
```yaml
status:
  type: string
  enum:
    - active
    - inactive
    - pending
  description: Account status
```

### Array Definitions
```yaml
tags:
  type: array
  items:
    type: string
  minItems: 1
  maxItems: 10
  uniqueItems: true
```

### Object Composition
```yaml
# Use allOf for inheritance
ExtendedUser:
  allOf:
    - $ref: '#/components/schemas/User'
    - type: object
      properties:
        preferences:
          $ref: '#/components/schemas/UserPreferences'

# Use oneOf for polymorphism
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CreditCard'
    - $ref: '#/components/schemas/BankAccount'
  discriminator:
    propertyName: type
```

## Security Schemes

### JWT Bearer Authentication
```yaml
securitySchemes:
  BearerAuth:
    type: http
    scheme: bearer
    bearerFormat: JWT
    description: JWT token for authenticated requests
```

### OAuth2 Flows
```yaml
securitySchemes:
  OAuth2:
    type: oauth2
    flows:
      authorizationCode:
        authorizationUrl: https://auth.example.com/oauth/authorize
        tokenUrl: https://auth.example.com/oauth/token
        scopes:
          read: Read access
          write: Write access
          admin: Administrative access
```

### API Key Authentication
```yaml
securitySchemes:
  ApiKeyAuth:
    type: apiKey
    in: header
    name: X-API-Key
    description: API key for service authentication
```

## Error Handling Patterns

### Standard Error Response
```yaml
Error:
  type: object
  required:
    - code
    - message
  properties:
    code:
      type: string
      description: Machine-readable error code
    message:
      type: string
      description: Human-readable error message
    details:
      type: object
      description: Additional error context
    timestamp:
      type: string
      format: date-time
    path:
      type: string
      description: Request path that caused the error
```

### Validation Error Response
```yaml
ValidationError:
  type: object
  required:
    - code
    - message
    - errors
  properties:
    code:
      type: string
      example: "VALIDATION_ERROR"
    message:
      type: string
      example: "Request validation failed"
    errors:
      type: array
      items:
        type: object
        properties:
          field:
            type: string
            description: Field that failed validation
          code:
            type: string
            description: Validation error code
          message:
            type: string
            description: Validation error message
```

## Pagination Patterns

### Offset-based Pagination
```yaml
parameters:
  - name: page
    in: query
    schema:
      type: integer
      minimum: 1
      default: 1
  - name: limit
    in: query
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20

# Response with pagination metadata
PaginatedResponse:
  type: object
  properties:
    data:
      type: array
      items:
        $ref: '#/components/schemas/Resource'
    pagination:
      type: object
      properties:
        page:
          type: integer
        limit:
          type: integer
        total:
          type: integer
        totalPages:
          type: integer
        hasNext:
          type: boolean
        hasPrev:
          type: boolean
```

### Cursor-based Pagination
```yaml
parameters:
  - name: cursor
    in: query
    schema:
      type: string
      description: Pagination cursor
  - name: limit
    in: query
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20

# Response with cursor pagination
CursorPaginatedResponse:
  type: object
  properties:
    data:
      type: array
      items:
        $ref: '#/components/schemas/Resource'
    pagination:
      type: object
      properties:
        nextCursor:
          type: string
          nullable: true
        prevCursor:
          type: string
          nullable: true
        hasNext:
          type: boolean
        hasPrev:
          type: boolean
```

## Documentation Best Practices

### Operation Descriptions
- Use clear, concise summaries
- Provide detailed descriptions for complex operations
- Include usage examples and common scenarios
- Document side effects and business rules

### Parameter Documentation
- Describe the purpose of each parameter
- Include validation rules and constraints
- Provide example values
- Specify required vs optional parameters

### Response Documentation
- Document all possible response codes
- Include example response bodies
- Describe error conditions
- Document response headers when relevant

### Schema Documentation
- Add descriptions to all properties
- Include business rules and constraints
- Provide realistic example values
- Document relationships between schemas

This comprehensive guide ensures high-quality, standards-compliant OpenAPI 3.1 specifications that are well-documented, secure, and follow REST API best practices.