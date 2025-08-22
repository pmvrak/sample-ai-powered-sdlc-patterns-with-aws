"""
Base interfaces and abstract classes for extensibility.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timedelta

from ..models.incident import Incident, IncidentStatus
from ..models.analysis import AnalysisResult, IncidentCorrelation
from ..models.remediation import RemediationTask, ExecutionResult
from ..models.audit import AuditEvent


class BaseIncidentManager(ABC):
    """
    Abstract base class for incident management engines.
    
    Defines the core interface that all incident managers must implement.
    """
    
    @abstractmethod
    async def detect_incidents(self) -> List[Incident]:
        """Detect new incidents from monitoring data"""
        pass
    
    @abstractmethod
    async def create_incident(self, data: Dict[str, Any]) -> Incident:
        """Create a new incident"""
        pass
    
    @abstractmethod
    async def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Retrieve incident by ID"""
        pass
    
    @abstractmethod
    async def update_incident(self, incident_id: str, updates: Dict[str, Any]) -> bool:
        """Update incident with new information"""
        pass
    
    @abstractmethod
    async def assign_incident(self, incident_id: str, team: str, user: Optional[str] = None) -> bool:
        """Assign incident to team/user"""
        pass
    
    @abstractmethod
    async def resolve_incident(self, incident_id: str, resolution: str, resolved_by: str) -> bool:
        """Mark incident as resolved"""
        pass
    
    @abstractmethod
    async def get_active_incidents(self, filters: Optional[Dict[str, Any]] = None) -> List[Incident]:
        """Get all active incidents with optional filters"""
        pass
    
    @abstractmethod
    async def search_incidents(self, query: str, limit: int = 50) -> List[Incident]:
        """Search incidents by query"""
        pass


class BaseAnalyzer(ABC):
    """
    Abstract base class for AI-powered incident analyzers.
    """
    
    @abstractmethod
    async def analyze_incident(self, incident: Incident) -> AnalysisResult:
        """Analyze incident and provide insights"""
        pass
    
    @abstractmethod
    async def suggest_remediation(self, incident: Incident) -> List[RemediationTask]:
        """Suggest remediation tasks for incident"""
        pass
    
    @abstractmethod
    async def correlate_incidents(self, incidents: List[Incident]) -> List[IncidentCorrelation]:
        """Find correlations between incidents"""
        pass
    
    @abstractmethod
    async def learn_from_resolution(self, incident: Incident, resolution_data: Dict[str, Any]) -> None:
        """Learn from incident resolution for future improvements"""
        pass
    
    @abstractmethod
    async def get_similar_incidents(self, incident: Incident, limit: int = 10) -> List[Incident]:
        """Find similar historical incidents"""
        pass


class BaseRouter(ABC):
    """
    Abstract base class for incident routing engines.
    """
    
    @abstractmethod
    async def route_incident(self, incident: Incident) -> Dict[str, Any]:
        """Route incident to appropriate team"""
        pass
    
    @abstractmethod
    async def escalate_incident(self, incident: Incident, reason: str) -> bool:
        """Escalate incident to next level"""
        pass
    
    @abstractmethod
    async def get_team_capacity(self, team: str) -> Dict[str, Any]:
        """Get current team capacity information"""
        pass
    
    @abstractmethod
    async def update_routing_rules(self, rules: Dict[str, Any]) -> bool:
        """Update routing configuration"""
        pass
    
    @abstractmethod
    async def get_available_teams(self, incident_type: str) -> List[str]:
        """Get teams available for incident type"""
        pass


class BaseAutomationEngine(ABC):
    """
    Abstract base class for automation engines.
    """
    
    @abstractmethod
    async def execute_task(self, task: RemediationTask) -> ExecutionResult:
        """Execute a remediation task"""
        pass
    
    @abstractmethod
    async def validate_task(self, task: RemediationTask) -> Dict[str, Any]:
        """Validate task before execution"""
        pass
    
    @abstractmethod
    async def get_available_tasks(self, incident_type: str) -> List[RemediationTask]:
        """Get available tasks for incident type"""
        pass
    
    @abstractmethod
    async def schedule_task(self, task: RemediationTask, schedule_time: datetime) -> bool:
        """Schedule task for future execution"""
        pass
    
    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled or running task"""
        pass
    
    @abstractmethod
    async def get_task_status(self, task_id: str) -> Optional[ExecutionResult]:
        """Get status of a task execution"""
        pass


class BaseAuditLogger(ABC):
    """
    Abstract base class for audit logging systems.
    """
    
    @abstractmethod
    async def log_event(self, event: AuditEvent) -> None:
        """Log an audit event"""
        pass
    
    @abstractmethod
    async def get_events(self, filters: Dict[str, Any], limit: int = 100) -> List[AuditEvent]:
        """Retrieve audit events with filters"""
        pass
    
    @abstractmethod
    async def generate_report(self, start_time: datetime, end_time: datetime, 
                            filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate audit report for time period"""
        pass
    
    @abstractmethod
    async def export_events(self, filters: Dict[str, Any], format: str = "json") -> bytes:
        """Export audit events in specified format"""
        pass


class BaseNotificationManager(ABC):
    """
    Abstract base class for notification managers.
    """
    
    @abstractmethod
    async def send_notification(self, incident: Incident, channels: List[str], 
                              message_type: str = "incident_created") -> bool:
        """Send notification about incident"""
        pass
    
    @abstractmethod
    async def send_custom_message(self, channel: str, message: str, 
                                metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Send custom message to channel"""
        pass
    
    @abstractmethod
    async def handle_user_response(self, user_id: str, channel: str, 
                                 response: str) -> Dict[str, Any]:
        """Handle user response from notification"""
        pass
    
    @abstractmethod
    async def get_available_channels(self) -> List[str]:
        """Get list of available notification channels"""
        pass


class BaseStorage(ABC):
    """
    Abstract base class for data storage backends.
    """
    
    @abstractmethod
    async def store_incident(self, incident: Incident) -> bool:
        """Store incident in persistent storage"""
        pass
    
    @abstractmethod
    async def retrieve_incident(self, incident_id: str) -> Optional[Incident]:
        """Retrieve incident from storage"""
        pass
    
    @abstractmethod
    async def update_incident(self, incident: Incident) -> bool:
        """Update incident in storage"""
        pass
    
    @abstractmethod
    async def delete_incident(self, incident_id: str) -> bool:
        """Delete incident from storage"""
        pass
    
    @abstractmethod
    async def query_incidents(self, filters: Dict[str, Any], 
                            limit: int = 100) -> List[Incident]:
        """Query incidents with filters"""
        pass
    
    @abstractmethod
    async def store_audit_event(self, event: AuditEvent) -> bool:
        """Store audit event"""
        pass
    
    @abstractmethod
    async def query_audit_events(self, filters: Dict[str, Any], 
                               limit: int = 100) -> List[AuditEvent]:
        """Query audit events"""
        pass


class BaseConfigManager(ABC):
    """
    Abstract base class for configuration management.
    """
    
    @abstractmethod
    async def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        pass
    
    @abstractmethod
    async def set_config(self, key: str, value: Any) -> bool:
        """Set configuration value"""
        pass
    
    @abstractmethod
    async def get_detection_rules(self) -> Dict[str, Any]:
        """Get incident detection rules"""
        pass
    
    @abstractmethod
    async def update_detection_rules(self, rules: Dict[str, Any]) -> bool:
        """Update detection rules"""
        pass
    
    @abstractmethod
    async def get_routing_config(self) -> Dict[str, Any]:
        """Get routing configuration"""
        pass
    
    @abstractmethod
    async def update_routing_config(self, config: Dict[str, Any]) -> bool:
        """Update routing configuration"""
        pass


class BaseHealthChecker(ABC):
    """
    Abstract base class for system health checking.
    """
    
    @abstractmethod
    async def check_system_health(self) -> Dict[str, Any]:
        """Check overall system health"""
        pass
    
    @abstractmethod
    async def check_component_health(self, component: str) -> Dict[str, Any]:
        """Check specific component health"""
        pass
    
    @abstractmethod
    async def get_health_metrics(self) -> Dict[str, Any]:
        """Get system health metrics"""
        pass
    
    @abstractmethod
    async def register_health_check(self, name: str, check_func: callable) -> bool:
        """Register custom health check"""
        pass