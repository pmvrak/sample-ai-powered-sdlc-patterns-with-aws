#!/usr/bin/env python3
"""
Simple Incident Management Service for ECS Deployment
====================================================

This is a simplified version of the incident management service
designed to start successfully in ECS containers.
"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

# FastAPI and related imports
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Incident Management Service",
    description="Simplified incident management service for ECS deployment",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Development frontend
        "http://localhost:8000",  # Development API docs
        "http://127.0.0.1:3000",  # Local development
        "http://127.0.0.1:8000",  # Local API docs
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Global state
service_stats = {
    "service_start_time": datetime.now(),
    "status": "running",
    "environment": os.getenv("ENVIRONMENT", "dev"),
    "version": "1.0.0"
}

# Pydantic models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    environment: str
    version: str
    uptime_seconds: float

class ServiceStats(BaseModel):
    service_start_time: str
    status: str
    environment: str
    version: str
    uptime_seconds: float

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Incident Management Service",
        "status": "running",
        "environment": os.getenv("ENVIRONMENT", "dev"),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for load balancer"""
    uptime = (datetime.now() - service_stats["service_start_time"]).total_seconds()
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        environment=service_stats["environment"],
        version=service_stats["version"],
        uptime_seconds=uptime
    )

@app.get("/stats", response_model=ServiceStats)
async def get_stats():
    """Get service statistics"""
    uptime = (datetime.now() - service_stats["service_start_time"]).total_seconds()
    
    return ServiceStats(
        service_start_time=service_stats["service_start_time"].isoformat(),
        status=service_stats["status"],
        environment=service_stats["environment"],
        version=service_stats["version"],
        uptime_seconds=uptime
    )

@app.get("/incidents")
async def list_incidents():
    """List incidents (mock data for now)"""
    return {
        "incidents": [],
        "total": 0,
        "message": "No incidents detected",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/test-slack")
async def test_slack_notification():
    """Test Slack notification functionality"""
    try:
        import requests
        
        # Get Slack webhook URL from environment or secrets
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        
        if not webhook_url:
            return {
                "status": "error",
                "message": "SLACK_WEBHOOK_URL not configured",
                "timestamp": datetime.now().isoformat()
            }
        
        # Send test message
        message = {
            "text": f"🧪 Test notification from Incident Management Service",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Test Notification* 🧪\n\nIncident Management Service is running successfully!\n\n*Environment:* {os.getenv('ENVIRONMENT', 'dev')}\n*Timestamp:* {datetime.now().isoformat()}"
                    }
                }
            ]
        }
        
        response = requests.post(webhook_url, json=message, timeout=10)
        
        if response.status_code == 200:
            return {
                "status": "success",
                "message": "Slack notification sent successfully",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": f"Slack API returned status {response.status_code}",
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")
        return {
            "status": "error",
            "message": f"Failed to send Slack notification: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.post("/simulate-incident")
async def simulate_incident():
    """Simulate an incident and send Slack notification"""
    try:
        import requests
        
        webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        
        if not webhook_url:
            return {
                "status": "error",
                "message": "SLACK_WEBHOOK_URL not configured",
                "timestamp": datetime.now().isoformat()
            }
        
        # Create mock incident
        incident_id = f"INC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        message = {
            "text": f"🚨 INCIDENT DETECTED: {incident_id}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*🚨 INCIDENT DETECTED*\n\n*Incident ID:* {incident_id}\n*Severity:* HIGH\n*Description:* Simulated incident for testing\n*Environment:* {os.getenv('ENVIRONMENT', 'dev')}\n*Detected:* {datetime.now().isoformat()}"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Acknowledge"
                            },
                            "style": "primary",
                            "value": f"ack_{incident_id}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View Details"
                            },
                            "value": f"details_{incident_id}"
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(webhook_url, json=message, timeout=10)
        
        if response.status_code == 200:
            return {
                "status": "success",
                "message": f"Incident {incident_id} simulated and Slack notification sent",
                "incident_id": incident_id,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "error",
                "message": f"Slack API returned status {response.status_code}",
                "timestamp": datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Incident simulation failed: {e}")
        return {
            "status": "error",
            "message": f"Failed to simulate incident: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/system/info")
async def system_info():
    """Get system information"""
    return {
        "python_version": sys.version,
        "environment_variables": {
            "ENVIRONMENT": os.getenv("ENVIRONMENT", "not_set"),
            "AWS_REGION": os.getenv("AWS_REGION", "not_set"),
            "API_HOST": os.getenv("API_HOST", "not_set"),
            "API_PORT": os.getenv("API_PORT", "not_set"),
            "LOG_LEVEL": os.getenv("LOG_LEVEL", "not_set")
        },
        "working_directory": str(Path.cwd()),
        "timestamp": datetime.now().isoformat()
    }

@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("🚀 Incident Management Service starting up...")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'dev')}")
    logger.info(f"AWS Region: {os.getenv('AWS_REGION', 'not_set')}")
    logger.info(f"API Host: {os.getenv('API_HOST', '0.0.0.0')}")
    logger.info(f"API Port: {os.getenv('API_PORT', '8002')}")
    logger.info("✅ Service startup completed successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("🛑 Incident Management Service shutting down...")
    service_stats["status"] = "shutting_down"

if __name__ == "__main__":
    try:
        # Get configuration from environment
        host = os.getenv("API_HOST", "0.0.0.0")
        port = int(os.getenv("API_PORT", "8002"))
        log_level = os.getenv("LOG_LEVEL", "info").lower()
        
        logger.info("=" * 50)
        logger.info("🚀 STARTING INCIDENT MANAGEMENT SERVICE")
        logger.info("=" * 50)
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Platform: {sys.platform}")
        logger.info(f"Working directory: {Path.cwd()}")
        logger.info(f"Host: {host}")
        logger.info(f"Port: {port}")
        logger.info(f"Log level: {log_level}")
        logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'not_set')}")
        logger.info("=" * 50)
        
        # Test basic imports
        logger.info("Testing imports...")
        import fastapi
        import uvicorn
        import pydantic
        logger.info(f"FastAPI version: {fastapi.__version__}")
        logger.info(f"Uvicorn version: {uvicorn.__version__}")
        logger.info(f"Pydantic version: {pydantic.__version__}")
        
        logger.info("All imports successful!")
        logger.info(f"Starting server on {host}:{port}")
        
        # Run the server
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=True
        )
    except Exception as e:
        logger.error(f"❌ FATAL ERROR during startup: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        sys.exit(255)  # Exit with code 255 to match the error we're seeing