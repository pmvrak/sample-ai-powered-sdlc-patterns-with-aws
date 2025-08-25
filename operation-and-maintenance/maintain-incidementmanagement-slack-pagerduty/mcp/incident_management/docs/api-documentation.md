# API Documentation

The Incident Management System provides a comprehensive REST API for external system integration. This API enables programmatic access to all incident management functionality with proper authentication, rate limiting, and comprehensive error handling.

## 📋 Table of Contents

- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)
- [Incident Management](#incident-management)
- [Webhook Management](#webhook-management)
- [Examples](#examples)
- [SDKs and Libraries](#sdks-and-libraries)

## 🔐 Authentication

The API uses JWT (JSON Web Token) authentication. All requests (except `/health` and `/auth/token`) require a valid Bearer token.

### Getting an Access Token

```http
POST /auth/token
Content-Type: application/x-www-form-urlencoded

username=your-username&password=your-password
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### Using the Token

Include the token in the Authorization header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Token Permissions

Tokens include role-based permissions:
- `incident:read` - View incidents
- `incident:write` - Create/update incidents
- `incident:delete` - Delete incidents (admin only)
- `automation:execute` - Execute automated remediation
- `webhook:read` - View webhook subscriptions
- `webhook:write` - Manage webhook subscriptions

## ⚡ Rate Limiting

The API implements rate limiting to ensure fair usage:

| Endpoint Category | Rate Limit | Window |
|------------------|------------|---------|
| Authentication | 5 requests | 1 minute |
| Read Operations | 100-200 requests | 1 minute |
| Write Operations | 50-100 requests | 1 minute |
| Delete Operations | 20 requests | 1 minute |
| Automation | 5 requests | 1 minute |

Rate limit headers are included in responses:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640995200
```

## ❌ Error Handling

The API returns consistent error responses:

```json
{
  "error": "validation_error",
  "message": "Invalid incident severity level",
  "details": {
    "field": "severity",
    "allowed_values": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
  }
}
```

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request data |
| 401 | Unauthorized | Invalid or missing token |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |

## 🚨 Incident Management

### List Incidents

```http
GET /incidents?page=1&page_size=20&status=open&severity=high&assigned_team=devops
```

**Parameters:**
- `page` (int, optional): Page number (default: 1)
- `page_size` (int, optional): Items per page (1-100, default: 20)
- `status` (string, optional): Filter by status
- `severity` (string, optional): Filter by severity
- `assigned_team` (string, optional): Filter by assigned team

**Response:**
```json
{
  "incidents": [
    {
      "id": "INC-20240123-ABC123",
      "title": "Database connection timeout",
      "description": "Multiple database connection timeouts detected",
      "severity": "HIGH",
      "status": "ASSIGNED",
      "source_query": "index=app_logs error=timeout",
      "affected_systems": ["database", "api"],
      "assigned_team": "devops",
      "assigned_user": "john.doe",
      "created_at": "2024-01-23T10:30:00Z",
      "updated_at": "2024-01-23T10:35:00Z",
      "resolved_at": null,
      "tags": ["database", "timeout", "production"]
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "has_next": false
}
```

### Get Specific Incident

```http
GET /incidents/{incident_id}
```

**Response:**
```json
{
  "id": "INC-20240123-ABC123",
  "title": "Database connection timeout",
  "description": "Multiple database connection timeouts detected",
  "severity": "HIGH",
  "status": "ASSIGNED",
  "source_query": "index=app_logs error=timeout",
  "affected_systems": ["database", "api"],
  "assigned_team": "devops",
  "assigned_user": "john.doe",
  "created_at": "2024-01-23T10:30:00Z",
  "updated_at": "2024-01-23T10:35:00Z",
  "resolved_at": null,
  "tags": ["database", "timeout", "production"]
}
```

### Create Incident

```http
POST /incidents
Content-Type: application/json

{
  "title": "API response time degradation",
  "description": "API response times have increased by 300% in the last 10 minutes",
  "severity": "HIGH",
  "source_query": "index=api_logs | stats avg(response_time)",
  "affected_systems": ["api", "load_balancer"],
  "tags": ["performance", "api", "production"]
}
```

**Response:**
```json
{
  "id": "INC-20240123-DEF456",
  "title": "API response time degradation",
  "description": "API response times have increased by 300% in the last 10 minutes",
  "severity": "HIGH",
  "status": "DETECTED",
  "source_query": "index=api_logs | stats avg(response_time)",
  "affected_systems": ["api", "load_balancer"],
  "assigned_team": null,
  "assigned_user": null,
  "created_at": "2024-01-23T11:00:00Z",
  "updated_at": "2024-01-23T11:00:00Z",
  "resolved_at": null,
  "tags": ["performance", "api", "production"]
}
```

### Update Incident

```http
PUT /incidents/{incident_id}
Content-Type: application/json

{
  "status": "IN_PROGRESS",
  "assigned_team": "devops",
  "assigned_user": "jane.smith",
  "tags": ["database", "timeout", "production", "investigating"]
}
```

### Delete Incident

```http
DELETE /incidents/{incident_id}
```

**Response:**
```json
{
  "message": "Incident deleted successfully"
}
```

### Analyze Incident

Trigger AI analysis for an incident:

```http
POST /incidents/{incident_id}/analyze
```

**Response:**
```json
{
  "message": "Analysis completed",
  "analysis": {
    "root_causes": [
      "Database connection pool exhaustion",
      "High query load during peak hours"
    ],
    "confidence_score": 0.85,
    "affected_components": ["database", "connection_pool", "api"],
    "suggested_actions": [
      "Increase connection pool size",
      "Implement query optimization",
      "Add database read replicas"
    ],
    "similar_incidents": ["INC-20240120-XYZ789"],
    "risk_assessment": "HIGH",
    "estimated_resolution_time": "PT2H"
  }
}
```

### Execute Remediation

Execute automated remediation for an incident:

```http
POST /incidents/{incident_id}/remediate
Content-Type: application/json

{
  "action": "restart_service",
  "parameters": {
    "service_name": "api-service",
    "environment": "production",
    "wait_for_health_check": true
  }
}
```

**Response:**
```json
{
  "message": "Remediation executed",
  "result": {
    "success": true,
    "action": "restart_service",
    "execution_time": "PT45S",
    "details": {
      "service_name": "api-service",
      "previous_status": "unhealthy",
      "current_status": "healthy",
      "health_check_passed": true
    },
    "logs": [
      "2024-01-23T11:05:00Z: Initiating service restart",
      "2024-01-23T11:05:30Z: Service stopped gracefully",
      "2024-01-23T11:05:45Z: Service started successfully",
      "2024-01-23T11:05:50Z: Health check passed"
    ]
  }
}
```

## 🔗 Webhook Management

### Create Webhook Subscription

```http
POST /webhooks
Content-Type: application/json

{
  "name": "ITSM Integration",
  "url": "https://your-system.com/webhooks/incidents",
  "events": ["INCIDENT_CREATED", "INCIDENT_RESOLVED"],
  "headers": {
    "X-API-Key": "your-api-key",
    "Content-Type": "application/json"
  },
  "timeout_seconds": 30,
  "max_retries": 3
}
```

**Response:**
```json
{
  "id": "webhook-123",
  "name": "ITSM Integration",
  "url": "https://your-system.com/webhooks/incidents",
  "events": ["INCIDENT_CREATED", "INCIDENT_RESOLVED"],
  "is_active": true,
  "created_at": "2024-01-23T12:00:00Z",
  "updated_at": "2024-01-23T12:00:00Z",
  "headers": {
    "X-API-Key": "your-api-key",
    "Content-Type": "application/json"
  },
  "timeout_seconds": 30,
  "max_retries": 3,
  "secret": "webhook-secret-abc123"
}
```

### List Webhook Subscriptions

```http
GET /webhooks
```

### Get Webhook Subscription

```http
GET /webhooks/{subscription_id}
```

### Update Webhook Subscription

```http
PUT /webhooks/{subscription_id}
Content-Type: application/json

{
  "name": "Updated ITSM Integration",
  "events": ["INCIDENT_CREATED", "INCIDENT_UPDATED", "INCIDENT_RESOLVED"],
  "timeout_seconds": 45
}
```

### Delete Webhook Subscription

```http
DELETE /webhooks/{subscription_id}
```

### List Webhook Deliveries

```http
GET /webhooks/{subscription_id}/deliveries?status=failed&limit=50
```

**Response:**
```json
[
  {
    "id": "delivery-456",
    "subscription_id": "webhook-123",
    "event_type": "INCIDENT_CREATED",
    "status": "DELIVERED",
    "attempts": 1,
    "last_attempt_at": "2024-01-23T12:05:00Z",
    "next_retry_at": null,
    "response_status": 200,
    "error_message": null,
    "created_at": "2024-01-23T12:05:00Z"
  }
]
```

### Get Webhook Statistics

```http
GET /webhooks/{subscription_id}/stats
```

**Response:**
```json
{
  "subscription_id": "webhook-123",
  "total_deliveries": 150,
  "successful_deliveries": 145,
  "failed_deliveries": 5,
  "success_rate": 0.967,
  "average_response_time": 250,
  "last_delivery_at": "2024-01-23T12:05:00Z",
  "events_by_type": {
    "INCIDENT_CREATED": 75,
    "INCIDENT_UPDATED": 50,
    "INCIDENT_RESOLVED": 25
  }
}
```

## 💡 Examples

### Example 1: Monitor High-Severity Incidents

```python
import requests
import time

# Authenticate
auth_response = requests.post('https://api.incident-mgmt.com/auth/token', 
                            data={'username': 'monitor', 'password': 'secret'})
token = auth_response.json()['access_token']

headers = {'Authorization': f'Bearer {token}'}

# Poll for high-severity incidents
while True:
    response = requests.get(
        'https://api.incident-mgmt.com/incidents',
        headers=headers,
        params={'severity': 'HIGH', 'status': 'open'}
    )
    
    incidents = response.json()['incidents']
    
    for incident in incidents:
        print(f"High-severity incident: {incident['id']} - {incident['title']}")
        
        # Trigger analysis if not already done
        if not incident.get('ai_analysis'):
            requests.post(f'https://api.incident-mgmt.com/incidents/{incident["id"]}/analyze',
                         headers=headers)
    
    time.sleep(60)  # Check every minute
```

### Example 2: Automated Incident Creation from Monitoring

```python
import requests
from datetime import datetime

def create_incident_from_alert(alert_data):
    # Authenticate
    auth_response = requests.post('https://api.incident-mgmt.com/auth/token',
                                data={'username': 'monitoring', 'password': 'secret'})
    token = auth_response.json()['access_token']
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # Map alert severity to incident severity
    severity_mapping = {
        'critical': 'CRITICAL',
        'warning': 'HIGH',
        'info': 'MEDIUM'
    }
    
    incident_data = {
        'title': f"Alert: {alert_data['alert_name']}",
        'description': f"Alert triggered: {alert_data['description']}\n"
                      f"Threshold: {alert_data['threshold']}\n"
                      f"Current value: {alert_data['current_value']}",
        'severity': severity_mapping.get(alert_data['severity'], 'MEDIUM'),
        'affected_systems': alert_data['affected_systems'],
        'tags': ['automated', 'monitoring', alert_data['source']]
    }
    
    response = requests.post('https://api.incident-mgmt.com/incidents',
                           headers=headers, json=incident_data)
    
    if response.status_code == 201:
        incident = response.json()
        print(f"Created incident: {incident['id']}")
        return incident['id']
    else:
        print(f"Failed to create incident: {response.text}")
        return None

# Example usage
alert = {
    'alert_name': 'High CPU Usage',
    'description': 'CPU usage exceeded 90% for 5 minutes',
    'severity': 'critical',
    'threshold': '90%',
    'current_value': '95%',
    'affected_systems': ['web-server-01', 'web-server-02'],
    'source': 'prometheus'
}

incident_id = create_incident_from_alert(alert)
```

### Example 3: Webhook Integration

```python
from flask import Flask, request, jsonify
import hmac
import hashlib

app = Flask(__name__)
WEBHOOK_SECRET = 'webhook-secret-abc123'

@app.route('/webhooks/incidents', methods=['POST'])
def handle_incident_webhook():
    # Verify webhook signature
    signature = request.headers.get('X-Signature-256')
    if not verify_signature(request.data, signature):
        return jsonify({'error': 'Invalid signature'}), 401
    
    event_data = request.json
    event_type = event_data['event_type']
    incident = event_data['data']
    
    if event_type == 'INCIDENT_CREATED':
        # Create ticket in ITSM system
        create_itsm_ticket(incident)
    elif event_type == 'INCIDENT_RESOLVED':
        # Close ticket in ITSM system
        close_itsm_ticket(incident)
    elif event_type == 'INCIDENT_ASSIGNED':
        # Update ticket assignment
        update_itsm_assignment(incident)
    
    return jsonify({'status': 'processed'})

def verify_signature(payload, signature):
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f'sha256={expected}', signature)

def create_itsm_ticket(incident):
    # Implementation for your ITSM system
    print(f"Creating ITSM ticket for incident {incident['incident_id']}")

def close_itsm_ticket(incident):
    # Implementation for your ITSM system
    print(f"Closing ITSM ticket for incident {incident['incident_id']}")

def update_itsm_assignment(incident):
    # Implementation for your ITSM system
    print(f"Updating ITSM assignment for incident {incident['incident_id']}")

if __name__ == '__main__':
    app.run(port=5000)
```

## 📚 SDKs and Libraries

### Python SDK

```python
from incident_management_sdk import IncidentClient

client = IncidentClient(
    base_url='https://api.incident-mgmt.com',
    username='your-username',
    password='your-password'
)

# List incidents
incidents = client.incidents.list(status='open', severity='high')

# Create incident
incident = client.incidents.create(
    title='Database connection issues',
    description='Connection pool exhausted',
    severity='HIGH',
    affected_systems=['database', 'api']
)

# Update incident
client.incidents.update(incident.id, status='IN_PROGRESS')

# Execute remediation
result = client.incidents.remediate(
    incident.id,
    action='restart_service',
    parameters={'service_name': 'api-service'}
)
```

### JavaScript SDK

```javascript
const { IncidentClient } = require('@company/incident-management-sdk');

const client = new IncidentClient({
  baseUrl: 'https://api.incident-mgmt.com',
  username: 'your-username',
  password: 'your-password'
});

// List incidents
const incidents = await client.incidents.list({
  status: 'open',
  severity: 'high'
});

// Create incident
const incident = await client.incidents.create({
  title: 'Database connection issues',
  description: 'Connection pool exhausted',
  severity: 'HIGH',
  affectedSystems: ['database', 'api']
});

// Set up webhook
const webhook = await client.webhooks.create({
  name: 'My Integration',
  url: 'https://my-system.com/webhooks',
  events: ['INCIDENT_CREATED', 'INCIDENT_RESOLVED']
});
```

## 🔍 OpenAPI Specification

The complete OpenAPI specification is available at:
- **Interactive Docs**: `https://api.incident-mgmt.com/docs`
- **ReDoc**: `https://api.incident-mgmt.com/redoc`
- **OpenAPI JSON**: `https://api.incident-mgmt.com/openapi.json`

## 📞 Support

- **API Issues**: Check the [Troubleshooting Guide](troubleshooting-guide.md)
- **Rate Limiting**: Contact your administrator to adjust limits
- **Authentication**: Verify your credentials and permissions
- **Integration Help**: See the [Integration Guide](integration-guide.md)

---

*For more examples and detailed integration patterns, see the [Integration Guide](integration-guide.md).*