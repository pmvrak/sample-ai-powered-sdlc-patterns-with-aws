"""
Remediation task data models and execution results.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid


class TaskType(Enum):
    """Types of remediation tasks"""
    RESTART_SERVICE = "restart_service"
    SCALE_RESOURCE = "scale_resource"
    UPDATE_CONFIG = "update_config"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    COLLECT_LOGS = "collect_logs"
    RUN_HEALTH_CHECK = "run_health_check"
    EXECUTE_SCRIPT = "execute_script"
    NOTIFY_TEAM = "notify_team"
    CREATE_TICKET = "create_ticket"
    CUSTOM = "custom"


class TaskStatus(Enum):
    """Remediation task execution status"""
    PENDING = "pending"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REQUIRES_APPROVAL = "requires_approval"


class SafetyCheckType(Enum):
    """Types of safety checks for remediation tasks"""
    RESOURCE_AVAILABILITY = "resource_availability"
    DEPENDENCY_CHECK = "dependency_check"
    BACKUP_VERIFICATION = "backup_verification"
    PERMISSION_CHECK = "permission_check"
    IMPACT_ASSESSMENT = "impact_assessment"
    ROLLBACK_READINESS = "rollback_readiness"


@dataclass
class SafetyCheck:
    """
    Safety check that must pass before task execution.
    """
    check_type: SafetyCheckType
    description: str
    validation_command: Optional[str] = None
    expected_result: Optional[str] = None
    is_blocking: bool = True
    timeout_seconds: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert safety check to dictionary"""
        return {
            'check_type': self.check_type.value,
            'description': self.description,
            'validation_command': self.validation_command,
            'expected_result': self.expected_result,
            'is_blocking': self.is_blocking,
            'timeout_seconds': self.timeout_seconds
        }


@dataclass
class RemediationTask:
    """
    Represents an automated remediation task that can be executed
    to resolve or mitigate an incident.
    """
    id: str
    name: str
    description: str
    task_type: TaskType
    parameters: Dict[str, Any]
    safety_checks: List[SafetyCheck]
    approval_required: bool
    estimated_duration: timedelta
    rollback_procedure: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: TaskStatus = TaskStatus.PENDING
    incident_id: Optional[str] = None
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.id:
            self.id = self.generate_task_id()
        
        if not self.created_at:
            self.created_at = datetime.utcnow()
    
    @staticmethod
    def generate_task_id() -> str:
        """Generate a unique task ID"""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        unique_suffix = str(uuid.uuid4())[:8]
        return f"TASK-{timestamp}-{unique_suffix.upper()}"
    
    def update_status(self, new_status: TaskStatus) -> None:
        """Update task status"""
        self.status = new_status
    
    def add_safety_check(self, safety_check: SafetyCheck) -> None:
        """Add a safety check to the task"""
        self.safety_checks.append(safety_check)
    
    def requires_approval(self) -> bool:
        """Check if task requires approval"""
        return self.approval_required or self.status == TaskStatus.REQUIRES_APPROVAL
    
    def approve(self, approved_by: str) -> None:
        """Approve the task for execution"""
        self.approved_by = approved_by
        self.status = TaskStatus.APPROVED
    
    def get_blocking_safety_checks(self) -> List[SafetyCheck]:
        """Get all blocking safety checks"""
        return [check for check in self.safety_checks if check.is_blocking]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'task_type': self.task_type.value,
            'parameters': self.parameters,
            'safety_checks': [check.to_dict() for check in self.safety_checks],
            'approval_required': self.approval_required,
            'estimated_duration': self.estimated_duration.total_seconds(),
            'rollback_procedure': self.rollback_procedure,
            'created_at': self.created_at.isoformat(),
            'status': self.status.value,
            'incident_id': self.incident_id,
            'created_by': self.created_by,
            'approved_by': self.approved_by,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RemediationTask':
        """Create task from dictionary"""
        task_type = TaskType(data['task_type'])
        status = TaskStatus(data['status'])
        estimated_duration = timedelta(seconds=data['estimated_duration'])
        created_at = datetime.fromisoformat(data['created_at'])
        
        safety_checks = []
        for check_data in data.get('safety_checks', []):
            check_type = SafetyCheckType(check_data['check_type'])
            safety_check = SafetyCheck(
                check_type=check_type,
                description=check_data['description'],
                validation_command=check_data.get('validation_command'),
                expected_result=check_data.get('expected_result'),
                is_blocking=check_data.get('is_blocking', True),
                timeout_seconds=check_data.get('timeout_seconds', 30)
            )
            safety_checks.append(safety_check)
        
        return cls(
            id=data['id'],
            name=data['name'],
            description=data['description'],
            task_type=task_type,
            parameters=data['parameters'],
            safety_checks=safety_checks,
            approval_required=data['approval_required'],
            estimated_duration=estimated_duration,
            rollback_procedure=data.get('rollback_procedure'),
            created_at=created_at,
            status=status,
            incident_id=data.get('incident_id'),
            created_by=data.get('created_by'),
            approved_by=data.get('approved_by'),
            metadata=data.get('metadata', {})
        )


@dataclass
class ExecutionResult:
    """
    Result of remediation task execution.
    """
    task_id: str
    status: TaskStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    output: str = ""
    error_message: Optional[str] = None
    exit_code: Optional[int] = None
    rollback_required: bool = False
    rollback_completed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Post-initialization processing"""
        if not self.started_at:
            self.started_at = datetime.utcnow()
    
    def mark_completed(self, output: str = "", exit_code: int = 0) -> None:
        """Mark execution as completed"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.output = output
        self.exit_code = exit_code
    
    def mark_failed(self, error_message: str, exit_code: int = 1) -> None:
        """Mark execution as failed"""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        self.exit_code = exit_code
    
    def get_duration(self) -> Optional[timedelta]:
        """Get execution duration"""
        if self.completed_at:
            return self.completed_at - self.started_at
        return None
    
    def is_successful(self) -> bool:
        """Check if execution was successful"""
        return self.status == TaskStatus.COMPLETED and (self.exit_code == 0 or self.exit_code is None)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert execution result to dictionary"""
        return {
            'task_id': self.task_id,
            'status': self.status.value,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'output': self.output,
            'error_message': self.error_message,
            'exit_code': self.exit_code,
            'rollback_required': self.rollback_required,
            'rollback_completed': self.rollback_completed,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExecutionResult':
        """Create execution result from dictionary"""
        status = TaskStatus(data['status'])
        started_at = datetime.fromisoformat(data['started_at'])
        completed_at = datetime.fromisoformat(data['completed_at']) if data.get('completed_at') else None
        
        return cls(
            task_id=data['task_id'],
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            output=data.get('output', ''),
            error_message=data.get('error_message'),
            exit_code=data.get('exit_code'),
            rollback_required=data.get('rollback_required', False),
            rollback_completed=data.get('rollback_completed', False),
            metadata=data.get('metadata', {})
        )