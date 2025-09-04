# OAuth Flow - Visual Diagram

## 🔄 The Complete OAuth Dance

```
┌─────────────┐                 ┌─────────────┐                 ┌─────────────┐
│             │                 │             │                 │             │
│ MCP Client  │                 │OAuth Server │                 │ MCP Server  │
│ (Amazon Q)  │                 │(Security)   │                 │(Jenkins)    │
│             │                 │             │                 │             │
└─────────────┘                 └─────────────┘                 └─────────────┘
       │                               │                               │
       │ 1. Register Client            │                               │
       │──────────────────────────────▶│                               │
       │                               │                               │
       │ 2. Client Credentials         │                               │
       │◀──────────────────────────────│                               │
       │                               │                               │
       │ 3. Authorization Request      │                               │
       │──────────────────────────────▶│                               │
       │                               │                               │
       │ 4. Authorization Code         │                               │
       │◀──────────────────────────────│                               │
       │                               │                               │
       │ 5. Token Exchange             │                               │
       │──────────────────────────────▶│                               │
       │                               │                               │
       │ 6. Access Token               │                               │
       │◀──────────────────────────────│                               │
       │                               │                               │
       │ 7. MCP Request + Token        │                               │
       │───────────────────────────────────────────────────────────────▶│
       │                               │                               │
       │                               │ 8. Validate Token            │
       │                               │◀──────────────────────────────│
       │                               │                               │
       │                               │ 9. Token Valid                │
       │                               │──────────────────────────────▶│
       │                               │                               │
       │ 10. Jenkins Data Response     │                               │
       │◀───────────────────────────────────────────────────────────────│
```

## 🔐 Security Features

### 1. **PKCE (Proof Key for Code Exchange)**
- Prevents authorization code interception attacks
- Uses cryptographically random code verifier
- SHA256 challenge method for enhanced security

### 2. **Token Introspection (RFC 7662)**
- Real-time token validation
- Immediate revocation support
- Detailed token metadata

### 3. **Dynamic Client Registration (RFC 7591)**
- Automatic client registration
- No manual client configuration needed
- Secure client credential generation

### 4. **OAuth 2.0 Discovery (RFC 8414)**
- Automatic endpoint discovery
- Standardized metadata format
- Reduced configuration complexity

## 🚀 Implementation Details

### OAuth Server Endpoints

- **Discovery**: `/.well-known/oauth-authorization-server`
- **Registration**: `/register`
- **Authorization**: `/authorize`
- **Token**: `/token`
- **Introspection**: `/introspect`

### Token Lifecycle

1. **Generation**: 1-hour expiry with secure random generation
2. **Storage**: DynamoDB with TTL for automatic cleanup
3. **Validation**: Real-time introspection on each request
4. **Refresh**: Manual refresh via `get_fresh_token.sh`

### Security Considerations

- ✅ **HTTPS Only**: All communication encrypted
- ✅ **Short-lived Tokens**: 1-hour expiry reduces exposure
- ✅ **Secure Storage**: DynamoDB with encryption at rest
- ✅ **Rate Limiting**: API Gateway throttling protection
- ✅ **CORS Protection**: Configured for secure origins

## 🔧 Token Management

### Getting Fresh Tokens

```bash
# Automatic token refresh
./get_fresh_token.sh

# Manual token check
python3 -c "from token_config import test_token_flow; import asyncio; asyncio.run(test_token_flow())"
```

### Token Format

```json
{
  "access_token": "test-token-1234567890",
  "token_type": "Bearer",
  "expires_in": 3600,
  "expires_at": 1234567890.123,
  "scope": "mcp:read mcp:write",
  "client_id": "auto-generated-client-id"
}
```
