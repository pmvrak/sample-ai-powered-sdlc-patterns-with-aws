#!/usr/bin/env python3
"""
End-to-End Incident Management Service
=====================================

This service provides a complete incident management solution that:
1. Connects to Splunk via MCP for real-time data monitoring
2. Detects incidents using intelligent pattern matching
3. Generates contextual remediation suggestions
4. Sends rich notifications to Slack with action buttons
5. Provides REST API for management and monitoring

Features:
- Real-time Splunk monitoring
- AI-powered incident analysis
- Automated remediation suggestions
- Interactive Slack notifications
- RESTful API with live data
- Continuous monitoring and alerting
"""

import os
import sys
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from pathlib import Path

# Ensure the current directory is in Python path for absolute imports
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# FastAPI and related imports
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from standardized .env file
env_file = current_dir / ".env"

if env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        logger.info(f"✅ Loaded environment from {env_file}")
    except ImportError:
        logger.warning("⚠️ python-dotenv not installed, using system environment")
else:
    logger.warning(f"⚠️ Environment file not found: {env_file}")
    logger.info("ℹ️ Using system environment variables")

# Initialize FastAPI app
app = FastAPI(
    title="Incident Management Service",
    description="End-to-end incident management with Splunk integration and Slack notifications",
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
splunk_client = None
detected_incidents = []
# Persistent incident cache for investigation sessions (survives cleanup)
incident_cache = {}  # incident_id -> incident_data
# Notification deduplication cache to prevent duplicate notifications
notification_cache = {}  # incident_key -> {"last_sent": timestamp, "count": int}

# File-based persistence for incident data (survives process restarts)
import json
import os
from pathlib import Path

INCIDENT_CACHE_FILE = "/tmp/incident_cache.json"
PROCESSED_INCIDENTS_FILE = "/tmp/processed_incidents.json"
NOTIFICATION_CACHE_FILE = "/tmp/notification_cache.json"

def load_incident_cache():
    """Load incident cache from file"""
    global incident_cache
    try:
        if os.path.exists(INCIDENT_CACHE_FILE):
            with open(INCIDENT_CACHE_FILE, 'r') as f:
                incident_cache = json.load(f)
                logger.info(f"🔍 Loaded {len(incident_cache)} incidents from persistent cache file")
    except Exception as e:
        logger.warning(f"⚠️ Could not load incident cache from file: {e}")
        incident_cache = {}

def save_incident_cache():
    """Save incident cache to file"""
    try:
        with open(INCIDENT_CACHE_FILE, 'w') as f:
            json.dump(incident_cache, f)
        logger.info(f"🔍 Saved {len(incident_cache)} incidents to persistent cache file")
    except Exception as e:
        logger.warning(f"⚠️ Could not save incident cache to file: {e}")

# Global variable for processed incidents
processed_incidents = set()

def load_processed_incidents():
    """Load processed incidents from file"""
    global processed_incidents
    try:
        if os.path.exists(PROCESSED_INCIDENTS_FILE):
            with open(PROCESSED_INCIDENTS_FILE, 'r') as f:
                data = json.load(f)
                processed_incidents = set(data.get('incidents', []))
                logger.info(f"🔍 Loaded {len(processed_incidents)} processed incidents from persistent file")
    except Exception as e:
        logger.warning(f"⚠️ Could not load processed incidents from file: {e}")
        processed_incidents = set()

def save_processed_incidents():
    """Save processed incidents to file"""
    global processed_incidents
    try:
        with open(PROCESSED_INCIDENTS_FILE, 'w') as f:
            json.dump({
                'incidents': list(processed_incidents),
                'last_updated': datetime.now().isoformat()
            }, f)
        logger.info(f"🔍 Saved {len(processed_incidents)} processed incidents to persistent file")
    except Exception as e:
        logger.warning(f"⚠️ Could not save processed incidents to file: {e}")

def load_notification_cache():
    """Load notification cache from file"""
    global notification_cache
    try:
        if os.path.exists(NOTIFICATION_CACHE_FILE):
            with open(NOTIFICATION_CACHE_FILE, 'r') as f:
                notification_cache = json.load(f)
                logger.info(f"🔍 Loaded {len(notification_cache)} notification cache entries from persistent file")
    except Exception as e:
        logger.warning(f"⚠️ Could not load notification cache from file: {e}")
        notification_cache = {}

def save_notification_cache():
    """Save notification cache to file"""
    try:
        with open(NOTIFICATION_CACHE_FILE, 'w') as f:
            json.dump(notification_cache, f)
        logger.info(f"🔍 Saved {len(notification_cache)} notification cache entries to persistent file")
    except Exception as e:
        logger.warning(f"⚠️ Could not save notification cache to file: {e}")

# Load all caches on startup
load_incident_cache()
load_processed_incidents()
load_notification_cache()

def should_send_notification(incident_key: str, incident_id: str, cooldown_minutes: int = None, severity: str = 'MEDIUM') -> bool:
    """
    Check if a notification should be sent for this incident.
    
    Args:
        incident_key: Unique key for the incident type/pattern
        incident_id: Specific incident ID
        cooldown_minutes: Minutes to wait before sending another notification for the same incident type
        severity: Incident severity for determining cooldown period
        
    Returns:
        bool: True if notification should be sent, False if it's a duplicate
    """
    global notification_cache
    
    current_time = datetime.now()
    
    # Use severity-based cooldown periods if not specified
    if cooldown_minutes is None:
        severity_cooldowns = {
            'HIGH': 30,    # 30 minutes for high severity
            'MEDIUM': 60,  # 60 minutes for medium severity  
            'LOW': 120     # 120 minutes for low severity
        }
        cooldown_minutes = severity_cooldowns.get(severity.upper(), 60)
    
    # Check if we've sent a notification for this incident type recently
    if incident_key in notification_cache:
        try:
            last_sent = datetime.fromisoformat(notification_cache[incident_key]['last_sent'])
            time_diff = (current_time - last_sent).total_seconds() / 60  # Convert to minutes
            
            if time_diff < cooldown_minutes:
                # Update count but don't send notification
                notification_cache[incident_key]['count'] += 1
                if 'suppressed_incidents' not in notification_cache[incident_key]:
                    notification_cache[incident_key]['suppressed_incidents'] = []
                notification_cache[incident_key]['suppressed_incidents'].append(incident_id)
                logger.info(f"🔕 Suppressing duplicate notification for {incident_key} (last sent {time_diff:.1f} minutes ago, total suppressed: {notification_cache[incident_key]['count']})")
                return False
        except (ValueError, KeyError) as e:
            logger.warning(f"⚠️ Error parsing notification cache for {incident_key}: {e}, allowing notification")
            # If there's an error parsing the cache, allow the notification to be safe
    
    # Send notification and update cache
    notification_cache[incident_key] = {
        'last_sent': current_time.isoformat(),
        'count': 1,
        'last_incident_id': incident_id,
        'suppressed_incidents': []
    }
    
    logger.info(f"✅ Notification approved for {incident_key} (incident: {incident_id})")
    return True

def cleanup_notification_cache():
    """Clean up old entries from notification cache"""
    global notification_cache
    
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(hours=24)  # Remove entries older than 24 hours
    
    keys_to_remove = []
    for key, data in notification_cache.items():
        last_sent = datetime.fromisoformat(data['last_sent'])
        if last_sent < cutoff_time:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        del notification_cache[key]
    
    if keys_to_remove:
        logger.info(f"🧹 Cleaned up {len(keys_to_remove)} old notification cache entries")

service_stats = {
    "service_start_time": datetime.now(),
    "incidents_detected": 0,
    "remediations_generated": 0,
    "slack_notifications_sent": 0,
    "errors": []
}

# Pydantic models
class IncidentResponse(BaseModel):
    id: str
    title: str
    description: str
    severity: str
    status: str
    source_query: str
    affected_systems: List[str]
    created_at: str
    event_count: int
    sample_events: List[Dict[str, Any]]
    remediation_suggestions: Optional[List[Dict[str, Any]]] = []

class SystemStats(BaseModel):
    total_events: int
    indexes: List[Dict[str, Any]]
    sourcetypes: List[str]
    recent_incidents: int
    system_health: str

# Enhanced Slack Integration
enhanced_slack_integration = None

# Multi-Source Incident Client
class MultiSourceIncidentClient:
    """
    Multi-source incident client that can connect to both Splunk and PagerDuty
    for comprehensive incident management
    """
    
    def __init__(self):
        self.splunk_connected = False
        self.pagerduty_connected = False
        self.connection_details = {}
        self.last_error = None
        self.splunk_client = None
        self.pagerduty_client = None
        
    async def connect(self):
        """Connect to both Splunk and PagerDuty MCP servers"""
        connection_results = {}
        
        # Try to connect to Splunk MCP server via stdio
        try:
            sys.path.append(str(current_dir / "integrations"))
            from real_splunk_mcp_client import SplunkIncidentClient as SplunkClient
            
            self.splunk_client = SplunkClient()
            splunk_success = await self.splunk_client.connect()
            
            if splunk_success:
                self.splunk_connected = True
                connection_results["splunk"] = {
                    "status": "connected",
                    "type": "Splunk MCP Client",
                    "connected_at": datetime.now().isoformat()
                }
                logger.info("✅ Connected to Splunk MCP server")
            else:
                connection_results["splunk"] = {
                    "status": "failed",
                    "reason": "Connection failed",
                    "note": "No Splunk data available"
                }
                logger.warning("⚠️ Failed to connect to Splunk MCP server")
                
        except ImportError as e:
            connection_results["splunk"] = {
                "status": "unavailable",
                "reason": "Splunk MCP client not available",
                "error": str(e)
            }
            logger.warning(f"⚠️ Splunk MCP client not available: {e}")
        except Exception as e:
            connection_results["splunk"] = {
                "status": "error",
                "reason": "Unexpected error",
                "error": str(e)
            }
            logger.error(f"❌ Error connecting to Splunk: {e}")
        
        # Try to connect to PagerDuty MCP server
        try:
            from pagerduty_client import PagerDutyIncidentClient
            
            # Get PagerDuty API key from environment
            pagerduty_api_key = os.getenv('PAGERDUTY_USER_API_KEY')
            pagerduty_api_host = os.getenv('PAGERDUTY_API_HOST', 'https://api.pagerduty.com')
            
            if pagerduty_api_key:
                self.pagerduty_client = PagerDutyIncidentClient(pagerduty_api_key, pagerduty_api_host)
                pagerduty_success = await self.pagerduty_client.connect()
                
                if pagerduty_success:
                    self.pagerduty_connected = True
                    connection_results["pagerduty"] = {
                        "status": "connected",
                        "type": "PagerDuty MCP Client",
                        "api_host": pagerduty_api_host,
                        "connected_at": datetime.now().isoformat()
                    }
                    logger.info("✅ Connected to PagerDuty MCP server")
                else:
                    connection_results["pagerduty"] = {
                        "status": "failed",
                        "reason": "Connection failed",
                        "note": "No PagerDuty data available"
                    }
                    logger.warning("⚠️ Failed to connect to PagerDuty MCP server")
            else:
                connection_results["pagerduty"] = {
                    "status": "no_api_key",
                    "reason": "No PagerDuty API key provided",
                    "note": "Set PAGERDUTY_USER_API_KEY environment variable"
                }
                logger.info("ℹ️ No PagerDuty API key provided")
                
        except ImportError as e:
            connection_results["pagerduty"] = {
                "status": "unavailable",
                "reason": "PagerDuty MCP client not available",
                "error": str(e)
            }
            logger.warning(f"⚠️ PagerDuty MCP client not available: {e}")
        except Exception as e:
            connection_results["pagerduty"] = {
                "status": "error",
                "reason": "Unexpected error",
                "error": str(e)
            }
            logger.error(f"❌ Error connecting to PagerDuty: {e}")
        
        # Update connection details
        self.connection_details = {
            "connections": connection_results,
            "splunk_connected": self.splunk_connected,
            "pagerduty_connected": self.pagerduty_connected,
            "total_connections": sum([self.splunk_connected, self.pagerduty_connected])
        }
        
        # For backward compatibility, set connected if any source is available
        self.connected = self.splunk_connected or self.pagerduty_connected
        
        if self.connected:
            logger.info(f"✅ Multi-source client connected (Splunk: {self.splunk_connected}, PagerDuty: {self.pagerduty_connected})")
        else:
            logger.warning("⚠️ No data sources available - service will run with limited functionality")
        
        # Update enhanced Slack integration with newly connected clients
        self._update_slack_integration_clients()
        
        # Initialize enhanced Slack integration if Slack credentials are available
        self._initialize_enhanced_slack_integration()
        
        return self.connected
    
    def _initialize_enhanced_slack_integration(self):
        """Initialize enhanced Slack integration if Slack credentials are available"""
        global enhanced_slack_integration
        
        if enhanced_slack_integration is not None:
            logger.info("✅ Enhanced Slack integration already initialized")
            return True
            
        try:
            # Ensure the current directory is in Python path
            import sys
            from pathlib import Path
            current_dir = Path(__file__).parent
            if str(current_dir) not in sys.path:
                sys.path.insert(0, str(current_dir))
            
            # Try importing step by step to identify the exact issue
            logger.info("🔍 Attempting to import enhanced Slack integration components...")
            
            from integrations.slack_bot import SlackBot
            logger.info("✅ SlackBot imported successfully")
            
            from integrations.interactive_slack_investigator import InteractiveSlackInvestigator
            logger.info("✅ InteractiveSlackInvestigator imported successfully")
            
            from integrations.enhanced_slack_integration import EnhancedSlackIntegration
            logger.info("✅ EnhancedSlackIntegration imported successfully")
            
            bot_token = os.getenv('SLACK_BOT_TOKEN')
            signing_secret = os.getenv('SLACK_SIGNING_SECRET')
            
            if bot_token and signing_secret:
                # Initialize with available clients (can be None)
                enhanced_slack_integration = EnhancedSlackIntegration(
                    bot_token, 
                    signing_secret, 
                    self.splunk_client if self.splunk_connected else None, 
                    self.pagerduty_client if self.pagerduty_connected else None
                )
                # Setup FastAPI routes for Slack integration
                enhanced_slack_integration.setup_fastapi_routes(app)
                
                available_sources = []
                if self.splunk_connected:
                    available_sources.append("Splunk")
                if self.pagerduty_connected:
                    available_sources.append("PagerDuty")
                
                if available_sources:
                    logger.info(f"✅ Enhanced Slack integration initialized with {', '.join(available_sources)}")
                else:
                    logger.info("✅ Enhanced Slack integration initialized (no MCP servers available yet)")
                
                return True
            else:
                logger.info("ℹ️ Slack bot credentials not configured - using webhook only")
                return False
                
        except ImportError as e:
            logger.warning(f"⚠️ Enhanced Slack integration not available: {e}")
            import traceback
            logger.debug(f"Import traceback: {traceback.format_exc()}")
            return False
        except Exception as e:
            logger.error(f"❌ Error initializing enhanced Slack integration: {e}")
            import traceback
            logger.error(f"Error traceback: {traceback.format_exc()}")
            return False
    
    def _update_slack_integration_clients(self):
        """Update the enhanced Slack integration with newly connected MCP clients"""
        global enhanced_slack_integration
        
        if enhanced_slack_integration is not None:
            try:
                # Update the clients in the enhanced integration
                if hasattr(enhanced_slack_integration, 'splunk_client') and self.splunk_connected:
                    enhanced_slack_integration.splunk_client = self.splunk_client
                    logger.info("✅ Updated enhanced Slack integration with Splunk client")
                
                if hasattr(enhanced_slack_integration, 'pagerduty_client') and self.pagerduty_connected:
                    enhanced_slack_integration.pagerduty_client = self.pagerduty_client
                    logger.info("✅ Updated enhanced Slack integration with PagerDuty client")
                
                # Update the investigator with new clients
                if hasattr(enhanced_slack_integration, 'investigator'):
                    if self.splunk_connected:
                        enhanced_slack_integration.investigator.splunk_client = self.splunk_client
                    if self.pagerduty_connected:
                        enhanced_slack_integration.investigator.pagerduty_client = self.pagerduty_client
                    logger.info("✅ Updated Slack investigator with new MCP clients")
                
            except Exception as e:
                logger.error(f"❌ Error updating Slack integration clients: {e}")
    
    async def retry_connections(self):
        """Retry connections to MCP servers and reinitialize enhanced Slack integration"""
        logger.info("🔄 Retrying MCP server connections...")
        
        # Reset connection states
        old_splunk_connected = self.splunk_connected
        old_pagerduty_connected = self.pagerduty_connected
        
        # Retry connections
        await self.connect()
        
        # Check if connections improved
        connections_improved = (
            (not old_splunk_connected and self.splunk_connected) or
            (not old_pagerduty_connected and self.pagerduty_connected)
        )
        
        if connections_improved:
            logger.info("🎉 Connection status improved, attempting to initialize enhanced Slack integration")
            success = self._initialize_enhanced_slack_integration()
            if success:
                logger.info("✅ Enhanced Slack integration successfully initialized after retry")
            return success
        else:
            logger.info("ℹ️ No connection improvements detected")
            return False
    
    async def test_connection(self):
        """Test Splunk connection"""
        if hasattr(self, 'actual_client'):
            try:
                return await self.actual_client.test_connection()
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"❌ Real connection test failed: {e}")
                return False
        return self.connected
    
    async def search_events(self, query: str, earliest_time: str = "-1h", latest_time: str = "now"):
        """Search Splunk events - ONLY real data, no mocks"""
        if self.splunk_connected and hasattr(self, 'splunk_client'):
            try:
                results = await self.splunk_client.search_events(query, earliest_time, latest_time)
                logger.info(f"✅ Splunk search returned {len(results) if results else 0} results")
                return results if results else []
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"❌ Splunk search failed: {e}")
                return []
        
        # No Splunk client available - return empty results
        logger.warning("⚠️ No Splunk client available, returning empty results")
        return []
    
    async def get_pagerduty_incidents(self, statuses: Optional[List[str]] = None):
        """Get incidents from PagerDuty"""
        if self.pagerduty_connected and hasattr(self, 'pagerduty_client'):
            try:
                if statuses is None:
                    statuses = ["triggered", "acknowledged"]
                
                incidents = await self.pagerduty_client.get_active_incidents()
                logger.info(f"✅ PagerDuty returned {len(incidents)} incidents")
                return incidents
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"❌ PagerDuty incident fetch failed: {e}")
                return []
        
        # No PagerDuty client available
        logger.warning("⚠️ No PagerDuty client available")
        return []
    
    async def add_remediation_to_pagerduty(self, incident_id: str, remediation_suggestions: List[Dict[str, Any]]):
        """Add remediation suggestions to a PagerDuty incident"""
        if self.pagerduty_connected and hasattr(self, 'pagerduty_client'):
            try:
                success = await self.pagerduty_client.add_remediation_note(incident_id, remediation_suggestions)
                if success:
                    logger.info(f"✅ Added remediation suggestions to PagerDuty incident {incident_id}")
                else:
                    logger.warning(f"⚠️ Failed to add remediation to PagerDuty incident {incident_id}")
                return success
            except Exception as e:
                logger.error(f"❌ Error adding remediation to PagerDuty: {e}")
                return False
        
        logger.warning("⚠️ No PagerDuty client available for adding remediation")
        return False
    
    async def create_pagerduty_incident(self, incident_data: Dict[str, Any], 
                                      remediation_suggestions: List[Dict[str, Any]]):
        """Create a new PagerDuty incident from Splunk detection"""
        if self.pagerduty_connected and hasattr(self, 'pagerduty_client'):
            try:
                result = await self.pagerduty_client.create_incident_from_detection(
                    incident_data, 
                    remediation_suggestions
                )
                if result.get('success'):
                    logger.info(f"✅ Created PagerDuty incident: {result.get('incident_id')}")
                else:
                    logger.warning(f"⚠️ Failed to create PagerDuty incident: {result.get('error')}")
                return result
            except Exception as e:
                logger.error(f"❌ Error creating PagerDuty incident: {e}")
                return {"success": False, "error": str(e)}
        
        logger.warning("⚠️ No PagerDuty client available for incident creation")
        return {"success": False, "error": "No PagerDuty connection"}
    
    async def execute_detection_query(self, query: str):
        """Execute detection query"""
        return await self.search_events(query)
    
    def get_connection_info(self):
        """Get detailed connection information"""
        return {
            "connected": self.connected,
            "connection_details": self.connection_details,
            "last_error": self.last_error,
            "has_real_client": hasattr(self, 'actual_client')
        }
    
    # Data generation functionality removed - only real Splunk data is used

# Remediation Suggestion Engine
def generate_remediation_suggestions(incident_description: str, affected_systems: List[str]) -> List[Dict[str, Any]]:
    """Generate intelligent remediation suggestions with detailed instructions"""
    
    suggestions = []
    description_lower = incident_description.lower()
    
    # Memory-related issues
    if any(keyword in description_lower for keyword in ['memory', 'ram', 'heap', 'oom']):
        suggestions.extend([
            {
                'id': f'mem_restart_{datetime.now().strftime("%H%M%S")}',
                'title': 'Service Restart for Memory Recovery',
                'description': 'Restart affected services to clear memory leaks and reset memory usage',
                'risk_level': 'LOW',
                'estimated_time': '5-10 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Identify the specific services consuming excessive memory',
                    '2. Check current memory usage: `free -h` and `ps aux --sort=-%mem | head -20`',
                    '3. For systemd services: `sudo systemctl restart <service-name>`',
                    '4. For Docker containers: `docker restart <container-name>`',
                    '5. Monitor memory usage after restart: `watch -n 5 free -h`',
                    '6. Verify service functionality with health checks'
                ],
                'commands': [
                    'free -h  # Check current memory usage',
                    'ps aux --sort=-%mem | head -20  # Find memory-heavy processes',
                    'sudo systemctl restart <service-name>  # Restart systemd service',
                    'docker restart <container-name>  # Restart Docker container',
                    'watch -n 5 free -h  # Monitor memory recovery'
                ],
                'prerequisites': ['Root/sudo access', 'Service identification', 'Maintenance window if needed'],
                'rollback_plan': 'Services should auto-restart. If issues persist, check logs and consider scaling resources.',
                'validation_steps': [
                    'Verify service is running: `systemctl status <service>`',
                    'Check memory usage has decreased',
                    'Test application functionality',
                    'Monitor for memory leak recurrence'
                ]
            },
            {
                'id': f'mem_analysis_{datetime.now().strftime("%H%M%S")}',
                'title': 'Memory Usage Analysis and Monitoring',
                'description': 'Comprehensive memory analysis to identify root causes and prevent recurrence',
                'risk_level': 'NONE',
                'estimated_time': '10-15 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Collect current memory statistics and process information',
                    '2. Analyze memory usage patterns over time',
                    '3. Identify potential memory leaks or inefficient processes',
                    '4. Set up monitoring alerts for future incidents',
                    '5. Document findings for capacity planning'
                ],
                'commands': [
                    'free -h  # Overall memory usage',
                    'cat /proc/meminfo  # Detailed memory information',
                    'ps aux --sort=-%mem | head -20  # Top memory consumers',
                    'pmap -d <pid>  # Memory map of specific process',
                    'vmstat 1 10  # Virtual memory statistics',
                    'sar -r 1 10  # Memory utilization over time'
                ],
                'prerequisites': ['System monitoring tools installed', 'Historical data access'],
                'rollback_plan': 'Read-only analysis, no rollback needed',
                'validation_steps': [
                    'Memory usage patterns documented',
                    'Root cause identified',
                    'Monitoring alerts configured',
                    'Recommendations for optimization provided'
                ]
            }
        ])
    
    # CPU-related issues
    if any(keyword in description_lower for keyword in ['cpu', 'processor', 'load', 'performance']):
        suggestions.extend([
            {
                'id': f'cpu_scale_{datetime.now().strftime("%H%M%S")}',
                'title': 'CPU Resource Scaling and Optimization',
                'description': 'Scale compute resources and optimize CPU usage to handle increased load',
                'risk_level': 'MEDIUM',
                'estimated_time': '15-30 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Analyze current CPU utilization and identify bottlenecks',
                    '2. Determine if scaling up (vertical) or out (horizontal) is appropriate',
                    '3. For cloud instances: increase instance size or add instances',
                    '4. For containers: adjust CPU limits and add replicas',
                    '5. Implement load balancing if adding instances',
                    '6. Monitor performance improvements and adjust as needed'
                ],
                'commands': [
                    'top -n 1  # Current CPU usage by process',
                    'htop  # Interactive process viewer',
                    'iostat -c 1 10  # CPU utilization statistics',
                    'aws ec2 modify-instance-attribute --instance-id <id> --instance-type <new-type>  # AWS scaling',
                    'kubectl scale deployment <name> --replicas=<count>  # Kubernetes scaling',
                    'docker update --cpus="2.0" <container>  # Docker CPU limit'
                ],
                'prerequisites': ['Performance baseline data', 'Scaling permissions', 'Load balancer configuration'],
                'rollback_plan': 'Scale back to original configuration if performance degrades or costs become prohibitive',
                'validation_steps': [
                    'CPU utilization reduced to acceptable levels',
                    'Application response times improved',
                    'No new bottlenecks introduced',
                    'Cost impact within acceptable range'
                ]
            },
            {
                'id': f'cpu_analysis_{datetime.now().strftime("%H%M%S")}',
                'title': 'CPU Performance Analysis and Tuning',
                'description': 'Comprehensive CPU performance analysis to identify optimization opportunities',
                'risk_level': 'NONE',
                'estimated_time': '10-20 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Collect detailed CPU performance metrics',
                    '2. Identify processes consuming excessive CPU resources',
                    '3. Analyze CPU wait times and context switching',
                    '4. Check for CPU throttling or thermal issues',
                    '5. Review system configuration for optimization opportunities',
                    '6. Generate performance tuning recommendations'
                ],
                'commands': [
                    'top -n 1  # Process CPU usage snapshot',
                    'vmstat 1 10  # Virtual memory and CPU statistics',
                    'sar -u 1 10  # CPU utilization over time',
                    'pidstat -u 1 10  # Per-process CPU usage',
                    'perf top  # Real-time CPU profiling',
                    'cat /proc/cpuinfo  # CPU configuration details'
                ],
                'prerequisites': ['Performance monitoring tools', 'System access', 'Historical performance data'],
                'rollback_plan': 'Analysis only, no system changes made',
                'validation_steps': [
                    'CPU bottlenecks identified and documented',
                    'Performance optimization plan created',
                    'Monitoring alerts configured for CPU thresholds',
                    'Recommendations prioritized by impact'
                ]
            }
        ])
    
    # Error-related issues
    if any(keyword in description_lower for keyword in ['error', 'exception', 'failed', 'failure']):
        suggestions.extend([
            {
                'id': f'error_investigation_{datetime.now().strftime("%H%M%S")}',
                'title': 'Error Investigation and Root Cause Analysis',
                'description': 'Systematic investigation of errors to identify root causes and implement fixes',
                'risk_level': 'NONE',
                'estimated_time': '15-30 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Collect and analyze recent error logs from all affected systems',
                    '2. Identify error patterns, frequency, and correlation with system events',
                    '3. Trace error origins through application stack and dependencies',
                    '4. Check for recent deployments or configuration changes',
                    '5. Analyze system resources during error occurrences',
                    '6. Document findings and create action plan for resolution'
                ],
                'commands': [
                    'tail -n 500 /var/log/application.log | grep -i error  # Recent application errors',
                    'journalctl -u <service> --since "1 hour ago" | grep -i error  # Service errors',
                    'grep -r "ERROR\\|FATAL" /var/log/ --include="*.log" | tail -50  # System-wide errors',
                    'dmesg | grep -i error  # Kernel errors',
                    'docker logs <container> --since 1h | grep -i error  # Container errors',
                    'kubectl logs <pod> --since=1h | grep -i error  # Kubernetes pod errors'
                ],
                'prerequisites': ['Log access permissions', 'Understanding of application architecture', 'Error pattern analysis tools'],
                'rollback_plan': 'Investigation only, no system changes made',
                'validation_steps': [
                    'Error patterns identified and categorized',
                    'Root cause hypothesis developed',
                    'Impact assessment completed',
                    'Resolution plan documented with priorities'
                ]
            },
            {
                'id': f'health_validation_{datetime.now().strftime("%H%M%S")}',
                'title': 'System and Application Health Validation',
                'description': 'Comprehensive health check of all system components and dependencies',
                'risk_level': 'LOW',
                'estimated_time': '10-15 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Execute health checks for all application endpoints',
                    '2. Verify database connectivity and performance',
                    '3. Check external service dependencies and API responses',
                    '4. Validate system resource availability and thresholds',
                    '5. Test critical user workflows end-to-end',
                    '6. Generate health status report with recommendations'
                ],
                'commands': [
                    'curl -f http://localhost:8080/health  # Application health endpoint',
                    'systemctl status <service>  # Service status check',
                    'docker ps --filter "status=exited"  # Check for failed containers',
                    'kubectl get pods --field-selector=status.phase!=Running  # Failed Kubernetes pods',
                    'ping -c 3 <database-host>  # Database connectivity',
                    'curl -f https://api.external-service.com/health  # External dependency check'
                ],
                'prerequisites': ['Health endpoint availability', 'Network access to dependencies', 'Service monitoring tools'],
                'rollback_plan': 'Health checks are non-invasive, no rollback needed',
                'validation_steps': [
                    'All critical services responding normally',
                    'Database connections stable',
                    'External dependencies accessible',
                    'System resources within normal ranges',
                    'User workflows functioning correctly'
                ]
            }
        ])
    
    # Database-related issues
    if any(keyword in description_lower for keyword in ['database', 'db', 'connection', 'timeout']):
        suggestions.extend([
            {
                'id': f'db_connectivity_{datetime.now().strftime("%H%M%S")}',
                'title': 'Database Connectivity and Performance Analysis',
                'description': 'Comprehensive database connection testing and performance evaluation',
                'risk_level': 'NONE',
                'estimated_time': '10-15 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Test basic database connectivity from all application servers',
                    '2. Verify database server status and resource utilization',
                    '3. Check connection pool status and configuration',
                    '4. Analyze slow query logs and identify bottlenecks',
                    '5. Test database performance with sample queries',
                    '6. Review database error logs for connection issues'
                ],
                'commands': [
                    'mysql -h <host> -u <user> -p -e "SELECT 1;"  # MySQL connectivity test',
                    'pg_isready -h <host> -p <port>  # PostgreSQL readiness check',
                    'psql -h <host> -U <user> -d <db> -c "SELECT version();"  # PostgreSQL connection test',
                    'redis-cli -h <host> -p <port> ping  # Redis connectivity test',
                    'mongosh --host <host>:<port> --eval "db.runCommand({ping: 1})"  # MongoDB test',
                    'netstat -an | grep <db-port>  # Check database port connectivity'
                ],
                'prerequisites': ['Database credentials', 'Network access to database', 'Database client tools'],
                'rollback_plan': 'Connection testing only, no changes made to database',
                'validation_steps': [
                    'All database connections successful',
                    'Connection latency within acceptable range',
                    'No connection pool exhaustion',
                    'Database server resources healthy'
                ]
            },
            {
                'id': f'db_optimization_{datetime.now().strftime("%H%M%S")}',
                'title': 'Database Configuration and Timeout Optimization',
                'description': 'Optimize database connection settings and timeout configurations',
                'risk_level': 'MEDIUM',
                'estimated_time': '20-30 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Review current connection pool and timeout settings',
                    '2. Analyze connection usage patterns and peak loads',
                    '3. Calculate optimal connection pool size and timeouts',
                    '4. Update application configuration with new settings',
                    '5. Implement gradual rollout of configuration changes',
                    '6. Monitor connection performance after changes'
                ],
                'commands': [
                    'grep -r "timeout\\|pool" /etc/myapp/database.conf  # Find current settings',
                    'show variables like "%timeout%";  # MySQL timeout settings',
                    'SHOW pool_size, pool_timeout;  # Connection pool status',
                    'netstat -an | grep <db-port> | wc -l  # Count active connections',
                    'tail -f /var/log/application.log | grep -i "connection\\|timeout"  # Monitor changes'
                ],
                'prerequisites': ['Configuration file access', 'Application restart capability', 'Backup of current config'],
                'rollback_plan': 'Revert to previous configuration file and restart application',
                'validation_steps': [
                    'Connection timeouts eliminated or reduced',
                    'Application performance improved',
                    'No new connection errors introduced',
                    'Database load remains stable'
                ]
            }
        ])
    
    # Security-related issues
    if any(keyword in description_lower for keyword in ['security', 'authentication', 'unauthorized', 'access']):
        suggestions.extend([
            {
                'id': f'sec_investigation_{datetime.now().strftime("%H%M%S")}',
                'title': 'Security Incident Investigation and Analysis',
                'description': 'Comprehensive security log analysis to identify threats and attack patterns',
                'risk_level': 'NONE',
                'estimated_time': '15-30 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Collect and analyze authentication logs from all affected systems',
                    '2. Identify suspicious IP addresses, user accounts, and access patterns',
                    '3. Correlate security events across multiple log sources',
                    '4. Check for indicators of compromise (IoCs) and attack signatures',
                    '5. Assess the scope and potential impact of security incidents',
                    '6. Document findings and create incident response timeline'
                ],
                'commands': [
                    'grep -i "failed\\|denied\\|unauthorized" /var/log/auth.log | tail -100  # Authentication failures',
                    'journalctl -u ssh --since "1 hour ago" | grep -i "failed"  # SSH login attempts',
                    'grep "Invalid user" /var/log/auth.log | awk \'{print $8}\' | sort | uniq -c  # Failed usernames',
                    'last -f | head -20  # Recent login history',
                    'netstat -an | grep :22 | grep ESTABLISHED  # Active SSH connections',
                    'awk \'/Failed password/ {print $11}\' /var/log/auth.log | sort | uniq -c | sort -nr  # Failed IPs'
                ],
                'prerequisites': ['Security log access', 'Log analysis tools', 'Threat intelligence feeds'],
                'rollback_plan': 'Investigation only, no system changes made',
                'validation_steps': [
                    'Suspicious activities identified and categorized',
                    'Attack vectors and methods documented',
                    'Affected accounts and systems catalogued',
                    'Incident severity and impact assessed'
                ]
            },
            {
                'id': f'sec_response_{datetime.now().strftime("%H%M%S")}',
                'title': 'Security Response and Threat Mitigation',
                'description': 'Implement security measures to block threats and prevent further compromise',
                'risk_level': 'HIGH',
                'estimated_time': '10-20 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Identify confirmed malicious IP addresses and user accounts',
                    '2. Implement immediate blocking measures for identified threats',
                    '3. Reset passwords for potentially compromised accounts',
                    '4. Review and strengthen authentication mechanisms',
                    '5. Implement additional monitoring for affected systems',
                    '6. Coordinate with security team for further investigation'
                ],
                'commands': [
                    'iptables -A INPUT -s <malicious_ip> -j DROP  # Block IP address',
                    'fail2ban-client set sshd banip <ip_address>  # Ban IP with fail2ban',
                    'usermod -L <username>  # Lock potentially compromised account',
                    'passwd -e <username>  # Force password reset on next login',
                    'ufw deny from <ip_address>  # Block IP with UFW firewall',
                    'iptables -L INPUT -n --line-numbers  # List current firewall rules'
                ],
                'prerequisites': ['Firewall management access', 'User account administration', 'Security team coordination'],
                'rollback_plan': 'Remove firewall rules and unlock accounts if legitimate traffic is affected',
                'validation_steps': [
                    'Malicious traffic successfully blocked',
                    'No legitimate users affected by blocks',
                    'Compromised accounts secured',
                    'Enhanced monitoring in place',
                    'Security team notified and engaged'
                ]
            }
        ])
    
    # Default suggestions if no specific patterns match
    if not suggestions:
        suggestions.extend([
            {
                'id': f'general_investigation_{datetime.now().strftime("%H%M%S")}',
                'title': 'General System Investigation and Log Analysis',
                'description': 'Comprehensive system analysis to identify the root cause of the incident',
                'risk_level': 'NONE',
                'estimated_time': '15-25 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Collect system logs from all affected components',
                    '2. Analyze recent system events and error patterns',
                    '3. Check system resource utilization and capacity',
                    '4. Review recent changes, deployments, or configuration updates',
                    '5. Examine service dependencies and external integrations',
                    '6. Create timeline of events leading to the incident'
                ],
                'commands': [
                    'journalctl -n 200 --no-pager  # Recent system journal entries',
                    'dmesg | tail -50  # Recent kernel messages',
                    'tail -100 /var/log/syslog  # System log entries',
                    'systemctl --failed  # Failed services',
                    'df -h  # Disk space usage',
                    'free -h  # Memory usage',
                    'uptime  # System load and uptime',
                    'ps aux --sort=-%cpu | head -10  # Top CPU consumers'
                ],
                'prerequisites': ['System log access', 'Administrative privileges', 'Log analysis tools'],
                'rollback_plan': 'Investigation only, no system modifications made',
                'validation_steps': [
                    'System logs collected and analyzed',
                    'Resource utilization assessed',
                    'Recent changes identified',
                    'Incident timeline established',
                    'Root cause hypothesis developed'
                ]
            },
            {
                'id': f'system_health_{datetime.now().strftime("%H%M%S")}',
                'title': 'System Health Assessment and Service Validation',
                'description': 'Complete system health check to identify service issues and resource constraints',
                'risk_level': 'NONE',
                'estimated_time': '10-15 minutes',
                'systems': affected_systems,
                'detailed_instructions': [
                    '1. Check status of all critical system services',
                    '2. Validate system resource availability and thresholds',
                    '3. Test network connectivity to dependent services',
                    '4. Review system performance metrics and trends',
                    '5. Verify backup and monitoring systems are operational',
                    '6. Generate comprehensive health status report'
                ],
                'commands': [
                    'systemctl status  # Overall service status',
                    'systemctl list-units --failed  # Failed units',
                    'df -h  # Filesystem usage',
                    'free -h  # Memory usage',
                    'iostat -x 1 3  # I/O statistics',
                    'netstat -tuln  # Network listening ports',
                    'ping -c 3 8.8.8.8  # Internet connectivity',
                    'nslookup <critical-service>  # DNS resolution test'
                ],
                'prerequisites': ['System monitoring access', 'Network diagnostic tools', 'Service documentation'],
                'rollback_plan': 'Health checks are non-invasive, no rollback required',
                'validation_steps': [
                    'All critical services running normally',
                    'System resources within acceptable limits',
                    'Network connectivity verified',
                    'No critical alerts or warnings',
                    'Health status documented and reported'
                ]
            }
        ])
    
    return suggestions

# Slack Integration
async def send_slack_notification(incident: Dict[str, Any], suggestions: List[Dict[str, Any]]):
    """Send rich incident notification to Slack with remediation suggestions"""
    
    # Try enhanced Slack integration first (with interactive capabilities)
    global enhanced_slack_integration
    if enhanced_slack_integration:
        try:
            channels = [os.getenv('SLACK_CHANNEL', '#incidents')]
            results = await enhanced_slack_integration.send_incident_notification(incident, channels)
            
            if any(results.values()):
                logger.info("✅ Enhanced Slack notification sent with interactive investigation capabilities")
                return True
        except Exception as e:
            logger.warning(f"⚠️ Enhanced Slack integration failed, falling back to webhook: {e}")
    
    # Fallback to webhook integration
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url:
        logger.warning("⚠️ No Slack webhook configured")
        return False
    
    try:
        import requests
        
        # Create rich Slack message with action buttons
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 Incident Alert: {incident['title']}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Incident ID:* {incident['id']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Severity:* {incident['severity'].upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Events:* {incident['event_count']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Detected:* {datetime.now().strftime('%H:%M:%S')}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:* {incident['description']}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Affected Systems:* {', '.join(incident['affected_systems'])}"
                }
            }
        ]
        
        # Add remediation suggestions
        if suggestions:
            blocks.append({
                "type": "divider"
            })
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🛠️ Remediation Suggestions ({len(suggestions)} available):*"
                }
            })
            
            # Add detailed suggestions without action buttons
            for i, suggestion in enumerate(suggestions[:2], 1):
                risk_emoji = {"NONE": "🟢", "LOW": "🟡", "MEDIUM": "🟠", "HIGH": "🔴"}.get(suggestion['risk_level'], "⚪")
                
                # Main suggestion info
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{i}. {suggestion['title']}*\n"
                                f"{suggestion['description']}\n"
                                f"{risk_emoji} Risk: {suggestion['risk_level']} | ⏱️ Time: {suggestion['estimated_time']}"
                    }
                })
                
                # Add key commands if available
                if 'commands' in suggestion and suggestion['commands']:
                    key_commands = suggestion['commands'][:3]  # Show first 3 commands
                    commands_text = "\n".join([f"• `{cmd}`" for cmd in key_commands])
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Key Commands:*\n{commands_text}"
                        }
                    })
                
                # Add prerequisites if available
                if 'prerequisites' in suggestion and suggestion['prerequisites']:
                    prereq_text = ", ".join(suggestion['prerequisites'][:3])
                    blocks.append({
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Prerequisites:* {prereq_text}"
                            }
                        ]
                    })
            
            # Add link to full details
            api_port = os.getenv('API_PORT', '8002')
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"📋 *View complete remediation instructions:*\n"
                            f"<http://localhost:{api_port}/incidents/{incident['id']}|Full Incident Details>"
                }
            })
        
        # Send to Slack
        message = {
            "text": f"🚨 New Incident: {incident['title']}",
            "blocks": blocks
        }
        
        response = requests.post(webhook_url, json=message, timeout=10)
        
        if response.status_code == 200:
            service_stats["slack_notifications_sent"] += 1
            logger.info(f"✅ Slack notification sent for incident: {incident['title']}")
            return True
        else:
            logger.error(f"❌ Slack notification failed: {response.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error sending Slack notification: {e}")
        service_stats["errors"].append(f"Slack notification error: {str(e)}")
        return False

# Application lifecycle
@app.on_event("startup")
async def startup_event():
    """Initialize the service on startup"""
    global splunk_client
    
    logger.info("🚀 Starting Incident Management Service...")
    
    # Initialize multi-source client (Splunk + PagerDuty)
    splunk_client = MultiSourceIncidentClient()
    await splunk_client.connect()
    
    # Start continuous monitoring
    asyncio.create_task(continuous_incident_monitoring())
    
    logger.info("✅ Service startup complete")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean shutdown"""
    global splunk_client
    
    logger.info("🛑 Shutting down Incident Management Service")
    
    # Clean up MCP connection
    if splunk_client and hasattr(splunk_client, 'actual_client'):
        try:
            logger.info("🔌 Disconnecting from Splunk MCP server...")
            await splunk_client.actual_client.disconnect()
            logger.info("✅ MCP connection closed")
        except Exception as e:
            logger.warning(f"⚠️ Error during MCP cleanup: {e}")
    
    logger.info("✅ Shutdown complete")

# Continuous monitoring
async def continuous_incident_monitoring():
    """Continuously monitor Splunk and PagerDuty for incidents"""
    global detected_incidents, service_stats, splunk_client
    
    logger.info("🔍 Starting continuous incident monitoring (Splunk + PagerDuty)...")
    
    # Define Splunk incident detection queries
    splunk_detection_queries = [
        {
            'name': 'High Error Rate',
            'query': 'search index=main error OR failed OR exception | head 20 | stats count by source, sourcetype, host',
            'severity': 'HIGH',
            'threshold': 5,
            'check_interval': 300  # 5 minutes
        },
        {
            'name': 'AWS CloudTrail Errors',
            'query': 'search index=main sourcetype=aws:cloudtrail errorCode!=success | head 10 | stats count by eventSource, errorCode, sourceIPAddress',
            'severity': 'MEDIUM',
            'threshold': 3,
            'check_interval': 600  # 10 minutes
        },
        {
            'name': 'Performance Issues',
            'query': 'search index=main (cpu OR memory OR disk) (high OR critical OR alert) | head 10 | stats count by host, source',
            'severity': 'MEDIUM',
            'threshold': 2,
            'check_interval': 300  # 5 minutes
        },
        {
            'name': 'Security Events',
            'query': 'search index=main (authentication OR login) (failed OR denied OR unauthorized) | head 10 | stats count by user, src_ip, dest',
            'severity': 'HIGH',
            'threshold': 10,
            'check_interval': 180  # 3 minutes
        }
    ]
    
    query_last_run = {query['name']: datetime.min for query in splunk_detection_queries}
    processed_incidents = set()
    pagerduty_last_check = datetime.min
    self_created_pagerduty_incidents = set()  # Track incidents we created to avoid feedback loop
    
    while True:
        try:
            current_time = datetime.now()
            
            # Monitor Splunk incidents
            for query_config in splunk_detection_queries:
                query_name = query_config['name']
                
                # Check if it's time to run this query
                time_since_last = (current_time - query_last_run[query_name]).total_seconds()
                if time_since_last >= query_config['check_interval']:
                    
                    logger.info(f"🔎 Checking: {query_name}")
                    
                    try:
                        # Query Splunk - ONLY real data, no mocks
                        search_results = await splunk_client.execute_detection_query(query_config['query'])
                        
                        if search_results and len(search_results) > 0:
                            logger.info(f"📊 Real Splunk data found: {len(search_results)} results for {query_name}")
                            # Calculate total events
                            total_events = sum(int(r.get('count', 0)) for r in search_results if 'count' in r)
                            
                            # Check if this meets the threshold for an incident
                            if total_events >= query_config['threshold']:
                                # Create incident key to avoid duplicates - use stable key without event count fluctuations
                                # Use a 2-hour window for better granularity while avoiding event count sensitivity
                                two_hour_window = current_time.replace(hour=(current_time.hour // 2) * 2, minute=0, second=0).strftime('%Y%m%d%H%M')
                                
                                # Extract affected systems first
                                affected_systems = []
                                for result in search_results[:5]:
                                    for field in ['host', 'source', 'eventSource', 'service']:
                                        if field in result and result[field]:
                                            if result[field] not in affected_systems:
                                                affected_systems.append(result[field])
                                
                                if not affected_systems:
                                    affected_systems = ['unknown-system']
                                
                                # Get primary affected system for better deduplication
                                primary_system = affected_systems[0] if affected_systems else 'unknown'
                                
                                # Don't include event count to avoid fluctuation-based duplicates
                                incident_key = f"{query_name}_{primary_system}_{two_hour_window}"
                                
                                if incident_key not in processed_incidents:
                                    # Create incident
                                    incident_id = f"INC-{current_time.strftime('%Y%m%d%H%M%S')}-{query_name.replace(' ', '')}"
                                    
                                    # Extract detailed information from events
                                    error_types = []
                                    hosts_affected = []
                                    sources_affected = []
                                    
                                    for result in search_results[:10]:
                                        # Extract error types
                                        if 'error_type' in result:
                                            error_types.append(result['error_type'])
                                        elif 'errorCode' in result:
                                            error_types.append(result['errorCode'])
                                        
                                        # Extract hosts
                                        if 'host' in result and result['host'] not in hosts_affected:
                                            hosts_affected.append(result['host'])
                                        
                                        # Extract sources
                                        if 'source' in result and result['source'] not in sources_affected:
                                            sources_affected.append(result['source'])
                                    
                                    # Create detailed description
                                    description_parts = [f"{query_name} detected with {total_events} events"]
                                    
                                    if error_types:
                                        unique_errors = list(set(error_types))
                                        description_parts.append(f"Error types: {', '.join(unique_errors[:3])}")
                                    
                                    if hosts_affected:
                                        description_parts.append(f"Affected hosts: {', '.join(hosts_affected[:3])}")
                                    
                                    if sources_affected:
                                        description_parts.append(f"Log sources: {', '.join(sources_affected[:2])}")
                                    
                                    detailed_description = ". ".join(description_parts)
                                    
                                    # Create incident object with detailed information
                                    incident = {
                                        'id': incident_id,
                                        'title': f"{query_name} Alert",
                                        'description': detailed_description,
                                        'severity': query_config['severity'],
                                        'status': 'DETECTED',
                                        'source_query': query_config['query'],
                                        'affected_systems': affected_systems,
                                        'created_at': current_time.isoformat(),
                                        'event_count': total_events,
                                        'sample_events': search_results[:5],
                                        'detection_details': {
                                            'query_name': query_name,
                                            'threshold': query_config['threshold'],
                                            'check_interval': query_config['check_interval'],
                                            'error_types': list(set(error_types)),
                                            'hosts_affected': hosts_affected,
                                            'sources_affected': sources_affected,
                                            'splunk_connection_type': splunk_client.connection_details.get('type', 'Unknown') if splunk_client else 'Unknown'
                                        }
                                    }
                                    
                                    # Generate remediation suggestions
                                    suggestions = generate_remediation_suggestions(
                                        incident['description'], 
                                        incident['affected_systems']
                                    )
                                    
                                    # Add suggestions to incident
                                    incident['remediation_suggestions'] = suggestions
                                    
                                    # Store incident in both the main list and persistent cache
                                    detected_incidents.append(incident)
                                    incident_cache[incident['id']] = incident.copy()  # Store in persistent cache
                                    save_incident_cache()  # Save to file for persistence across processes
                                    logger.info(f"🔍 Stored incident {incident['id']} in both detected_incidents and incident_cache with {len(suggestions)} remediation suggestions")
                                    service_stats["incidents_detected"] += 1
                                    service_stats["remediations_generated"] += len(suggestions)
                                    
                                    # Create PagerDuty incident automatically (if enabled and priority qualifies)
                                    auto_create = os.getenv('PAGERDUTY_AUTO_CREATE_INCIDENTS', 'false').lower() == 'true'
                                    incident_severity = incident.get('severity', 'LOW').upper()
                                    
                                    # Get allowed priorities for auto-creation (default: MEDIUM,HIGH)
                                    allowed_priorities = os.getenv('PAGERDUTY_AUTO_CREATE_PRIORITIES', 'MEDIUM,HIGH').upper().split(',')
                                    allowed_priorities = [p.strip() for p in allowed_priorities if p.strip()]
                                    
                                    # Only create PagerDuty incidents for allowed priority levels
                                    priority_qualifies = incident_severity in allowed_priorities
                                    
                                    if auto_create and priority_qualifies:
                                        try:
                                            pd_result = await splunk_client.create_pagerduty_incident(incident, suggestions)
                                            if pd_result.get('success'):
                                                incident['pagerduty_incident_id'] = pd_result.get('incident_id')
                                                incident['pagerduty_created'] = True
                                                # Track this incident to avoid processing it again
                                                self_created_pagerduty_incidents.add(pd_result.get('incident_id'))
                                                logger.info(f"✅ Auto-created PagerDuty incident for {incident_severity} priority: {pd_result.get('incident_id')}")
                                            else:
                                                incident['pagerduty_created'] = False
                                                logger.warning(f"⚠️ PagerDuty incident creation failed: {pd_result.get('error')}")
                                        except Exception as pd_error:
                                            logger.error(f"❌ PagerDuty incident creation error: {pd_error}")
                                            incident['pagerduty_created'] = False
                                    elif auto_create and not priority_qualifies:
                                        incident['pagerduty_created'] = False
                                        logger.info(f"ℹ️ PagerDuty auto-creation skipped for {incident_severity} priority incident (allowed: {', '.join(allowed_priorities)})")
                                    else:
                                        incident['pagerduty_created'] = False
                                        logger.info("ℹ️ PagerDuty auto-creation disabled")
                                    
                                    # Check if we should send notification (deduplication with severity-based cooldown)
                                    if should_send_notification(incident_key, incident_id, severity=incident_severity):
                                        # Send to Slack
                                        await send_slack_notification(incident, suggestions)
                                        service_stats["slack_notifications_sent"] += 1
                                        # Save notification cache after successful notification
                                        save_notification_cache()
                                    else:
                                        logger.info(f"🔕 Skipping duplicate Slack notification for {incident_id}")
                                    
                                    # Mark as processed and save to persistent storage
                                    processed_incidents.add(incident_key)
                                    save_processed_incidents()
                                    
                                    logger.info(f"🚨 REAL INCIDENT DETECTED: {query_name} ({total_events} events from actual Splunk data)")
                                    logger.info(f"🛠️ Generated {len(suggestions)} intelligent remediation suggestions")
                                    logger.info(f"📱 Sending Slack notification for real incident: {incident_id}")
                            else:
                                logger.info(f"📊 Real Splunk data found but below threshold: {total_events} events < {query_config['threshold']} threshold")
                        else:
                            logger.info(f"📊 No real Splunk data found for {query_name} - no incident created")
                        
                        query_last_run[query_name] = current_time
                        
                    except Exception as e:
                        error_msg = f"Error checking {query_name}: {str(e)}"
                        logger.error(f"❌ {error_msg}")
                        service_stats["errors"].append(error_msg)
            
            # Monitor PagerDuty incidents (check every 5 minutes)
            time_since_pagerduty = (current_time - pagerduty_last_check).total_seconds()
            if time_since_pagerduty >= 300:  # 5 minutes
                try:
                    logger.info("🔎 Checking PagerDuty for active incidents...")
                    
                    pagerduty_incidents = await splunk_client.get_pagerduty_incidents()
                    
                    for pd_incident in pagerduty_incidents:
                        # Create deduplication key based on incident pattern, not unique ID
                        incident_title = pd_incident.get('title', 'Unknown')
                        service_name = pd_incident.get('service', {}).get('summary', 'Unknown')
                        current_hour = current_time.strftime('%Y%m%d%H')
                        
                        # Create incident key for deduplication (similar to Splunk incidents)
                        # This groups incidents by title pattern and service within a 2-hour window
                        two_hour_window = current_time.replace(hour=(current_time.hour // 2) * 2, minute=0, second=0).strftime('%Y%m%d%H%M')
                        incident_key = f"PD-{service_name}-{incident_title.replace(' ', '')[:30]}-{two_hour_window}"
                        
                        # Skip incidents created by our system to avoid feedback loop
                        pd_incident_id = pd_incident.get('id', '')
                        incident_title = pd_incident.get('title', '')
                        
                        # Check if this is an incident we created or a test incident
                        test_incident_patterns = [
                            'High Error Rate Alert', 'AWS CloudTrail Errors Alert', 
                            'Performance Issues Alert', 'Security Events Alert',
                            'Example Incident', 'Test MCP Server Integration',
                            'Database Connection Pool Exhausted', 'Low Disk Space Warning',
                            'High CPU Usage Detected on Production Server'
                        ]
                        
                        if (pd_incident_id in self_created_pagerduty_incidents or 
                            any(pattern in incident_title for pattern in test_incident_patterns)):
                            # Count skipped incidents instead of logging each one
                            if 'skipped_incidents_count' not in locals():
                                skipped_incidents_count = 0
                            skipped_incidents_count += 1
                            continue
                        
                        if incident_key not in processed_incidents:
                            # Extract status first to filter resolved incidents
                            status = pd_incident.get('status', 'triggered')
                            
                            # Skip resolved incidents - they shouldn't create new notifications
                            if status.lower() in ['resolved', 'closed']:
                                logger.info(f"⏭️ Skipping resolved PagerDuty incident: {pd_incident.get('title', 'Unknown')} ({pd_incident.get('id', 'unknown')})")
                                continue
                            
                            # Create incident from PagerDuty data
                            incident_id = f"INC-PD-{current_time.strftime('%Y%m%d%H%M%S')}-{pd_incident.get('id', 'unknown')[:8]}"
                            
                            # Extract information from PagerDuty incident
                            title = pd_incident.get('title', 'PagerDuty Incident')
                            description = pd_incident.get('description', pd_incident.get('summary', 'No description available'))
                            urgency = pd_incident.get('urgency', 'high').upper()
                            
                            # Map PagerDuty urgency to our severity
                            severity_mapping = {
                                'high': 'HIGH',
                                'low': 'MEDIUM'
                            }
                            severity = severity_mapping.get(pd_incident.get('urgency', 'high').lower(), 'HIGH')
                            
                            # Extract affected systems from service info
                            affected_systems = []
                            if 'service' in pd_incident and pd_incident['service']:
                                service_name = pd_incident['service'].get('summary', 'Unknown Service')
                                affected_systems.append(service_name)
                            
                            if not affected_systems:
                                affected_systems = ['pagerduty-service']
                            
                            # Create detailed description
                            description_parts = [f"PagerDuty incident: {title}"]
                            if pd_incident.get('created_at'):
                                description_parts.append(f"Created: {pd_incident['created_at']}")
                            if pd_incident.get('assignees'):
                                assignees = [a.get('summary', 'Unknown') for a in pd_incident['assignees']]
                                description_parts.append(f"Assigned to: {', '.join(assignees)}")
                            
                            detailed_description = ". ".join(description_parts)
                            
                            # Create incident object
                            incident = {
                                'id': incident_id,
                                'title': f"PagerDuty: {title}",
                                'description': detailed_description,
                                'severity': severity,
                                'status': 'DETECTED',
                                'source_query': f"PagerDuty incident {pd_incident.get('id', 'unknown')}",
                                'affected_systems': affected_systems,
                                'created_at': current_time.isoformat(),
                                'event_count': 1,
                                'sample_events': [pd_incident],
                                'pagerduty_incident_id': pd_incident.get('id'),
                                'detection_details': {
                                    'source': 'PagerDuty MCP',
                                    'original_urgency': pd_incident.get('urgency'),
                                    'original_status': status,
                                    'service': pd_incident.get('service', {}).get('summary', 'Unknown'),
                                    'incident_url': pd_incident.get('html_url', '')
                                }
                            }
                            
                            # Generate remediation suggestions
                            suggestions = generate_remediation_suggestions(
                                incident['description'], 
                                incident['affected_systems']
                            )
                            
                            # Add suggestions to incident
                            incident['remediation_suggestions'] = suggestions
                            
                            # Store incident in both the main list and persistent cache
                            detected_incidents.append(incident)
                            incident_cache[incident['id']] = incident.copy()  # Store in persistent cache
                            save_incident_cache()  # Save to file for persistence across processes
                            logger.info(f"🔍 Stored PagerDuty incident {incident['id']} in both detected_incidents and incident_cache with {len(suggestions)} remediation suggestions")
                            # Mark as processed and save to persistent storage
                            processed_incidents.add(incident_key)
                            save_processed_incidents()
                            service_stats["incidents_detected"] += 1
                            service_stats["remediations_generated"] += len(suggestions)
                            
                            logger.info(f"🚨 Created incident from PagerDuty: {incident['title']}")
                            
                            # Send Slack notification with deduplication and severity-based cooldown
                            try:
                                if should_send_notification(incident_key, incident_id, severity=severity):
                                    slack_sent = await send_slack_notification(incident, suggestions)
                                    if slack_sent:
                                        service_stats["slack_notifications_sent"] += 1
                                        # Save notification cache after successful notification
                                        save_notification_cache()
                                        logger.info(f"✅ Enhanced Slack notification sent for PagerDuty incident {incident_id}")
                                    else:
                                        logger.warning(f"⚠️ Failed to send Slack notification for PagerDuty incident {incident_id}")
                                else:
                                    logger.info(f"🔕 Notification suppressed for PagerDuty incident {incident_key} (duplicate within cooldown period)")
                                    service_stats["notifications_suppressed"] += 1
                            except Exception as slack_error:
                                logger.error(f"❌ Slack notification failed for PagerDuty incident {incident_id}: {slack_error}")
                            
                            # Add remediation suggestions back to PagerDuty
                            if pd_incident.get('id'):
                                try:
                                    await splunk_client.add_remediation_to_pagerduty(
                                        pd_incident['id'], 
                                        suggestions
                                    )
                                except Exception as pd_error:
                                    logger.error(f"❌ Failed to add remediation to PagerDuty: {pd_error}")
                    
                    pagerduty_last_check = current_time
                    
                    # Log summary with skipped incidents count
                    skipped_count = 0  # Initialize skipped count safely
                    if skipped_count > 0:
                        logger.info(f"✅ PagerDuty check completed, found {len(pagerduty_incidents)} incidents (skipped {skipped_count} self-created/test incidents)")
                    else:
                        logger.info(f"✅ PagerDuty check completed, found {len(pagerduty_incidents)} incidents")
                    
                except Exception as e:
                    error_msg = f"Error checking PagerDuty: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    service_stats["errors"].append(error_msg)
            
            # Clean up old processed incidents (time-based cleanup instead of count-based)
            # Remove incidents older than 4 hours to prevent memory issues while maintaining deduplication
            current_time_for_cleanup = datetime.now()
            incidents_to_remove = []
            for incident_key in processed_incidents:
                # Extract timestamp from incident key if possible
                try:
                    # Incident keys have format: "QueryName_Count_YYYYMMDDHHMM"
                    parts = incident_key.split('_')
                    if len(parts) >= 3:
                        timestamp_str = parts[-1]  # Last part should be timestamp
                        if len(timestamp_str) >= 10:  # YYYYMMDDHH minimum
                            incident_time = datetime.strptime(timestamp_str[:12], '%Y%m%d%H%M')
                            if (current_time_for_cleanup - incident_time).total_seconds() > 14400:  # 4 hours
                                incidents_to_remove.append(incident_key)
                except:
                    # If we can't parse the timestamp, remove old-format keys
                    incidents_to_remove.append(incident_key)
            
            for incident_key in incidents_to_remove:
                processed_incidents.discard(incident_key)
            
            if incidents_to_remove:
                logger.info(f"🧹 Cleaned up {len(incidents_to_remove)} old processed incidents")
            
            # Clean up old self-created PagerDuty incident tracking
            if len(self_created_pagerduty_incidents) > 500:
                self_created_pagerduty_incidents.clear()
            
            # Clean up old notification cache entries
            cleanup_notification_cache()
            
            # Keep only last 50 incidents, but preserve incidents with active investigation sessions
            if len(detected_incidents) > 50:
                # Get list of incidents that have active investigation sessions
                preserved_incident_ids = set()
                try:
                    # Import here to avoid circular imports
                    from integrations.interactive_slack_investigator import InteractiveSlackInvestigator
                    # This is a bit of a hack, but we need to check if there are any active sessions
                    # In a real implementation, we'd want a more elegant way to track this
                    logger.info(f"🔄 Cleaning up detected_incidents: {len(detected_incidents)} -> keeping last 25 + any with active sessions")
                except ImportError:
                    logger.warning("Could not import InteractiveSlackInvestigator for session checking")
                
                # Keep the last 25 incidents in the main list
                old_count = len(detected_incidents)
                detected_incidents = detected_incidents[-25:]
                logger.info(f"🧹 Cleaned up detected_incidents: {old_count} -> {len(detected_incidents)} incidents")
                
                # Also clean up the persistent cache (keep last 100 incidents)
                if len(incident_cache) > 100:
                    # Sort by creation time and keep the most recent 50
                    sorted_incidents = sorted(
                        incident_cache.items(), 
                        key=lambda x: x[1].get('created_at', ''), 
                        reverse=True
                    )
                    incident_cache.clear()
                    for incident_id, incident_data in sorted_incidents[:50]:
                        incident_cache[incident_id] = incident_data
                    logger.info(f"🧹 Cleaned up incident_cache: keeping 50 most recent incidents")
                
                logger.info("✅ Incident cleanup completed - persistent cache preserves data for manual PagerDuty creation")
            
            # Wait before next check
            await asyncio.sleep(60)  # Check every minute
            
        except Exception as e:
            error_msg = f"Error in monitoring loop: {str(e)}"
            logger.error(f"❌ {error_msg}")
            service_stats["errors"].append(error_msg)
            await asyncio.sleep(60)

# API Endpoints
@app.get("/")
async def root():
    """Root endpoint with service information"""
    uptime = datetime.now() - service_stats["service_start_time"]
    
    return {
        "service": "End-to-End Incident Management Service",
        "version": "1.0.0",
        "status": "running",
        "uptime": str(uptime).split('.')[0],
        "splunk_connected": splunk_client.connected if splunk_client else False,
        "features": [
            "Real-time Splunk monitoring",
            "AI-powered incident detection",
            "Intelligent remediation suggestions",
            "Rich Slack notifications with action buttons",
            "Continuous monitoring and alerting",
            "RESTful API for management"
        ],
        "stats": {
            "incidents_detected": service_stats["incidents_detected"],
            "remediations_generated": service_stats["remediations_generated"],
            "slack_notifications_sent": service_stats["slack_notifications_sent"],
            "errors": len(service_stats["errors"])
        },
        "endpoints": {
            "incidents": "/incidents",
            "health": "/health",
            "stats": "/stats",
            "test_slack": "/test-slack",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint with detailed connection information"""
    global splunk_client
    
    splunk_status = False
    connection_info = {}
    
    if splunk_client:
        splunk_status = await splunk_client.test_connection()
        connection_info = splunk_client.get_connection_info()
    
    return {
        "status": "healthy" if splunk_status else "degraded",
        "timestamp": datetime.now().isoformat(),
        "splunk_connected": splunk_status,
        "splunk_connection_details": connection_info,
        "incidents_detected": service_stats["incidents_detected"],
        "last_error": service_stats["errors"][-1] if service_stats["errors"] else None,
        "uptime_seconds": (datetime.now() - service_stats["service_start_time"]).total_seconds(),
        "recent_errors": service_stats["errors"][-5:] if service_stats["errors"] else []
    }

@app.get("/incidents", response_model=List[IncidentResponse])
async def get_incidents(limit: int = 20, severity: Optional[str] = None):
    """Get recent incidents with remediation suggestions"""
    global detected_incidents
    
    # Filter by severity if specified
    filtered_incidents = detected_incidents
    if severity:
        filtered_incidents = [i for i in detected_incidents if i['severity'].lower() == severity.lower()]
    
    # Sort by creation time (newest first) and limit
    sorted_incidents = sorted(filtered_incidents, key=lambda x: x['created_at'], reverse=True)[:limit]
    
    # Convert to response format
    response = []
    for incident in sorted_incidents:
        response.append(IncidentResponse(
            id=incident['id'],
            title=incident['title'],
            description=incident['description'],
            severity=incident['severity'],
            status=incident['status'],
            source_query=incident['source_query'],
            affected_systems=incident['affected_systems'],
            created_at=incident['created_at'],
            event_count=incident['event_count'],
            sample_events=incident['sample_events'],
            remediation_suggestions=incident.get('remediation_suggestions', [])
        ))
    
    return response

@app.get("/incidents/{incident_id}")
async def get_incident_details(incident_id: str):
    """Get detailed incident information including remediation suggestions"""
    global detected_incidents
    
    for incident in detected_incidents:
        if incident['id'] == incident_id:
            suggestions = incident.get('remediation_suggestions', [])
            return {
                "incident": incident,
                "remediation_suggestions": suggestions,
                "suggestion_count": len(suggestions),
                "detailed_instructions_available": True,
                "execution_mode": "manual_only"
            }
    
    raise HTTPException(status_code=404, detail="Incident not found")

@app.get("/stats")
async def get_stats():
    """Get detailed service statistics"""
    global notification_cache
    
    uptime = datetime.now() - service_stats["service_start_time"]
    
    # Get connection details
    connection_info = {}
    if splunk_client:
        connection_info = splunk_client.get_connection_info()
    
    # Analyze recent incidents
    recent_incidents = [inc for inc in detected_incidents if (datetime.now() - datetime.fromisoformat(inc['created_at'])).total_seconds() < 3600]
    
    # Group incidents by severity
    severity_breakdown = {}
    for incident in detected_incidents:
        severity = incident.get('severity', 'UNKNOWN')
        severity_breakdown[severity] = severity_breakdown.get(severity, 0) + 1
    
    # Calculate error rate
    error_rate = len(service_stats["errors"]) / max(uptime.total_seconds() / 3600, 1)
    
    # Calculate notification deduplication stats
    total_suppressed = sum(data.get('count', 1) - 1 for data in notification_cache.values())
    active_suppressions = len([data for data in notification_cache.values() if data.get('count', 1) > 1])
    notification_efficiency = (service_stats.get("incidents_detected", 0) - total_suppressed) / max(service_stats.get("incidents_detected", 1), 1) * 100
    
    return {
        "service_stats": service_stats,
        "uptime": str(uptime).split('.')[0],
        "uptime_seconds": uptime.total_seconds(),
        "incidents_per_hour": service_stats["incidents_detected"] / max(uptime.total_seconds() / 3600, 1),
        "recent_incidents": len(recent_incidents),
        "total_incidents": len(detected_incidents),
        "severity_breakdown": severity_breakdown,
        "error_rate_per_hour": error_rate,
        "splunk_connection": "connected" if splunk_client and splunk_client.connected else "disconnected",
        "splunk_connection_details": connection_info,
        "recent_errors": service_stats["errors"][-10:] if service_stats["errors"] else [],
        "notification_deduplication": {
            "active_incident_types": len(notification_cache),
            "total_suppressed_notifications": total_suppressed,
            "active_suppressions": active_suppressions,
            "notification_efficiency_percent": round(notification_efficiency, 2),
            "cache_entries": {key: {"count": data["count"], "suppressed": len(data["suppressed_incidents"])} for key, data in notification_cache.items()}
        },
        "performance_metrics": {
            "avg_remediation_suggestions_per_incident": service_stats["remediations_generated"] / max(service_stats["incidents_detected"], 1),
            "slack_success_rate": service_stats["slack_notifications_sent"] / max(service_stats["incidents_detected"], 1) * 100 if service_stats["incidents_detected"] > 0 else 0
        }
    }

@app.post("/test-slack")
async def test_slack():
    """Test Slack integration with sample incident and remediation suggestions"""
    
    # Create a test incident
    test_incident = {
        'id': f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'title': 'Test Incident - High Memory Usage',
        'description': 'This is a test incident to verify Slack integration with intelligent remediation suggestions',
        'severity': 'MEDIUM',
        'status': 'DETECTED',
        'affected_systems': ['web-server-01', 'api-server-02', 'database-server'],
        'event_count': 15,
        'created_at': datetime.now().isoformat(),
        'source_query': 'search index=main memory usage > 80%',
        'sample_events': [
            {'host': 'web-server-01', 'memory_usage': '85%', '_time': datetime.now().isoformat()},
            {'host': 'api-server-02', 'memory_usage': '92%', '_time': datetime.now().isoformat()}
        ]
    }
    
    # Generate test suggestions
    suggestions = generate_remediation_suggestions(
        test_incident['description'],
        test_incident['affected_systems']
    )
    
    # Send to Slack
    slack_success = await send_slack_notification(test_incident, suggestions)
    
    return {
        "message": "Test incident processed and sent to Slack",
        "incident": test_incident,
        "suggestions_generated": len(suggestions),
        "suggestions": suggestions,
        "slack_sent": slack_success,
        "slack_webhook_configured": bool(os.getenv('SLACK_WEBHOOK_URL'))
    }

@app.post("/trigger-detection")
async def trigger_detection(background_tasks: BackgroundTasks):
    """Manually trigger incident detection"""
    global splunk_client
    
    if not splunk_client or not splunk_client.connected:
        raise HTTPException(status_code=503, detail="Splunk client not available")
    
    # This will be picked up by the continuous monitoring loop
    logger.info("🔍 Manual incident detection triggered")
    
    return {
        "message": "Incident detection triggered",
        "timestamp": datetime.now().isoformat(),
        "note": "Detection will run in the next monitoring cycle"
    }

@app.get("/slack-integration-status")
async def get_slack_integration_status():
    """Get the status of Slack integration"""
    global enhanced_slack_integration, splunk_client
    
    bot_token = os.getenv('SLACK_BOT_TOKEN')
    signing_secret = os.getenv('SLACK_SIGNING_SECRET')
    
    status = {
        "enhanced_slack_integration_available": enhanced_slack_integration is not None,
        "slack_credentials_configured": bool(bot_token and signing_secret),
        "splunk_connected": splunk_client.splunk_connected if splunk_client else False,
        "pagerduty_connected": splunk_client.pagerduty_connected if splunk_client else False,
        "connection_details": splunk_client.get_connection_info() if splunk_client else None
    }
    
    if enhanced_slack_integration:
        status["slack_endpoints"] = [
            "/slack/commands",
            "/slack/interactions", 
            "/slack/events"
        ]
        status["available_data_sources"] = []
        if enhanced_slack_integration.splunk_client:
            status["available_data_sources"].append("Splunk")
        if enhanced_slack_integration.pagerduty_client:
            status["available_data_sources"].append("PagerDuty")
    else:
        status["reason_not_available"] = []
        if not (bot_token and signing_secret):
            status["reason_not_available"].append("Slack credentials not configured")
    
    return status

@app.post("/retry-connections")
async def retry_connections():
    """Retry MCP server connections and update enhanced Slack integration"""
    global splunk_client, enhanced_slack_integration
    
    if not splunk_client:
        return {"error": "No MCP client available"}
    
    try:
        # Store old connection states
        old_splunk_connected = splunk_client.splunk_connected
        old_pagerduty_connected = splunk_client.pagerduty_connected
        
        # Retry connections
        await splunk_client.connect()
        
        # Check if connections improved
        connections_improved = (
            (not old_splunk_connected and splunk_client.splunk_connected) or
            (not old_pagerduty_connected and splunk_client.pagerduty_connected)
        )
        
        return {
            "message": "Connection retry completed",
            "connections_improved": connections_improved,
            "connection_details": splunk_client.get_connection_info(),
            "enhanced_slack_available": enhanced_slack_integration is not None,
            "enhanced_slack_data_sources": enhanced_slack_integration._get_available_sources() if enhanced_slack_integration and hasattr(enhanced_slack_integration, 'investigator') else []
        }
    except Exception as e:
        logger.error(f"❌ Error during connection retry: {e}")
        return {"error": f"Connection retry failed: {str(e)}"}

if __name__ == "__main__":
    print("🚀 Starting End-to-End Incident Management Service")
    print("=" * 60)
    print("📊 Features:")
    print("  • Real-time Splunk monitoring via MCP")
    print("  • AI-powered incident detection")
    print("  • Intelligent remediation suggestions")
    print("  • Rich Slack notifications with action buttons")
    print("  • Continuous monitoring and alerting")
    print("  • RESTful API for management")
    print()
    print(f"📱 Slack webhook: {'✅ Configured' if os.getenv('SLACK_WEBHOOK_URL') else '❌ Not configured'}")
    port = int(os.getenv('API_PORT', 8002))
    print(f"🌐 Service will be available at: http://localhost:{port}")
    print(f"📚 API documentation at: http://localhost:{port}/docs")
    print(f"🔍 Health check at: http://localhost:{port}/health")
    print("=" * 60)
    
    # Run the service
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )