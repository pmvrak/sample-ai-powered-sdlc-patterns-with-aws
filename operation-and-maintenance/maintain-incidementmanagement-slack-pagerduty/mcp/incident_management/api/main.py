"""
FastAPI-based REST API for Incident Management System (Slack-Only Authentication)

This module provides a REST API secured for Slack integration only using
Slack's signature verification. Only requests from Slack are allowed.
"""

from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import hmac
import hashlib
import time
from pydantic import BaseModel, Field, validator
import logging
from contextlib import asynccontextmanager

from ..models.incident import Incident, IncidentSeverity, IncidentStatus
from ..models.analysis import AnalysisResult
from ..storage.memory_store import MemoryIncidentStore
from ..core.ai_analyzer import AIAnalyzer
from ..core.incident_router import IncidentRouter
from ..core.automation_engine import AutomationEngine
from .webhooks import webhook_manager, WebhookSubscription, WebhookEvent, WebhookStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)

# Slack authentication
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")

class APIError(BaseModel):
    """Standard API error response"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None

class IncidentCreateRequest(BaseModel):
    """Request model for creating incidents"""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1, max_length=2000)
    severity: IncidentSeverity
    source_query: Optional[str] = None
    affected_systems: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    
    @validator('affected_systems')
    def validate_affected_systems(cls, v):
        if len(v) > 50:
            raise ValueError('Too many affected systems (max 50)')
        return v

class IncidentUpdateRequest(BaseModel):
    """Request model for updating incidents"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    severity: Optional[IncidentSeverity] = None
    status: Optional[IncidentStatus] = None
    assigned_team: Optional[str] = None
    assigned_user: Optional[str] = None
    tags: Optional[List[str]] = None

class IncidentResponse(BaseModel):
    """Response model for incident data"""
    id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    source_query: Optional[str]
    affected_systems: List[str]
    assigned_team: Optional[str]
    assigned_user: Optional[str]
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime]
    tags: List[str]

class IncidentListResponse(BaseModel):
    """Response model for incident lists"""
    incidents: List[IncidentResponse]
    total: int
    page: int
    page_size: int
    has_next: bool

def verify_slack_signature(request: Request) -> bool:
    """
    Verify that the request came from Slack using signature verification
    https://api.slack.com/authentication/verifying-requests-from-slack
    """
    if not SLACK_SIGNING_SECRET:
        logger.warning("SLACK_SIGNING_SECRET not configured - allowing all requests")
        return True
    
    # Get headers
    timestamp = request.headers.get('X-Slack-Request-Timestamp')
    signature = request.headers.get('X-Slack-Signature')
    
    if not timestamp or not signature:
        logger.warning("Missing Slack signature headers")
        return False
    
    # Check timestamp (prevent replay attacks)
    if abs(time.time() - int(timestamp)) > 60 * 5:  # 5 minutes
        logger.warning("Slack request timestamp too old")
        return False
    
    # Get request body
    body = request.body if hasattr(request, 'body') else b''
    
    # Create signature
    sig_basestring = f'v0:{timestamp}:{body.decode()}'
    my_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Compare signatures
    if hmac.compare_digest(my_signature, signature):
        return True
    else:
        logger.warning("Slack signature verification failed")
        return False

async def verify_slack_request(request: Request):
    """Dependency to verify Slack requests"""
    # Store body for signature verification
    body = await request.body()
    request._body = body
    
    if not verify_slack_signature(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack signature"
        )
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Incident Management API (Slack-Only)")
    
    # Initialize components
    app.state.incident_store = IncidentStore()
    app.state.ai_analyzer = AIAnalyzer()
    app.state.incident_router = IncidentRouter()
    app.state.automation_engine = AutomationEngine()
    
    # Start webhook manager
    await webhook_manager.start()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Incident Management API")
    await webhook_manager.stop()

# Create FastAPI app
app = FastAPI(
    title="Incident Management API (Slack-Only)",
    description="REST API for Slack-based incident management system with signature verification",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://slack.com",
        "https://*.slack.com",
        "http://localhost:3000",  # For development
        "http://localhost:8000",  # For development
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]
)

# Rate limiting error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# API Routes

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint (public)"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

@app.get("/incidents", response_model=IncidentListResponse, tags=["Incidents"])
@limiter.limit("100/minute")
async def list_incidents(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    status: Optional[IncidentStatus] = None,
    severity: Optional[IncidentSeverity] = None,
    assigned_team: Optional[str] = None,
    _: bool = Depends(verify_slack_request)
):
    """List incidents with filtering and pagination (Slack-only)"""
    try:
        # Validate pagination parameters
        if page < 1:
            raise HTTPException(status_code=400, detail="Page must be >= 1")
        if page_size < 1 or page_size > 100:
            raise HTTPException(status_code=400, detail="Page size must be between 1 and 100")
        
        # Build filters
        filters = {}
        if status:
            filters["status"] = status
        if severity:
            filters["severity"] = severity
        if assigned_team:
            filters["assigned_team"] = assigned_team
        
        # Get incidents from store
        incidents, total = await app.state.incident_store.list_incidents(
            filters=filters,
            page=page,
            page_size=page_size
        )
        
        # Convert to response format
        incident_responses = [
            IncidentResponse(
                id=incident.id,
                title=incident.title,
                description=incident.description,
                severity=incident.severity,
                status=incident.status,
                source_query=incident.source_query,
                affected_systems=incident.affected_systems,
                assigned_team=incident.assigned_team,
                assigned_user=incident.assigned_user,
                created_at=incident.created_at,
                updated_at=incident.updated_at,
                resolved_at=incident.resolved_at,
                tags=incident.tags
            )
            for incident in incidents
        ]
        
        return IncidentListResponse(
            incidents=incident_responses,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total
        )
        
    except Exception as e:
        logger.error(f"Error listing incidents: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/incidents/{incident_id}", response_model=IncidentResponse, tags=["Incidents"])
@limiter.limit("200/minute")
async def get_incident(
    request: Request, 
    incident_id: str,
    _: bool = Depends(verify_slack_request)
):
    """Get specific incident by ID (Slack-only)"""
    try:
        incident = await app.state.incident_store.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        return IncidentResponse(
            id=incident.id,
            title=incident.title,
            description=incident.description,
            severity=incident.severity,
            status=incident.status,
            source_query=incident.source_query,
            affected_systems=incident.affected_systems,
            assigned_team=incident.assigned_team,
            assigned_user=incident.assigned_user,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            resolved_at=incident.resolved_at,
            tags=incident.tags
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting incident {incident_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/incidents", response_model=IncidentResponse, tags=["Incidents"])
@limiter.limit("50/minute")
async def create_incident(
    request: Request, 
    incident_data: IncidentCreateRequest,
    _: bool = Depends(verify_slack_request)
):
    """Create new incident (Slack-only)"""
    try:
        # Create incident object
        incident = Incident(
            title=incident_data.title,
            description=incident_data.description,
            severity=incident_data.severity,
            source_query=incident_data.source_query,
            affected_systems=incident_data.affected_systems,
            tags=incident_data.tags,
            created_by="slack-bot"
        )
        
        # Store incident
        created_incident = await app.state.incident_store.create_incident(incident)
        
        # Route incident to appropriate team
        await app.state.incident_router.route_incident(created_incident)
        
        # Send webhook notification
        await webhook_manager.send_webhook(
            event=WebhookEvent.INCIDENT_CREATED,
            data={
                "incident_id": created_incident.id,
                "title": created_incident.title,
                "severity": created_incident.severity,
                "status": created_incident.status,
                "assigned_team": created_incident.assigned_team,
                "created_by": "slack-bot"
            }
        )
        
        return IncidentResponse(
            id=created_incident.id,
            title=created_incident.title,
            description=created_incident.description,
            severity=created_incident.severity,
            status=created_incident.status,
            source_query=created_incident.source_query,
            affected_systems=created_incident.affected_systems,
            assigned_team=created_incident.assigned_team,
            assigned_user=created_incident.assigned_user,
            created_at=created_incident.created_at,
            updated_at=created_incident.updated_at,
            resolved_at=created_incident.resolved_at,
            tags=created_incident.tags
        )
        
    except Exception as e:
        logger.error(f"Error creating incident: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.put("/incidents/{incident_id}", response_model=IncidentResponse, tags=["Incidents"])
@limiter.limit("100/minute")
async def update_incident(
    request: Request, 
    incident_id: str, 
    incident_data: IncidentUpdateRequest,
    _: bool = Depends(verify_slack_request)
):
    """Update existing incident (Slack-only)"""
    try:
        # Get existing incident
        incident = await app.state.incident_store.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        # Update fields
        update_data = incident_data.dict(exclude_unset=True)
        updated_incident = await app.state.incident_store.update_incident(incident_id, update_data)
        
        # Determine webhook event based on changes
        webhook_event = WebhookEvent.INCIDENT_UPDATED
        if 'status' in update_data and update_data['status'] == IncidentStatus.RESOLVED:
            webhook_event = WebhookEvent.INCIDENT_RESOLVED
        elif 'assigned_team' in update_data or 'assigned_user' in update_data:
            webhook_event = WebhookEvent.INCIDENT_ASSIGNED
        
        # Send webhook notification
        await webhook_manager.send_webhook(
            event=webhook_event,
            data={
                "incident_id": updated_incident.id,
                "title": updated_incident.title,
                "severity": updated_incident.severity,
                "status": updated_incident.status,
                "assigned_team": updated_incident.assigned_team,
                "assigned_user": updated_incident.assigned_user,
                "changes": update_data,
                "updated_by": "slack-bot"
            }
        )
        
        return IncidentResponse(
            id=updated_incident.id,
            title=updated_incident.title,
            description=updated_incident.description,
            severity=updated_incident.severity,
            status=updated_incident.status,
            source_query=updated_incident.source_query,
            affected_systems=updated_incident.affected_systems,
            assigned_team=updated_incident.assigned_team,
            assigned_user=updated_incident.assigned_user,
            created_at=updated_incident.created_at,
            updated_at=updated_incident.updated_at,
            resolved_at=updated_incident.resolved_at,
            tags=updated_incident.tags
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating incident {incident_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/incidents/{incident_id}/analyze", tags=["Analysis"])
@limiter.limit("10/minute")
async def analyze_incident(
    request: Request, 
    incident_id: str,
    _: bool = Depends(verify_slack_request)
):
    """Trigger AI analysis for incident (Slack-only)"""
    try:
        incident = await app.state.incident_store.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        # Perform AI analysis
        analysis = await app.state.ai_analyzer.analyze_incident(incident)
        
        # Update incident with analysis
        await app.state.incident_store.update_incident(
            incident_id, 
            {"ai_analysis": analysis}
        )
        
        # Send webhook notification
        await webhook_manager.send_webhook(
            event=WebhookEvent.ANALYSIS_COMPLETED,
            data={
                "incident_id": incident_id,
                "analysis": analysis,
                "analyzed_by": "slack-bot"
            }
        )
        
        return {"message": "Analysis completed", "analysis": analysis}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing incident {incident_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/incidents/{incident_id}/remediate", tags=["Automation"])
@limiter.limit("5/minute")
async def execute_remediation(
    request: Request,
    incident_id: str,
    action: str,
    parameters: Dict[str, Any] = {},
    _: bool = Depends(verify_slack_request)
):
    """Execute automated remediation for incident (Slack-only)"""
    try:
        incident = await app.state.incident_store.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        
        # Send automation started webhook
        await webhook_manager.send_webhook(
            event=WebhookEvent.AUTOMATION_STARTED,
            data={
                "incident_id": incident_id,
                "action": action,
                "parameters": parameters,
                "started_by": "slack-bot"
            }
        )
        
        # Execute remediation
        result = await app.state.automation_engine.execute_remediation(
            incident, action, parameters, "slack-bot"
        )
        
        # Send completion webhook
        webhook_event = WebhookEvent.AUTOMATION_COMPLETED if result.get("success") else WebhookEvent.AUTOMATION_FAILED
        await webhook_manager.send_webhook(
            event=webhook_event,
            data={
                "incident_id": incident_id,
                "action": action,
                "result": result,
                "executed_by": "slack-bot"
            }
        )
        
        return {"message": "Remediation executed", "result": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing remediation for incident {incident_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)