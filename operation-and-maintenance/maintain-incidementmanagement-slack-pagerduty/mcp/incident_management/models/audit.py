"""
Audit and compliance data models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
import uuid


class AuditEventType(Enum):
    """Types of audit events"""
    INCIDENT_CREATED = "incident_created"
    INCIDENT_UPDATED = "incident_updated"
    INCIDENT_ASSIGNED = "incident_assigned"
    INCIDENT_RESOLVED = "incident_resolved"
    INCIDENT_CLOSED = "incident_closed"
    TASK_CREATED = "task_created"
    TASK_EXECUTED = "task_executed"
    TASK_APPROVED = "task_approved"
    TASK_FAILED = "task_failed"
    USER_ACTION = "user_action"
    SYSTEM_ACTION = "system_action"
    CONFIGURATION_CHANGED = "configuration_changed"
    SECURITY_EVENT = "security_event"
    AUTOMATION_STARTED = "automation_started"
    AUTOMATION_COMPLETED = "automation_completed"
    AUTOMATION_FAILED = "automation_failed"
    SAFETY_CHECK_COMPLETED = "safety_check_completed"
    ROLLBACK_STARTED = "rollback_started"
    ROLLBACK_COMPLETED = "rollback_completed"
    ROLLBACK_FAILED = "rollback_failed"
    ROLLBACK_MANUAL_REQUIRED = "rollback_manual_required"
    TASK_APPROVAL_REQUESTED = "task_approval_requested"
    TASK_REJECTED = "task_rejected"
    TASK_CANCELLED = "task_cancelled"
    TASK_EXPIRED = "task_expired"


@dataclass
class AuditEvent:
    """
    Represents an audit event for compliance and tracking purposes.
    """
    id: str
    event_type: AuditEventType
    timestamp: datetime
    user_id: Optional[str]
    incident_id: Optional[str]
    task_id: Optional[str]
    action: str
    details: Dict[str, Any]
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.id:
            self.id = self.generate_event_id()
        
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
    
    @staticmethod
    def generate_event_id() -> str:
        """Generate a unique audit event ID"""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        unique_suffix = str(uuid.uuid4())[:8]
        return f"AUDIT-{timestamp}-{unique_suffix.upper()}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert audit event to dictionary"""
        return {
            'id': self.id,
            'event_type': self.event_type.value,
            'timestamp': self.timestamp.isoformat(),
            'user_id': self.user_id,
            'incident_id': self.incident_id,
            'task_id': self.task_id,
            'action': self.action,
            'details': self.details,
            'source_ip': self.source_ip,
            'user_agent': self.user_agent,
            'session_id': self.session_id,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuditEvent':
        """Create audit event from dictionary"""
        event_type = AuditEventType(data['event_type'])
        timestamp = datetime.fromisoformat(data['timestamp'])
        
        return cls(
            id=data['id'],
            event_type=event_type,
            timestamp=timestamp,
            user_id=data.get('user_id'),
            incident_id=data.get('incident_id'),
            task_id=data.get('task_id'),
            action=data['action'],
            details=data['details'],
            source_ip=data.get('source_ip'),
            user_agent=data.get('user_agent'),
            session_id=data.get('session_id'),
            metadata=data.get('metadata', {})
        )
    
    def __str__(self) -> str:
        """String representation of audit event"""
        return f"AuditEvent({self.event_type.value}, {self.action}, {self.timestamp})"