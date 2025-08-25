"""
Core incident data model and related types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import uuid


class IncidentSeverity(Enum):
    """Incident severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(Enum):
    """Incident lifecycle status"""
    DETECTED = "detected"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class Incident:
    """
    Core incident data model representing a detected issue requiring attention.
    
    This model captures all essential information about an incident throughout
    its lifecycle, from detection to resolution.
    """
    id: str
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    source_query: str
    affected_systems: List[str]
    assigned_team: Optional[str] = None
    assigned_user: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.id:
            self.id = self.generate_incident_id()
        
        # Ensure timestamps are set
        if not self.created_at:
            self.created_at = datetime.utcnow()
        if not self.updated_at:
            self.updated_at = datetime.utcnow()
    
    @staticmethod
    def generate_incident_id() -> str:
        """Generate a unique incident ID"""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        unique_suffix = str(uuid.uuid4())[:8]
        return f"INC-{timestamp}-{unique_suffix.upper()}"
    
    def update_status(self, new_status: IncidentStatus) -> None:
        """Update incident status with timestamp"""
        self.status = new_status
        self.updated_at = datetime.utcnow()
        
        if new_status == IncidentStatus.RESOLVED:
            self.resolved_at = datetime.utcnow()
    
    def assign_to_team(self, team: str, user: Optional[str] = None) -> None:
        """Assign incident to a team and optionally a specific user"""
        self.assigned_team = team
        self.assigned_user = user
        self.status = IncidentStatus.ASSIGNED
        self.updated_at = datetime.utcnow()
    
    def add_tag(self, tag: str) -> None:
        """Add a tag to the incident"""
        if tag not in self.tags:
            self.tags.append(tag)
            self.updated_at = datetime.utcnow()
    
    def remove_tag(self, tag: str) -> None:
        """Remove a tag from the incident"""
        if tag in self.tags:
            self.tags.remove(tag)
            self.updated_at = datetime.utcnow()
    
    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata key-value pair"""
        self.metadata[key] = value
        self.updated_at = datetime.utcnow()
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata value by key"""
        return self.metadata.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert incident to dictionary representation"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'severity': self.severity.value,
            'status': self.status.value,
            'source_query': self.source_query,
            'affected_systems': self.affected_systems,
            'assigned_team': self.assigned_team,
            'assigned_user': self.assigned_user,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'tags': self.tags,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Incident':
        """Create incident from dictionary representation"""
        # Convert string enums back to enum objects
        severity = IncidentSeverity(data['severity'])
        status = IncidentStatus(data['status'])
        
        # Convert ISO strings back to datetime objects
        created_at = datetime.fromisoformat(data['created_at']) if data.get('created_at') else None
        updated_at = datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None
        resolved_at = datetime.fromisoformat(data['resolved_at']) if data.get('resolved_at') else None
        
        return cls(
            id=data['id'],
            title=data['title'],
            description=data['description'],
            severity=severity,
            status=status,
            source_query=data['source_query'],
            affected_systems=data['affected_systems'],
            assigned_team=data.get('assigned_team'),
            assigned_user=data.get('assigned_user'),
            created_at=created_at,
            updated_at=updated_at,
            resolved_at=resolved_at,
            tags=data.get('tags', []),
            metadata=data.get('metadata', {})
        )
    
    def __str__(self) -> str:
        """String representation of incident"""
        return f"Incident({self.id}, {self.severity.value}, {self.status.value}): {self.title}"
    
    def __repr__(self) -> str:
        """Detailed string representation"""
        return (f"Incident(id='{self.id}', title='{self.title}', "
                f"severity={self.severity}, status={self.status})")